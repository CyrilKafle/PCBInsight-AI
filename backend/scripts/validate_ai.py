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
makes ~8 billed calls per run.

Usage
-----
1. Put your key in backend/.env:  ANTHROPIC_API_KEY=sk-ant-...
2. From the repo root:            python backend/scripts/validate_ai.py

Exit code is non-zero if any board produced an unsupported citation.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"

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

from app.ai.review import answer_question, find_unsupported_citations, generate_review  # noqa: E402
from app.ai.summarizer import summarize  # noqa: E402
from app.analysis import run_all_checks  # noqa: E402
from app.analysis.scoring import score as compute_score  # noqa: E402
from app.parser.kicad_project import find_project_files, parse_board  # noqa: E402
from factories import make_board, make_component, make_net, make_trace, make_via  # noqa: E402

ISSUE_ID_RE = re.compile(r"\b[A-Z]{2,6}-\d{3}\b")


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


def check_board(label, board):
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

    review = generate_review(digest)
    print("\n--- AI REVIEW ---\n" + review)
    unsupported = find_unsupported_citations(review, digest)
    print("\n--- CHECKS ---")
    print(f"  cited ids: {sorted(set(ISSUE_ID_RE.findall(review))) or 'none'}")
    print(f"  HALLUCINATED citations (must be empty): {unsupported or 'NONE'}")
    if len(issues) == 0:
        print("  clean-board invented-issue watch: read the prose above for fabricated findings")
    if low_conf_ids:
        hedged = any(w in review.lower() for w in ("verify", "manual", "confirm", "uncertain", "low confidence", "may "))
        print(f"  hedging present for low-confidence findings: {'yes' if hedged else 'NO -- REVIEW'}")

    question = "What is the single most important thing to fix on this board, and why?"
    answer = answer_question(digest, question)
    print(f"\n--- CHAT Q: {question}\n{answer}")
    chat_unsupported = find_unsupported_citations(answer, digest)
    print(f"  chat hallucinated citations (must be empty): {chat_unsupported or 'NONE'}")
    return {"label": label, "issues": len(issues), "unsupported": unsupported + chat_unsupported}


def main() -> int:
    results = [
        check_board("example simple_board", load_example("simple_board")),
        check_board("example stm32_usb_dev", load_example("stm32_usb_dev")),
        check_board("clean minimal", clean_board()),
        check_board("messy (multi-issue)", messy_board()),
        check_board("weird net names + unicode", weird_names_board()),
    ]

    print("\n" + "#" * 78)
    print("SUMMARY")
    ok = True
    for r in results:
        clean = not r["unsupported"]
        ok = ok and clean
        print(f"  {r['label']:32} issues={r['issues']:<3} hallucinated={'NONE' if clean else r['unsupported']}  {'OK' if clean else 'REVIEW'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
