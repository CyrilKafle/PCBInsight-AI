"""Regenerates docs/try-it-demo.html: a real, self-contained report for
examples/stm32_usb_dev, embedded on the landing page as a free "Try it" demo.

Deterministic analysis is re-run locally (free). The AI review text is reused
verbatim from reports/ai_validation.json (a real, already-captured live Claude
response) rather than calling the API again, so this script makes zero
Anthropic API calls.

Run after regenerating reports/ai_validation.json, or whenever
examples/stm32_usb_dev or the report renderer changes.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.analysis import run_all_checks
from app.analysis.scoring import score as compute_score
from app.parser.kicad_project import find_project_files, parse_board
from app.reports.html_report import render

REPO_ROOT = Path(__file__).resolve().parents[2]
BOARD_DIR = REPO_ROOT / "examples" / "stm32_usb_dev"
VALIDATION_JSON = REPO_ROOT / "reports" / "ai_validation.json"
OUTPUT_PATH = REPO_ROOT / "docs" / "try-it-demo.html"

_BANNER = """
<div style="max-width:960px;margin:0 auto 1.5rem;padding:0.9rem 1.25rem;
     background:#EDE7F9;border:1px solid #c9b8ef;border-radius:8px;
     font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
     font-size:0.9rem;line-height:1.5;color:#3c1f6b;">
  This is a real report PCBInsight generated for
  <code style="background:rgba(0,0,0,0.06);padding:0.1rem 0.35rem;border-radius:3px;">examples/stm32_usb_dev</code>,
  a board in the <a href="https://github.com/CyrilKafle/PCBInsight-AI/tree/master/examples"
  style="color:#3c1f6b;">Engineering Validation Corpus</a> &mdash; deterministic findings and the AI
  review below are both unedited output, not a mockup. The upload dashboard runs locally; see the
  <a href="https://github.com/CyrilKafle/PCBInsight-AI" style="color:#3c1f6b;">GitHub repo</a> to run it
  on your own boards. &larr; <a href="index.html" style="color:#3c1f6b;">Back to the landing page</a>
</div>
"""


def _real_review_text() -> str:
    data = json.loads(VALIDATION_JSON.read_text(encoding="utf-8"))
    for board in data["boards"]:
        if board["board_name"] == "stm32_usb_dev":
            return board["review"]["text"]
    raise SystemExit("stm32_usb_dev not found in reports/ai_validation.json")


def main() -> None:
    pcb_file = find_project_files(BOARD_DIR)["pcb"]
    board = parse_board(pcb_file)
    issues = run_all_checks(board)
    engineering_score = compute_score(issues)
    ai_review = _real_review_text()

    html = render(board, issues, engineering_score, ai_review)
    html = html.replace("<body>", "<body>\n" + _BANNER, 1)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(html):,} bytes)")
    print(f"Score: {engineering_score.overall}/100, {len(issues)} issues")


if __name__ == "__main__":
    main()
