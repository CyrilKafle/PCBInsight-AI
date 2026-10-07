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
    assert html.count('class="subscore"') == len(score.subscores)
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


def test_render_shows_score_derivation_and_confidence_legend():
    board = make_board(name="board")
    issues = [_issue(summary="Thin trace", category="power", severity=Severity.MEDIUM)]
    score = compute_score(issues)
    html = render(board, issues, score)
    assert "How the score is computed" in html
    assert "&minus;8.0" in html
    assert "fixed per-rule heuristic" in html


def test_render_produces_valid_utf8_string_for_larger_board():
    board = make_board(name="stress_board")
    issues = [_issue(summary=f"Issue {i}", severity=Severity.MEDIUM) for i in range(20)]
    score = compute_score(issues)
    html = render(board, issues, score)
    assert html.encode("utf-8")
    for i in range(20):
        assert f"Issue {i}" in html
