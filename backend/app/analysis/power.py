"""Power checks: thin power traces relative to estimated current, daisy-chained
power distribution, weak power routing, poor decoupling placement, long
supply paths."""

from __future__ import annotations

from app.analysis.util import is_power_net, net_length
from app.models.board import Board, Net
from app.models.issue import Issue, Severity

MIN_POWER_TRACE_WIDTH_MM = 0.30
CRITICAL_POWER_TRACE_WIDTH_MM = 0.15
DAISY_CHAIN_SEGMENT_THRESHOLD = 3
LONG_SUPPLY_PATH_MM = 80.0


def check(board: Board) -> list[Issue]:
    issues: list[Issue] = []
    for net in board.nets:
        if not is_power_net(net.name):
            continue
        issues.extend(_check_thin_traces(net))
        issues.extend(_check_missing_plane(net, board))
        issues.extend(_check_long_supply_path(net))
    return issues


def _check_thin_traces(net: Net) -> list[Issue]:
    issues = []
    for trace in net.traces:
        if trace.width >= MIN_POWER_TRACE_WIDTH_MM:
            continue
        severity = Severity.HIGH if trace.width < CRITICAL_POWER_TRACE_WIDTH_MM else Severity.MEDIUM
        issues.append(
            Issue(
                category="power",
                severity=severity,
                confidence=0.65,
                summary=f"Thin power trace on net {net.name} ({trace.width:.2f}mm)",
                explanation=(
                    "A trace this narrow limits current-carrying capacity and increases IR "
                    "drop along the supply path, which can starve downstream components under load."
                ),
                principle="Size power trace width to the expected current, not the minimum fab rule.",
                suggested_fix=f"Widen this trace to at least {MIN_POWER_TRACE_WIDTH_MM:.2f}mm, more for high-current rails.",
                location=trace.start,
                refs=[net.name],
            )
        )
    return issues


def _check_missing_plane(net: Net, board: Board) -> list[Issue]:
    if len(net.traces) < DAISY_CHAIN_SEGMENT_THRESHOLD:
        return []
    has_pour = any(pour.net == net.name for pour in board.pours)
    if has_pour:
        return []
    return [
        Issue(
            category="power",
            severity=Severity.MEDIUM,
            confidence=0.5,
            summary=f"Power net {net.name} has no dedicated copper pour",
            explanation=(
                f"This net is routed as {len(net.traces)} discrete trace segments with no "
                "supporting plane, which looks like a daisy-chained distribution — each "
                "downstream component sees a longer, noisier supply path than the last."
            ),
            principle="Prefer a power plane/pour or star distribution over daisy-chaining.",
            suggested_fix="Add a copper pour on this net, or route as a star from the source.",
            refs=[net.name],
        )
    ]


def _check_long_supply_path(net: Net) -> list[Issue]:
    total_length = net_length(net)
    if total_length < LONG_SUPPLY_PATH_MM:
        return []
    return [
        Issue(
            category="power",
            severity=Severity.LOW,
            confidence=0.5,
            summary=f"Supply net {net.name} totals {total_length:.1f}mm of trace",
            explanation="Long cumulative supply paths increase IR drop and transient response lag.",
            principle="Keep power delivery paths short between source and load.",
            suggested_fix="Move the regulator/source closer to its loads, or add local bulk capacitance.",
            refs=[net.name],
        )
    ]
