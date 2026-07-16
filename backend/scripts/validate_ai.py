"""Live validation of the AI review layer against the real Anthropic API.

Unlike the unit tests (which use a dependency-injected fake client to prove the
plumbing without spending money), this script exercises the *actual* model on
boards of varying quality and checks the properties that matter for a
deterministic-first tool:

  - no hallucinated issue IDs cited (find_unsupported_citations must be empty)
  - the deterministic engine stays the sole source of findings -- a clean board
    must not get invented problems
  - low-confidence findings (<0.5) are hedged, not stated as fact
  - adversarial net names (XML-hostile, unicode) don't break prompting or leak

It is a manual QA tool, not part of the CI suite: it needs a real API key and
makes ~10 billed calls per run.

Usage
-----
1. Put your key in backend/.env:  ANTHROPIC_API_KEY=sk-ant-...
2. From the repo root:            python backend/scripts/validate_ai.py

Exit code is non-zero if any board produced an unsupported citation.

Output
------
Every run overwrites two evidence files at the repo root:

  reports/ai_validation.md    human-readable summary + full AI prose per board
  reports/ai_validation.json  structured results: usage, cost, timestamps

These are committed (not gitignored) -- they are the record that the AI layer
was validated against a real model, not just against the fake test client.
Re-run this script and recommit the outputs whenever the prompts, model, or
digest schema change.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
REPORTS_DIR = REPO / "reports"

# --- load backend/.env without printing the key -----------------------------
env_path = BACKEND / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit("No ANTHROPIC_API_KEY found (put it in backend/.env). Aborting.")

sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tests"))

from app.ai.review import DEFAULT_MODEL, answer_question, find_unsupported_citations, generate_review  # noqa: E402
from app.ai.summarizer import summarize  # noqa: E402
from app.analysis import run_all_checks  # noqa: E402
from app.analysis.scoring import score as compute_score  # noqa: E402
from app.parser.kicad_project import find_project_files, parse_board  # noqa: E402
from factories import make_board, make_component, make_net, make_trace, make_via  # noqa: E402

ISSUE_ID_RE = re.compile(r"\b[A-Z]{2,6}-\d{3}\b")

# Standard per-MTok pricing for DEFAULT_MODEL (see backend/app/ai/review.py).
# Anthropic runs a temporary lower intro rate for claude-sonnet-5 through
# 2026-08-31 ($2.00/$10.00) -- this table uses the standard post-intro rate so
# reported cost stays correct after that date rather than silently
# under-reporting once the intro pricing lapses.
PRICING_PER_MTOK = {
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
}


def _cost_usd(usage: dict, model: str) -> float:
    rates = PRICING_PER_MTOK.get(model)
    if rates is None:
        return 0.0
    return (usage["input_tokens"] / 1_000_000) * rates["input"] + (usage["output_tokens"] / 1_000_000) * rates[
        "output"
    ]


def clean_board():
    """Minimal, well-formed board -- the key 'don't invent problems' test."""
    return make_board(
        name="clean_min",
        components=[make_component("R1", "10k", "passive", 10, 10)],
        nets=[make_net("N1", traces=[make_trace("N1", 10, 10, 12, 10)])],
    )


def messy_board():
    """Deliberately trips several checks: thin + fragmented ground, no ground
    pour, a long / via-heavy clock net."""
    return make_board(
        name="messy",
        components=[
            make_component("U1", "MCU", "MCU", 5, 5),
            make_component("J1", "USB", "connector", 40, 20),
        ],
        nets=[
            make_net("GND", traces=[make_trace("GND", 0, 0, 20, 0, width=0.20)]),
            make_net("GNDA", traces=[make_trace("GNDA", 0, 10, 10, 10)]),
            make_net(
                "CLK",
                traces=[make_trace("CLK", 0, 5, 25, 5), make_trace("CLK", 25, 5, 25, 30)],
                vias=[make_via("CLK", 25, 5), make_via("CLK", 25, 20), make_via("CLK", 25, 30)],
            ),
            make_net("3V3", traces=[make_trace("3V3", 5, 5, 8, 5)]),
        ],
        pours=[],
    )


def weird_names_board():
    """XML/prompt-hostile net names + unicode."""
    return make_board(
        name="weird<&>names",
        components=[make_component("R&D1", "1k", "passive", 3, 3)],
        nets=[
            make_net("<VCC>", traces=[make_trace("<VCC>", 0, 0, 3, 0)]),
            make_net("R&D_NET", traces=[make_trace("R&D_NET", 0, 2, 3, 2)]),
            make_net(
                "信号CLK",
                traces=[make_trace("信号CLK", 0, 4, 40, 4), make_trace("信号CLK", 40, 4, 40, 10)],
                vias=[make_via("信号CLK", 40, 4), make_via("信号CLK", 40, 10), make_via("信号CLK", 20, 4)],
            ),
        ],
    )


def load_example(name: str):
    return parse_board(find_project_files(REPO / "examples" / name)["pcb"])


def check_board(label, board) -> dict:
    print("\n" + "=" * 78)
    print(f"BOARD: {label}  (name={board.name!r})")
    print("=" * 78)
    issues = run_all_checks(board)
    score = compute_score(issues)
    real_ids = {i.id for i in issues}
    low_conf_ids = {i.id for i in issues if i.confidence < 0.5}
    print(f"deterministic: score={score.overall}  issues={len(issues)}  ids={sorted(real_ids)}")
    if low_conf_ids:
        print(f"  low-confidence (<0.5) ids: {sorted(low_conf_ids)}")

    digest = summarize(board, issues, score)

    review_text, review_usage = generate_review(digest, return_usage=True)
    print("\n--- AI REVIEW ---\n" + review_text)
    unsupported = find_unsupported_citations(review_text, digest)
    print("\n--- CHECKS ---")
    print(f"  cited ids: {sorted(set(ISSUE_ID_RE.findall(review_text))) or 'none'}")
    print(f"  HALLUCINATED citations (must be empty): {unsupported or 'NONE'}")
    if len(issues) == 0:
        print("  clean-board invented-issue watch: read the prose above for fabricated findings")
    hedged = None
    if low_conf_ids:
        hedged = any(
            w in review_text.lower() for w in ("verify", "manual", "confirm", "uncertain", "low confidence", "may ")
        )
        print(f"  hedging present for low-confidence findings: {'yes' if hedged else 'NO -- REVIEW'}")

    question = "What is the single most important thing to fix on this board, and why?"
    answer_text, chat_usage = answer_question(digest, question, return_usage=True)
    print(f"\n--- CHAT Q: {question}\n{answer_text}")
    chat_unsupported = find_unsupported_citations(answer_text, digest)
    print(f"  chat hallucinated citations (must be empty): {chat_unsupported or 'NONE'}")

    review_cost = _cost_usd(review_usage, DEFAULT_MODEL)
    chat_cost = _cost_usd(chat_usage, DEFAULT_MODEL)

    return {
        "label": label,
        "board_name": board.name,
        "deterministic": {"score": score.overall, "issue_count": len(issues), "issue_ids": sorted(real_ids)},
        "low_confidence_issue_ids": sorted(low_conf_ids),
        "low_confidence_hedged": hedged,
        "review": {"text": review_text, "usage": review_usage, "cost_usd": round(review_cost, 6)},
        "chat": {
            "question": question,
            "answer": answer_text,
            "usage": chat_usage,
            "cost_usd": round(chat_cost, 6),
        },
        "unsupported_citations": unsupported + chat_unsupported,
    }


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def write_reports(results: list[dict]) -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    total_cost = sum(r["review"]["cost_usd"] + r["chat"]["cost_usd"] for r in results)
    total_hallucinated = sum(len(r["unsupported_citations"]) for r in results)

    payload = {
        "schema_version": 1,
        "generated_at": timestamp,
        "model": DEFAULT_MODEL,
        "git_commit": _git("rev-parse", "HEAD"),
        "git_tag": _git("describe", "--tags", "--abbrev=0"),
        "pricing_per_mtok_usd": PRICING_PER_MTOK.get(DEFAULT_MODEL),
        "boards": results,
        "summary": {
            "total_boards": len(results),
            "total_cost_usd": round(total_cost, 6),
            "boards_with_hallucinated_citations": sum(1 for r in results if r["unsupported_citations"]),
            "total_hallucinated_citations": total_hallucinated,
        },
    }
    (REPORTS_DIR / "ai_validation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# AI Validation Report",
        "",
        f"Generated {timestamp} against `{DEFAULT_MODEL}` via `backend/scripts/validate_ai.py`.",
        f"Repo state: commit `{(payload['git_commit'] or 'unknown')[:12]}`"
        + (f", tag `{payload['git_tag']}`" if payload["git_tag"] else "") + ".",
        "",
        "This is evidence the AI review layer was validated against the real Anthropic API "
        "(not just the dependency-injected fake client used in the unit tests) -- see "
        "`backend/scripts/validate_ai.py` for what each check verifies.",
        "",
        "| Board | Score | Issues | Hallucinated citations | Low-conf. hedged | Review cost | Chat cost |",
        "|---|---:|---:|---:|:---:|---:|---:|",
    ]
    for r in results:
        hedged = "n/a" if r["low_confidence_hedged"] is None else ("yes" if r["low_confidence_hedged"] else "NO")
        lines.append(
            f"| {r['label']} | {r['deterministic']['score']} | {r['deterministic']['issue_count']} | "
            f"{len(r['unsupported_citations']) or 'none'} | {hedged} | "
            f"${r['review']['cost_usd']:.4f} | ${r['chat']['cost_usd']:.4f} |"
        )
    lines += [
        "",
        f"**Total cost this run:** ${total_cost:.4f}  |  "
        f"**Boards with hallucinated citations:** {payload['summary']['boards_with_hallucinated_citations']}/{len(results)}",
        "",
        "## Per-board detail",
    ]
    for r in results:
        lines += [
            "",
            f"### {r['label']}",
            "",
            f"Deterministic: score {r['deterministic']['score']}, {r['deterministic']['issue_count']} issues "
            f"({', '.join(r['deterministic']['issue_ids']) or 'none'}).",
            "",
            "**AI review:**",
            "",
            r["review"]["text"],
            "",
            f"**Chat -- {r['chat']['question']}**",
            "",
            r["chat"]["answer"],
        ]
    (REPORTS_DIR / "ai_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {REPORTS_DIR / 'ai_validation.md'}")
    print(f"Wrote {REPORTS_DIR / 'ai_validation.json'}")


def main() -> int:
    results = [
        check_board("example simple_board", load_example("simple_board")),
        check_board("example stm32_usb_dev", load_example("stm32_usb_dev")),
        check_board("clean minimal", clean_board()),
        check_board("messy (multi-issue)", messy_board()),
        check_board("weird net names + unicode", weird_names_board()),
    ]

    write_reports(results)

    print("\n" + "#" * 78)
    print("SUMMARY")
    ok = True
    for r in results:
        clean = not r["unsupported_citations"]
        ok = ok and clean
        print(
            f"  {r['label']:32} issues={r['deterministic']['issue_count']:<3} "
            f"hallucinated={'NONE' if clean else r['unsupported_citations']}  {'OK' if clean else 'REVIEW'}"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
