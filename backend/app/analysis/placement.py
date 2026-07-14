"""Placement checks: connectors far from board edge, crowded regions, large
unused board space, poor functional-block grouping, rotated components that
complicate routing."""

from __future__ import annotations

from app.analysis.util import distance
from app.models.board import Board, Component
from app.models.issue import Issue, Severity

CONNECTOR_EDGE_DISTANCE_WARN_MM = 10.0
CROWDED_DISTANCE_MM = 1.0
UNUSED_SPACE_MIN_FRACTION = 0.15
ROTATION_TOLERANCE_DEG = 0.5


def check(board: Board) -> list[Issue]:
    issues: list[Issue] = []
    issues.extend(_check_connector_edge_distance(board))
    issues.extend(_check_crowding(board))
    issues.extend(_check_unused_space(board))
    issues.extend(_check_non_orthogonal_rotation(board))
    return issues


def _distance_to_edge(component: Component, board: Board) -> float:
    x, y = component.footprint.position.x, component.footprint.position.y
    return min(
        x - board.origin.x,
        (board.origin.x + board.width_mm) - x,
        y - board.origin.y,
        (board.origin.y + board.height_mm) - y,
    )


def _check_connector_edge_distance(board: Board) -> list[Issue]:
    issues = []
    for component in board.components:
        if component.kind != "connector":
            continue
        edge_distance = _distance_to_edge(component, board)
        if edge_distance <= CONNECTOR_EDGE_DISTANCE_WARN_MM:
            continue
        issues.append(
            Issue(
                category="placement",
                severity=Severity.LOW,
                confidence=0.5,
                summary=f"Connector {component.footprint.reference} is {edge_distance:.1f}mm from the nearest board edge",
                explanation="Connectors placed away from the board edge complicate enclosure design and cable access.",
                principle="Place connectors at the board edge for mechanical/cable accessibility.",
                suggested_fix=f"Move {component.footprint.reference} closer to the nearest edge.",
                location=component.footprint.position,
                refs=[component.footprint.reference],
            )
        )
    return issues


def _check_crowding(board: Board) -> list[Issue]:
    issues = []
    seen: set[frozenset[str]] = set()
    components = board.components
    for i in range(len(components)):
        for j in range(i + 1, len(components)):
            a, b = components[i], components[j]
            gap = distance(a.footprint.position, b.footprint.position)
            if gap >= CROWDED_DISTANCE_MM:
                continue
            key = frozenset({a.footprint.reference, b.footprint.reference})
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                Issue(
                    category="placement",
                    severity=Severity.MEDIUM,
                    confidence=0.5,
                    summary=f"{a.footprint.reference} and {b.footprint.reference} are only {gap:.2f}mm apart",
                    explanation="Components placed this close together risk assembly/rework clearance violations.",
                    principle="Maintain adequate component-to-component clearance for placement and rework tooling.",
                    suggested_fix="Increase spacing between these two components.",
                    location=a.footprint.position,
                    refs=[a.footprint.reference, b.footprint.reference],
                )
            )
    return issues


def _check_unused_space(board: Board) -> list[Issue]:
    if not board.components or board.width_mm <= 0 or board.height_mm <= 0:
        return []
    xs = [c.footprint.position.x for c in board.components]
    ys = [c.footprint.position.y for c in board.components]
    bbox_area = (max(xs) - min(xs)) * (max(ys) - min(ys))
    board_area = board.width_mm * board.height_mm
    fraction = bbox_area / board_area if board_area else 0.0
    if fraction >= UNUSED_SPACE_MIN_FRACTION:
        return []
    return [
        Issue(
            category="placement",
            severity=Severity.INFO,
            confidence=0.35,
            summary=f"Components occupy only {fraction * 100:.0f}% of the board footprint area",
            explanation="A large amount of unused board area may mean the outline is bigger than necessary, adding fabrication cost.",
            principle="Right-size the board outline to the actual component footprint, unless the extra area is a deliberate keep-out/mounting margin.",
            suggested_fix="Consider shrinking the board outline, or confirm the extra area is intentional.",
        )
    ]


def _check_non_orthogonal_rotation(board: Board) -> list[Issue]:
    issues = []
    for component in board.components:
        remainder = component.footprint.rotation % 90.0
        if remainder <= ROTATION_TOLERANCE_DEG or remainder >= (90.0 - ROTATION_TOLERANCE_DEG):
            continue
        issues.append(
            Issue(
                category="placement",
                severity=Severity.LOW,
                confidence=0.3,
                summary=f"{component.footprint.reference} placed at a non-orthogonal rotation ({component.footprint.rotation:.0f}°)",
                explanation="Components rotated off a 0/90/180/270° axis complicate routing and often indicate an unintentional placement.",
                principle="Align components to orthogonal rotations unless there's a deliberate mechanical reason not to.",
                suggested_fix="Snap this component's rotation to the nearest 90° increment, or confirm it's intentional.",
                location=component.footprint.position,
                refs=[component.footprint.reference],
            )
        )
    return issues
