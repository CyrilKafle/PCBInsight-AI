import json

from app.ai.summarizer import summarize
from app.analysis.scoring import score as compute_score
from app.models.issue import Issue, Severity
from tests.factories import make_board, make_component, make_net, make_trace


def _issue(id_: str, category: str, severity: Severity, suggested_fix: str = "Fix it") -> Issue:
    issue = Issue(
        category=category,
        severity=severity,
        confidence=1.0,
        summary=f"{category} problem",
        explanation="explanation text",
        principle="principle text",
        suggested_fix=suggested_fix,
    )
    issue.id = id_
    return issue


def test_digest_top_level_shape():
    board = make_board()
    result = compute_score([])
    digest = summarize(board, [], result)
    assert set(digest.keys()) == {"schema_version", "overall_score", "subscores", "evidence", "issues", "statistics"}
    assert digest["schema_version"] == 1
    assert digest["overall_score"] == 100
    assert digest["subscores"]["Routing"] == 100


def test_issue_dicts_carry_id_and_no_raw_geometry():
    board = make_board()
    issues = [_issue("PWR-001", "power", Severity.HIGH)]
    result = compute_score(issues)
    digest = summarize(board, issues, result)

    issue_dict = digest["issues"][0]
    assert issue_dict["id"] == "PWR-001"
    assert issue_dict["severity"] == "high"
    assert "location" not in issue_dict
    assert "x" not in issue_dict and "y" not in issue_dict


def test_evidence_severity_counts():
    board = make_board()
    issues = [_issue("PWR-001", "power", Severity.CRITICAL), _issue("PWR-002", "power", Severity.LOW)]
    result = compute_score(issues)
    digest = summarize(board, issues, result)

    assert digest["evidence"]["severity_counts"] == {
        "critical": 1,
        "high": 0,
        "medium": 0,
        "low": 1,
        "info": 0,
    }


def test_evidence_highest_impact_categories():
    board = make_board()
    issues = [_issue(f"PWR-{k:03d}", "power", Severity.CRITICAL) for k in range(1, 4)]
    result = compute_score(issues)
    digest = summarize(board, issues, result)
    assert "Power" in digest["evidence"]["highest_impact_categories"]


def test_evidence_no_issues_gives_neutral_evidence():
    board = make_board()
    result = compute_score([])
    digest = summarize(board, [], result)
    assert digest["evidence"]["highest_impact_categories"] == []
    assert digest["evidence"]["most_common_recommendation"] is None


def test_evidence_most_common_recommendation():
    board = make_board()
    issues = [
        _issue("PWR-001", "power", Severity.MEDIUM, suggested_fix="Widen the trace"),
        _issue("PWR-002", "power", Severity.MEDIUM, suggested_fix="Widen the trace"),
        _issue("GND-001", "ground", Severity.LOW, suggested_fix="Add a pour"),
    ]
    result = compute_score(issues)
    digest = summarize(board, issues, result)
    assert digest["evidence"]["most_common_recommendation"] == "Widen the trace"


def test_statistics_net_classification_and_counts():
    board = make_board(
        components=[
            make_component("U1", "ATmega328P", "MCU", x=0, y=0, pad_nets=["+3V3", "GND"]),
            make_component("J1", "USB_C", "connector", x=45, y=20),
        ],
        nets=[
            make_net("+3V3", traces=[make_trace("+3V3", 0, 0, 5, 0)]),
            make_net("GND", traces=[make_trace("GND", 0, 0, 5, 0)]),
            make_net("SCLK", traces=[make_trace("SCLK", 0, 0, 5, 0)]),
        ],
    )
    result = compute_score([])
    digest = summarize(board, [], result)
    stats = digest["statistics"]

    assert stats["component_count"] == 2
    assert stats["net_count"] == 3
    assert stats["power_nets"] == ["+3V3"]
    assert stats["ground_nets"] == ["GND"]
    assert stats["connector_refs"] == ["J1"]
    assert stats["component_kinds"] == {"MCU": 1, "connector": 1}


def test_digest_is_json_serializable():
    board = make_board(components=[make_component("U1", "LM7805", "regulator", x=10, y=10)])
    issues = [_issue("THERM-001", "thermal", Severity.MEDIUM)]
    result = compute_score(issues)
    digest = summarize(board, issues, result)
    assert json.dumps(digest)
