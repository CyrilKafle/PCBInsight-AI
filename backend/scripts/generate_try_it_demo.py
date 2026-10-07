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
<style>
  .demo-banner { max-width: 1040px; margin: 0 auto; padding: 14px 24px 0; box-sizing: border-box; }
  .demo-banner-inner { padding: 12px 16px; background: #10151C; border: 1px solid #232B36;
    border-left: 3px solid #2FD9C4; border-radius: 4px; font-family: 'IBM Plex Sans', -apple-system, 'Segoe UI', sans-serif;
    font-size: 0.875rem; line-height: 1.55; color: #8B96A5; }
  .demo-banner a { color: #2FD9C4; }
  .demo-banner code { font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: #E6EDF3; }
  .demo-banner .back { display: inline-block; padding: 10px 0; margin-top: 4px; white-space: nowrap; }
</style>
<div class="demo-banner"><div class="demo-banner-inner">
  <strong style="color:#E6EDF3;font-weight:600;">Real output, not a mockup.</strong>
  This is the report PCBInsight generated for <code>examples/stm32_usb_dev</code>, a synthetic board in the
  ten-board <a href="https://github.com/CyrilKafle/PCBInsight-AI/tree/master/examples">validation corpus</a>;
  its low-confidence stub warnings were not checked against a real design.
  Run it on your own boards from the <a href="https://github.com/CyrilKafle/PCBInsight-AI">GitHub repository</a>.<br>
  <a class="back" href="index.html">&larr; Back to the landing page</a>
</div></div>
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
