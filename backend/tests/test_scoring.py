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


def test_no_issues_gives_perfect_score_on_evaluated_subscores():
    result = score([])
    assert result.overall == 100
    assert result.formula_version == 2
    assert {s.category for s in result.subscores} == set(_SUBSCORE_NAMES)
    assert all(s.score == 100 for s in result.evaluated)


def test_documentation_is_not_evaluated():
    result = score([_issue("routing", Severity.CRITICAL)] * 10)
    doc = next(s for s in result.subscores if s.category == "Documentation")
    assert doc.score is None
    assert not doc.evaluated
    assert [s.category for s in result.not_evaluated] == ["Documentation"]


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


def test_overall_is_average_of_evaluated_subscores_only():
    result = score([_issue("routing", Severity.CRITICAL, confidence=1.0)])
    # Six evaluated subscores; Documentation (N/A) is not counted as 100.
    assert len(result.evaluated) == 6
    assert result.overall == round((75 + 100 * 5) / 6)  # 95.83 -> 96


def test_overall_uses_unrounded_subscores_and_rounds_once():
    # Routing 99.5, Power 99.5, Thermals 97.3, three subscores at 100.
    # Rounded once (v2):        (99.5 + 99.5 + 97.3 + 300) / 6 = 99.38 -> 99
    # Rounded twice (v1 style): (100 + 100 + 97 + 300) / 6     = 99.5  -> 100
    issues = [
        _issue("routing", Severity.INFO, confidence=0.5),
        _issue("power", Severity.INFO, confidence=0.5),
        _issue("thermal", Severity.LOW, confidence=0.9),
    ]
    result = score(issues)
    by_name = {s.category: s for s in result.evaluated}
    assert by_name["Routing"].unrounded == pytest.approx(99.5)
    assert by_name["Routing"].score == 100
    assert by_name["Thermals"].score == 97
    assert result.overall == 99
    assert round(sum(s.score for s in result.evaluated) / 6) == 100  # what rounding twice would give


def test_top_findings_lists_highest_severity_first():
    from app.analysis.scoring import top_findings

    issues = [
        _issue("routing", Severity.LOW),
        _issue("power", Severity.CRITICAL, confidence=0.9),
        _issue("thermal", Severity.HIGH),
        _issue("placement", Severity.CRITICAL, confidence=0.4),
    ]
    issues[1].id, issues[3].id = "PWR-001", "PLC-001"
    top, total = top_findings(issues)
    assert total == 2
    assert [i.id for i in top] == ["PWR-001", "PLC-001"]  # same severity, higher confidence first
    assert top_findings([]) == ([], 0)


def test_top_findings_caps_the_list_and_reports_the_total():
    from app.analysis.scoring import top_findings

    issues = [_issue("routing", Severity.HIGH) for _ in range(5)]
    top, total = top_findings(issues, limit=3)
    assert len(top) == 3 and total == 5


def test_score_without_formula_version_reads_as_v1():
    from app.models.issue import EngineeringScore

    old = EngineeringScore.model_validate({"overall": 90, "subscores": [{"category": "Routing", "score": 90}]})
    assert old.formula_version == 1
