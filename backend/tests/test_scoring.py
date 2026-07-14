import pytest

from app.analysis.scoring import score
from app.models.issue import Issue, Severity

_SUBSCORE_NAMES = [
    "Routing",
    "Power",
    "Signal Integrity",
    "Manufacturability",
    "Placement",
    "Thermals",
    "Documentation",
]


def _issue(category: str, severity: Severity, confidence: float = 1.0) -> Issue:
    return Issue(
        category=category,
        severity=severity,
        confidence=confidence,
        summary="test issue",
        explanation="test explanation",
        principle="test principle",
        suggested_fix="test fix",
    )


def test_no_issues_gives_perfect_score():
    result = score([])
    assert result.overall == 100
    assert {s.category for s in result.subscores} == set(_SUBSCORE_NAMES)
    assert all(s.score == 100 for s in result.subscores)


def test_documentation_always_100():
    result = score([_issue("routing", Severity.CRITICAL)] * 10)
    doc = next(s for s in result.subscores if s.category == "Documentation")
    assert doc.score == 100


def test_deduction_scaled_by_severity_and_confidence():
    result = score([_issue("routing", Severity.MEDIUM, confidence=0.5)])
    routing = next(s for s in result.subscores if s.category == "Routing")
    assert routing.score == 96  # 100 - (8 * 0.5) = 96


def test_score_floors_at_zero():
    result = score([_issue("routing", Severity.CRITICAL, confidence=1.0)] * 10)
    routing = next(s for s in result.subscores if s.category == "Routing")
    assert routing.score == 0


def test_ground_and_decoupling_roll_into_power():
    result = score([_issue("ground", Severity.HIGH), _issue("decoupling", Severity.HIGH)])
    power = next(s for s in result.subscores if s.category == "Power")
    assert power.score == pytest.approx(100 - 15 - 15)


def test_diff_pairs_and_signal_integrity_share_subscore():
    result = score([_issue("differential_pairs", Severity.MEDIUM), _issue("signal_integrity", Severity.MEDIUM)])
    si = next(s for s in result.subscores if s.category == "Signal Integrity")
    assert si.score == pytest.approx(100 - 8 - 8)


def test_overall_is_average_of_subscores():
    result = score([_issue("routing", Severity.CRITICAL, confidence=1.0)])
    expected = round((75 + 100 * 6) / 7)
    assert result.overall == expected
