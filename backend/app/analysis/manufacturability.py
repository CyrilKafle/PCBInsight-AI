"""Manufacturability checks: minimum trace-width violations, small annular
rings, high via density.

Scope note: DESIGN.md's catalogue also lists silkscreen-over-pad conflicts,
clipped text, and copper slivers. Those require silkscreen text geometry and
copper-polygon sliver detection that the current board model doesn't capture
(the parser only extracts refdes/value strings, not their on-board bounding
boxes or the actual pour polygon shape beyond its outline). Left as future
work rather than faked with a check that can never fire."""

from __future__ import annotations

from app.models.board import Board
from app.models.issue import Issue, Severity

MIN_TRACE_WIDTH_MM = 0.15
MIN_ANNULAR_RING_MM = 0.075
HIGH_VIA_DENSITY_PER_CM2 = 5.0


def check(board: Board) -> list[Issue]:
    issues: list[Issue] = []
    issues.extend(_check_trace_widths(board))
    issues.extend(_check_annular_rings(board))
    issues.extend(_check_via_density(board))
    return issues


def _check_trace_widths(board: Board) -> list[Issue]:
    issues = []
    for net in board.nets:
        for trace in net.traces:
            if trace.width >= MIN_TRACE_WIDTH_MM:
                continue
            issues.append(
                Issue(
                    category="manufacturability",
                    severity=Severity.HIGH,
                    confidence=0.7,
                    summary=f"Trace on net {net.name} is {trace.width:.2f}mm wide",
                    explanation=f"This is below a typical fab minimum of {MIN_TRACE_WIDTH_MM:.2f}mm, risking open circuits or yield loss.",
                    principle="Respect the fab house's minimum trace width design rule.",
                    suggested_fix=f"Widen this trace to at least {MIN_TRACE_WIDTH_MM:.2f}mm.",
                    location=trace.start,
                    refs=[net.name],
                )
            )
    return issues


def _check_annular_rings(board: Board) -> list[Issue]:
    issues = []
    for net in board.nets:
        for via in net.vias:
            ring = (via.diameter - via.drill) / 2
            if ring >= MIN_ANNULAR_RING_MM:
                continue
            issues.append(
                Issue(
                    category="manufacturability",
                    severity=Severity.HIGH,
                    confidence=0.7,
                    summary=f"Via on net {net.name} has a {ring:.3f}mm annular ring",
                    explanation=f"This is below a typical fab minimum of {MIN_ANNULAR_RING_MM:.3f}mm, risking drill breakout.",
                    principle="Keep via annular ring above the fab's minimum to avoid drill breakout.",
                    suggested_fix="Increase the via's pad diameter relative to its drill size.",
                    location=via.position,
                    refs=[net.name],
                )
            )
    return issues


def _check_via_density(board: Board) -> list[Issue]:
    total_vias = sum(len(net.vias) for net in board.nets)
    board_area_cm2 = (board.width_mm * board.height_mm) / 100.0
    if total_vias == 0 or board_area_cm2 <= 0:
        return []
    density = total_vias / board_area_cm2
    if density < HIGH_VIA_DENSITY_PER_CM2:
        return []
    return [
        Issue(
            category="manufacturability",
            severity=Severity.LOW,
            confidence=0.4,
            summary=f"Via density is {density:.1f} vias/cm²",
            explanation="High via density can raise fabrication cost and reduce yield, particularly with microvias or tight drill tolerances.",
            principle="Keep via density proportionate to what the design actually needs.",
            suggested_fix="Review whether all vias are necessary; consolidate where possible.",
        )
    ]
