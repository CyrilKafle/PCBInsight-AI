"""Renders the HTML design review report: score, subscores, grouped findings,
the AI narrative, and board statistics.

Self-contained single-file HTML: all CSS is inlined and the charts are native
HTML/SVG, so the report can be emailed or opened offline. The only external
request is the optional Google Fonts stylesheet, which degrades to system
fonts when offline.

The matplotlib chart renderers at the bottom are kept because pdf_report.py
reuses them to embed PNG charts in the PDF export."""

from __future__ import annotations

import base64
import io
import re
from collections import Counter
from datetime import datetime, timezone
from html import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app.analysis.scoring import deduction, severity_points, subscore_for
from app.models.board import Board
from app.models.issue import EngineeringScore, Issue, Severity, SubScore
from app.reports.theme import SEVERITY_COLORS, SEVERITY_ORDER, score_color

# The shared theme.py palette is tuned for light backgrounds (PDF, dashboard).
# This report is dark, so it uses lighter variants of the same semantics.
_DARK_SEVERITY = {
    Severity.CRITICAL: "#ff5d5d",
    Severity.HIGH: "#ff7b72",
    Severity.MEDIUM: "#f0883e",
    Severity.LOW: "#e3b341",
    Severity.INFO: "#8b96a5",
}
_CONFIDENCE_FLOOR = 0.5
_DARK_BANDS = [(90, "#3fb98a"), (75, "#e3b341"), (50, "#f0883e"), (0, "#ff7b72")]


def _dark_score_color(value: int) -> str:
    for minimum, color in _DARK_BANDS:
        if value >= minimum:
            return color
    return _DARK_BANDS[-1][1]


def render(board: Board, issues: list[Issue], score: EngineeringScore, ai_review: str | None = None) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    severity_counts = Counter(issue.severity for issue in issues)

    body = "\n".join(
        [
            _topbar(board, generated_at),
            _hero(board, issues, score, severity_counts),
            _score_section(score, issues),
            _issues_section(issues),
            _ai_review_section(ai_review),
            _board_statistics_section(board),
            _footer(),
        ]
    )
    return _wrap_document(board.name, body)


# --- header ------------------------------------------------------------------


def _topbar(board: Board, generated_at: str) -> str:
    return f"""
    <nav class="topbar">
      <span class="brand">PCBInsight<span class="brand-slash"> / </span>report</span>
      <span class="topbar-links">
        <a href="#scores">Scores</a>
        <a href="#findings">Findings</a>
        <a href="#ai-review">AI review</a>
        <a href="#board">Board</a>
      </span>
      <span class="topbar-meta">Generated {escape(generated_at)}</span>
    </nav>
    """


def _hero(board: Board, issues: list[Issue], score: EngineeringScore, severity_counts: Counter) -> str:
    color = _dark_score_color(score.overall)
    counts_line = ", ".join(
        f"{severity_counts[sev]} {sev.value}" for sev in SEVERITY_ORDER if severity_counts[sev]
    ) or "no issues found"
    facts = [
        f"{board.layer_count} layers",
        f"{board.width_mm:.0f} &times; {board.height_mm:.0f} mm",
        f"{len(board.components)} components",
        f"{len(board.nets)} nets",
    ]
    facts_html = "".join(f"<span>{fact}</span>" for fact in facts)
    tiles = "".join(_severity_tile(sev, severity_counts[sev]) for sev in SEVERITY_ORDER[:4])
    checked = [sub_.score for sub_ in score.subscores if sub_.category != "Documentation"]
    excl_note = (
        f" Excluding Documentation, which has no checks yet: {round(sum(checked) / len(checked))}."
        if checked and len(checked) < len(score.subscores)
        else ""
    )
    unverified = sum(1 for issue in issues if issue.confidence < _CONFIDENCE_FLOOR)
    unverified_cats = {issue.category.replace("_", " ") for issue in issues if issue.confidence < _CONFIDENCE_FLOOR}
    where = f" (all {next(iter(unverified_cats))})" if len(unverified_cats) == 1 else ""
    unverified_sentence = (
        f" {unverified} of {len(issues)} fall below the {_CONFIDENCE_FLOOR} confidence line{where} and need manual verification."
        if unverified
        else ""
    )
    return f"""
    <header class="hero">
      <div class="hero-main">
        <p class="eyebrow">Design review</p>
        <h1>{escape(board.name)}</h1>
        <p class="facts">{facts_html}</p>
        <p class="lead">
          {len(issues)} finding{'s' if len(issues) != 1 else ''} from the deterministic check engine
          ({escape(counts_line)}).{unverified_sentence}
          Section 01 itemizes each deduction.
        </p>
      </div>
      <div class="hero-score" style="--score-color:{color}">
        <div class="hero-score-value"><span>{score.overall}</span><small>/100</small></div>
        <div class="meter" role="meter" aria-labelledby="overall-label" aria-valuetext="{score.overall} of 100" aria-valuenow="{score.overall}" aria-valuemin="0" aria-valuemax="100"><div class="meter-fill" style="width:{score.overall}%"></div></div>
        <p class="hero-score-label" id="overall-label">Overall score</p>
        <p class="hero-score-note">Mean of seven subscores. Unverified findings are discounted by confidence, not excluded.{excl_note}</p>
      </div>
    </header>
    <div class="severity-strip">{tiles}</div>
    """


def _severity_tile(severity: Severity, count: int) -> str:
    color = _DARK_SEVERITY[severity]
    muted = " is-zero" if count == 0 else ""
    return f"""
      <div class="sev-tile{muted}" style="--sev:{color}">
        <span class="sev-count">{count}</span>
        <span class="sev-name">{escape(severity.value)}</span>
      </div>
    """


# --- scores ------------------------------------------------------------------


def _score_section(score: EngineeringScore, issues: list[Issue]) -> str:
    lost: Counter = Counter()
    for issue in issues:
        name = subscore_for(issue.category)
        if name:
            lost[name] += deduction(issue)
    rows = "\n".join(_subscore_row(s, lost[s.category]) for s in score.subscores)
    return f"""
    <section id="scores" class="block">
      <h2><span class="h-label">01</span> Engineering scores</h2>
      <div class="subscores">
        <div class="subscore subscore-head" aria-hidden="true">
          <span>Subscore</span><span></span><span class="subscore-loss">Points lost</span><span class="subscore-value">Score</span>
        </div>
        {rows}
      </div>
      {_derivation(score, issues)}
    </section>
    """


def _subscore_row(subscore: SubScore, lost: float) -> str:
    color = _dark_score_color(subscore.score)
    loss = f"&minus;{lost:.1f}" if lost else "0.0"
    unchecked = subscore.category == "Documentation"
    title = ' title="Not assessed: no checks feed this subscore yet"' if unchecked else ""
    note = '<small class="subscore-sub">no checks yet</small>' if unchecked else ""
    color = "#8B96A5" if unchecked else color
    return f"""
        <div class="subscore" style="--score-color:{color}"{title}>
          <span class="subscore-name">{escape(subscore.category)}{note}</span>
          <span class="meter" role="meter" aria-label="{escape(subscore.category)}" aria-valuetext="{subscore.score} of 100" aria-valuenow="{subscore.score}" aria-valuemin="0" aria-valuemax="100"><span class="meter-fill" style="width:{subscore.score}%"></span></span>
          <span class="subscore-loss">{loss}</span>
          <span class="subscore-value">{subscore.score}</span>
        </div>
    """


def _derivation(score: EngineeringScore, issues: list[Issue]) -> str:
    rows = []
    for group in _group_issues(sorted(issues, key=lambda i: SEVERITY_ORDER.index(i.severity))):
        first = group[0]
        subscore = subscore_for(first.category)
        if not subscore:
            continue
        points = severity_points(first.severity)
        total = sum(deduction(issue) for issue in group)
        confidences = {issue.confidence for issue in group}
        if len(confidences) == 1:
            calc = f"{points:g} &times; {first.confidence:.2f}"
            if len(group) > 1:
                calc = f"{len(group)} &times; {calc}"
        else:
            calc = "sum over findings"
        label = first.id if len(group) == 1 else f"{group[0].id} to {group[-1].id}"
        rows.append(
            f'<tr><td class="nowrap"><code>{escape(label)}</code></td><td>{escape(subscore)}</td>'
            f'<td class="num">&minus;{total:.1f}</td><td class="num">{calc}</td></tr>'
        )
    body = "\n".join(rows) or '<tr><td colspan="4" class="muted">No deductions.</td></tr>'
    scale = ", ".join(f"{sev.value} {severity_points(sev):g}" for sev in SEVERITY_ORDER)
    parts = " + ".join(str(s.score) for s in score.subscores)
    mean = sum(s.score for s in score.subscores) / len(score.subscores)
    return f"""
      <div class="derivation">
        <h3>How the score is computed</h3>
        <p class="formula"><code>subscore = 100 &minus; &Sigma; (severity points &times; confidence)</code></p>
        <p class="derivation-note">Severity points: {scale}. Overall is the plain mean of the seven rounded subscores.
        Decoupling and ground findings roll into Power. Weighting by confidence, rather than a hard cutoff, keeps
        uncertain findings from being either ignored or counted in full. The confidence values are set by hand
        per rule by the rule's author, not calibrated against labelled boards.</p>
        <div class="table-scroll" tabindex="0" role="region" aria-label="Score deductions table">
        <table>
          <thead><tr><th>Finding</th><th>Subscore</th><th class="num">Deducted</th><th class="num">Severity &times; confidence</th></tr></thead>
          <tbody>
            {body}
          </tbody>
        </table>
        </div>
        <p class="derivation-note">Each row multiplies severity points by confidence, by the number of findings in the group. Overall = ({parts}) / {len(score.subscores)} = {mean:.1f}, shown as {score.overall}.</p>
      </div>
    """


# --- findings ----------------------------------------------------------------


def _issues_section(issues: list[Issue]) -> str:
    if not issues:
        return """
        <section id="findings" class="block">
          <h2><span class="h-label">02</span> Findings</h2>
          <p class="muted">No issues found by the deterministic check engine.</p>
        </section>
        """

    ordered = sorted(issues, key=lambda issue: SEVERITY_ORDER.index(issue.severity))
    cards = "\n".join(_group_card(group) for group in _group_issues(ordered))
    return f"""
    <section id="findings" class="block">
      <h2><span class="h-label">02</span> Findings</h2>
      <p class="legend"><strong>Confidence</strong> is a fixed per-rule heuristic from 0 to 1 that estimates how likely a
      finding is to be real. It is not a statistical probability. Below {_CONFIDENCE_FLOOR}, a finding is treated as
      unverified and should be checked by hand in the CAD tool; {_CONFIDENCE_FLOOR} or above is not tagged.</p>
      <div class="findings">
        {cards}
      </div>
    </section>
    """


def _group_issues(issues: list[Issue]) -> list[list[Issue]]:
    """Group findings that share the same explanation and fix, so six copies
    of the same stub warning read as one finding listing six nets."""
    groups: dict[tuple, list[Issue]] = {}
    for issue in issues:
        key = (issue.category, issue.severity, issue.explanation, issue.principle, issue.suggested_fix)
        groups.setdefault(key, []).append(issue)
    return list(groups.values())


def _group_card(group: list[Issue]) -> str:
    first = group[0]
    color = _DARK_SEVERITY[first.severity]
    category = escape(first.category.replace("_", " "))
    confidences = sorted({issue.confidence for issue in group})
    confidence = (
        f"{confidences[0]:.2f}" if len(confidences) == 1 else f"{confidences[0]:.2f}&ndash;{confidences[-1]:.2f}"
    )

    if len(group) == 1:
        title = escape(first.summary)
        refs = "".join(f'<span class="chip">{escape(ref)}</span>' for ref in first.refs)
        refs_html = f'<p class="chips">{refs}</p>' if refs else ""
        members = ""
        id_html = f'<code class="issue-id">{escape(first.id)}</code>'
    else:
        title = f"{len(group)} &times; {escape(_group_title(first))}"
        refs_html = ""
        items = "".join(
            f'<li><code class="issue-id">{escape(issue.id)}</code>'
            f"<span>{escape(issue.summary)}</span></li>"
            for issue in group
        )
        members = f'<ul class="members">{items}</ul>'
        id_html = f'<code class="issue-id">{escape(group[0].id)} to {escape(group[-1].id)}</code>'

    unverified_tag = (
        '<span class="unverified">unverified: check by hand</span>'
        if any(issue.confidence < _CONFIDENCE_FLOOR for issue in group)
        else ""
    )
    return f"""
        <article class="finding" style="--sev:{color}">
          <div class="finding-head">
            {id_html}
            <span class="sev-tag">{escape(first.severity.value)}</span>
            <span class="finding-cat">{category}</span>
            <span class="finding-conf">confidence {confidence}</span>
            {unverified_tag}
          </div>
          <h3>{title}</h3>
          {refs_html}
          {members}
          <div class="finding-body">
            <div>
              <h4>Why it matters</h4>
              <p>{escape(first.explanation)}</p>
              <p class="principle">{escape(first.principle)}</p>
            </div>
            <div>
              <h4>Suggested fix</h4>
              <p>{escape(first.suggested_fix)}</p>
            </div>
          </div>
        </article>
    """


def _group_title(issue: Issue) -> str:
    # "Possible dangling trace end on net /USB_DP" -> "Possible dangling trace end"
    return re.split(r"\s+on net\s+", issue.summary, maxsplit=1)[0]


# --- AI review ---------------------------------------------------------------


def _ai_review_section(ai_review: str | None) -> str:
    if ai_review:
        text = ai_review.strip()
        truncated = not re.search(r"[.!?)\]*`\"']$", text)
        if truncated and "\n\n" in text:
            text = text.rsplit("\n\n", 1)[0]
        content = _markdown_to_html(text)
        if truncated:
            content += (
                '<p class="truncation-note">The model reached its output limit, so one trailing '
                "incomplete sentence is omitted. Everything above is verbatim.</p>"
            )
        note = (
            '<p class="ai-note">Written by Claude <em>over</em> the findings above and shown verbatim. It never sees '
            "raw board geometry and cannot add findings of its own. It repeats the engine's score and confidence values and adds no evidence from the board beyond them. Any general engineering background in it is the model's own.</p>"
        )
        content = note + f'<div class="ai-body">{content}</div>'
    else:
        content = '<p class="muted">No AI narrative review was generated for this report. The findings above come entirely from the deterministic check engine.</p>'
    return f"""
    <section id="ai-review" class="block ai-block">
      <h2><span class="h-label ai-label">03</span> AI review</h2>
      {content}
    </section>
    """


def _inline(text: str) -> str:
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def _markdown_to_html(text: str) -> str:
    """Tiny, safe renderer for the subset of markdown the review uses:
    headings, bullet lists, bold, inline code, paragraphs. All input is
    HTML-escaped before any tag is added."""
    out: list[str] = []
    in_list = False
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush_paragraph()
            close_list()
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        bullet = re.match(r"^[-*]\s+(.*)$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = 3 if len(heading.group(1)) <= 2 else 4
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
        elif bullet:
            flush_paragraph()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(bullet.group(1))}</li>")
        else:
            close_list()
            paragraph.append(line)
    flush_paragraph()
    close_list()
    return "\n".join(out)


# --- board stats + footer ----------------------------------------------------


def _board_statistics_section(board: Board) -> str:
    via_count = sum(len(net.vias) for net in board.nets)
    trace_count = sum(len(net.traces) for net in board.nets)
    rows = [
        ("Board", escape(board.name)),
        ("Dimensions", f"{board.width_mm:.1f} &times; {board.height_mm:.1f} mm"),
        ("Layers", str(board.layer_count)),
        ("Components", str(len(board.components))),
        ("Nets", str(len(board.nets))),
        ("Trace segments", str(trace_count)),
        ("Vias", str(via_count)),
        ("Copper pours", str(len(board.pours))),
    ]
    cells = "\n".join(
        f'<div class="stat"><dt>{label}</dt><dd>{value}</dd></div>' for label, value in rows
    )
    return f"""
    <section id="board" class="block">
      <h2><span class="h-label">04</span> Board</h2>
      <dl class="stats">
        {cells}
      </dl>
    </section>
    """


def _footer() -> str:
    return """
    <footer class="footer">
      <p class="eyebrow">Known limits</p>
      <ul>
        <li>The 0 to 100 score has no pass threshold; it summarizes deductions and is not a certification.</li>
        <li>Documentation has no checks yet, so it reads 100 by default. More generally, a subscore at 100 means no deductions were found, not that the area was validated.</li>
        <li>Dangling-end detection compares endpoints to pads, vias and traces within a position tolerance, so it can
        flag ends that are actually connected. This is why those findings carry low confidence.</li>
        <li>Manufacturability checks currently cover trace width, annular ring, and via density.
        Silkscreen-over-pad and copper-sliver detection are planned once the parser captures silkscreen text
        geometry and full pour polygon shape.</li>
      </ul>
    </footer>
    """


# --- matplotlib charts (reused by pdf_report.py) ------------------------------


def render_subscore_chart(score: EngineeringScore) -> str:
    names = [s.category for s in score.subscores]
    values = [s.score for s in score.subscores]
    colors = [score_color(v) for v in values]

    fig, ax = plt.subplots(figsize=(5.5, 3.2), dpi=150)
    ax.barh(names, values, color=colors)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Score")
    ax.set_title("Engineering Subscores")
    ax.invert_yaxis()
    fig.tight_layout()
    return _figure_to_base64(fig)


def render_severity_chart(severity_counts: Counter) -> str | None:
    present = [sev for sev in SEVERITY_ORDER if severity_counts[sev]]
    if not present:
        return None

    fig, ax = plt.subplots(figsize=(4.2, 3.2), dpi=150)
    ax.pie(
        [severity_counts[sev] for sev in present],
        labels=[sev.value.title() for sev in present],
        colors=[SEVERITY_COLORS[sev] for sev in present],
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


# --- document shell ----------------------------------------------------------

_CSS = """
  :root {
    color-scheme: dark;
    --bg: #0A0E14;
    --surface: #10151C;
    --surface-alt: #151B24;
    --border: #232B36;
    --text: #E6EDF3;
    --text-muted: #8B96A5;
    --accent: #2FD9C4;
    --accent-dim: #1B8F82;
    --ai: #8A63D2;
    --ai-soft: #b79af0;
    --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    --sans: 'IBM Plex Sans', -apple-system, 'Segoe UI', Roboto, sans-serif;
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  code { font-family: var(--mono); font-size: 0.85em; }
  .page { max-width: 1040px; margin: 0 auto; padding: 0 24px 64px; }
  .muted { color: var(--text-muted); }

  .topbar {
    display: flex; align-items: center; gap: 24px;
    padding: 16px 0; border-bottom: 1px solid var(--border);
    font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted);
  }
  .brand { color: var(--text); font-weight: 600; letter-spacing: 0.02em; }
  .brand-slash { color: var(--accent); }
  .topbar-links { display: flex; gap: 20px; margin-left: auto; }
  .topbar-links a { color: var(--text-muted); }
  .topbar-links a:hover { color: var(--accent); text-decoration: none; }

  .eyebrow {
    font-family: var(--mono); font-size: 0.8125rem; text-transform: uppercase;
    letter-spacing: 0.12em; color: var(--accent); margin: 0 0 8px;
  }

  .hero {
    display: grid; grid-template-columns: 1fr 280px; gap: 48px;
    align-items: end; padding: 56px 0 32px;
  }
  .hero h1 {
    font-family: var(--mono); font-weight: 600; font-size: clamp(1.75rem, 4vw, 2.5rem);
    letter-spacing: -0.02em; margin: 0 0 12px; word-break: break-word;
  }
  .facts { display: flex; flex-wrap: wrap; gap: 6px 20px; margin: 0 0 20px;
    font-family: var(--mono); font-size: 0.8rem; color: var(--text-muted); }
  .lead { margin: 0; max-width: 56ch; color: var(--text-muted); font-size: 1.0625rem; }
  .hero-score-value { display: flex; align-items: baseline; gap: 6px; color: var(--score-color); }
  .hero-score-value span { font-family: var(--mono); font-size: 4.5rem; font-weight: 600; line-height: 1; }
  .hero-score-value small { font-family: var(--mono); font-size: 1rem; color: var(--text-muted); }
  .hero-score-label { margin: 10px 0 0; font-family: var(--mono); font-size: 0.8125rem;
    text-transform: uppercase; letter-spacing: 0.12em; color: var(--text-muted); }

  .hero-score-note { margin: 8px 0 0; font-size: 0.8125rem; color: var(--text-muted); max-width: 30ch; }
  .meter { display: block; height: 6px; background: var(--surface-alt); border: 1px solid var(--border); border-radius: 2px; overflow: hidden; margin-top: 14px; }
  .meter-fill { display: block; height: 100%; background: var(--score-color); }

  .severity-strip { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px;
    background: var(--border); border: 1px solid var(--border); border-radius: 4px; overflow: hidden; margin-bottom: 8px; }
  .sev-tile { background: var(--surface); padding: 16px 20px; display: flex; align-items: baseline; gap: 12px;
    border-top: 2px solid var(--sev); }
  .sev-tile.is-zero { border-top-color: var(--border); }
  .sev-tile.is-zero .sev-count { color: var(--text-muted); }
  .sev-count { font-family: var(--mono); font-size: 1.75rem; font-weight: 600; }
  .sev-name { font-family: var(--mono); font-size: 0.8125rem; text-transform: uppercase;
    letter-spacing: 0.1em; color: var(--text-muted); }

  .block { padding-top: 56px; }
  h2 { display: flex; align-items: baseline; gap: 14px; margin: 0 0 24px;
    font-size: 1.5rem; font-weight: 600; letter-spacing: -0.01em; }
  .h-label { font-family: var(--mono); font-size: 0.8125rem; font-weight: 500; color: var(--accent); }
  .ai-label { color: var(--ai-soft); }

  .subscores { border: 1px solid var(--border); border-radius: 4px; background: var(--surface); }
  .subscore { display: grid; grid-template-columns: 160px 1fr 96px 40px; gap: 20px; align-items: center;
    padding: 12px 20px; border-bottom: 1px solid var(--border); }
  .subscore:last-child { border-bottom: 0; }
  .subscore .meter { margin: 0; }
  .subscore-name { font-size: 0.9375rem; text-transform: capitalize; }
  .subscore-loss { font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted); text-align: right; }
  .subscore-head { padding-top: 8px; padding-bottom: 8px; font-family: var(--mono); font-size: 0.8125rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); background: var(--surface-alt); }
  .subscore-sub { display: block; font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted); }
  .table-scroll { overflow-x: auto; }
  .table-scroll:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .derivation table { min-width: 440px; }
  .nowrap { white-space: nowrap; }
  .subscore-sub { text-transform: none; }
  .footer ul { margin: 0; padding-left: 18px; }
  .footer li { margin-bottom: 6px; }
  .subscore-value { font-family: var(--mono); font-weight: 600; text-align: right; color: var(--score-color); }

  .derivation { margin-top: 24px; background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 20px 24px; }
  .derivation h3 { margin: 0 0 10px; font-size: 1rem; }
  .formula { margin: 0 0 6px; }
  .formula code { color: var(--accent); font-size: 0.875rem; }
  .derivation-note { margin: 0 0 14px; font-size: 0.875rem; color: var(--text-muted); max-width: 76ch; }
  .derivation table { width: 100%; border-collapse: collapse; margin: 0 0 12px; font-size: 0.875rem; }
  .derivation th { text-align: left; font-family: var(--mono); font-size: 0.8125rem; font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted);
    padding: 6px 10px; border-bottom: 1px solid var(--border); }
  .derivation td { padding: 7px 10px; border-bottom: 1px solid var(--border); }
  .derivation .num { text-align: right; font-family: var(--mono); white-space: nowrap; }
  .legend { margin: -8px 0 20px; font-size: 0.875rem; color: var(--text-muted); max-width: 76ch; }
  .legend strong { color: var(--text); font-weight: 500; }
  .unverified { font-family: var(--mono); font-size: 0.8125rem; color: var(--text); border: 1px dashed var(--text-muted);
    padding: 0 7px; border-radius: 2px; }
  .findings { display: grid; gap: 16px; }
  .finding { background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--sev);
    border-radius: 4px; padding: 20px 24px; }
  .finding-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; margin-bottom: 10px;
    font-family: var(--mono); font-size: 0.8125rem; }
  .issue-id { color: var(--text); background: var(--surface-alt); border: 1px solid var(--border);
    padding: 1px 7px; border-radius: 2px; }
  .sev-tag { color: var(--sev); text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; }
  .finding-cat { color: var(--text-muted); text-transform: capitalize; }
  .finding-conf { margin-left: auto; color: var(--text-muted); }
  .finding-conf + .unverified { margin-left: 0; }
  .finding h3 { margin: 0 0 10px; font-size: 1.125rem; font-weight: 600; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 12px; }
  .chip { font-family: var(--mono); font-size: 0.8125rem; padding: 1px 8px; border: 1px solid var(--border);
    border-radius: 2px; color: var(--text-muted); }
  .members { list-style: none; margin: 0 0 16px; padding: 0; border: 1px solid var(--border); border-radius: 3px; }
  .members li { display: flex; gap: 14px; align-items: baseline; padding: 7px 12px;
    border-bottom: 1px solid var(--border); font-size: 0.875rem; }
  .members li:last-child { border-bottom: 0; }
  .members .issue-id { flex-shrink: 0; }
  .finding-body { display: grid; grid-template-columns: 3fr 2fr; gap: 32px; padding-top: 14px;
    border-top: 1px solid var(--border); }
  .finding-body h4 { margin: 0 0 6px; font-family: var(--mono); font-size: 0.8125rem; font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.12em; color: var(--text-muted); }
  .finding-body p { margin: 0 0 8px; font-size: 0.9375rem; }
  .principle { color: var(--text-muted); font-size: 0.875rem !important; font-style: italic; }

  .ai-block h2 { margin-bottom: 12px; }
  .ai-note { margin: 0 0 20px; color: var(--text-muted); font-size: 0.9375rem; max-width: 78ch; }
  .ai-body { background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--ai);
    border-radius: 4px; padding: 8px 28px 20px; }
  .ai-body h3 { font-size: 1.125rem; margin: 22px 0 8px; }
  .ai-body h4 { font-size: 0.8125rem; font-family: var(--mono); text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--ai-soft); margin: 22px 0 6px; font-weight: 500; }
  .ai-body p, .ai-body li { font-size: 0.9375rem; max-width: 78ch; }
  .ai-body ul { padding-left: 20px; margin: 6px 0 10px; }
  .ai-body code { background: var(--surface-alt); padding: 1px 5px; border-radius: 2px; }
  .truncation-note { font-family: var(--mono); font-size: 0.8125rem; color: var(--text-muted);
    border-top: 1px dashed var(--border); padding-top: 12px; margin-top: 18px; }

  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; margin: 0;
    background: var(--border); border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
  .stat { background: var(--surface); padding: 14px 18px; }
  .stat dt { font-family: var(--mono); font-size: 0.8125rem; text-transform: uppercase;
    letter-spacing: 0.12em; color: var(--text-muted); margin-bottom: 4px; }
  .stat dd { margin: 0; font-family: var(--mono); font-size: 1.0625rem; }

  .footer { margin-top: 64px; padding-top: 24px; border-top: 1px solid var(--border);
    color: var(--text-muted); font-size: 0.9375rem; max-width: 70ch; }
  .footer .eyebrow { color: var(--text-muted); }

  @media (max-width: 760px) {
    .hero { grid-template-columns: 1fr; gap: 28px; padding-top: 36px; }
    .severity-strip, .stats { grid-template-columns: repeat(2, 1fr); }
    .subscore { grid-template-columns: 1fr 64px 36px; gap: 4px 12px; }
    .subscore-head { display: none; }
    .subscore .meter { grid-column: 1 / -1; grid-row: 2; }
    .finding-body { grid-template-columns: 1fr; gap: 16px; }
    .topbar { flex-wrap: wrap; gap: 4px 16px; }
    .topbar-links { order: 3; width: 100%; margin-left: 0; overflow-x: auto; }
    .topbar-links a { padding: 12px 4px; }
    .derivation { padding: 16px; }
    .finding-conf { margin-left: 0; }
    .stat dd { white-space: nowrap; font-size: 1rem; }
    .stat dt { letter-spacing: 0.06em; }
    .sev-tile { border-top: 0; box-shadow: inset 3px 0 0 var(--sev); }
    .sev-tile.is-zero { box-shadow: inset 3px 0 0 var(--border); }
    .derivation table { min-width: 0; }
    .derivation thead { display: none; }
    .derivation tr { display: grid; grid-template-columns: 1fr auto; gap: 2px 12px; padding: 10px 0; border-bottom: 1px solid var(--border); }
    .derivation td { padding: 0; border: 0; }
    .derivation td:nth-child(1) { grid-column: 1; grid-row: 1; }
    .derivation td:nth-child(3) { grid-column: 2; grid-row: 1; }
    .derivation td:nth-child(2) { grid-column: 1; grid-row: 2; }
    .derivation td:nth-child(4) { grid-column: 2; grid-row: 2; }
    .derivation td:nth-child(2), .derivation td:nth-child(4) { color: var(--text-muted); font-size: 0.8125rem; }
    .finding-head, .sev-name, .chip, .stat dt { font-size: 0.875rem; }
    .topbar-meta { order: 4; width: 100%; margin-left: 0; }
  }
"""


def _wrap_document(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} &middot; PCB Design Review Report</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 16 16%27%3E%3Crect width=%2716%27 height=%2716%27 fill=%27%230A0E14%27/%3E%3Cpath d=%27M2 8h4l2-4 2 8 2-4h2%27 stroke=%27%232FD9C4%27 fill=%27none%27 stroke-width=%271.5%27/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap">
<style>{_CSS}</style>
</head>
<body>
  <div class="page">
    {body}
  </div>
</body>
</html>
"""
