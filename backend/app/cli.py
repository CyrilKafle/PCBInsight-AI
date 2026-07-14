"""Command-line interface: analyze one KiCad board, or a whole folder of
them, without going through the (Phase 4, not yet built) web dashboard.

    python -m app.cli review path/to/board_dir
    python -m app.cli review path/to/boards_folder      # batch mode, auto-detected

Or, once installed (`pip install -e .` from backend/), as a real `pcbinsight`
command:

    pcbinsight review path/to/board_dir
    pcbinsight review path/to/boards_folder --out reports/ --ai
"""

from __future__ import annotations

import argparse
import sys
from html import escape
from pathlib import Path

from app.ai.review import generate_review
from app.ai.summarizer import summarize
from app.analysis import run_all_checks
from app.analysis.scoring import score as compute_score
from app.models.board import Board
from app.models.issue import EngineeringScore, Issue, Severity
from app.parser.kicad_project import find_project_files, parse_board
from app.reports.html_report import render

AnalysisResult = tuple[Board, list[Issue], EngineeringScore, str | None]


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pcbinsight", description="Automated KiCad PCB design review.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    review = subparsers.add_parser("review", help="Analyze one board, or every board in a folder")
    review.add_argument("path", type=Path, help="A KiCad project directory, or a folder containing several")
    review.add_argument(
        "--out", type=Path, default=None, help="Output path: an HTML file for a single board, a directory for a batch"
    )
    review.add_argument(
        "--ai", action="store_true", help="Also generate a Claude narrative review (requires ANTHROPIC_API_KEY)"
    )
    review.set_defaults(func=_run_review)

    return parser


def _run_review(args: argparse.Namespace) -> int:
    input_path = args.path.resolve()
    board_dirs = _discover_board_dirs(input_path)
    if not board_dirs:
        print(f"error: no KiCad project (.kicad_pcb) found under {args.path}", file=sys.stderr)
        return 1

    if len(board_dirs) == 1 and board_dirs[0] == input_path:
        _review_single(board_dirs[0], args.out, args.ai)
    else:
        _review_batch(board_dirs, args.out or Path("pcbinsight_reports"), args.ai)
    return 0


def _discover_board_dirs(root: Path) -> list[Path]:
    """A directory with a .kicad_pcb directly inside it is one board project.
    Otherwise, treat each of its subdirectories that contains a .kicad_pcb
    (at any depth) as a separate board project -- batch mode."""
    if not root.exists():
        return []
    if list(root.glob("*.kicad_pcb")):
        return [root]
    return sorted(child for child in root.iterdir() if child.is_dir() and list(child.rglob("*.kicad_pcb")))


def _analyze(board_dir: Path, want_ai: bool) -> AnalysisResult:
    files = find_project_files(board_dir)
    board = parse_board(files["pcb"])
    issues = run_all_checks(board)
    score = compute_score(issues)

    ai_review = None
    if want_ai:
        try:
            digest = summarize(board, issues, score)
            ai_review = generate_review(digest)
        except RuntimeError as exc:
            print(f"warning: skipping AI review for {board.name}: {exc}", file=sys.stderr)

    return board, issues, score, ai_review


def _print_summary(board: Board, issues: list[Issue], score: EngineeringScore, report_path: Path) -> None:
    critical = sum(1 for issue in issues if issue.severity == Severity.CRITICAL)
    warnings = len(issues) - critical
    print(f"{board.name}")
    print(f"  Overall Score:    {score.overall}")
    print(f"  Critical Issues:  {critical}")
    print(f"  Warnings:         {warnings}")
    print(f"  Report saved:     {report_path}")


def _review_single(board_dir: Path, out: Path | None, want_ai: bool) -> None:
    board, issues, score, ai_review = _analyze(board_dir, want_ai)
    report_path = out or Path(f"{board.name}_report.html")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render(board, issues, score, ai_review), encoding="utf-8")
    _print_summary(board, issues, score, report_path)


def _review_batch(board_dirs: list[Path], out_dir: Path, want_ai: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[str, Board, list[Issue], EngineeringScore, Path]] = []

    for board_dir in board_dirs:
        try:
            board, issues, score, ai_review = _analyze(board_dir, want_ai)
        except Exception as exc:  # noqa: BLE001 -- one malformed board must not abort the whole batch
            print(f"warning: skipping {board_dir} ({exc.__class__.__name__}: {exc})", file=sys.stderr)
            continue

        # Keyed by the input subdirectory name, not board.name -- two board
        # projects can easily share a .kicad_pcb filename, but not a folder
        # name within the same parent, so this can't collide.
        report_path = out_dir / board_dir.name / "report.html"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render(board, issues, score, ai_review), encoding="utf-8")
        _print_summary(board, issues, score, report_path)
        print()
        results.append((board_dir.name, board, issues, score, report_path))

    summary_path = out_dir / "summary.html"
    summary_path.write_text(_render_batch_summary(results), encoding="utf-8")
    print(f"Batch summary saved: {summary_path}")


def _render_batch_summary(results: list[tuple[str, Board, list[Issue], EngineeringScore, Path]]) -> str:
    rows = "\n".join(
        f'<tr><td><a href="{escape(folder_name)}/report.html">{escape(board.name)}</a></td>'
        f"<td>{score.overall}</td><td>{len(issues)}</td></tr>"
        for folder_name, board, issues, score, _report_path in results
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Batch Review Summary</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 2rem; color: #1f2328; }}
  table {{ border-collapse: collapse; }}
  td, th {{ padding: 0.5rem 1rem; border-bottom: 1px solid #d0d7de; text-align: left; }}
</style>
</head><body>
<h1>Batch Review Summary</h1>
<table>
  <thead><tr><th>Board</th><th>Score</th><th>Issues</th></tr></thead>
  <tbody>
{rows}
  </tbody>
</table>
</body></html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
