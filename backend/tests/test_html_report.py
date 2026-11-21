import pytest

from app.analysis.scoring import score as compute_score
from app.models.issue import Issue, Severity
from app.reports.html_report import render
from tests.factories import make_board


def _issue(summary: str = "Test issue", category: str = "routing", severity: Severity = Severity.HIGH) -> Issue:
    return Issue(
        category=category,
        severity=severity,
        confidence=1.0,
        summary=summary,
        explanation="Test explanation",
        principle="Test principle",
        suggested_fix="Test fix",
    )


def test_render_contains_board_name_and_score():
    board = make_board(name="my_board")
    score = compute_score([])
    html = render(board, [], score)
    assert "my_board" in html
    assert "100" in html
    assert html.startswith("<!doctype html>")


def test_render_with_issues_includes_issue_content():
    board = make_board(name="flawed_board")
    issues = [_issue(summary="Thin power trace on net +3V3")]
    score = compute_score(issues)
    html = render(board, issues, score)
    assert "Thin power trace on net +3V3" in html
    assert "Test explanation" in html
    assert "Test fix" in html
    assert "high" in html.lower()


def test_render_escapes_html_in_issue_content():
    board = make_board(name="board")
    issues = [_issue(summary="<script>alert(1)</script>")]
    score = compute_score(issues)
    html = render(board, issues, score)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_with_no_issues_shows_clean_message():
    board = make_board(name="clean_board")
    score = compute_score([])
    html = render(board, [], score)
    assert "No issues found" in html


def test_render_without_ai_review_notes_deferred():
    board = make_board(name="board")
    score = compute_score([])
    html = render(board, [], score)
    assert "No AI narrative review was generated" in html


def test_render_with_ai_review_includes_it():
    board = make_board(name="board")
    score = compute_score([])
    html = render(board, [], score, ai_review="This board looks solid overall.")
    assert "This board looks solid overall." in html


def test_render_shows_subscore_bars_and_severity_counts():
    board = make_board(name="board")
    issues = [_issue(severity=Severity.CRITICAL), _issue(severity=Severity.LOW)]
    score = compute_score(issues)
    html = render(board, issues, score)
    assert html.count('class="subscore"') == len(score.evaluated)
    assert html.count('class="subscore is-na"') == len(score.not_evaluated) == 1
    assert 'class="sev-tile"' in html


def test_render_groups_identical_findings_into_one_card():
    board = make_board(name="board")
    issues = [_issue(summary=f"Stub on net N{i}", severity=Severity.LOW) for i in range(6)]
    score = compute_score(issues)
    html = render(board, issues, score)
    assert html.count('class="finding"') == 1
    assert "6 &times;" in html
    for i in range(6):
        assert f"Stub on net N{i}" in html


def test_render_renders_ai_review_markdown_and_flags_truncation():
    board = make_board(name="board")
    score = compute_score([])
    html = render(board, [], score, ai_review="## Summary\n\n- **Bold** point\n\nEnds mid sentence and")
    assert "<h3>Summary</h3>" in html
    assert "<strong>Bold</strong>" in html
    assert "Ends mid sentence" not in html
    assert "output limit" in html


def test_render_shows_score_derivation_and_rule_weight_legend():
    board = make_board(name="board")
    issues = [_issue(summary="Thin trace", category="power", severity=Severity.MEDIUM)]
    score = compute_score(issues)
    html = render(board, issues, score)
    assert "How the score is computed" in html
    assert "&minus;8.0" in html
    assert "<strong>Rule weight</strong>" in html
    assert "not a measured" in html
    assert "rule weight 1.00" in html


def test_no_user_facing_label_calls_the_rule_weight_a_confidence():
    """Item 4: the hand-set rule weight must not be presented as a confidence
    or probability. The data field keeps its name, so only `confidence` inside
    <code> (the field name) or the legend's field mention may remain."""
    import re

    from app.reports import interactive_report as ir

    issues = [_issue(summary="Thin trace", category="power", severity=Severity.MEDIUM)]
    for html in (
        render(make_board(name="board"), issues, compute_score(issues)),
        ir.render(make_board(name="board"), issues, compute_score(issues)),
    ):
        visible = re.sub(r"<script.*?</script>|<style.*?</style>|<code>confidence</code>|the confidence field", "", html, flags=re.S)
        visible = re.sub(r"<[^>]+>", " ", visible)
        assert not re.search(r"\bconfidence\b", visible, re.I), re.findall(r".{40}confidence.{40}", visible, re.I)[:3]


def test_render_produces_valid_utf8_string_for_larger_board():
    board = make_board(name="stress_board")
    issues = [_issue(summary=f"Issue {i}", severity=Severity.MEDIUM) for i in range(20)]
    score = compute_score(issues)
    html = render(board, issues, score)
    assert html.encode("utf-8")
    for i in range(20):
        assert f"Issue {i}" in html


def test_critical_finding_is_listed_above_the_overall_score():
    critical = _issue(summary="Regulator output shorted to ground", category="power", severity=Severity.CRITICAL)
    critical.id = "PWR-001"
    minor = _issue(summary="Slightly long trace", severity=Severity.LOW)
    minor.id = "RTE-001"
    issues = [critical, minor]
    html = render(make_board(name="board"), issues, compute_score(issues))
    top = html.index("Most severe: 1 critical")
    score_value = html.index('class="hero-score-value"')
    assert top < score_value
    assert "PWR-001" in html[top:score_value]
    assert "RTE-001" not in html[top:score_value]


def test_score_states_formula_version_and_na_subscore():
    html = render(make_board(name="board"), [], compute_score([]))
    assert "formula v2" in html
    assert "Documentation is N/A" in html
