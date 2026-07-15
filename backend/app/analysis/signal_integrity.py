"""Signal integrity checks: high-speed net identification, clock routing
quality, stub length, branch points, unnecessary vias on critical nets."""

from __future__ import annotations

from collections import Counter

from app.analysis.util import is_clock_net, net_length
from app.models.board import Board, Net
from app.models.issue import Issue, Severity

CLOCK_VIA_WARN = 2
CLOCK_LENGTH_WARN_MM = 40.0
_ENDPOINT_ROUND_NDIGITS = 3  # round() decimal places for endpoint coincidence matching


def check(board: Board) -> list[Issue]:
    issues: list[Issue] = []
    for net in board.nets:
        if not is_clock_net(net.name):
            continue
        issues.extend(_check_branch_points(net))
        issues.extend(_check_via_count(net))
        issues.extend(_check_net_length(net))
    return issues


def _check_branch_points(net: Net) -> list[Issue]:
    endpoint_counts: Counter[tuple[float, float]] = Counter()
    for trace in net.traces:
        endpoint_counts[(round(trace.start.x, _ENDPOINT_ROUND_NDIGITS), round(trace.start.y, _ENDPOINT_ROUND_NDIGITS))] += 1
        endpoint_counts[(round(trace.end.x, _ENDPOINT_ROUND_NDIGITS), round(trace.end.y, _ENDPOINT_ROUND_NDIGITS))] += 1

    issues = []
    for (x, y), count in endpoint_counts.items():
        if count < 3:
            continue
        issues.append(
            Issue(
                category="signal_integrity",
                severity=Severity.MEDIUM,
                confidence=0.5,
                summary=f"Branch point on clock net {net.name} near ({x:.1f}, {y:.1f})",
                explanation="Branching (more than two segment ends meeting at one point) creates impedance discontinuities and reflections on a high-speed net.",
                principle="Route clock/high-speed nets point-to-point or fly-by, not as a branching tree.",
                suggested_fix="Re-route as a single path (or a deliberate fly-by topology) instead of a T-branch.",
                refs=[net.name],
            )
        )
    return issues


def _check_via_count(net: Net) -> list[Issue]:
    if len(net.vias) <= CLOCK_VIA_WARN:
        return []
    return [
        Issue(
            category="signal_integrity",
            severity=Severity.LOW,
            confidence=0.45,
            summary=f"Clock net {net.name} uses {len(net.vias)} vias",
            explanation="Each layer transition on a high-speed net adds inductance and a potential return-path discontinuity.",
            principle="Minimize layer transitions on clock/high-speed nets.",
            suggested_fix="Route this net on a single layer where possible.",
            refs=[net.name],
        )
    ]


def _check_net_length(net: Net) -> list[Issue]:
    length = net_length(net)
    if length < CLOCK_LENGTH_WARN_MM:
        return []
    return [
        Issue(
            category="signal_integrity",
            severity=Severity.LOW,
            confidence=0.4,
            summary=f"Clock net {net.name} totals {length:.1f}mm",
            explanation="A long clock trace increases propagation delay and makes the net more susceptible to noise pickup and skew against other signals.",
            principle="Keep clock/high-speed net length within the target frequency's propagation-delay budget.",
            suggested_fix="Shorten the route, or reposition the source/loads closer together.",
            refs=[net.name],
        )
    ]
