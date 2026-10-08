"""Renders the interactive, tabbed version of the design review report used by
the "Try it" demo on the landing page.

Same data as html_report.render (score, findings, AI review, board), but
organised as separate views behind a tab bar (Overview, Scores, Findings, AI
review, Board, Try it) with a back button on every view, plus two things the
static report does not have:

* a what-if score simulator: mark findings as fixed and watch the subscores
  recompute with the exact formula scoring.py uses;
* a rule checker: type in numbers (trace width, via drill, capacitor distance,
  ...) and see what the real engine would say, using the engine's own
  thresholds (imported from app.analysis, not retyped).

Self-contained single file: inline CSS, inline JS, inline SVG. The only
external request is the optional Google Fonts stylesheet."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from html import escape

from app.analysis import (
    decoupling,
    differential_pairs,
    ground,
    manufacturability,
    placement,
    power,
    routing,
    signal_integrity,
    thermal,
)
from app.analysis.scoring import deduction, severity_points, subscore_for
from app.models.board import Board
from app.models.issue import EngineeringScore, Issue, Severity
from app.reports import html_report as base
from app.reports.html_report import _DARK_SEVERITY, _CONFIDENCE_FLOOR, _dark_score_color
from app.reports.theme import SEVERITY_ORDER

VIEWS = [
    ("overview", "Overview"),
    ("scores", "Scores"),
    ("findings", "Findings"),
    ("ai-review", "AI review"),
    ("board", "Board"),
    ("try-it", "Try it"),
]

_SUBSCORE_ORDER = ["Routing", "Power", "Signal Integrity", "Manufacturability", "Placement", "Thermals", "Documentation"]

_CATEGORY_LABELS = {
    "routing": "Routing",
    "power": "Power",
    "ground": "Ground",
    "decoupling": "Decoupling",
    "differential_pairs": "Differential pairs",
    "signal_integrity": "Signal integrity",
    "manufacturability": "Manufacturability",
    "placement": "Placement",
    "thermal": "Thermal",
}


def _cat_label(category: str) -> str:
    return _CATEGORY_LABELS.get(category, category.replace("_", " ").title())


# --- public entry point --------------------------------------------------------


def render(
    board: Board,
    issues: list[Issue],
    score: EngineeringScore,
    ai_review: str | None = None,
    *,
    landing_href: str | None = None,
    demo_note: str | None = None,
) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ordered = sorted(issues, key=lambda i: SEVERITY_ORDER.index(i.severity))
    groups = base._group_issues(ordered)
    data = _build_data(board, issues, score, groups)

    views = {
        "overview": _view_overview(board, issues, score, groups, demo_note),
        "scores": _view_scores(score, issues, groups),
        "findings": _view_findings(issues, groups),
        "ai-review": _view_ai(ai_review),
        "board": _view_board(board, issues),
        "try-it": _view_try_it(),
    }
    sections = []
    for index, (key, label) in enumerate(VIEWS):
        prev_key = VIEWS[index - 1] if index > 0 else None
        next_key = VIEWS[index + 1] if index < len(VIEWS) - 1 else None
        sections.append(
            f'<section id="view-{key}" class="view" data-view="{key}" role="tabpanel" tabindex="-1" aria-labelledby="tab-{key}" hidden>'
            f"{_view_nav_top(key, label)}{views[key]}{_view_nav_bottom(prev_key, next_key)}</section>"
        )
    body = _topbar(board, generated_at, landing_href) + '<main class="page">' + "\n".join(sections) + "</main>" + _footer_bar()
    return _wrap(board.name, body, data)


# --- data handed to the page script ------------------------------------------------


def _build_data(board: Board, issues: list[Issue], score: EngineeringScore, groups: list[list[Issue]]) -> dict:
    return {
        "subscores": [{"name": s.category, "score": s.score} for s in score.subscores],
        "order": _SUBSCORE_ORDER,
        "severityPoints": {sev.value: severity_points(sev) for sev in SEVERITY_ORDER},
        "severityColors": {sev.value: _DARK_SEVERITY[sev] for sev in SEVERITY_ORDER},
        "issues": [
            {
                "id": issue.id,
                "sub": subscore_for(issue.category),
                "sev": issue.severity.value,
                "conf": issue.confidence,
                "group": gi,
            }
            for gi, group in enumerate(groups)
            for issue in group
        ],
        "rules": _rule_definitions(),
        "confidenceFloor": _CONFIDENCE_FLOOR,
    }


def _rule_definitions() -> list[dict]:
    """Rule metadata for the checker. Thresholds come from the engine modules
    themselves so the checker cannot drift from the real checks."""
    return [
        {
            "id": "trace_width", "sub": "Power", "label": "Trace width",
            "what": "How wide a copper trace is, in millimetres. Wider traces carry more current with less heating and are easier to manufacture.",
            "fields": [
                {"key": "width", "label": "Trace width", "unit": "mm", "value": 0.25, "step": 0.01, "min": 0.01},
                {"key": "net", "label": "What does it carry?", "type": "select",
                 "options": [["signal", "A signal"], ["power", "Power (VCC, 3V3, ...)"], ["ground", "Ground"]], "value": "power"},
            ],
            "limits": {"power_min": power.MIN_POWER_TRACE_WIDTH_MM, "power_crit": power.CRITICAL_POWER_TRACE_WIDTH_MM,
                       "ground_min": ground.MIN_GROUND_TRACE_WIDTH_MM, "fab_min": manufacturability.MIN_TRACE_WIDTH_MM},
            "rule": "Power and ground traces under {power_min} mm are flagged (under {power_crit} mm is high severity). "
                    "Any trace under {fab_min} mm is flagged as hard to manufacture.",
            "presets": [["Passes", {"width": 0.5, "net": "power"}], ["Fails", {"width": 0.12, "net": "power"}]],
        },
        {
            "id": "annular_ring", "sub": "Manufacturability", "label": "Via annular ring",
            "what": "The ring of copper left around a via's drill hole. Drill wander can break a ring that is too thin and cut the connection.",
            "fields": [
                {"key": "pad", "label": "Via pad diameter", "unit": "mm", "value": 0.6, "step": 0.01, "min": 0.1},
                {"key": "drill", "label": "Drill diameter", "unit": "mm", "value": 0.3, "step": 0.01, "min": 0.05},
            ],
            "limits": {"min": manufacturability.MIN_ANNULAR_RING_MM},
            "rule": "Ring = (pad - drill) / 2. Flagged when the ring is under {min} mm.",
            "presets": [["Passes", {"pad": 0.6, "drill": 0.3}], ["Fails", {"pad": 0.4, "drill": 0.3}]],
        },
        {
            "id": "long_trace", "sub": "Routing", "label": "Long trace segment",
            "what": "The length of one straight trace segment. Long runs add resistance, pick up noise and are more likely to need rerouting.",
            "fields": [{"key": "length", "label": "Segment length", "unit": "mm", "value": 45, "step": 1, "min": 0}],
            "limits": {"warn": routing.LONG_TRACE_WARN_MM, "crit": routing.LONG_TRACE_CRITICAL_MM},
            "rule": "Flagged at {warn} mm or more (medium) and {crit} mm or more (high).",
            "presets": [["Passes", {"length": 25}], ["Fails", {"length": 130}]],
        },
        {
            "id": "via_count", "sub": "Routing", "label": "Vias on one net",
            "what": "How many layer changes (vias) one net makes. Each via adds inductance and a place for a fabrication defect.",
            "fields": [
                {"key": "vias", "label": "Number of vias", "unit": "", "value": 3, "step": 1, "min": 0},
                {"key": "clock", "label": "This is a clock net", "type": "checkbox", "value": False},
            ],
            "limits": {"max": routing.EXCESSIVE_VIA_COUNT, "clock_max": signal_integrity.CLOCK_VIA_WARN},
            "rule": "Flagged above {max} vias. Clock nets are stricter: flagged above {clock_max} vias.",
            "presets": [["Passes", {"vias": 2, "clock": False}], ["Fails", {"vias": 7, "clock": True}]],
        },
        {
            "id": "segments", "sub": "Routing", "label": "Segments on one net",
            "what": "How many separate straight pieces a net is routed with. Many tiny segments usually mean a messy, hard-to-maintain route.",
            "fields": [{"key": "segments", "label": "Number of segments", "unit": "", "value": 6, "step": 1, "min": 1}],
            "limits": {"max": routing.MAX_REASONABLE_SEGMENTS},
            "rule": "Flagged above {max} segments.",
            "presets": [["Passes", {"segments": 4}], ["Fails", {"segments": 14}]],
        },
        {
            "id": "acute_angle", "sub": "Routing", "label": "Trace bend angle",
            "what": "The angle where two trace segments meet. Sharp bends can trap etchant during fabrication and disturb fast signals.",
            "fields": [{"key": "angle", "label": "Angle between segments", "unit": "degrees", "value": 90, "step": 1, "min": 1, "max": 180}],
            "limits": {"max": routing.ACUTE_ANGLE_MAX_DEG},
            "rule": "Flagged when the angle is under {max} degrees.",
            "presets": [["Passes", {"angle": 135}], ["Fails", {"angle": 45}]],
        },
        {
            "id": "decoupling", "sub": "Power", "label": "Decoupling capacitor distance",
            "what": "How far the nearest bypass capacitor sits from the chip it protects. Close capacitors supply fast current spikes; distant ones cannot.",
            "fields": [
                {"key": "kind", "label": "Chip type", "type": "select",
                 "options": [["MCU", "Microcontroller"], ["FPGA", "FPGA"], ["regulator", "Voltage regulator"], ["IC", "Other IC"]], "value": "MCU"},
                {"key": "gap", "label": "Distance to nearest capacitor", "unit": "mm", "value": 2.0, "step": 0.1, "min": 0},
                {"key": "none", "label": "No capacitor on this power net at all", "type": "checkbox", "value": False},
            ],
            "limits": dict(decoupling._MAX_DISTANCE_MM_BY_KIND),
            "rule": "Allowed distance by chip type (mm): MCU {MCU}, FPGA {FPGA}, regulator {regulator}, other IC {IC}. "
                    "A missing capacitor is a separate, higher severity finding.",
            "presets": [["Passes", {"kind": "MCU", "gap": 1.5, "none": False}], ["Fails", {"kind": "FPGA", "gap": 6, "none": False}]],
        },
        {
            "id": "supply_path", "sub": "Power", "label": "Supply path length",
            "what": "Total copper length of one power net. Long supply paths drop voltage and add noise.",
            "fields": [{"key": "length", "label": "Total length of the net", "unit": "mm", "value": 50, "step": 1, "min": 0}],
            "limits": {"max": power.LONG_SUPPLY_PATH_MM},
            "rule": "Flagged at {max} mm or more of total trace on one supply net.",
            "presets": [["Passes", {"length": 40}], ["Fails", {"length": 110}]],
        },
        {
            "id": "diff_pair", "sub": "Signal Integrity", "label": "Differential pair matching",
            "what": "A differential pair (like USB D+ and D-) works best when both wires are the same length and shape, so the signal arrives together.",
            "fields": [
                {"key": "lenP", "label": "Length of positive wire", "unit": "mm", "value": 42.0, "step": 0.1, "min": 0},
                {"key": "lenN", "label": "Length of negative wire", "unit": "mm", "value": 42.1, "step": 0.1, "min": 0},
                {"key": "viaP", "label": "Vias on positive wire", "unit": "", "value": 1, "step": 1, "min": 0},
                {"key": "viaN", "label": "Vias on negative wire", "unit": "", "value": 1, "step": 1, "min": 0},
                {"key": "segP", "label": "Segments on positive wire", "unit": "", "value": 4, "step": 1, "min": 1},
                {"key": "segN", "label": "Segments on negative wire", "unit": "", "value": 4, "step": 1, "min": 1},
            ],
            "limits": {"len": differential_pairs.LENGTH_MISMATCH_WARN_MM, "seg": differential_pairs.SEGMENT_COUNT_MISMATCH_WARN},
            "rule": "Length mismatch above {len} mm is flagged. Different via counts are flagged. "
                    "Segment counts differing by more than {seg} are flagged.",
            "presets": [["Passes", {"lenP": 42, "lenN": 42.1, "viaP": 1, "viaN": 1, "segP": 4, "segN": 4}],
                        ["Fails", {"lenP": 42, "lenN": 44.5, "viaP": 2, "viaN": 0, "segP": 3, "segN": 8}]],
        },
        {
            "id": "clock_length", "sub": "Signal Integrity", "label": "Clock net length",
            "what": "Total length of a clock net. Long clock routes radiate noise and degrade edges.",
            "fields": [{"key": "length", "label": "Clock net length", "unit": "mm", "value": 25, "step": 1, "min": 0}],
            "limits": {"max": signal_integrity.CLOCK_LENGTH_WARN_MM},
            "rule": "Flagged at {max} mm or more.",
            "presets": [["Passes", {"length": 20}], ["Fails", {"length": 65}]],
        },
        {
            "id": "via_density", "sub": "Manufacturability", "label": "Via density",
            "what": "Vias per square centimetre of board. Very dense via fields raise fabrication cost and reduce yield.",
            "fields": [
                {"key": "vias", "label": "Total vias on board", "unit": "", "value": 40, "step": 1, "min": 0},
                {"key": "w", "label": "Board width", "unit": "mm", "value": 60, "step": 1, "min": 1},
                {"key": "h", "label": "Board height", "unit": "mm", "value": 40, "step": 1, "min": 1},
            ],
            "limits": {"max": manufacturability.HIGH_VIA_DENSITY_PER_CM2},
            "rule": "Density = vias / board area in cm2. Flagged at {max} per cm2 or more.",
            "presets": [["Passes", {"vias": 40, "w": 60, "h": 40}], ["Fails", {"vias": 160, "w": 40, "h": 30}]],
        },
        {
            "id": "connector_edge", "sub": "Placement", "label": "Connector distance from board edge",
            "what": "How far a connector sits from the nearest board edge. Connectors away from the edge are awkward to plug into and to fit in an enclosure.",
            "fields": [{"key": "dist", "label": "Distance to nearest edge", "unit": "mm", "value": 4, "step": 0.5, "min": 0}],
            "limits": {"max": placement.CONNECTOR_EDGE_DISTANCE_WARN_MM},
            "rule": "Flagged when a connector is more than {max} mm from the edge.",
            "presets": [["Passes", {"dist": 3}], ["Fails", {"dist": 18}]],
        },
        {
            "id": "crowding", "sub": "Placement", "label": "Component crowding",
            "what": "Centre-to-centre spacing between two parts. Parts packed too tightly are hard to assemble, probe and rework.",
            "fields": [{"key": "gap", "label": "Centre-to-centre spacing", "unit": "mm", "value": 3, "step": 0.1, "min": 0}],
            "limits": {"min": placement.CROWDED_DISTANCE_MM},
            "rule": "Flagged when two components are closer than {min} mm.",
            "presets": [["Passes", {"gap": 3}], ["Fails", {"gap": 0.6}]],
        },
        {
            "id": "heat_spacing", "sub": "Thermals", "label": "Heat source spacing",
            "what": "Spacing between two parts that run hot (regulators, power transistors). Hot parts side by side heat each other up.",
            "fields": [{"key": "gap", "label": "Distance between the two hot parts", "unit": "mm", "value": 12, "step": 0.5, "min": 0}],
            "limits": {"min": thermal.CONGESTION_DISTANCE_MM},
            "rule": "Flagged when two heat sources are closer than {min} mm.",
            "presets": [["Passes", {"gap": 15}], ["Fails", {"gap": 4}]],
        },
    ]


# --- shared chrome ------------------------------------------------------------------


def _topbar(board: Board, generated_at: str, landing_href: str | None) -> str:
    tabs = "".join(
        f'<a role="tab" class="tab" href="#{key}" data-go="{key}" id="tab-{key}" aria-controls="view-{key}">{escape(label)}</a>'
        for key, label in VIEWS
    )
    landing = (
        f'<a class="landing-link" href="{escape(landing_href)}">&larr; Landing page</a>' if landing_href else ""
    )
    return f"""
    <header class="topbar-wrap">
      <div class="topbar-inner">
        <div class="topbar-row">
          <a class="brand" href="#overview" data-go="overview">PCBInsight<span class="brand-slash"> / </span>demo</a>
          <span class="topbar-meta">{escape(board.name)} &middot; generated {escape(generated_at)}</span>
          {landing}
        </div>
        <nav class="tabs" role="tablist" aria-label="Report sections">{tabs}</nav>
      </div>
    </header>
    """


def _view_nav_top(key: str, label: str) -> str:
    if key == "overview":
        return ""
    return f"""
    <div class="view-nav">
      <button type="button" class="back-btn" data-go="overview"><span aria-hidden="true">&larr;</span> Back to overview</button>
      <span class="crumbs"><a href="#overview" data-go="overview">Overview</a> / {escape(label)}</span>
    </div>
    """


def _view_nav_bottom(prev_item: tuple[str, str] | None, next_item: tuple[str, str] | None) -> str:
    parts = []
    if prev_item:
        parts.append(
            f'<button type="button" class="pager" data-go="{prev_item[0]}"><span aria-hidden="true">&larr;</span> {escape(prev_item[1])}</button>'
        )
    parts.append('<button type="button" class="pager pager-home" data-go="overview">All sections</button>')
    if next_item:
        parts.append(
            f'<button type="button" class="pager pager-next" data-go="{next_item[0]}">Next: {escape(next_item[1])} <span aria-hidden="true">&rarr;</span></button>'
        )
    return f'<div class="view-pager">{"".join(parts)}</div>'


def _footer_bar() -> str:
    return """
    <footer class="site-footer">
      <p>PCBInsight AI &middot; deterministic PCB design review with an evidence-constrained AI narrator.
      <a href="https://github.com/CyrilKafle/PCBInsight-AI">Source on GitHub</a></p>
    </footer>
    """


def _help(term: str, text: str) -> str:
    return f'<abbr class="term" tabindex="0" title="{escape(text, quote=True)}">{escape(term)}</abbr>'


def _intro(title: str, body: str) -> str:
    return f"""
    <div class="what">
      <p class="what-title">{escape(title)}</p>
      {body}
    </div>
    """


# --- Overview -----------------------------------------------------------------------


def _view_overview(board: Board, issues: list[Issue], score: EngineeringScore, groups: list[list[Issue]], demo_note: str | None) -> str:
    color = _dark_score_color(score.overall)
    counts = Counter(i.severity for i in issues)
    unverified = sum(1 for i in issues if i.confidence < _CONFIDENCE_FLOOR)
    via_count = sum(len(n.vias) for n in board.nets)
    trace_count = sum(len(n.traces) for n in board.nets)
    facts = "".join(
        f"<span>{fact}</span>"
        for fact in [
            f"{board.layer_count} layers",
            f"{board.width_mm:.0f} &times; {board.height_mm:.0f} mm",
            f"{len(board.components)} components",
            f"{len(board.nets)} nets",
        ]
    )
    sev_line = ", ".join(f"{counts[s]} {s.value}" for s in SEVERITY_ORDER if counts[s]) or "none"
    cards = [
        ("scores", "Scores", f"{score.overall}/100 overall", "Seven subscores and the exact arithmetic behind them. Mark findings as fixed to see the score move."),
        ("findings", "Findings", f"{len(issues)} found &middot; {len(groups)} groups", f"Every problem the engine found ({escape(sev_line)}), with why it matters and how to fix it. Filter by severity or area."),
        ("ai-review", "AI review", "Written by Claude", "A plain-English summary of the findings. It can only talk about what the engine already found."),
        ("board", "Board", f"{len(board.components)} parts &middot; {via_count} vias", "A map of the board with every finding pinned to where it was detected, plus the raw statistics."),
        ("try-it", "Try it", "Type in your own numbers", "Enter a trace width, via size, or capacitor distance and see what the real rule engine says."),
    ]
    card_html = "".join(
        f"""<a class="card" href="#{key}" data-go="{key}">
          <span class="card-top"><span class="card-title">{title}</span><span class="card-arrow" aria-hidden="true">&rarr;</span></span>
          <span class="card-stat">{stat}</span>
          <span class="card-desc">{desc}</span>
        </a>"""
        for key, title, stat, desc in cards
    )
    note = (
        f'<div class="demo-note"><strong>Real output, not a mockup.</strong> {demo_note}</div>' if demo_note else ""
    )
    return f"""
    <div class="hero">
      <div class="hero-main">
        <p class="eyebrow">Design review</p>
        <h1 id="h-overview">{escape(board.name)}</h1>
        <p class="facts">{facts}</p>
        <p class="lead">PCBInsight reads a KiCad board, runs 28 engineering checks across 9
        categories against it, scores the result, and has an AI explain the findings. This page is that report for a real
        example board. Pick a section below to explore it.</p>
        <p class="hero-cta"><button type="button" class="btn-primary" data-go="scores">Start with the scores <span aria-hidden="true">&rarr;</span></button>
        <button type="button" class="btn-ghost" data-go="try-it">Jump to Try it</button></p>
      </div>
      <div class="hero-score" style="--score-color:{color}">
        <div class="hero-score-value"><span>{score.overall}</span><small>/100</small></div>
        <div class="meter"><span class="meter-fill" style="width:{score.overall}%"></span></div>
        <p class="hero-score-label">Overall score</p>
        <p class="hero-score-note">The plain average of seven subscores. {unverified} of {len(issues)} findings are low confidence and need a manual look.</p>
      </div>
    </div>
    {note}
    <h2 class="section-title">Explore the report</h2>
    <div class="cards">{card_html}</div>
    <div class="how">
      <h3>How to read this</h3>
      <ol>
        <li><strong>The engine decides.</strong> Deterministic rules with named thresholds find every problem. No machine learning is involved in the score.</li>
        <li><strong>The score is arithmetic.</strong> Each finding removes points based on its severity and how confident the rule is.</li>
        <li><strong>The AI only explains.</strong> Claude receives a digest of the findings, never the raw board, and its citations are checked in code.</li>
      </ol>
    </div>
    <details class="limits">
      <summary>Known limits of this demo</summary>
      <ul>
        <li>The 0 to 100 score has no pass threshold. It summarizes deductions and is not a certification.</li>
        <li>Documentation has no checks yet, so it reads 100 by default. A subscore of 100 means no deductions were found, not that the area was validated.</li>
        <li>Dangling-end detection compares endpoints to pads, vias and traces within a position tolerance, so it can flag ends that are actually connected. That is why those findings carry low confidence.</li>
        <li>Manufacturability checks currently cover trace width, annular ring, and via density.</li>
        <li>Confidence values are set by hand per rule, not calibrated against labelled boards.</li>
      </ul>
    </details>
    """


# --- Scores ---------------------------------------------------------------------------


def _view_scores(score: EngineeringScore, issues: list[Issue], groups: list[list[Issue]]) -> str:
    lost: Counter = Counter()
    for issue in issues:
        name = subscore_for(issue.category)
        if name:
            lost[name] += deduction(issue)
    rows = []
    for sub_ in score.subscores:
        unchecked = sub_.category == "Documentation"
        note = '<small class="subscore-sub">no checks yet</small>' if unchecked else ""
        color = "#8B96A5" if unchecked else _dark_score_color(sub_.score)
        loss = f"&minus;{lost[sub_.category]:.1f}" if lost[sub_.category] else "0.0"
        rows.append(
            f"""<div class="subscore" data-sub="{escape(sub_.category)}" style="--score-color:{color}">
              <span class="subscore-name">{escape(sub_.category)}{note}</span>
              <span class="meter"><span class="meter-fill" style="width:{sub_.score}%"></span></span>
              <span class="subscore-loss">{loss}</span>
              <span class="subscore-value">{sub_.score}</span>
              <span class="subscore-delta" aria-live="polite"></span>
            </div>"""
        )
    sim_rows = []
    for gi, group in enumerate(groups):
        first = group[0]
        name = subscore_for(first.category)
        if not name:
            continue
        total = sum(deduction(i) for i in group)
        title = first.summary if len(group) == 1 else f"{len(group)} &times; {escape(base._group_title(first))}"
        title = escape(first.summary) if len(group) == 1 else title
        ids = first.id if len(group) == 1 else f"{group[0].id} to {group[-1].id}"
        sim_rows.append(
            f"""<label class="sim-row" style="--sev:{_DARK_SEVERITY[first.severity]}">
              <input type="checkbox" class="sim-check" data-group="{gi}">
              <span class="sim-main"><span class="sim-title">{title}</span>
              <span class="sim-meta"><code>{escape(ids)}</code> &middot; {escape(first.severity.value)} &middot; {escape(name)}</span></span>
              <span class="sim-pts">&minus;{total:.1f}</span>
            </label>"""
        )
    sim_html = "".join(sim_rows) or '<p class="muted">No findings to simulate.</p>'
    intro = _intro(
        "What is this?",
        "<p>Every finding removes points from the area it belongs to. The size of the penalty depends on how "
        "<strong>severe</strong> the problem is and how <strong>confident</strong> the rule is that it is real. "
        "Each area starts at 100, and the overall score is the average of all seven areas.</p>",
    )
    return f"""
    <h2 id="h-scores"><span class="h-label">01</span> Engineering scores</h2>
    {intro}
    <div class="subscores">
      <div class="subscore subscore-head" aria-hidden="true"><span>Area</span><span></span><span class="subscore-loss">Points lost</span><span class="subscore-value">Score</span><span></span></div>
      {"".join(rows)}
      <div class="subscore subscore-total" id="overall-row" style="--score-color:{_dark_score_color(score.overall)}">
        <span class="subscore-name">Overall</span>
        <span class="meter"><span class="meter-fill" style="width:{score.overall}%"></span></span>
        <span class="subscore-loss">average</span>
        <span class="subscore-value">{score.overall}</span>
        <span class="subscore-delta" aria-live="polite"></span>
      </div>
    </div>

    <div class="panel sim" id="what-if">
      <div class="panel-head">
        <h3>What if you fixed these?</h3>
        <button type="button" class="btn-ghost" id="sim-reset">Reset</button>
      </div>
      <p class="panel-note">Tick a finding to pretend you fixed it. The bars above update using the same formula as the engine.
      <span id="sim-test-note"></span></p>
      <div class="sim-list">{sim_html}</div>
      <div id="sim-extra" class="sim-extra" hidden></div>
    </div>

    {_derivation_panel(score, issues, groups)}
    """


def _derivation_panel(score: EngineeringScore, issues: list[Issue], groups: list[list[Issue]]) -> str:
    rows = []
    for group in groups:
        first = group[0]
        sub_ = subscore_for(first.category)
        if not sub_:
            continue
        points = severity_points(first.severity)
        total = sum(deduction(i) for i in group)
        confidences = {i.confidence for i in group}
        calc = (
            (f"{len(group)} &times; " if len(group) > 1 else "") + f"{points:g} &times; {first.confidence:.2f}"
            if len(confidences) == 1
            else "sum over findings"
        )
        label = first.id if len(group) == 1 else f"{group[0].id} to {group[-1].id}"
        rows.append(
            f'<tr><td class="nowrap"><code>{escape(label)}</code></td><td>{escape(sub_)}</td>'
            f'<td class="num">&minus;{total:.1f}</td><td class="num">{calc}</td></tr>'
        )
    body = "\n".join(rows) or '<tr><td colspan="4" class="muted">No deductions.</td></tr>'
    scale = ", ".join(f"{s.value} {severity_points(s):g}" for s in SEVERITY_ORDER)
    parts = " + ".join(str(s.score) for s in score.subscores)
    mean = sum(s.score for s in score.subscores) / len(score.subscores)
    return f"""
    <details class="panel derivation">
      <summary><h3>Show the exact arithmetic</h3></summary>
      <p class="formula"><code>area score = 100 &minus; &Sigma; (severity points &times; confidence)</code></p>
      <p class="panel-note">Severity points: {scale}. Decoupling and ground findings roll into Power. Confidence is a hand-set
      per-rule estimate, not a statistical probability.</p>
      <div class="table-scroll" tabindex="0" role="region" aria-label="Score deductions table">
        <table>
          <thead><tr><th>Finding</th><th>Area</th><th class="num">Deducted</th><th class="num">Severity &times; confidence</th></tr></thead>
          <tbody>{body}</tbody>
        </table>
      </div>
      <p class="panel-note">Overall = ({parts}) / {len(score.subscores)} = {mean:.1f}, shown as {score.overall}.</p>
    </details>
    """


# --- Findings -------------------------------------------------------------------------


_GLOSSARY = [
    ("Net", "A set of pads that must be electrically connected, such as every pin that touches the 3.3 V supply."),
    ("Trace", "A strip of copper that carries a signal or power between pads."),
    ("Via", "A plated hole that moves a trace from one board layer to another."),
    ("Annular ring", "The ring of copper left around a drilled hole. Too thin and a slightly off-centre drill breaks the connection."),
    ("Decoupling capacitor", "A small capacitor placed right next to a chip's power pin to supply fast bursts of current."),
    ("Copper pour", "A large filled area of copper, usually ground, that gives current an easy return path and helps spread heat."),
    ("Differential pair", "Two traces that carry one signal as a voltage difference, like USB D+ and D-. They should match in length and shape."),
    ("Confidence", "A fixed per-rule estimate from 0 to 1 of how likely a finding is real. It is not a statistical probability."),
]


def _view_findings(issues: list[Issue], groups: list[list[Issue]]) -> str:
    counts = Counter(i.severity for i in issues)
    sev_buttons = "".join(
        f'<button type="button" class="chip-btn" data-filter-sev="{s.value}" style="--sev:{_DARK_SEVERITY[s]}" aria-pressed="false">'
        f"{escape(s.value.title())} <span class=\"chip-count\">{counts[s]}</span></button>"
        for s in SEVERITY_ORDER
        if counts[s]
    )
    cats = sorted({i.category for i in issues})
    cat_options = "".join(f'<option value="{escape(c)}">{escape(_cat_label(c))}</option>' for c in cats)
    cards = "\n".join(_finding_card(gi, group) for gi, group in enumerate(groups))
    gloss = "".join(f"<dt>{escape(t)}</dt><dd>{escape(d)}</dd>" for t, d in _GLOSSARY)
    intro = _intro(
        "What is this?",
        f"<p>Each card is one problem the rule engine found. Cards that share the same explanation are grouped, so six copies of the "
        f"same warning read as one card listing six nets. Open a card to see <strong>why it matters</strong> and "
        f"<strong>how to fix it</strong>. Findings below <strong>{_CONFIDENCE_FLOOR}</strong> confidence are marked "
        f"<span class=\"unverified\">unverified</span>: check them by hand in your CAD tool.</p>",
    )
    if not issues:
        return f'<h2 id="h-findings"><span class="h-label">02</span> Findings</h2>{intro}<p class="muted">No issues found by the deterministic check engine.</p>'
    return f"""
    <h2 id="h-findings"><span class="h-label">02</span> Findings</h2>
    {intro}
    <div class="toolbar" role="group" aria-label="Filter findings">
      <div class="chip-row">
        <button type="button" class="chip-btn is-on" data-filter-sev="all" aria-pressed="true">All <span class="chip-count">{len(issues)}</span></button>
        {sev_buttons}
      </div>
      <div class="toolbar-right">
        <label class="select-wrap">Area
          <select id="filter-cat"><option value="all">All areas</option>{cat_options}</select>
        </label>
        <label class="check-wrap"><input type="checkbox" id="filter-unverified"> Only unverified</label>
        <button type="button" class="btn-ghost" id="expand-all">Expand all</button>
        <button type="button" class="btn-ghost" id="collapse-all">Collapse all</button>
      </div>
    </div>
    <p class="result-count" id="result-count" aria-live="polite">Showing {len(groups)} of {len(groups)} groups</p>
    <div class="findings" id="findings-list">{cards}</div>
    <p class="muted empty" id="findings-empty" hidden>No findings match these filters. <button type="button" class="link-btn" id="filters-clear">Clear filters</button></p>
    <details class="panel glossary"><summary><h3>Glossary</h3></summary><dl>{gloss}</dl></details>
    """


def _finding_card(gi: int, group: list[Issue]) -> str:
    first = group[0]
    color = _DARK_SEVERITY[first.severity]
    confidences = sorted({i.confidence for i in group})
    conf_text = (
        f"{confidences[0]:.2f}" if len(confidences) == 1 else f"{confidences[0]:.2f}&ndash;{confidences[-1]:.2f}"
    )
    unverified = any(i.confidence < _CONFIDENCE_FLOOR for i in group)
    if len(group) == 1:
        title = escape(first.summary)
        id_html = f'<code class="issue-id">{escape(first.id)}</code>'
        refs = "".join(f'<span class="chip">{escape(r)}</span>' for r in first.refs)
        refs_html = f'<p class="chips">{refs}</p>' if refs else ""
    else:
        title = f"{len(group)} &times; {escape(base._group_title(first))}"
        id_html = f'<code class="issue-id">{escape(group[0].id)} to {escape(group[-1].id)}</code>'
        refs_html = ""
    members = ""
    if len(group) > 1:
        items = []
        for i in group:
            locate = (
                f'<button type="button" class="link-btn locate" data-locate="{escape(i.id)}">Show on board</button>'
                if i.location is not None
                else ""
            )
            items.append(f'<li><code class="issue-id">{escape(i.id)}</code><span>{escape(i.summary)}</span>{locate}</li>')
        members = f'<ul class="members">{"".join(items)}</ul>'
    elif first.location is not None:
        id_html += f'<button type="button" class="link-btn" data-locate="{escape(first.id)}">Show on board</button>'
    unv = '<span class="unverified">unverified: check by hand</span>' if unverified else ""
    return f"""
    <details class="finding" data-group="{gi}" data-sev="{first.severity.value}" data-cat="{escape(first.category)}" data-unverified="{1 if unverified else 0}" style="--sev:{color}">
      <summary>
        <span class="finding-sev">{escape(first.severity.value)}</span>
        <span class="finding-title">{title}</span>
        <span class="finding-side">
          <span class="finding-cat">{escape(_cat_label(first.category))}</span>
          <span class="finding-conf" title="Confidence: how likely this finding is real (0 to 1)">conf {conf_text}</span>
          {unv}
          <span class="finding-chev" aria-hidden="true"></span>
        </span>
      </summary>
      <div class="finding-detail">
        <div class="finding-ids">{id_html}</div>
        {refs_html}
        {members}
        <div class="finding-body">
          <div><h4>Why it matters</h4><p>{escape(first.explanation)}</p><p class="principle">{escape(first.principle)}</p></div>
          <div><h4>Suggested fix</h4><p>{escape(first.suggested_fix)}</p></div>
        </div>
      </div>
    </details>
    """


# --- AI review -------------------------------------------------------------------------


def _view_ai(ai_review: str | None) -> str:
    intro = _intro(
        "What is this?",
        "<p>After the engine finishes, Claude writes a short engineering review of the findings, the way a senior engineer "
        "would in a code review. It is a <strong>narrator, not an analyst</strong>: it receives a structured digest of what "
        "the engine already found and nothing else.</p>",
    )
    flow = """
    <ol class="flow" aria-label="How the AI review is produced">
      <li><strong>1 &middot; Engine</strong><span>28 deterministic checks produce findings</span></li>
      <li><strong>2 &middot; Digest</strong><span>Findings are summarized. No raw board geometry.</span></li>
      <li><strong>3 &middot; Claude</strong><span>Writes the narrative from the digest only</span></li>
      <li><strong>4 &middot; Check</strong><span>Every citation is verified in code</span></li>
    </ol>
    """
    if ai_review:
        text = ai_review.strip()
        import re

        truncated = not re.search(r"[.!?)\]*`\"']$", text)
        if truncated and "\n\n" in text:
            text = text.rsplit("\n\n", 1)[0]
        content = base._markdown_to_html(text)
        if truncated:
            content += (
                '<p class="truncation-note">The model reached its output limit, so one trailing incomplete '
                "sentence is omitted. Everything above is verbatim.</p>"
            )
        note = (
            '<p class="panel-note">Shown verbatim from a real Claude run. It repeats the engine\'s score and confidence values and '
            "adds no evidence from the board beyond them. Any general engineering background in it is the model's own.</p>"
        )
        body = f'{note}<article class="ai-body">{content}</article>'
    else:
        body = '<p class="muted">No AI narrative review was generated for this report. The findings come entirely from the deterministic check engine.</p>'
    return f'<h2 id="h-ai-review"><span class="h-label ai-label">03</span> AI review</h2>{intro}{flow}{body}'


# --- Board -----------------------------------------------------------------------------


_STAT_HELP = {
    "Dimensions": "Outline of the board in millimetres.",
    "Layers": "Copper layers. More layers allow denser routing and dedicated power and ground planes.",
    "Components": "Parts placed on the board: chips, passives, connectors.",
    "Nets": "Groups of pads that must be electrically connected.",
    "Trace segments": "Straight pieces of copper that make up the routing.",
    "Vias": "Plated holes that move a trace between layers.",
    "Copper pours": "Large filled copper areas, usually ground.",
    "Findings": "Problems the rule engine flagged. Each one with a known position is pinned on the map above.",
}


def _view_board(board: Board, issues: list[Issue]) -> str:
    via_count = sum(len(n.vias) for n in board.nets)
    trace_count = sum(len(n.traces) for n in board.nets)
    rows = [
        ("Dimensions", f"{board.width_mm:.1f} &times; {board.height_mm:.1f} mm"),
        ("Layers", str(board.layer_count)),
        ("Components", str(len(board.components))),
        ("Nets", str(len(board.nets))),
        ("Trace segments", str(trace_count)),
        ("Vias", str(via_count)),
        ("Copper pours", str(len(board.pours))),
        ("Findings", str(len(issues))),
    ]
    stats = "".join(
        f'<div class="stat"><dt>{label}</dt><dd>{value}</dd><p>{escape(_STAT_HELP[label])}</p></div>' for label, value in rows
    )
    intro = _intro(
        "What is this?",
        "<p>A top-down map of the board as the parser read it. Dots mark where each finding was detected. "
        "Hover or tap a dot to read it, or use <strong>Show on board</strong> in the Findings tab to jump straight to one.</p>",
    )
    return f"""
    <h2 id="h-board"><span class="h-label">04</span> Board</h2>
    {intro}
    {_board_svg(board, issues)}
    <dl class="stats">{stats}</dl>
    """


def _board_svg(board: Board, issues: list[Issue]) -> str:
    ox, oy = board.origin.x, board.origin.y
    pad = max(board.width_mm, board.height_mm) * 0.04 + 1
    w, h = board.width_mm, board.height_mm
    layers = sorted({t.layer for n in board.nets for t in n.traces})
    layer_class = {name: f"layer-{i % 4}" for i, name in enumerate(layers)}
    pours = "".join(
        '<polygon class="pour" points="{}"/>'.format(" ".join(f"{p.x - ox:.2f},{p.y - oy:.2f}" for p in pour.outline))
        for pour in board.pours
        if len(pour.outline) >= 3
    )
    traces = "".join(
        f'<line class="trace {layer_class[t.layer]}" x1="{t.start.x - ox:.2f}" y1="{t.start.y - oy:.2f}" x2="{t.end.x - ox:.2f}" y2="{t.end.y - oy:.2f}" stroke-width="{max(t.width, 0.2):.2f}"/>'
        for n in board.nets
        for t in n.traces
    )
    vias = "".join(
        f'<circle class="via" cx="{v.position.x - ox:.2f}" cy="{v.position.y - oy:.2f}" r="{max(v.diameter / 2, 0.3):.2f}"/>'
        for n in board.nets
        for v in n.vias
    )
    kind_class = {"MCU": "k-ic", "FPGA": "k-ic", "IC": "k-ic", "regulator": "k-ic", "connector": "k-conn"}
    comps = "".join(
        f'<g class="comp {kind_class.get(c.kind, "k-pass")}" transform="translate({c.footprint.position.x - ox:.2f},{c.footprint.position.y - oy:.2f})">'
        f'<rect x="-1.1" y="-0.7" width="2.2" height="1.4" rx="0.2"/>'
        f'<text y="-1.1" text-anchor="middle">{escape(c.footprint.reference)}</text></g>'
        for c in board.components
    )
    markers = "".join(
        f'<circle class="marker" tabindex="0" role="button" data-id="{escape(i.id)}" data-sev="{i.severity.value}" '
        f'cx="{i.location.x - ox:.2f}" cy="{i.location.y - oy:.2f}" r="{max(w, h) * 0.014:.2f}" style="--sev:{_DARK_SEVERITY[i.severity]}">'
        f"<title>{escape(i.id)}: {escape(i.summary)}</title></circle>"
        for i in issues
        if i.location is not None
    )
    located = sum(1 for i in issues if i.location is not None)
    legend_layers = "".join(
        f'<span class="lg"><i class="sw {layer_class[name]}"></i>{escape(name)}</span>' for name in layers
    )
    return f"""
    <div class="panel boardmap">
      <div class="panel-head">
        <h3>Board map</h3>
        <div class="layer-toggles" role="group" aria-label="Map layers">
          <label><input type="checkbox" data-layer="pours" checked> Pours</label>
          <label><input type="checkbox" data-layer="traces" checked> Traces</label>
          <label><input type="checkbox" data-layer="vias" checked> Vias</label>
          <label><input type="checkbox" data-layer="comps" checked> Parts</label>
          <label><input type="checkbox" data-layer="markers" checked> Findings ({located})</label>
        </div>
      </div>
      <svg id="board-svg" viewBox="{-pad:.2f} {-pad:.2f} {w + 2 * pad:.2f} {h + 2 * pad:.2f}" role="img"
           aria-label="Top-down map of the board with {located} findings pinned">
        <rect class="outline" x="0" y="0" width="{w:.2f}" height="{h:.2f}" rx="0.8"/>
        <g class="g-pours">{pours}</g>
        <g class="g-traces">{traces}</g>
        <g class="g-vias">{vias}</g>
        <g class="g-comps">{comps}</g>
        <g class="g-markers">{markers}</g>
      </svg>
      <div class="map-legend">
        {legend_layers}
        <span class="lg"><i class="sw sw-via"></i>Via</span>
        <span class="lg"><i class="sw sw-marker"></i>Finding (colour = severity)</span>
      </div>
      <div class="map-detail" id="map-detail" aria-live="polite"><span class="muted">Select a dot on the map to read the finding.</span></div>
    </div>
    """


# --- Try it ----------------------------------------------------------------------------


def _view_try_it() -> str:
    intro = _intro(
        "What is this?",
        "<p>This is the real rule engine's logic with the numbers left blank. Pick a check, type in a value from your own board, "
        "and it tells you instantly whether the engine would flag it, how severe it would be, and how many points it would cost. "
        "The thresholds shown come straight from the engine's source code.</p>",
    )
    return f"""
    <h2 id="h-try-it"><span class="h-label">05</span> Try it yourself</h2>
    {intro}
    <div class="try">
      <div class="panel try-form">
        <div class="panel-head"><h3>1. Choose a check</h3></div>
        <label class="field"><span class="field-label">Check</span>
          <select id="rule-select" aria-describedby="rule-what"></select>
        </label>
        <p class="panel-note" id="rule-what"></p>
        <div class="panel-head"><h3>2. Enter your numbers</h3></div>
        <div id="rule-fields" class="fields"></div>
        <div class="presets" id="rule-presets" aria-label="Example values"></div>
        <p class="rule-line" id="rule-line"></p>
      </div>
      <div class="panel try-result" aria-live="polite">
        <div class="panel-head"><h3>3. What the engine says</h3></div>
        <div id="rule-result"></div>
        <div class="try-actions">
          <button type="button" class="btn-primary" id="rule-add" hidden>Add to the what-if score</button>
          <span class="muted" id="rule-add-note"></span>
        </div>
      </div>
    </div>
    <details class="panel rules-table">
      <summary><h3>All checks you can try, and when each one flags</h3></summary>
      <div class="table-scroll" tabindex="0" role="region" aria-label="Rule thresholds">
        <table>
          <thead><tr><th>Check</th><th>Area</th><th>Flagged when</th></tr></thead>
          <tbody>{_rules_table_rows()}</tbody>
        </table>
      </div>
    </details>
    <div class="panel test-list" id="test-list" hidden>
      <div class="panel-head"><h3>Findings you added</h3><button type="button" class="btn-ghost" id="test-clear">Clear</button></div>
      <p class="panel-note">These count against the board's scores in the <a href="#scores" data-go="scores">what-if panel</a>.</p>
      <ul id="test-items"></ul>
      <button type="button" class="btn-primary" data-go="scores">See the effect on the scores</button>
    </div>
    """


def _rules_table_rows() -> str:
    import re

    rows = []
    for rule in _rule_definitions():
        flagged = re.sub(r"\{(\w+)\}", lambda m: str(rule["limits"][m.group(1)]), rule["rule"])
        rows.append(f'<tr><td class="nowrap">{escape(rule["label"])}</td><td>{escape(rule["sub"])}</td><td>{escape(flagged)}</td></tr>')
    return "".join(rows)


# --- document shell ----------------------------------------------------------------------

_EXTRA_CSS = """
  html { scroll-behavior: auto; }
  body { padding-bottom: 0; }
  .page { padding-top: 8px; min-height: 70vh; }
  .view[hidden] { display: none; }
  .view:focus { outline: none; }
  .topbar-wrap { position: sticky; top: 0; z-index: 20; background: rgba(10,14,20,0.94);
    backdrop-filter: blur(6px); border-bottom: 1px solid var(--border); }
  .topbar-inner { max-width: 1040px; margin: 0 auto; padding: 0 24px; }
  .topbar-row { display: flex; align-items: center; gap: 16px; padding: 12px 0 4px;
    font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted); }
  .brand { color: var(--text); font-weight: 600; letter-spacing: 0.02em; }
  .brand:hover { text-decoration: none; }
  .topbar-meta { margin-left: auto; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .landing-link { white-space: nowrap; }
  .tabs { display: flex; gap: 4px; overflow-x: auto; scrollbar-width: none; margin: 0 -8px; padding: 0 8px; }
  .tabs::-webkit-scrollbar { display: none; }
  .tab { flex: 0 0 auto; padding: 10px 14px; font-family: var(--mono); font-size: 0.875rem; color: var(--text-muted);
    border-bottom: 2px solid transparent; }
  .tab:hover { color: var(--text); text-decoration: none; }
  .tab[aria-selected="true"] { color: var(--accent); border-bottom-color: var(--accent); }
  .tab:focus-visible, .card:focus-visible, button:focus-visible, select:focus-visible, input:focus-visible,
  summary:focus-visible, .marker:focus-visible, abbr:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

  .view-nav { display: flex; align-items: center; gap: 16px; padding: 20px 0 4px; }
  .crumbs { font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted); }
  .back-btn, .pager, .btn-ghost, .btn-primary, .chip-btn, .link-btn {
    font-family: var(--mono); cursor: pointer; border-radius: 4px; }
  .back-btn { background: var(--surface); color: var(--text); border: 1px solid var(--border);
    padding: 9px 14px; font-size: 0.875rem; min-height: 40px; }
  .back-btn:hover, .pager:hover, .btn-ghost:hover, .chip-btn:hover { border-color: var(--accent); color: var(--accent); }
  .view-pager { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 56px; padding-top: 24px; border-top: 1px solid var(--border); }
  .pager { background: var(--surface); color: var(--text); border: 1px solid var(--border); padding: 11px 16px; font-size: 0.875rem; min-height: 44px; }
  .pager-next { margin-left: auto; border-color: var(--accent-dim); color: var(--accent); }
  .btn-ghost { background: transparent; color: var(--text-muted); border: 1px solid var(--border); padding: 7px 12px; font-size: 0.8125rem; min-height: 36px; }
  .btn-primary { background: var(--accent); color: #04110f; border: 1px solid var(--accent); padding: 11px 18px; font-size: 0.875rem; font-weight: 600; min-height: 44px; }
  .btn-primary:hover { filter: brightness(1.08); }
  .link-btn { background: none; border: 0; color: var(--accent); padding: 4px 6px; font-size: 0.8125rem; text-decoration: underline; min-height: 32px; }

  .view > h2 { margin-top: 20px; }
  .section-title { margin: 40px 0 16px; font-size: 1.25rem; }
  .what { background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--accent-dim);
    border-radius: 4px; padding: 14px 20px; margin: 0 0 24px; max-width: 80ch; }
  .what p { margin: 0; font-size: 0.9375rem; color: var(--text-muted); }
  .what p strong { color: var(--text); font-weight: 500; }
  .what-title { font-family: var(--mono); font-size: 0.8125rem !important; text-transform: uppercase; letter-spacing: 0.12em;
    color: var(--accent) !important; margin-bottom: 6px !important; }
  .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 20px 24px; margin-top: 24px; }
  .panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
  .panel h3 { margin: 0; font-size: 1.0625rem; }
  .panel-note { margin: 0 0 14px; font-size: 0.875rem; color: var(--text-muted); max-width: 76ch; }
  details.panel > summary { cursor: pointer; list-style: none; }
  details.panel > summary::-webkit-details-marker { display: none; }
  details.panel > summary h3::before { content: "+"; display: inline-block; width: 1.2em; color: var(--accent); font-family: var(--mono); }
  details.panel[open] > summary h3::before { content: "\\2212"; }
  details.panel[open] > summary { margin-bottom: 14px; }

  .hero { padding-top: 36px; }
  .hero-cta { display: flex; gap: 12px; flex-wrap: wrap; margin: 20px 0 0; }
  .demo-note { margin: 8px 0 0; padding: 12px 16px; background: var(--surface); border: 1px solid var(--border);
    border-left: 3px solid var(--accent); border-radius: 4px; font-size: 0.875rem; color: var(--text-muted); }
  .demo-note strong { color: var(--text); }
  .demo-note a { color: var(--accent); }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 16px; }
  .card { display: flex; flex-direction: column; gap: 6px; background: var(--surface); border: 1px solid var(--border);
    border-radius: 4px; padding: 18px 20px; color: var(--text); transition: border-color .12s, transform .12s; }
  .card:hover { border-color: var(--accent); text-decoration: none; transform: translateY(-1px); }
  .card-top { display: flex; justify-content: space-between; align-items: baseline; }
  .card-title { font-size: 1.125rem; font-weight: 600; }
  .card-arrow { color: var(--accent); font-family: var(--mono); }
  .card-stat { font-family: var(--mono); font-size: 0.8125rem; color: var(--accent); }
  .card-desc { font-size: 0.875rem; color: var(--text-muted); }
  @media (min-width: 980px) { .cards .card:last-child:nth-child(3n+2) { grid-column: span 2; } }
  .how { margin-top: 40px; }
  .how h3 { margin: 0 0 8px; font-size: 1.0625rem; }
  .how ol { margin: 0; padding-left: 20px; color: var(--text-muted); max-width: 80ch; }
  .how li { margin-bottom: 6px; }
  .how strong { color: var(--text); font-weight: 500; }
  .limits { margin-top: 32px; color: var(--text-muted); font-size: 0.9375rem; max-width: 80ch; }
  .limits summary { cursor: pointer; font-family: var(--mono); font-size: 0.8125rem; text-transform: uppercase; letter-spacing: 0.1em; padding: 6px 0; }
  .limits ul { padding-left: 18px; }
  .limits li { margin-bottom: 6px; }

  .subscore { grid-template-columns: 170px 1fr 100px 44px 56px; }
  .subscore-loss { white-space: nowrap; }
  .subscore-delta { font-family: var(--mono); font-size: 0.8125rem; text-align: right; min-height: 1em; }
  .delta-up { color: #3fb98a; } .delta-down { color: #ff7b72; }
  .subscore-total { background: var(--surface-alt); font-weight: 600; }
  .meter-fill { transition: width .25s ease, background .25s; }
  .sim-list { display: grid; gap: 8px; }
  .sim-row { display: grid; grid-template-columns: auto 1fr auto; gap: 14px; align-items: center; padding: 10px 14px;
    background: var(--surface-alt); border: 1px solid var(--border); border-left: 3px solid var(--sev); border-radius: 3px; cursor: pointer; }
  .sim-row:hover { border-color: var(--accent); }
  .sim-row input { width: 18px; height: 18px; accent-color: #2FD9C4; }
  .sim-row:has(input:checked) { opacity: .6; }
  .sim-row:has(input:checked) .sim-title { text-decoration: line-through; }
  .sim-title { display: block; font-size: 0.9375rem; }
  .sim-meta { font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted); }
  .sim-pts { font-family: var(--mono); font-size: 0.875rem; color: var(--text-muted); }
  .sim-extra { margin-top: 12px; }
  .derivation summary h3 { display: inline; }
  .derivation { padding: 18px 24px; }

  .toolbar { display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: center; justify-content: space-between; margin-bottom: 12px; }
  .chip-row, .toolbar-right { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .chip-btn { background: var(--surface); color: var(--text-muted); border: 1px solid var(--border); padding: 7px 12px; font-size: 0.8125rem; min-height: 36px; }
  .chip-btn[aria-pressed="true"] { color: var(--text); border-color: var(--sev, var(--accent)); box-shadow: inset 0 -2px 0 var(--sev, var(--accent)); }
  .chip-count { color: var(--text-muted); margin-left: 4px; }
  .select-wrap, .check-wrap { font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted); display: flex; align-items: center; gap: 8px; }
  select, input[type=number] { background: var(--surface-alt); color: var(--text); border: 1px solid var(--border); border-radius: 4px;
    padding: 9px 10px; font-family: var(--mono); font-size: 0.875rem; min-height: 40px; max-width: 100%; }
  .check-wrap input { width: 16px; height: 16px; accent-color: #2FD9C4; }
  .result-count { font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted); margin: 4px 0 12px; }
  .finding { padding: 0; }
  .finding > summary { list-style: none; cursor: pointer; display: grid; grid-template-columns: 74px 1fr auto; gap: 14px; align-items: center; padding: 14px 20px; }
  .finding > summary::-webkit-details-marker { display: none; }
  .finding > summary:hover { background: var(--surface-alt); }
  .finding-sev { font-family: var(--mono); font-size: 0.8125rem; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; color: var(--sev); }
  .finding-title { font-size: 1rem; font-weight: 500; }
  .finding-side { display: flex; align-items: center; gap: 12px; font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted); flex-wrap: wrap; justify-content: flex-end; }
  .finding-chev::before { content: "+"; color: var(--accent); font-size: 1.1rem; }
  .finding[open] .finding-chev::before { content: "\\2212"; }
  .finding-detail { padding: 4px 24px 20px; border-top: 1px solid var(--border); }
  .finding-ids { padding-top: 12px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .finding-detail .members { margin-top: 12px; }
  .members .locate { margin-left: auto; }
  .empty { padding: 24px; text-align: center; }
  .glossary dl { margin: 0; display: grid; grid-template-columns: 180px 1fr; gap: 8px 20px; }
  .glossary dt { font-family: var(--mono); font-size: 0.875rem; color: var(--accent); }
  .glossary dd { margin: 0; font-size: 0.9375rem; color: var(--text-muted); }

  .flow { list-style: none; margin: 0 0 20px; padding: 0; display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
  .flow li { background: var(--surface); border: 1px solid var(--border); border-top: 2px solid var(--ai); border-radius: 4px; padding: 12px 14px; display: flex; flex-direction: column; gap: 4px; }
  .flow strong { font-family: var(--mono); font-size: 0.875rem; color: var(--ai-soft); font-weight: 500; }
  .flow span { font-size: 0.8125rem; color: var(--text-muted); }
  .ai-body { max-width: 80ch; }

  .stats { grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); margin-top: 24px; }
  .stat p { margin: 6px 0 0; font-size: 0.8125rem; color: var(--text-muted); }
  .boardmap svg { display: block; width: 100%; height: auto; max-height: 560px; background: #0c1119; border: 1px solid var(--border); border-radius: 4px; }
  .layer-toggles { display: flex; flex-wrap: wrap; gap: 6px 16px; font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted); }
  .layer-toggles label { display: flex; gap: 6px; align-items: center; cursor: pointer; }
  .layer-toggles input { accent-color: #2FD9C4; width: 16px; height: 16px; }
  .outline { fill: #0f1620; stroke: #3a4656; stroke-width: 0.35; }
  .pour { fill: rgba(47,217,196,0.07); stroke: rgba(47,217,196,0.35); stroke-width: 0.2; }
  .trace { stroke-linecap: round; opacity: .9; }
  .layer-0 { stroke: #e06c75; } .layer-1 { stroke: #61afef; } .layer-2 { stroke: #c678dd; } .layer-3 { stroke: #98c379; }
  .via { fill: #0c1119; stroke: #d6c26a; stroke-width: 0.25; }
  .comp rect { fill: #1b2431; stroke: #6b7889; stroke-width: 0.2; }
  .comp.k-ic rect { fill: #243349; stroke: #8fb4e8; }
  .comp.k-conn rect { fill: #2c2a1c; stroke: #d6c26a; }
  .comp text { font-family: var(--mono); font-size: 1.25px; fill: #9fb0c4; }
  .marker { fill: var(--sev); fill-opacity: .55; stroke: var(--sev); stroke-width: 0.35; cursor: pointer; }
  .marker:hover, .marker.is-active { fill-opacity: 1; stroke: #fff; }
  .marker.is-active { stroke-width: 0.6; }
  .hide-pours .g-pours, .hide-traces .g-traces, .hide-vias .g-vias, .hide-comps .g-comps, .hide-markers .g-markers { display: none; }
  .map-legend { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-top: 12px; font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted); }
  .lg { display: inline-flex; align-items: center; gap: 6px; }
  .sw { display: inline-block; width: 18px; height: 0; border-top: 3px solid; }
  .sw.layer-0 { border-color: #e06c75; } .sw.layer-1 { border-color: #61afef; } .sw.layer-2 { border-color: #c678dd; } .sw.layer-3 { border-color: #98c379; }
  .sw-via { width: 10px; height: 10px; border: 2px solid #d6c26a; border-radius: 50%; }
  .sw-marker { width: 10px; height: 10px; border-radius: 50%; background: #f0883e; border: 0; }
  .map-detail { margin-top: 14px; padding: 12px 16px; background: var(--surface-alt); border: 1px solid var(--border); border-radius: 4px; font-size: 0.9375rem; min-height: 48px; }
  .map-detail code { margin-right: 8px; }

  .try { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: start; }
  .try .panel { margin-top: 0; }
  .field { display: grid; gap: 6px; margin-bottom: 8px; }
  .field-label { font-family: var(--mono); font-size: 0.8125rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); }
  .field select { width: 100%; }
  .fields { display: grid; gap: 12px; margin-bottom: 14px; }
  .input-row { display: flex; align-items: center; gap: 10px; }
  .input-row input[type=number] { flex: 1; min-width: 0; }
  .input-row select { flex: 1; }
  .input-row .unit { font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted); min-width: 52px; }
  .input-row input[type=checkbox] { width: 20px; height: 20px; accent-color: #2FD9C4; }
  .check-field { display: flex; align-items: center; gap: 12px; font-size: 0.9375rem; cursor: pointer; min-height: 40px; }
  .presets { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
  .presets .lbl { font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted); }
  .rule-line { margin: 0; padding-top: 12px; border-top: 1px solid var(--border); font-size: 0.8125rem; color: var(--text-muted); font-family: var(--mono); }
  .verdict { display: flex; align-items: center; gap: 12px; padding: 14px 16px; border-radius: 4px; font-weight: 600; margin-bottom: 14px; border: 1px solid; }
  .verdict .dot { width: 12px; height: 12px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
  .verdict.pass { color: #3fb98a; background: rgba(63,185,138,0.08); border-color: rgba(63,185,138,0.4); }
  .verdict.fail { color: #f0883e; background: rgba(240,136,62,0.08); border-color: rgba(240,136,62,0.4); }
  .verdict small { display: block; font-weight: 400; color: var(--text-muted); font-size: 0.8125rem; }
  .res-finding { border: 1px solid var(--border); border-left: 3px solid var(--sev); border-radius: 3px; padding: 12px 14px; margin-bottom: 10px; background: var(--surface-alt); }
  .res-finding h4 { margin: 0 0 6px; font-size: 0.9375rem; }
  .res-meta { font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted); display: flex; gap: 6px 14px; flex-wrap: wrap; margin-bottom: 6px; }
  .res-meta .sevw { color: var(--sev); text-transform: uppercase; letter-spacing: .08em; font-weight: 600; }
  .res-finding p { margin: 0 0 4px; font-size: 0.875rem; color: var(--text-muted); }
  .res-finding p strong { color: var(--text); font-weight: 500; }
  .try-actions { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; margin-top: 8px; }
  .rules-table table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
  .rules-table th { text-align: left; font-family: var(--mono); font-size: 0.8125rem; font-weight: 500; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--text-muted); padding: 6px 10px; border-bottom: 1px solid var(--border); }
  .rules-table td { padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: top; color: var(--text-muted); }
  .rules-table td:first-child { color: var(--text); }
  .test-list ul { list-style: none; padding: 0; margin: 0 0 14px; display: grid; gap: 8px; }
  .test-list li { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 8px 12px; background: var(--surface-alt); border: 1px solid var(--border); border-radius: 3px; font-size: 0.875rem; }
  abbr.term { text-decoration: underline dotted; cursor: help; }
  .site-footer { max-width: 1040px; margin: 48px auto 0; padding: 20px 24px 40px; border-top: 1px solid var(--border); font-size: 0.8125rem; color: var(--text-muted); }

  @media (max-width: 760px) {
    .topbar-inner { padding: 0 16px; }
    .page { padding: 0 16px 48px; }
    .topbar-meta { display: none; }
    .landing-link { margin-left: auto; }
    .try { grid-template-columns: 1fr; }
    .flow { grid-template-columns: 1fr 1fr; }
    .glossary dl { grid-template-columns: 1fr; gap: 2px; }
    .glossary dd { margin-bottom: 10px; }
    .finding > summary { grid-template-columns: 1fr; gap: 6px; }
    .finding-side { justify-content: flex-start; }
    .subscore { grid-template-columns: 1fr 64px 40px; }
    .subscore-delta { grid-column: 1 / -1; text-align: left; }
    .subscore-delta:empty { display: none; }
    .subscore-head { display: none; }
    .subscore .meter { grid-column: 1 / -1; grid-row: 2; }
    .toolbar-right { width: 100%; }
    .pager-next { margin-left: 0; }
    .view-pager .pager { flex: 1 1 100%; }
    .panel { padding: 16px; }
    .finding-detail { padding: 4px 16px 16px; }
  }
  @media (prefers-reduced-motion: reduce) { .meter-fill, .card { transition: none; } }
"""


def _wrap(title: str, body: str, data: dict) -> str:
    payload = json.dumps(data).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} &middot; PCBInsight demo</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 16 16%27%3E%3Crect width=%2716%27 height=%2716%27 fill=%27%230A0E14%27/%3E%3Cpath d=%27M2 8h4l2-4 2 8 2-4h2%27 stroke=%27%232FD9C4%27 fill=%27none%27 stroke-width=%271.5%27/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap">
<style>{base._CSS}{_EXTRA_CSS}</style>
<noscript><style>.view[hidden] {{ display: block; }} .view-nav, .view-pager {{ display: none; }}</style></noscript>
</head>
<body>
{body}
<script id="pcbi-data" type="application/json">{payload}</script>
<script>(function () {{ 'use strict'; {_RULES_JS}
{_JS} }})();</script>
</body>
</html>
"""


_RULES_JS = r"""
  function fnd(sub, sev, conf, title, why, fix) { return { sub: sub, sev: sev, conf: conf, title: title, why: why, fix: fix }; }
  var f2 = function (x) { return (Math.round(x * 100) / 100).toString(); };
  var EVAL = {
    trace_width: function (v, L) {
      var out = [], w = v.width;
      if (v.net === 'power' && w < L.power_min) out.push(fnd('Power', w < L.power_crit ? 'high' : 'medium', 0.65,
        'Thin power trace (' + f2(w) + ' mm)', 'A narrow power trace has higher resistance, drops voltage and heats up under load.', 'Widen the trace to at least ' + L.power_min + ' mm or use a copper pour.'));
      if (v.net === 'ground' && w < L.ground_min) out.push(fnd('Power', 'medium', 0.55,
        'Thin ground trace (' + f2(w) + ' mm)', 'A narrow ground return path adds resistance and noise to everything that shares it.', 'Widen the ground trace to at least ' + L.ground_min + ' mm or use a pour.'));
      if (w < L.fab_min) out.push(fnd('Manufacturability', 'high', 0.7,
        'Trace is ' + f2(w) + ' mm wide', 'Traces this narrow are at or beyond what many fabricators can reliably etch.', 'Widen the trace to at least ' + L.fab_min + ' mm.'));
      return out;
    },
    annular_ring: function (v, L) {
      var ring = (v.pad - v.drill) / 2;
      return ring >= L.min ? [] : [fnd('Manufacturability', 'high', 0.7, 'Via has a ' + (Math.round(ring * 1000) / 1000) + ' mm annular ring',
        'A thin annular ring can break when the drill is slightly off-centre, cutting the connection.', 'Increase the via pad diameter or reduce the drill so the ring is at least ' + L.min + ' mm.')];
    },
    long_trace: function (v, L) {
      if (v.length >= L.crit) return [fnd('Routing', 'high', 0.75, 'Long trace segment (' + f2(v.length) + ' mm)', 'Long unbroken runs add resistance and pick up more noise.', 'Reroute the net with a shorter path.')];
      if (v.length >= L.warn) return [fnd('Routing', 'medium', 0.65, 'Long trace segment (' + f2(v.length) + ' mm)', 'Long unbroken runs add resistance and pick up more noise.', 'Consider a shorter path.')];
      return [];
    },
    via_count: function (v, L) {
      var out = [];
      if (v.vias > L.max) out.push(fnd('Routing', 'medium', 0.6, 'Net uses ' + v.vias + ' vias', 'Every via adds inductance and a place for a fabrication defect.', 'Reduce layer changes on this net.'));
      if (v.clock && v.vias > L.clock_max) out.push(fnd('Signal Integrity', 'low', 0.45, 'Clock net uses ' + v.vias + ' vias', 'Vias on a clock disturb its edges and add impedance discontinuities.', 'Keep the clock on one layer where possible.'));
      return out;
    },
    segments: function (v, L) {
      return v.segments > L.max ? [fnd('Routing', 'low', 0.5, 'Net routed with ' + v.segments + ' segments', 'A net built from many small pieces is usually a messy route and harder to maintain.', 'Re-route the net with fewer, longer segments.')] : [];
    },
    acute_angle: function (v, L) {
      return v.angle < L.max ? [fnd('Routing', 'medium', 0.6, 'Acute-angle bend (' + f2(v.angle) + ' degrees)', 'Sharp bends can trap etchant during fabrication and disturb high-speed signals.', 'Use 45-degree or rounded bends.')] : [];
    },
    decoupling: function (v, L) {
      var thr = L[v.kind], out = [];
      if (v.none) out.push(fnd('Power', 'high', 0.55, 'No decoupling capacitor on this power net', 'Without a local capacitor, switching current must come from further away, raising supply noise at the chip.', 'Add a 100 nF capacitor between the supply pin and ground, close to the chip.'));
      else if (v.gap > thr) out.push(fnd('Power', 'medium', 0.5, 'Decoupling capacitor is ' + f2(v.gap) + ' mm away (limit ' + thr + ' mm)', 'A distant capacitor lengthens the current loop and loses effectiveness at high frequency.', 'Move the capacitor within ' + thr + ' mm of the chip, or add a closer one.'));
      return out;
    },
    supply_path: function (v, L) {
      return v.length >= L.max ? [fnd('Power', 'low', 0.5, 'Supply net totals ' + f2(v.length) + ' mm of trace', 'Long supply paths drop voltage and pick up noise.', 'Shorten the route or distribute power with a plane.')] : [];
    },
    diff_pair: function (v, L) {
      var out = [], diff = Math.abs(v.lenP - v.lenN);
      if (diff > L.len) out.push(fnd('Signal Integrity', 'medium', 0.6, 'Length mismatch of ' + f2(diff) + ' mm', 'Unequal lengths make the two halves of the signal arrive at different times and degrade it.', 'Add serpentine length to the shorter wire.'));
      if (v.viaP !== v.viaN) out.push(fnd('Signal Integrity', 'low', 0.4, 'Asymmetric via count (' + v.viaP + ' vs ' + v.viaN + ')', 'Different via counts make the two wires see different impedance.', 'Use the same number of vias on both wires.'));
      if (Math.abs(v.segP - v.segN) > L.seg) out.push(fnd('Signal Integrity', 'low', 0.35, 'Different segment counts (' + v.segP + ' vs ' + v.segN + ')', 'Differently shaped routes usually mean the pair is not routed together.', 'Route the pair together with matching geometry.'));
      return out;
    },
    clock_length: function (v, L) {
      return v.length >= L.max ? [fnd('Signal Integrity', 'low', 0.4, 'Clock net totals ' + f2(v.length) + ' mm', 'Long clock routes radiate noise and degrade edges.', 'Move the clock source closer to its load.')] : [];
    },
    via_density: function (v, L) {
      var area = v.w * v.h / 100, d = area > 0 ? v.vias / area : 0;
      return (v.vias > 0 && area > 0 && d >= L.max) ? [fnd('Manufacturability', 'low', 0.4, 'Via density is ' + d.toFixed(1) + ' vias/cm²', 'High via density can raise fabrication cost and reduce yield.', 'Review whether every via is needed.')] : [];
    },
    connector_edge: function (v, L) {
      return v.dist > L.max ? [fnd('Placement', 'low', 0.5, 'Connector is ' + f2(v.dist) + ' mm from the nearest board edge', 'Connectors away from the edge complicate enclosure design and cable access.', 'Move the connector to the board edge.')] : [];
    },
    crowding: function (v, L) {
      return v.gap < L.min ? [fnd('Placement', 'medium', 0.5, 'Parts are only ' + f2(v.gap) + ' mm apart', 'Parts packed this tightly are hard to assemble, probe and rework.', 'Increase the spacing.')] : [];
    },
    heat_spacing: function (v, L) {
      return v.gap < L.min ? [fnd('Thermals', 'medium', 0.4, 'Heat sources are ' + f2(v.gap) + ' mm apart', 'Hot parts close together heat each other and raise local temperature.', 'Spread the heat sources out or add copper for heat spreading.')] : [];
    }
  };
"""


_JS = r"""
  var DATA = JSON.parse(document.getElementById('pcbi-data').textContent);
  var BASE_TITLE = document.title;
  var VIEWS = ['overview', 'scores', 'findings', 'ai-review', 'board', 'try-it'];
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---------- tabs / navigation ---------- */
  function currentFromHash() {
    var h = (location.hash || '').replace('#', '');
    return VIEWS.indexOf(h) >= 0 ? h : 'overview';
  }
  function show(view, opts) {
    opts = opts || {};
    $$('.view').forEach(function (v) { v.hidden = v.getAttribute('data-view') !== view; });
    $$('.tab').forEach(function (t) {
      var on = t.getAttribute('data-go') === view;
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      if (on) { t.setAttribute('aria-current', 'page'); t.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }
      else t.removeAttribute('aria-current');
    });
    var el = $('#view-' + view);
    if (!opts.keepScroll) window.scrollTo(0, 0);
    if (el && !opts.noFocus) el.focus({ preventScroll: true });
    document.title = (view === 'overview' ? '' : $('.tab[data-go="' + view + '"]').textContent + ' · ') + BASE_TITLE;
  }
  function go(view) {
    if (location.hash === '#' + view) show(view); else location.hash = '#' + view;
  }
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-go]');
    if (!t) return;
    e.preventDefault();
    go(t.getAttribute('data-go'));
  });
  window.addEventListener('hashchange', function () { show(currentFromHash()); });
  $('.tabs').addEventListener('keydown', function (e) {
    var i = VIEWS.indexOf(currentFromHash()), n = null;
    if (e.key === 'ArrowRight') n = VIEWS[(i + 1) % VIEWS.length];
    else if (e.key === 'ArrowLeft') n = VIEWS[(i + VIEWS.length - 1) % VIEWS.length];
    else if (e.key === 'Home') n = VIEWS[0];
    else if (e.key === 'End') n = VIEWS[VIEWS.length - 1];
    if (n) { e.preventDefault(); go(n); $('.tab[data-go="' + n + '"]').focus(); }
  });
  show(currentFromHash(), { noFocus: true });

  /* ---------- scoring (mirrors backend/app/analysis/scoring.py) ---------- */
  function roundHalfEven(x) {
    var f = Math.floor(x), d = x - f;
    if (Math.abs(d - 0.5) < 1e-9) return f % 2 === 0 ? f : f + 1;
    return Math.round(x);
  }
  var fixed = {};          // group index -> true
  var extra = [];          // findings added from the checker
  function compute() {
    var totals = {};
    DATA.order.forEach(function (n) { totals[n] = 100; });
    DATA.issues.forEach(function (i) {
      if (!i.sub || fixed[i.group]) return;
      totals[i.sub] = Math.max(0, totals[i.sub] - DATA.severityPoints[i.sev] * i.conf);
    });
    extra.forEach(function (f) {
      totals[f.sub] = Math.max(0, totals[f.sub] - DATA.severityPoints[f.sev] * f.conf);
    });
    var res = {}, sum = 0;
    DATA.order.forEach(function (n) { res[n] = roundHalfEven(totals[n]); sum += res[n]; });
    return { subs: res, overall: roundHalfEven(sum / DATA.order.length) };
  }
  function colorFor(v) { return v >= 90 ? '#3fb98a' : v >= 75 ? '#e3b341' : v >= 50 ? '#f0883e' : '#ff7b72'; }
  var baseline = {};
  DATA.subscores.forEach(function (s) { baseline[s.name] = s.score; });
  var baseOverall = roundHalfEven(DATA.subscores.reduce(function (a, s) { return a + s.score; }, 0) / DATA.subscores.length);

  function paintRow(row, value, base) {
    if (!row) return;
    var unchecked = row.getAttribute('data-sub') === 'Documentation';
    row.style.setProperty('--score-color', unchecked ? '#8B96A5' : colorFor(value));
    $('.meter-fill', row).style.width = value + '%';
    $('.subscore-value', row).textContent = value;
    var d = $('.subscore-delta', row), diff = value - base;
    d.textContent = diff === 0 ? '' : (diff > 0 ? '+' : '−') + Math.abs(diff);
    d.className = 'subscore-delta' + (diff > 0 ? ' delta-up' : diff < 0 ? ' delta-down' : '');
  }
  function paintScores() {
    var r = compute();
    DATA.order.forEach(function (n) { paintRow($('.subscore[data-sub="' + n + '"]'), r.subs[n], baseline[n]); });
    paintRow($('#overall-row'), r.overall, baseOverall);
    var note = $('#sim-test-note');
    if (note) note.textContent = extra.length ? ' Includes ' + extra.length + ' finding' + (extra.length > 1 ? 's' : '') + ' you added in Try it.' : '';
    var box = $('#sim-extra');
    if (box) {
      box.hidden = !extra.length;
      box.innerHTML = extra.length ? '<p class="panel-note">Added in Try it: ' + extra.map(function (f) { return escapeHtml(f.label); }).join('; ') + '</p>' : '';
    }
  }
  $$('.sim-check').forEach(function (c) {
    c.addEventListener('change', function () { fixed[c.getAttribute('data-group')] = c.checked; paintScores(); });
  });
  $('#sim-reset').addEventListener('click', function () {
    fixed = {}; extra = []; $$('.sim-check').forEach(function (c) { c.checked = false; });
    paintScores(); renderTestList();
  });

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; });
  }

  /* ---------- findings filters ---------- */
  var sevFilter = 'all';
  function applyFilters() {
    var cat = $('#filter-cat').value, onlyUnv = $('#filter-unverified').checked, shown = 0, total = 0;
    $$('#findings-list .finding').forEach(function (f) {
      total++;
      var ok = (sevFilter === 'all' || f.getAttribute('data-sev') === sevFilter) &&
               (cat === 'all' || f.getAttribute('data-cat') === cat) &&
               (!onlyUnv || f.getAttribute('data-unverified') === '1');
      f.hidden = !ok; if (ok) shown++;
    });
    $('#result-count').textContent = 'Showing ' + shown + ' of ' + total + ' groups';
    $('#findings-empty').hidden = shown !== 0;
  }
  if ($('#filter-cat')) {
    $$('[data-filter-sev]').forEach(function (b) {
      b.addEventListener('click', function () {
        sevFilter = b.getAttribute('data-filter-sev');
        $$('[data-filter-sev]').forEach(function (x) {
          var on = x === b; x.setAttribute('aria-pressed', on ? 'true' : 'false'); x.classList.toggle('is-on', on);
        });
        applyFilters();
      });
    });
    $('#filter-cat').addEventListener('change', applyFilters);
    $('#filter-unverified').addEventListener('change', applyFilters);
    $('#expand-all').addEventListener('click', function () { $$('#findings-list .finding').forEach(function (f) { if (!f.hidden) f.open = true; }); });
    $('#collapse-all').addEventListener('click', function () { $$('#findings-list .finding').forEach(function (f) { f.open = false; }); });
    $('#filters-clear').addEventListener('click', function () {
      sevFilter = 'all'; $('#filter-cat').value = 'all'; $('#filter-unverified').checked = false;
      $$('[data-filter-sev]').forEach(function (x) { var on = x.getAttribute('data-filter-sev') === 'all'; x.setAttribute('aria-pressed', on); x.classList.toggle('is-on', on); });
      applyFilters();
    });
  }
  // clicking a subscore row jumps to findings in that area
  var catForSub = { 'Routing': ['routing'], 'Power': ['power', 'ground', 'decoupling'], 'Signal Integrity': ['signal_integrity', 'differential_pairs'], 'Manufacturability': ['manufacturability'], 'Placement': ['placement'], 'Thermals': ['thermal'] };

  /* ---------- board map ---------- */
  $$('.layer-toggles input').forEach(function (c) {
    c.addEventListener('change', function () { $('#board-svg').classList.toggle('hide-' + c.getAttribute('data-layer'), !c.checked); });
  });
  var issueIndex = {};
  $$('.finding').forEach(function (card) {
    $$('.members li', card).forEach(function (li) {
      var code = $('code', li), btn = $('[data-locate]', li), span = $('span', li);
      var id = btn && btn.getAttribute('data-locate');
      if (id) issueIndex[id] = { sev: card.getAttribute('data-sev'), text: span ? span.textContent : $('.finding-title', card).textContent, card: card };
    });
    var single = $('.finding-ids [data-locate]', card);
    if (single) { var sid = single.getAttribute('data-locate'); issueIndex[sid] = { sev: card.getAttribute('data-sev'), text: $('.finding-title', card).textContent, card: card }; }
  });
  function selectMarker(id, scroll) {
    $$('.marker').forEach(function (m) { m.classList.toggle('is-active', m.getAttribute('data-id') === id); });
    var info = issueIndex[id];
    var d = $('#map-detail');
    d.innerHTML = '<code class="issue-id">' + escapeHtml(id) + '</code> ' + (info ? escapeHtml(info.text) : '') +
      (info ? ' <button type="button" class="link-btn" data-open-finding="' + escapeHtml(id) + '">Open finding</button>' : '');
    if (scroll) { var m = $('.marker[data-id="' + id + '"]'); if (m) $('#board-svg').scrollIntoView({ block: 'center' }); }
  }
  $$('.marker').forEach(function (m) {
    m.addEventListener('click', function () { selectMarker(m.getAttribute('data-id')); });
    m.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectMarker(m.getAttribute('data-id')); } });
  });
  document.addEventListener('click', function (e) {
    var loc = e.target.closest('[data-locate]');
    if (loc) { go('board'); setTimeout(function () { selectMarker(loc.getAttribute('data-locate')); }, 30); return; }
    var op = e.target.closest('[data-open-finding]');
    if (op) {
      var info = issueIndex[op.getAttribute('data-open-finding')];
      go('findings');
      if (info) setTimeout(function () { info.card.hidden = false; info.card.open = true; info.card.scrollIntoView({ block: 'center' }); }, 30);
    }
  });

  /* ---------- rule checker ---------- */
  var P = DATA.severityPoints;
  /* rule evaluators live in _RULES_JS (see top of script) */
  var ruleSel = $('#rule-select'), current = null, values = {};
  DATA.rules.forEach(function (r) {
    var og = $$('optgroup', ruleSel).filter(function (g) { return g.label === r.sub; })[0];
    if (!og) { og = document.createElement('optgroup'); og.label = r.sub; ruleSel.appendChild(og); }
    var o = document.createElement('option'); o.value = r.id; o.textContent = r.label; og.appendChild(o);
  });
  function fillRule(rule, preset) {
    current = rule; values = {};
    $('#rule-what').textContent = rule.what;
    var box = $('#rule-fields'); box.innerHTML = '';
    rule.fields.forEach(function (f) {
      var v = preset && preset[f.key] !== undefined ? preset[f.key] : f.value;
      values[f.key] = v;
      var wrap = document.createElement('div'), id = 'f-' + f.key;
      if (f.type === 'checkbox') {
        wrap.innerHTML = '<label class="check-field"><input type="checkbox" id="' + id + '"' + (v ? ' checked' : '') + '> <span>' + escapeHtml(f.label) + '</span></label>';
        wrap.querySelector('input').addEventListener('change', function (e) { values[f.key] = e.target.checked; run(); });
      } else if (f.type === 'select') {
        wrap.innerHTML = '<label class="field"><span class="field-label">' + escapeHtml(f.label) + '</span><select id="' + id + '">' +
          f.options.map(function (o) { return '<option value="' + escapeHtml(o[0]) + '"' + (o[0] === v ? ' selected' : '') + '>' + escapeHtml(o[1]) + '</option>'; }).join('') + '</select></label>';
        wrap.querySelector('select').addEventListener('change', function (e) { values[f.key] = e.target.value; run(); });
      } else {
        wrap.innerHTML = '<label class="field"><span class="field-label">' + escapeHtml(f.label) + '</span><span class="input-row"><input type="number" inputmode="decimal" id="' + id +
          '" value="' + v + '" step="' + f.step + '"' + (f.min !== undefined ? ' min="' + f.min + '"' : '') + (f.max !== undefined ? ' max="' + f.max + '"' : '') +
          '><span class="unit">' + escapeHtml(f.unit) + '</span></span></label>';
        wrap.querySelector('input').addEventListener('input', function (e) { var n = parseFloat(e.target.value); values[f.key] = isNaN(n) ? null : n; run(); });
      }
      box.appendChild(wrap);
    });
    var pr = $('#rule-presets'); pr.innerHTML = '<span class="lbl">Try an example:</span>';
    rule.presets.forEach(function (p) {
      var b = document.createElement('button'); b.type = 'button'; b.className = 'btn-ghost'; b.textContent = p[0];
      b.addEventListener('click', function () { fillRule(rule, p[1]); });
      pr.appendChild(b);
    });
    $('#rule-line').textContent = 'Engine rule: ' + rule.rule.replace(/\{(\w+)\}/g, function (m, k) { return rule.limits[k]; });
    run();
  }
  var lastFindings = [];
  function run() {
    var res = $('#rule-result'), add = $('#rule-add');
    $('#rule-add-note').textContent = '';
    var missing = current.fields.some(function (f) { return f.type !== 'checkbox' && f.type !== 'select' && (values[f.key] === null || values[f.key] === undefined); });
    if (missing) { res.innerHTML = '<p class="muted">Enter a number in every field.</p>'; add.hidden = true; lastFindings = []; return; }
    var found = EVAL[current.id](values, current.limits);
    lastFindings = found;
    if (!found.length) {
      res.innerHTML = '<div class="verdict pass"><span class="dot"></span><span>Passes<small>The engine would not flag this. No points are deducted.</small></span></div>';
      add.hidden = true; return;
    }
    var total = found.reduce(function (a, f) { return a + P[f.sev] * f.conf; }, 0);
    res.innerHTML = '<div class="verdict fail"><span class="dot"></span><span>' + found.length + ' finding' + (found.length > 1 ? 's' : '') +
      '<small>Would cost ' + f2(total) + ' points in total</small></span></div>' +
      found.map(function (f) {
        return '<div class="res-finding" style="--sev:' + DATA.severityColors[f.sev] + '"><h4>' + escapeHtml(f.title) + '</h4>' +
          '<div class="res-meta"><span class="sevw">' + f.sev + '</span><span>' + escapeHtml(f.sub) + '</span><span>confidence ' + f.conf.toFixed(2) +
          '</span><span>&minus;' + f2(P[f.sev] * f.conf) + ' pts (' + P[f.sev] + ' &times; ' + f.conf.toFixed(2) + ')</span></div>' +
          '<p><strong>Why it matters:</strong> ' + escapeHtml(f.why) + '</p><p><strong>Fix:</strong> ' + escapeHtml(f.fix) + '</p></div>';
      }).join('');
    add.hidden = false;
  }
  ruleSel.addEventListener('change', function () {
    var r = DATA.rules.filter(function (x) { return x.id === ruleSel.value; })[0]; fillRule(r);
  });
  $('#rule-add').addEventListener('click', function () {
    lastFindings.forEach(function (f) { extra.push({ sub: f.sub, sev: f.sev, conf: f.conf, label: f.title + ' [' + f.sub + ']' }); });
    $('#rule-add-note').textContent = 'Added. See it in the Scores tab.';
    paintScores(); renderTestList();
  });
  function renderTestList() {
    var box = $('#test-list'); box.hidden = !extra.length;
    $('#test-items').innerHTML = extra.map(function (f, i) {
      return '<li><span>' + escapeHtml(f.label) + '</span><button type="button" class="link-btn" data-remove="' + i + '">Remove</button></li>';
    }).join('');
  }
  document.addEventListener('click', function (e) {
    var rm = e.target.closest('[data-remove]');
    if (rm) { extra.splice(parseInt(rm.getAttribute('data-remove'), 10), 1); paintScores(); renderTestList(); }
  });
  $('#test-clear').addEventListener('click', function () { extra = []; paintScores(); renderTestList(); });
  fillRule(DATA.rules[0]);
  paintScores();
"""
