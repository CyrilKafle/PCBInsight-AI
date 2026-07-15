"""Thermal checks: high-current regulators/MOSFETs/power ICs, thermal
congestion, insufficient copper pour near power devices."""

from __future__ import annotations

from app.analysis.util import distance
from app.models.board import Board, Component, Point
from app.models.issue import Issue, Severity

POUR_PROXIMITY_MM = 5.0
CONGESTION_DISTANCE_MM = 8.0
_MOSFET_MARKERS = ("MOSFET", "FET")


def check(board: Board) -> list[Issue]:
    heat_sources = _heat_sources(board)
    issues: list[Issue] = []
    for component in heat_sources:
        issues.extend(_check_pour_proximity(component, board))
    issues.extend(_check_congestion(heat_sources))
    return issues


def _heat_sources(board: Board) -> list[Component]:
    sources = []
    for component in board.components:
        if component.kind == "regulator":
            sources.append(component)
        elif component.kind == "transistor" and any(
            marker in component.footprint.value.upper() for marker in _MOSFET_MARKERS
        ):
            sources.append(component)
    return sources


def _check_pour_proximity(component: Component, board: Board) -> list[Issue]:
    pos = component.footprint.position
    for pour in board.pours:
        if _within_proximity(pos, pour.outline, POUR_PROXIMITY_MM):
            return []
    return [
        Issue(
            category="thermal",
            severity=Severity.MEDIUM,
            confidence=0.45,
            summary=f"No copper pour near heat source {component.footprint.reference}",
            explanation=f"{component.footprint.reference} is a {component.kind} but has no copper pour within {POUR_PROXIMITY_MM:.0f}mm to spread heat away from it.",
            principle="Provide copper area near power devices to act as a heat spreader.",
            suggested_fix=f"Add or extend a copper pour near {component.footprint.reference}.",
            location=pos,
            refs=[component.footprint.reference],
        )
    ]


def _within_proximity(point: Point, outline: list[Point], tolerance_mm: float) -> bool:
    if not outline:
        return False
    xs = [p.x for p in outline]
    ys = [p.y for p in outline]
    return (
        min(xs) - tolerance_mm <= point.x <= max(xs) + tolerance_mm
        and min(ys) - tolerance_mm <= point.y <= max(ys) + tolerance_mm
    )


def _check_congestion(heat_sources: list[Component]) -> list[Issue]:
    issues = []
    seen: set[frozenset[str]] = set()
    for i in range(len(heat_sources)):
        for j in range(i + 1, len(heat_sources)):
            a, b = heat_sources[i], heat_sources[j]
            gap = distance(a.footprint.position, b.footprint.position)
            if gap >= CONGESTION_DISTANCE_MM:
                continue
            key = frozenset({a.footprint.reference, b.footprint.reference})
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                Issue(
                    category="thermal",
                    severity=Severity.MEDIUM,
                    confidence=0.4,
                    summary=f"Heat sources {a.footprint.reference} and {b.footprint.reference} are {gap:.1f}mm apart",
                    explanation="Two heat-generating components placed close together compound each other's thermal rise instead of spreading load across the board.",
                    principle="Distribute heat-generating components rather than clustering them.",
                    suggested_fix="Increase spacing between these components, or add thermal relief between them.",
                    location=a.footprint.position,
                    refs=[a.footprint.reference, b.footprint.reference],
                )
            )
    return issues
