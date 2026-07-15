"""Ground checks: fragmentation, poor return paths, disconnected pours,
ground islands/loops, current bottlenecks."""

from __future__ import annotations

from collections import Counter

from app.analysis.util import is_ground_net
from app.models.board import Board, Net
from app.models.issue import Issue, Severity

MIN_GROUND_TRACE_WIDTH_MM = 0.30


def check(board: Board) -> list[Issue]:
    issues: list[Issue] = []
    ground_nets = [net for net in board.nets if is_ground_net(net.name)]

    issues.extend(_check_fragmentation(ground_nets))
    issues.extend(_check_missing_pour(ground_nets, board))
    issues.extend(_check_islands(ground_nets, board))
    for net in ground_nets:
        issues.extend(_check_thin_traces(net))
    return issues


def _check_fragmentation(ground_nets: list[Net]) -> list[Issue]:
    if len(ground_nets) <= 1:
        return []
    names = ", ".join(sorted(net.name for net in ground_nets))
    return [
        Issue(
            category="ground",
            severity=Severity.MEDIUM,
            confidence=0.4,
            summary=f"{len(ground_nets)} separate ground-like nets found ({names})",
            explanation=(
                "Multiple distinct ground nets can be an intentional analog/digital split, but "
                "can also indicate fragmented return paths if they aren't deliberately isolated "
                "and stitched at a single point."
            ),
            principle="Return paths should be a single, low-impedance reference unless deliberately split.",
            suggested_fix="Confirm this split is intentional (e.g. AGND/DGND star-tied at one point).",
            refs=[net.name for net in ground_nets],
        )
    ]


def _check_missing_pour(ground_nets: list[Net], board: Board) -> list[Issue]:
    if not ground_nets:
        return []
    grounded_pour_nets = {pour.net for pour in board.pours if is_ground_net(pour.net)}
    issues = []
    for net in ground_nets:
        if net.name in grounded_pour_nets:
            continue
        issues.append(
            Issue(
                category="ground",
                severity=Severity.MEDIUM,
                confidence=0.55,
                summary=f"No copper pour found for ground net {net.name}",
                explanation=(
                    "Without a plane/pour, return current is confined to discrete traces, "
                    "increasing loop area, ground bounce, and EMI susceptibility."
                ),
                principle="Provide a low-impedance, continuous ground return plane.",
                suggested_fix="Add a ground copper pour on at least one layer.",
                refs=[net.name],
            )
        )
    return issues


def _check_islands(ground_nets: list[Net], board: Board) -> list[Issue]:
    issues = []
    pour_key_counts = Counter(
        (pour.net, pour.layer) for pour in board.pours if is_ground_net(pour.net)
    )
    for (net_name, layer), count in pour_key_counts.items():
        if count <= 1:
            continue
        issues.append(
            Issue(
                category="ground",
                severity=Severity.MEDIUM,
                confidence=0.5,
                summary=f"Ground net {net_name} split into {count} separate pours on {layer}",
                explanation="Multiple disjoint pour polygons on the same ground net/layer suggest ground islands rather than one continuous plane.",
                principle="Keep the ground plane continuous to avoid isolated islands and long return-path detours.",
                suggested_fix="Merge the pours, or add stitching vias/traces connecting the islands.",
                refs=[net_name],
            )
        )
    return issues


def _check_thin_traces(net: Net) -> list[Issue]:
    issues = []
    for trace in net.traces:
        if trace.width >= MIN_GROUND_TRACE_WIDTH_MM:
            continue
        issues.append(
            Issue(
                category="ground",
                severity=Severity.MEDIUM,
                confidence=0.55,
                summary=f"Thin ground trace on net {net.name} ({trace.width:.2f}mm)",
                explanation="A narrow ground trace is a return-current bottleneck, raising local impedance right where noise immunity matters most.",
                principle="Ground return paths should be at least as wide as the supply trace they mirror.",
                suggested_fix=f"Widen this trace to at least {MIN_GROUND_TRACE_WIDTH_MM:.2f}mm, or replace with a pour.",
                location=trace.start,
                refs=[net.name],
            )
        )
    return issues
