"""Regenerates docs/try-it-demo.html: a real, self-contained, interactive (tabbed) report for
examples/stm32_usb_dev, embedded on the landing page as a free "Try it" demo.

Deterministic analysis is re-run locally (free). The AI review text is reused
verbatim from reports/ai_validation.json (a real, already-captured live LLM
response) rather than calling the API again, so this script makes zero
LLM API calls.

Run after regenerating reports/ai_validation.json, or whenever
examples/stm32_usb_dev or the report renderer changes.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.analysis import run_all_checks
from app.analysis.scoring import score as compute_score
from app.parser.kicad_project import find_project_files, parse_board
from app.reports.interactive_report import render

REPO_ROOT = Path(__file__).resolve().parents[2]
BOARD_DIR = REPO_ROOT / "examples" / "stm32_usb_dev"
VALIDATION_JSON = REPO_ROOT / "reports" / "ai_validation.json"
OUTPUT_PATH = REPO_ROOT / "docs" / "try-it-demo.html"

_DEMO_NOTE = (
    'This is the report PCBInsight generated for <code>examples/stm32_usb_dev</code>, a synthetic board in the '
    'ten-board <a href="https://github.com/CyrilKafle/PCBInsight-AI/tree/master/examples">validation corpus</a>; '
    "its low-confidence stub warnings were not checked against a real design. "
    'Run it on your own boards from the <a href="https://github.com/CyrilKafle/PCBInsight-AI">GitHub repository</a>.'
)


def _captured_review() -> dict:
    """The stm32_usb_dev entry from the last live validation run."""
    data = json.loads(VALIDATION_JSON.read_text(encoding="utf-8"))
    for board in data["boards"]:
        if board["board_name"] == "stm32_usb_dev":
            if not board["review"].get("text"):
                raise SystemExit("The captured stm32_usb_dev review was withheld; rerun validate_ai.py first.")
            return board
    raise SystemExit("stm32_usb_dev not found in reports/ai_validation.json")


def _ai_note(captured: dict, current_score: int) -> str | None:
    """A notice beside the AI text when it was captured under a different score
    than the one shown now. None when they match."""
    det = captured["deterministic"]
    captured_score = det["score"]
    if captured_score == current_score:
        return None
    formula = det.get("formula_version", 1)
    return (
        f"<strong>Older score in this text.</strong> This explanation was captured in an earlier live run, when score "
        f"formula v{formula} gave this board {captured_score}/100, and it still says {captured_score}. The current "
        f"score is {current_score}/100. The findings it discusses are unchanged."
    )


def main() -> None:
    pcb_file = find_project_files(BOARD_DIR)["pcb"]
    board = parse_board(pcb_file)
    issues = run_all_checks(board)
    engineering_score = compute_score(issues)
    captured = _captured_review()
    ai_review = captured["review"]["text"]

    html = render(
        board,
        issues,
        engineering_score,
        ai_review,
        landing_href="index.html",
        demo_note=_DEMO_NOTE,
        ai_note=_ai_note(captured, engineering_score.overall),
    )
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(html):,} bytes)")
    print(f"Score: {engineering_score.overall}/100, {len(issues)} issues")


if __name__ == "__main__":
    main()
