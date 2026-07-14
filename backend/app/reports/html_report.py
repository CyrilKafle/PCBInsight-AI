"""Renders the professional HTML design review report: executive summary,
board statistics, engineering metrics, warnings, recommendations, AI review,
charts, and overall score.

Self-contained single-file HTML: all CSS is inlined and charts are embedded
as base64 PNGs (via matplotlib's non-interactive Agg backend), so the report
can be emailed, opened offline, or fed to Phase 4's PDF export without
depending on any external asset."""

from __future__ import annotations

import base64
import io
from collections import Counter
from datetime import datetime, timezone
from html import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app.models.board import Board
from app.models.issue import EngineeringScore, Issue, Severity, SubScore

_SEVERITY_ORDER = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]

_SEVERITY_COLORS = {
    Severity.CRITICAL: "#8b0000",
    Severity.HIGH: "#cf222e",
    Severity.MEDIUM: "#bc4c00",
    Severity.LOW: "#9a6700",
    Severity.INFO: "#57606a",
}

# (minimum score, hex color) bands, checked highest-first — DESIGN.md calls
# for green/yellow/orange/red color-coded thresholds.
_SCORE_BANDS = [
    (90, "#1a7f37"),
    (75, "#9a6700"),
    (50, "#bc4c00"),
    (0, "#cf222e"),
]


def render(board: Board, issues: list[Issue], score: EngineeringScore, ai_review: str | None = None) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    severity_counts = Counter(issue.severity for issue in issues)

    body = "\n".join(
        [
            _header(board, score, generated_at),
            _executive_summary(board, issues, score, severity_counts),
            _score_section(score),
            _charts_section(score, severity_counts),
            _board_statistics_section(board),
            _issues_section(issues),
            _ai_review_section(ai_review),
            _future_improvements_section(),
        ]
    )
    return _wrap_document(board.name, body)


def _score_color(value: int) -> str:
    for minimum, color in _SCORE_BANDS:
        if value >= minimum:
            return color
    return _SCORE_BANDS[-1][1]


def _header(board: Board, score: EngineeringScore, generated_at: str) -> str:
    color = _score_color(score.overall)
    return f"""
    <header class="report-header">
      <div>
        <h1>PCB Design Review Report</h1>
        <p class="subtitle">{escape(board.name)} &middot; generated {escape(generated_at)}</p>
      </div>
      <div class="overall-score" style="border-color:{color}; color:{color}">
        <span class="overall-score-value">{score.overall}</span>
        <span class="overall-score-label">/ 100</span>
      </div>
    </header>
    """


def _executive_summary(board: Board, issues: list[Issue], score: EngineeringScore, severity_counts: Counter) -> str:
    counts_line = ", ".join(
        f"{severity_counts[sev]} {sev.value}" for sev in _SEVERITY_ORDER if severity_counts[sev]
    ) or "no issues found"
    return f"""
    <section class="card">
      <h2>Executive Summary</h2>
      <p>
        This board scored <strong>{score.overall}/100</strong> overall across
        {len(board.components)} components and {len(board.nets)} nets.
        The deterministic engineering-check engine raised {len(issues)} issue(s): {escape(counts_line)}.
      </p>
    </section>
    """


def _score_section(score: EngineeringScore) -> str:
    badges = "\n".join(_subscore_badge(s) for s in score.subscores)
    return f"""
    <section class="card">
      <h2>Engineering Scores</h2>
      <div class="subscore-grid">
        {badges}
      </div>
    </section>
    """


def _subscore_badge(subscore: SubScore) -> str:
    color = _score_color(subscore.score)
    return f"""
        <div class="subscore-badge" style="border-color:{color}">
          <span class="subscore-value" style="color:{color}">{subscore.score}</span>
          <span class="subscore-label">{escape(subscore.category)}</span>
        </div>
    """


def _charts_section(score: EngineeringScore, severity_counts: Counter) -> str:
    subscore_chart = _render_subscore_chart(score)
    severity_chart = _render_severity_chart(severity_counts)
    return f"""
    <section class="card">
      <h2>Charts</h2>
      <div class="charts-grid">
        <img class="chart" src="data:image/png;base64,{subscore_chart}" alt="Subscore chart">
        {f'<img class="chart" src="data:image/png;base64,{severity_chart}" alt="Issue severity breakdown">' if severity_chart else '<p class="muted">No issues to chart by severity.</p>'}
      </div>
    </section>
    """


def _render_subscore_chart(score: EngineeringScore) -> str:
    names = [s.category for s in score.subscores]
    values = [s.score for s in score.subscores]
    colors = [_score_color(v) for v in values]

    fig, ax = plt.subplots(figsize=(5.5, 3.2), dpi=150)
    ax.barh(names, values, color=colors)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Score")
    ax.set_title("Engineering Subscores")
    ax.invert_yaxis()
    fig.tight_layout()
    return _figure_to_base64(fig)


def _render_severity_chart(severity_counts: Counter) -> str | None:
    present = [sev for sev in _SEVERITY_ORDER if severity_counts[sev]]
    if not present:
        return None

    fig, ax = plt.subplots(figsize=(4.2, 3.2), dpi=150)
    ax.pie(
        [severity_counts[sev] for sev in present],
        labels=[sev.value.title() for sev in present],
        colors=[_SEVERITY_COLORS[sev] for sev in present],
        autopct="%1.0f%%",
        startangle=90,
    )
    ax.set_title("Issues by Severity")
    fig.tight_layout()
    return _figure_to_base64(fig)


def _figure_to_base64(fig) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png")
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _board_statistics_section(board: Board) -> str:
    via_count = sum(len(net.vias) for net in board.nets)
    trace_count = sum(len(net.traces) for net in board.nets)
    rows = [
        ("Board name", board.name),
        ("Dimensions", f"{board.width_mm:.1f}mm &times; {board.height_mm:.1f}mm"),
        ("Layer count", str(board.layer_count)),
        ("Components", str(len(board.components))),
        ("Nets", str(len(board.nets))),
        ("Trace segments", str(trace_count)),
        ("Vias", str(via_count)),
        ("Copper pours", str(len(board.pours))),
    ]
    rows_html = "\n".join(f"<tr><th>{escape(label)}</th><td>{value}</td></tr>" for label, value in rows)
    return f"""
    <section class="card">
      <h2>Board Statistics</h2>
      <table class="stats-table">
        {rows_html}
      </table>
    </section>
    """


def _issues_section(issues: list[Issue]) -> str:
    if not issues:
        return """
        <section class="card">
          <h2>Warnings &amp; Recommendations</h2>
          <p class="muted">No issues found by the deterministic check engine.</p>
        </section>
        """

    ordered = sorted(issues, key=lambda issue: _SEVERITY_ORDER.index(issue.severity))
    rows_html = "\n".join(_issue_row(issue) for issue in ordered)
    return f"""
    <section class="card">
      <h2>Warnings &amp; Recommendations</h2>
      <table class="issues-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Severity</th>
            <th>Category</th>
            <th>Finding</th>
            <th>Why it matters</th>
            <th>Suggested fix</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </section>
    """


def _issue_row(issue: Issue) -> str:
    color = _SEVERITY_COLORS[issue.severity]
    refs = f" ({escape(', '.join(issue.refs))})" if issue.refs else ""
    return f"""
          <tr>
            <td><code>{escape(issue.id)}</code></td>
            <td><span class="severity-badge" style="background:{color}">{escape(issue.severity.value)}</span></td>
            <td>{escape(issue.category.replace('_', ' ').title())}</td>
            <td><strong>{escape(issue.summary)}</strong>{refs}</td>
            <td>{escape(issue.explanation)}<br><span class="principle">{escape(issue.principle)}</span></td>
            <td>{escape(issue.suggested_fix)}</td>
          </tr>
    """


def _ai_review_section(ai_review: str | None) -> str:
    if ai_review:
        content = f"<p>{escape(ai_review)}</p>"
    else:
        content = '<p class="muted">No AI narrative review was generated for this report — findings below are entirely from the deterministic check engine.</p>'
    return f"""
    <section class="card">
      <h2>AI Review</h2>
      {content}
    </section>
    """


def _future_improvements_section() -> str:
    return """
    <section class="card">
      <h2>Future Improvements</h2>
      <p class="muted">
        Manufacturability checks currently cover trace width, annular ring, and via density.
        Silkscreen-over-pad and copper-sliver detection are planned once the parser captures
        silkscreen text geometry and full pour polygon shape.
      </p>
    </section>
    """


def _wrap_document(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{escape(title)} &mdash; PCB Design Review Report</title>
<style>
  :root {{
    color-scheme: light;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 2.5rem 1.5rem;
    background: #f6f8fa;
    color: #1f2328;
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.5;
  }}
  .page {{
    max-width: 960px;
    margin: 0 auto;
  }}
  .card {{
    background: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 8px;
    padding: 1.5rem 1.75rem;
    margin-bottom: 1.5rem;
  }}
  .report-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
  }}
  .report-header h1 {{
    margin: 0;
    font-size: 1.6rem;
  }}
  .subtitle {{
    margin: 0.25rem 0 0;
    color: #57606a;
  }}
  .overall-score {{
    border: 3px solid;
    border-radius: 50%;
    width: 92px;
    height: 92px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    flex-shrink: 0;
  }}
  .overall-score-value {{ font-size: 1.6rem; }}
  .overall-score-label {{ font-size: 0.7rem; color: #57606a; }}
  h2 {{
    margin-top: 0;
    font-size: 1.1rem;
    border-bottom: 1px solid #d0d7de;
    padding-bottom: 0.5rem;
  }}
  .subscore-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
    gap: 0.75rem;
  }}
  .subscore-badge {{
    border: 2px solid;
    border-radius: 8px;
    padding: 0.75rem 0.5rem;
    text-align: center;
  }}
  .subscore-value {{ display: block; font-size: 1.4rem; font-weight: 700; }}
  .subscore-label {{ display: block; font-size: 0.75rem; color: #57606a; margin-top: 0.25rem; }}
  .charts-grid {{
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    align-items: flex-start;
  }}
  .chart {{ max-width: 100%; height: auto; border-radius: 6px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  .stats-table th {{
    text-align: left;
    color: #57606a;
    font-weight: 500;
    padding: 0.4rem 0.75rem 0.4rem 0;
    width: 40%;
    border-bottom: 1px solid #eaeef2;
  }}
  .stats-table td {{
    padding: 0.4rem 0;
    border-bottom: 1px solid #eaeef2;
  }}
  .issues-table th {{
    text-align: left;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    color: #57606a;
    border-bottom: 2px solid #d0d7de;
    padding: 0.5rem;
  }}
  .issues-table td {{
    padding: 0.6rem 0.5rem;
    border-bottom: 1px solid #eaeef2;
    vertical-align: top;
    font-size: 0.9rem;
  }}
  .issues-table td code {{
    white-space: nowrap;
  }}
  .severity-badge {{
    color: #fff;
    padding: 0.15rem 0.55rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: capitalize;
    white-space: nowrap;
  }}
  .principle {{ color: #57606a; font-size: 0.85rem; }}
  .muted {{ color: #57606a; }}
</style>
</head>
<body>
  <div class="page">
    {body}
  </div>
</body>
</html>
"""
