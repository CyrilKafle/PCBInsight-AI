"""Builds the compact structured digest sent to Claude: board size, layer
count, trace statistics, via count, power/ground nets, detected problems,
component summary, routing metrics, clock nets, connector locations, power
tree. This is the privacy/cost boundary -- raw geometry (trace/via
coordinates, pour polygons) never leaves the backend.

Every number in this digest is computed deterministically here or upstream
in app/analysis/*.py -- Claude never sees the board, only this summary, and
never decides what counts as a problem. See DESIGN.md's "AI Integration
Architecture (Phase 3)" section for the full rationale."""

from __future__ import annotations

from collections import Counter

from app.analysis.util import is_clock_net, is_ground_net, is_power_net, net_length
from app.models.board import Board
from app.models.issue import EngineeringScore, Issue, Severity

_SEVERITY_ORDER = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]
_HIGH_IMPACT_THRESHOLD = 90
_HIGH_IMPACT_MAX = 3

# Bump when the digest shape changes (fields added/removed/renamed) so the
# prompt in review.py and any future consumer can detect a mismatch instead
# of silently breaking.
SCHEMA_VERSION = 1


def summarize(board: Board, issues: list[Issue], score: EngineeringScore) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "overall_score": score.overall,
        "subscores": {s.category: s.score for s in score.subscores},
        "evidence": _evidence(issues, score),
        "issues": [_issue_dict(issue) for issue in issues],
        "statistics": _board_statistics(board),
    }


def _evidence(issues: list[Issue], score: EngineeringScore) -> dict:
    severity_counts = {sev.value: 0 for sev in _SEVERITY_ORDER}
    for issue in issues:
        severity_counts[issue.severity.value] += 1

    highest_impact = [
        subscore.category
        for subscore in sorted(score.subscores, key=lambda s: s.score)
        if subscore.score < _HIGH_IMPACT_THRESHOLD
    ][:_HIGH_IMPACT_MAX]

    most_common_recommendation = None
    if issues:
        counts = Counter(issue.suggested_fix for issue in issues)
        most_common_recommendation = counts.most_common(1)[0][0]

    return {
        "severity_counts": severity_counts,
        "highest_impact_categories": highest_impact,
        "most_common_recommendation": most_common_recommendation,
    }


def _issue_dict(issue: Issue) -> dict:
    return {
        "id": issue.id,
        "category": issue.category,
        "severity": issue.severity.value,
        "confidence": issue.confidence,
        "summary": issue.summary,
        "explanation": issue.explanation,
        "principle": issue.principle,
        "suggested_fix": issue.suggested_fix,
        "refs": issue.refs,
    }


def _board_statistics(board: Board) -> dict:
    traces = [trace for net in board.nets for trace in net.traces]
    via_count = sum(len(net.vias) for net in board.nets)
    total_trace_length = sum(net_length(net) for net in board.nets)
    component_kinds = Counter(component.kind for component in board.components)

    return {
        "board_name": board.name,
        "width_mm": board.width_mm,
        "height_mm": board.height_mm,
        "layer_count": board.layer_count,
        "component_count": len(board.components),
        "component_kinds": dict(component_kinds),
        "net_count": len(board.nets),
        "trace_count": len(traces),
        "total_trace_length_mm": round(total_trace_length, 2),
        "via_count": via_count,
        "pour_count": len(board.pours),
        "power_nets": sorted(net.name for net in board.nets if is_power_net(net.name)),
        "ground_nets": sorted(net.name for net in board.nets if is_ground_net(net.name)),
        "clock_nets": sorted(net.name for net in board.nets if is_clock_net(net.name)),
        "connector_refs": sorted(
            component.footprint.reference for component in board.components if component.kind == "connector"
        ),
    }
