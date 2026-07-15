"""Renders the design review as a professional PDF via ReportLab.

Content mirrors the HTML report (app/reports/html_report.py); rather than
duplicate the chart drawing and the score-color band logic, this module reuses
html_report's matplotlib chart renderers and `_score_color` directly -- the
HTML report stays the single source of truth for how a score maps to a color
and how the subscore/severity charts look. Only the page layout is PDF-specific."""

from __future__ import annotations

import base64
import io
from collections import Counter
from datetime import datetime, timezone
from html import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.board import Board
from app.models.issue import EngineeringScore, Issue
from app.reports.html_report import (
    _SEVERITY_COLORS,
    _SEVERITY_ORDER,
    _render_severity_chart,
    _render_subscore_chart,
    _score_color,
)

# Figure aspect ratios (figsize in html_report), used to size the embedded
# chart images without distorting them.
_SUBSCORE_ASPECT = 5.5 / 3.2
_SEVERITY_ASPECT = 4.2 / 3.2


def render(board: Board, issues: list[Issue], score: EngineeringScore, ai_review: str | None = None) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        title=f"{board.name} - PCB Design Review Report",
        author="PCBInsight AI",
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = _styles()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    severity_counts = Counter(issue.severity for issue in issues)

    story: list = []
    story += _header(board, score, generated_at, styles)
    story += _executive_summary(board, issues, score, severity_counts, styles)
    story += _scores(score, styles)
    story += _charts(score, severity_counts)
    story += _statistics(board, styles)
    story += _issues(issues, styles)
    story += _ai_review(ai_review, styles)

    doc.build(story)
    return buffer.getvalue()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=20, spaceAfter=2),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#57606a")),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=10, leading=14),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontSize=8, leading=11),
        "cellHead": ParagraphStyle("cellHead", parent=base["Normal"], fontSize=8, leading=11, textColor=colors.white),
        "muted": ParagraphStyle("muted", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#57606a")),
    }


def _section_title(text: str, styles: dict) -> list:
    return [
        Paragraph(text, styles["h2"]),
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#d0d7de"), spaceAfter=6),
    ]


def _header(board: Board, score: EngineeringScore, generated_at: str, styles: dict) -> list:
    color = colors.HexColor(_score_color(score.overall))
    left = [
        Paragraph("PCB Design Review Report", styles["title"]),
        Paragraph(f"{escape(board.name)} &middot; generated {escape(generated_at)}", styles["subtitle"]),
    ]
    score_cell = Paragraph(f'<font color="{_score_color(score.overall)}"><b>{score.overall}</b>/100</font>', styles["h2"])
    table = Table([[left, score_cell]], colWidths=[5.2 * inch, 1.8 * inch])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, -1), 1.5, color),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return [table, Spacer(1, 12)]


def _executive_summary(
    board: Board, issues: list[Issue], score: EngineeringScore, severity_counts: Counter, styles: dict
) -> list:
    counts_line = (
        ", ".join(f"{severity_counts[sev]} {sev.value}" for sev in _SEVERITY_ORDER if severity_counts[sev])
        or "no issues found"
    )
    text = (
        f"This board scored <b>{score.overall}/100</b> overall across {len(board.components)} components "
        f"and {len(board.nets)} nets. The deterministic engineering-check engine raised {len(issues)} "
        f"issue(s): {escape(counts_line)}."
    )
    return _section_title("Executive Summary", styles) + [Paragraph(text, styles["body"])]


def _scores(score: EngineeringScore, styles: dict) -> list:
    cells = [
        Paragraph(
            f'<para align="center"><font size="13" color="{_score_color(s.score)}"><b>{s.score}</b></font><br/>'
            f'<font size="7" color="#57606a">{escape(s.category)}</font></para>',
            styles["cell"],
        )
        for s in score.subscores
    ]
    # Lay subscores out in rows of up to 4 badges.
    per_row = 4
    rows = [cells[i : i + per_row] for i in range(0, len(cells), per_row)]
    for row in rows:
        while len(row) < per_row:
            row.append("")
    table = Table(rows, colWidths=[1.6 * inch] * per_row)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return _section_title("Engineering Scores", styles) + [table]


def _charts(score: EngineeringScore, severity_counts: Counter) -> list:
    # Reuse html_report's matplotlib renderers (base64 PNG) so the PDF charts
    # are identical to the HTML report's -- no second chart implementation.
    width = 3.3 * inch
    subscore_img = _image_from_base64(_render_subscore_chart(score), width, width / _SUBSCORE_ASPECT)
    severity_b64 = _render_severity_chart(severity_counts)
    severity_img = (
        _image_from_base64(severity_b64, width, width / _SEVERITY_ASPECT) if severity_b64 else Paragraph("", getSampleStyleSheet()["Normal"])
    )
    table = Table([[subscore_img, severity_img]], colWidths=[3.5 * inch, 3.5 * inch])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    return [Spacer(1, 10), table]


def _image_from_base64(b64: str, width: float, height: float) -> Image:
    return Image(io.BytesIO(base64.b64decode(b64)), width=width, height=height)


def _statistics(board: Board, styles: dict) -> list:
    via_count = sum(len(net.vias) for net in board.nets)
    trace_count = sum(len(net.traces) for net in board.nets)
    rows = [
        ("Board name", board.name),
        ("Dimensions", f"{board.width_mm:.1f}mm x {board.height_mm:.1f}mm"),
        ("Layer count", str(board.layer_count)),
        ("Components", str(len(board.components))),
        ("Nets", str(len(board.nets))),
        ("Trace segments", str(trace_count)),
        ("Vias", str(via_count)),
        ("Copper pours", str(len(board.pours))),
    ]
    data = [
        [Paragraph(f"<b>{escape(label)}</b>", styles["cell"]), Paragraph(escape(str(value)), styles["cell"])]
        for label, value in rows
    ]
    table = Table(data, colWidths=[2.5 * inch, 4.5 * inch])
    table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#eaeef2")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return _section_title("Board Statistics", styles) + [table]


def _issues(issues: list[Issue], styles: dict) -> list:
    title = _section_title("Warnings & Recommendations", styles)
    if not issues:
        return title + [Paragraph("No issues found by the deterministic check engine.", styles["muted"])]

    ordered = sorted(issues, key=lambda issue: _SEVERITY_ORDER.index(issue.severity))
    header = [Paragraph(f"<b>{h}</b>", styles["cellHead"]) for h in ("ID", "Sev", "Category", "Finding", "Why it matters / fix")]
    data = [header]
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#24292f")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for row_index, issue in enumerate(ordered, start=1):
        refs = f" ({escape(', '.join(issue.refs))})" if issue.refs else ""
        finding = f"<b>{escape(issue.summary)}</b>{refs}"
        detail = (
            f"{escape(issue.explanation)} <i>{escape(issue.principle)}</i>"
            f"<br/><b>Fix:</b> {escape(issue.suggested_fix)}"
        )
        data.append(
            [
                Paragraph(escape(issue.id), styles["cell"]),
                Paragraph(escape(issue.severity.value), styles["cell"]),
                Paragraph(escape(issue.category.replace("_", " ").title()), styles["cell"]),
                Paragraph(finding, styles["cell"]),
                Paragraph(detail, styles["cell"]),
            ]
        )
        # Tint the severity cell to match the HTML report's badge color.
        sev_color = colors.HexColor(_SEVERITY_COLORS[issue.severity])
        style_cmds.append(("BACKGROUND", (1, row_index), (1, row_index), sev_color))
        style_cmds.append(("TEXTCOLOR", (1, row_index), (1, row_index), colors.white))

    table = Table(data, colWidths=[0.7 * inch, 0.5 * inch, 0.9 * inch, 2.0 * inch, 2.9 * inch], repeatRows=1)
    table.setStyle(TableStyle(style_cmds))
    return title + [table]


def _ai_review(ai_review: str | None, styles: dict) -> list:
    title = _section_title("AI Review", styles)
    if ai_review:
        return title + [Paragraph(escape(ai_review).replace("\n", "<br/>"), styles["body"])]
    return title + [
        Paragraph(
            "No AI narrative review was generated for this report - findings above are entirely from the "
            "deterministic check engine.",
            styles["muted"],
        )
    ]
