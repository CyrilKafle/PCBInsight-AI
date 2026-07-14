"""Routing checks: unnecessarily long traces, excessive bends, acute angles,
excessive via count, inconsistent routing style, stubs/dead-ends."""

from __future__ import annotations

import math

from app.analysis.util import distance, points_close
from app.models.board import Board, Net, Point, Trace
from app.models.issue import Issue, Severity

LONG_TRACE_WARN_MM = 60.0
LONG_TRACE_CRITICAL_MM = 120.0
EXCESSIVE_VIA_COUNT = 4
MAX_REASONABLE_SEGMENTS = 8
ACUTE_ANGLE_MAX_DEG = 90.0
STUB_COMPONENT_PROXIMITY_MM = 3.0


def check(board: Board) -> list[Issue]:
    issues: list[Issue] = []
    for net in board.nets:
        issues.extend(_check_long_traces(net))
        issues.extend(_check_via_count(net))
        issues.extend(_check_segment_count(net))
        issues.extend(_check_acute_angles(net))
        issues.extend(_check_dangling_stubs(net, board))
    return issues


def _check_long_traces(net: Net) -> list[Issue]:
    issues = []
    for trace in net.traces:
        length = distance(trace.start, trace.end)
        if length >= LONG_TRACE_CRITICAL_MM:
            severity, confidence = Severity.HIGH, 0.75
        elif length >= LONG_TRACE_WARN_MM:
            severity, confidence = Severity.MEDIUM, 0.65
        else:
            continue
        issues.append(
            Issue(
                category="routing",
                severity=severity,
                confidence=confidence,
                summary=f"Long trace segment on net {net.name} ({length:.1f}mm)",
                explanation=(
                    "Long single trace runs increase resistive loss and make the net more "
                    "susceptible to noise pickup; they often indicate a routing detour around "
                    "an obstacle rather than a direct path."
                ),
                principle="Minimize trace length to reduce parasitic resistance/inductance and noise coupling.",
                suggested_fix="Reroute more directly, or reposition connected components closer together.",
                location=_midpoint(trace),
                refs=[net.name],
            )
        )
    return issues


def _check_via_count(net: Net) -> list[Issue]:
    if len(net.vias) <= EXCESSIVE_VIA_COUNT:
        return []
    return [
        Issue(
            category="routing",
            severity=Severity.MEDIUM,
            confidence=0.6,
            summary=f"Net {net.name} uses {len(net.vias)} vias",
            explanation=(
                "Each via adds inductance and a layer transition; a high via count on one net "
                "for a modest board size suggests inefficient routing."
            ),
            principle="Minimize via count on a given net to reduce parasitic inductance and cost.",
            suggested_fix="Look for a routing path that stays on fewer layers.",
            refs=[net.name],
        )
    ]


def _check_segment_count(net: Net) -> list[Issue]:
    if len(net.traces) <= MAX_REASONABLE_SEGMENTS:
        return []
    return [
        Issue(
            category="routing",
            severity=Severity.LOW,
            confidence=0.5,
            summary=f"Net {net.name} routed with {len(net.traces)} segments",
            explanation="Many short segments on one net usually indicate excessive bends.",
            principle="Prefer fewer, longer segments with clean 45°/90° bends over many short ones.",
            suggested_fix="Clean up routing to reduce the number of bend points.",
            refs=[net.name],
        )
    ]


def _check_acute_angles(net: Net) -> list[Issue]:
    issues = []
    flagged_points: set[tuple[float, float]] = set()
    traces = net.traces
    for i in range(len(traces)):
        for j in range(i + 1, len(traces)):
            shared = _shared_endpoint(traces[i], traces[j])
            if shared is None:
                continue
            angle = _bend_angle_deg(traces[i], traces[j], shared)
            if angle is None or angle >= ACUTE_ANGLE_MAX_DEG:
                continue
            key = (round(shared.x, 3), round(shared.y, 3))
            if key in flagged_points:
                continue
            flagged_points.add(key)
            issues.append(
                Issue(
                    category="routing",
                    severity=Severity.MEDIUM,
                    confidence=0.6,
                    summary=f"Acute-angle bend on net {net.name} ({angle:.0f}°)",
                    explanation=(
                        "Bends sharper than 90° can create acid traps during etching and "
                        "localized impedance discontinuities."
                    ),
                    principle="Route with 45° or 90° bends; avoid acute angles.",
                    suggested_fix="Replace the sharp bend with two 45° segments or a smoother curve.",
                    location=shared,
                    refs=[net.name],
                )
            )
    return issues


def _check_dangling_stubs(net: Net, board: Board) -> list[Issue]:
    issues = []
    endpoints: list[Point] = []
    for trace in net.traces:
        endpoints.append(trace.start)
        endpoints.append(trace.end)
    via_points = [via.position for via in net.vias]
    component_points = [
        c.footprint.position for c in board.components if net.name in c.footprint.pad_nets
    ]

    for trace in net.traces:
        for endpoint in (trace.start, trace.end):
            if _endpoint_is_terminated(endpoint, trace, net.traces, via_points, component_points):
                continue
            issues.append(
                Issue(
                    category="routing",
                    severity=Severity.LOW,
                    confidence=0.4,
                    summary=f"Possible dangling trace end on net {net.name}",
                    explanation=(
                        "This trace end doesn't connect to another trace, a via, or a component "
                        "pad on the same net within a small tolerance — it may be an unterminated stub."
                    ),
                    principle="Every trace should terminate at a pad, via, or another trace on its net.",
                    suggested_fix="Verify this endpoint actually lands on a pad; extend or remove the stub.",
                    location=endpoint,
                    refs=[net.name],
                )
            )
    return issues


def _endpoint_is_terminated(
    endpoint: Point,
    owning_trace: Trace,
    all_traces: list[Trace],
    via_points: list[Point],
    component_points: list[Point],
) -> bool:
    for other in all_traces:
        if other is owning_trace:
            continue
        if points_close(endpoint, other.start) or points_close(endpoint, other.end):
            return True
    for via_point in via_points:
        if points_close(endpoint, via_point):
            return True
    for comp_point in component_points:
        if distance(endpoint, comp_point) <= STUB_COMPONENT_PROXIMITY_MM:
            return True
    return False


def _shared_endpoint(a: Trace, b: Trace) -> Point | None:
    for pa in (a.start, a.end):
        for pb in (b.start, b.end):
            if points_close(pa, pb):
                return pa
    return None


def _bend_angle_deg(a: Trace, b: Trace, shared: Point) -> float | None:
    a_other = a.end if points_close(a.start, shared) else a.start
    b_other = b.end if points_close(b.start, shared) else b.start
    v1 = (a_other.x - shared.x, a_other.y - shared.y)
    v2 = (b_other.x - shared.x, b_other.y - shared.y)
    mag1 = math.hypot(*v1)
    mag2 = math.hypot(*v2)
    if mag1 == 0 or mag2 == 0:
        return None
    cos_angle = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (mag1 * mag2)))
    return math.degrees(math.acos(cos_angle))


def _midpoint(trace: Trace) -> Point:
    return Point(x=(trace.start.x + trace.end.x) / 2, y=(trace.start.y + trace.end.y) / 2)
