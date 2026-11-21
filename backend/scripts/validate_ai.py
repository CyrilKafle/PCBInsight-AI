"""Live validation of the AI review layer against the real LLM API.

Unlike the unit tests (which use a dependency-injected fake client to prove the
plumbing without spending money), this script exercises the *actual* model on
boards of varying quality through the same code path the API uses
(`generate_checked_review`: citation and completeness checks, one repair
attempt, then withhold). Per board it records:

  - the review's status (valid / repaired / withheld), attempts, the stop
    reason of every call, and whether each call finished normally
  - finding IDs the model cited that do not exist, on the first attempt
    (before any repair) -- the honest hallucination measure
  - per low-weight finding (rule weight < 0.5): whether the sentences that
    cite it hedge (hedged / unhedged / not mentioned), instead of one keyword
    search over the whole text
  - a true zero-finding board (examples/high_quality_reference), where any
    cited ID is by definition invented
  - adversarial net names (XML-hostile, unicode)
  - cost, or "unknown" when the model has no entry in the price table (never $0)

It is a manual QA tool, not part of the CI suite: it needs a real API key and
makes about 12 to 18 billed calls per run. Rerun it only when the prompts, the
model or the digest schema change.

Usage
-----
  Free estimate, no API calls, no key needed:
      python backend/scripts/validate_ai.py --dry-run

  Paid run (key read from the environment or backend/.env, never printed):
      python backend/scripts/validate_ai.py --budget-usd 1.00

  The run stops before starting a board if the money already spent plus a
  projection for that board would pass --budget-usd. If the model's price is
  not in PRICING_PER_MTOK the paid run refuses to start unless
  --allow-unknown-price is given.

Exit code is non-zero if any review was withheld, any chat answer cited an
unknown ID, or the budget stopped the run early.

Output
------
A paid run overwrites two evidence files at the repo root:

  reports/ai_validation.md    human-readable summary + full AI prose per board
  reports/ai_validation.json  structured results: status, stop reasons, usage, cost

These are committed -- they are the record that the AI layer was validated
against a real model, not just against the fake test client.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
REPORTS_DIR = REPO / "reports"

sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tests"))

from app.ai.review import (  # noqa: E402
    _MAX_ANSWER_TOKENS,
    _MAX_REVIEW_TOKENS,
    _NORMAL_STOP_REASONS,
    DEFAULT_MODEL,
    answer_question,
    find_unsupported_citations,
    generate_checked_review,
)
from app.ai.summarizer import summarize  # noqa: E402
from app.analysis import run_all_checks  # noqa: E402
from app.analysis.scoring import score as compute_score  # noqa: E402
from app.parser.kicad_project import find_project_files, parse_board  # noqa: E402
from factories import make_board, make_component, make_net, make_trace, make_via  # noqa: E402

REPORT_SCHEMA_VERSION = 2
ISSUE_ID_RE = re.compile(r"\b[A-Z]{2,6}-\d{3}\b")
LOW_WEIGHT = 0.5
HEDGE_WORDS = (
    "verify", "manual", "confirm", "check", "uncertain", "low confidence", "low rule weight",
    "may ", "might", "possible", "possibly", "likely", "could ", "worth a look", "worth checking",
)
CHAT_QUESTION = "What is the single most important thing to fix on this board, and why?"

# Standard per-MTok USD prices. Check them against the provider's current price
# list before a paid run; a model missing here reports cost as unknown.
PRICING_PER_MTOK = {
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
}


# --- pure helpers (unit-tested in tests/test_validate_ai.py) -------------------------


def cost_usd(usage: dict, model: str) -> float | None:
    """Cost of one call, or None when the model has no price entry."""
    rates = PRICING_PER_MTOK.get(model)
    if rates is None:
        return None
    return (usage["input_tokens"] / 1_000_000) * rates["input"] + (usage["output_tokens"] / 1_000_000) * rates["output"]


def sum_costs(costs: list[float | None]) -> float | None:
    """Total, or None if any part is unknown (an unknown is never treated as $0)."""
    if any(c is None for c in costs):
        return None
    return sum(costs)


def fmt_cost(value: float | None) -> str:
    return "unknown" if value is None else f"${value:.4f}"


def is_complete(stop_reason: str | None, text: str | None) -> bool:
    """A call finished on its own and produced text."""
    return stop_reason in _NORMAL_STOP_REASONS and bool(text and text.strip())


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def hedging_by_finding(text: str | None, low_weight_ids: set[str]) -> dict[str, str]:
    """For each low-weight finding: 'hedged' if every sentence citing it uses a
    hedge word, 'unhedged' if any citing sentence does not, 'not_mentioned' if
    no sentence cites it. A word list is a heuristic; read 'unhedged' cases."""
    result: dict[str, str] = {}
    sentences = _sentences(text or "")
    for finding_id in sorted(low_weight_ids):
        citing = [s for s in sentences if finding_id in ISSUE_ID_RE.findall(s)]
        if not citing:
            result[finding_id] = "not_mentioned"
        elif all(any(w in s.lower() for w in HEDGE_WORDS) for s in citing):
            result[finding_id] = "hedged"
        else:
            result[finding_id] = "unhedged"
    return result


def estimate_input_tokens(text: str) -> int:
    """Rough estimate (about 4 characters per token) for the dry run only."""
    return max(1, len(text) // 4)


# --- boards --------------------------------------------------------------------------


def minimal_board():
    """Small hand-built board. Not clean: it produces a few low-severity findings."""
    return make_board(
        name="minimal",
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
    project = REPO / "examples" / name
    return parse_board(find_project_files(project)["pcb"], project)


def boards() -> list[tuple[str, object]]:
    return [
        ("example simple_board", load_example("simple_board")),
        ("example stm32_usb_dev", load_example("stm32_usb_dev")),
        ("zero findings (high_quality_reference)", load_example("high_quality_reference")),
        ("minimal (hand-built)", minimal_board()),
        ("messy (multi-issue)", messy_board()),
        ("weird net names + unicode", weird_names_board()),
    ]


# --- one board -----------------------------------------------------------------------


def check_board(label: str, board) -> dict:
    print("\n" + "=" * 78)
    print(f"BOARD: {label}  (name={board.name!r})")
    print("=" * 78)
    issues = run_all_checks(board)
    score = compute_score(issues)
    real_ids = {i.id for i in issues}
    low_ids = {i.id for i in issues if i.confidence < LOW_WEIGHT}
    print(f"deterministic: score={score.overall} (formula v{score.formula_version})  issues={len(issues)}")
    digest = summarize(board, issues, score)

    review = generate_checked_review(digest)
    print(f"\n--- AI REVIEW: {review.status} after {review.attempts} attempt(s), stop reasons {review.stop_reasons}")
    print(review.text or "(withheld)")
    first_attempt_unknown = review.first_attempt_unknown_ids
    hedging = hedging_by_finding(review.text, low_ids)
    print(f"  first-attempt unknown IDs: {first_attempt_unknown or 'none'}")
    print(f"  hedging by low-weight finding: {hedging or 'no low-weight findings'}")
    if not issues:
        print("  zero-finding board: any cited ID is invented; read the prose for invented problems")

    answer, chat_meta = answer_question(digest, CHAT_QUESTION, return_usage=True)
    chat_unknown = find_unsupported_citations(answer, digest)
    print(f"\n--- CHAT Q: {CHAT_QUESTION}\n{answer}")
    print(f"  chat unknown IDs: {chat_unknown or 'none'}  stop reason: {chat_meta.get('stop_reason')}")

    review_cost = cost_usd(review.usage, DEFAULT_MODEL)
    chat_usage = {"input_tokens": chat_meta["input_tokens"], "output_tokens": chat_meta["output_tokens"]}
    chat_cost = cost_usd(chat_usage, DEFAULT_MODEL)
    return {
        "label": label,
        "board_name": board.name,
        "deterministic": {
            "score": score.overall,
            "formula_version": score.formula_version,
            "issue_count": len(issues),
            "issue_ids": sorted(real_ids),
        },
        "low_weight_issue_ids": sorted(low_ids),
        "hedging_by_finding": hedging,
        "review": {
            "status": review.status,
            "attempts": review.attempts,
            "stop_reasons": review.stop_reasons,
            "complete_per_attempt": [r in _NORMAL_STOP_REASONS for r in review.stop_reasons],
            "problems": review.problems,
            "first_attempt_unknown_ids": first_attempt_unknown,
            "text": review.text,
            "usage": review.usage,
            "cost_usd": None if review_cost is None else round(review_cost, 6),
        },
        "chat": {
            "question": CHAT_QUESTION,
            "answer": answer,
            "stop_reason": chat_meta.get("stop_reason"),
            "complete": is_complete(chat_meta.get("stop_reason"), answer),
            "unknown_ids": chat_unknown,
            "usage": chat_usage,
            "cost_usd": None if chat_cost is None else round(chat_cost, 6),
        },
    }


# --- reports -------------------------------------------------------------------------


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def board_cost(r: dict) -> float | None:
    return sum_costs([r["review"]["cost_usd"], r["chat"]["cost_usd"]])


def write_reports(results: list[dict], stopped_early: bool, budget: float) -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    total_cost = sum_costs([board_cost(r) for r in results])
    payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": timestamp,
        "model": DEFAULT_MODEL,
        "git_commit": _git("rev-parse", "HEAD"),
        "git_tag": _git("describe", "--tags", "--abbrev=0"),
        "pricing_per_mtok_usd": PRICING_PER_MTOK.get(DEFAULT_MODEL),
        "budget_usd": budget,
        "stopped_early_by_budget": stopped_early,
        "boards": results,
        "summary": {
            "total_boards": len(results),
            "total_cost_usd": None if total_cost is None else round(total_cost, 6),
            "reviews_by_status": {
                s: sum(1 for r in results if r["review"]["status"] == s) for s in ("valid", "repaired", "withheld")
            },
            "boards_with_first_attempt_unknown_ids": sum(1 for r in results if r["review"]["first_attempt_unknown_ids"]),
            "chat_answers_with_unknown_ids": sum(1 for r in results if r["chat"]["unknown_ids"]),
            "incomplete_calls": sum(
                r["review"]["complete_per_attempt"].count(False) + (0 if r["chat"]["complete"] else 1) for r in results
            ),
        },
    }
    (REPORTS_DIR / "ai_validation.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    s = payload["summary"]
    lines = [
        "# AI Validation Report",
        "",
        f"Generated {timestamp} against `{DEFAULT_MODEL}` via `backend/scripts/validate_ai.py` (report schema {REPORT_SCHEMA_VERSION}).",
        f"Repo state: commit `{(payload['git_commit'] or 'unknown')[:12]}`"
        + (f", tag `{payload['git_tag']}`" if payload["git_tag"] else "")
        + ".",
        "",
        "Each review goes through the same citation and completeness checks as the API (one repair attempt, then withhold). "
        "\"First-attempt unknown IDs\" counts invented finding IDs before any repair. Hedging is checked per low-weight "
        "finding (rule weight < 0.5) with a word list, so read any \"unhedged\" result. Passing these checks does not prove "
        "every sentence is supported by the findings.",
        "",
        "| Board | Score | Findings | Review | Attempts | Stop reasons | First-attempt unknown IDs | Low-weight hedging | Chat unknown IDs | Cost |",
        "|---|---:|---:|---|---:|---|---|---|---|---:|",
    ]
    for r in results:
        h = r["hedging_by_finding"]
        hedge = "n/a" if not h else ", ".join(f"{k}: {v}" for k, v in h.items())
        lines.append(
            f"| {r['label']} | {r['deterministic']['score']} | {r['deterministic']['issue_count']} | "
            f"{r['review']['status']} | {r['review']['attempts']} | {', '.join(map(str, r['review']['stop_reasons']))} | "
            f"{', '.join(r['review']['first_attempt_unknown_ids']) or 'none'} | {hedge} | "
            f"{', '.join(r['chat']['unknown_ids']) or 'none'} | {fmt_cost(board_cost(r))} |"
        )
    lines += [
        "",
        f"**Total cost:** {fmt_cost(total_cost)} (budget ${budget:.2f}"
        + (", stopped early by the budget" if stopped_early else "")
        + f").  **Reviews:** {s['reviews_by_status']}.  **Incomplete calls:** {s['incomplete_calls']}.",
        "",
        "## Per-board detail",
    ]
    for r in results:
        lines += [
            "",
            f"### {r['label']}",
            "",
            f"Deterministic: score {r['deterministic']['score']} (formula v{r['deterministic']['formula_version']}), "
            f"{r['deterministic']['issue_count']} findings ({', '.join(r['deterministic']['issue_ids']) or 'none'}).",
            "",
            f"**AI review ({r['review']['status']}):**",
            "",
            r["review"]["text"] or "_Withheld: it failed the checks twice._",
            "",
            f"**Chat -- {r['chat']['question']}**",
            "",
            r["chat"]["answer"],
        ]
    (REPORTS_DIR / "ai_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {REPORTS_DIR / 'ai_validation.md'}")
    print(f"Wrote {REPORTS_DIR / 'ai_validation.json'}")


# --- entry points ----------------------------------------------------------------------


def dry_run() -> int:
    """Plan and estimate a paid run without calling the API or needing a key."""
    rates = PRICING_PER_MTOK.get(DEFAULT_MODEL)
    print(f"model {DEFAULT_MODEL}; price per MTok: {rates or 'UNKNOWN'}")
    total_low = total_high = 0.0
    for label, board in boards():
        issues = run_all_checks(board)
        digest = json.dumps(summarize(board, issues, compute_score(issues)))
        review_in = estimate_input_tokens(digest) + 400  # + system prompt
        chat_in = review_in + 40
        # low: one review call + chat, typical output; high: review repaired (2 calls) + chat, max output
        low = {"input_tokens": review_in + chat_in, "output_tokens": 500 + 250}
        high = {"input_tokens": 2 * review_in + 200 + chat_in, "output_tokens": 2 * _MAX_REVIEW_TOKENS + _MAX_ANSWER_TOKENS}
        lo, hi = cost_usd(low, DEFAULT_MODEL), cost_usd(high, DEFAULT_MODEL)
        print(f"  {label:42} findings={len(issues):<3} est. input~{review_in} tok  calls 2-3  cost {fmt_cost(lo)} to {fmt_cost(hi)}")
        if lo is not None:
            total_low += lo
            total_high += hi
    if rates:
        print(f"estimated total: ${total_low:.2f} to ${total_high:.2f} (token counts are estimates, ~4 chars/token)")
    return 0


def _load_key_from_env_file() -> None:
    env_path = BACKEND / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="estimate calls and cost; no API calls, no key needed")
    parser.add_argument("--budget-usd", type=float, default=1.00, help="stop before a board that could pass this total")
    parser.add_argument("--allow-unknown-price", action="store_true", help="run even if the model has no price entry")
    args = parser.parse_args(argv)

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.dry_run:
        return dry_run()

    if PRICING_PER_MTOK.get(DEFAULT_MODEL) is None and not args.allow_unknown_price:
        sys.exit(f"No price entry for {DEFAULT_MODEL}; cost would be unknown. Add it or pass --allow-unknown-price.")
    _load_key_from_env_file()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("No ANTHROPIC_API_KEY found (environment or backend/.env). Aborting.")

    results: list[dict] = []
    spent = 0.0
    stopped_early = False
    for label, board in boards():
        projected = max((board_cost(r) or 0.0) for r in results) * 2 if results else 0.0
        if spent + projected > args.budget_usd:
            print(f"\nBudget stop: spent ${spent:.4f}, next board projected up to ${projected:.4f}, budget ${args.budget_usd:.2f}")
            stopped_early = True
            break
        result = check_board(label, board)
        results.append(result)
        spent += board_cost(result) or 0.0

    write_reports(results, stopped_early, args.budget_usd)

    print("\n" + "#" * 78)
    ok = not stopped_early
    for r in results:
        bad = r["review"]["status"] == "withheld" or r["chat"]["unknown_ids"]
        ok = ok and not bad
        print(
            f"  {r['label']:42} review={r['review']['status']:<9} first-attempt unknown={r['review']['first_attempt_unknown_ids'] or 'none'}"
            f"  chat unknown={r['chat']['unknown_ids'] or 'none'}  {'REVIEW' if bad else 'OK'}"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
