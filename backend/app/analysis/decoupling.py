"""Decoupling capacitor checks: auto-identify MCUs/FPGAs/ICs, measure distance
from VCC pins, judge placement quality and connection efficiency.

"Distance from VCC pins" is approximated as distance between component
centers (footprint.position), since the board model tracks per-pad net
membership but not individual pad geometry. "Connected efficiently" is
checked via pad_nets: a candidate capacitor must actually share the IC's
power net and touch a ground net, not just be physically nearby."""

from __future__ import annotations

from app.analysis.util import capacitor_components, distance, ic_components, is_ground_net, is_power_net
from app.models.board import Board, Component
from app.models.issue import Issue, Severity

_MAX_DISTANCE_MM_BY_KIND = {
    "MCU": 3.0,
    "FPGA": 2.5,
    "regulator": 5.0,
    "IC": 4.0,
}


def check(board: Board) -> list[Issue]:
    issues: list[Issue] = []
    capacitors = capacitor_components(board)

    for ic in ic_components(board):
        power_nets = [n for n in ic.footprint.pad_nets if is_power_net(n)]
        for power_net in power_nets:
            issues.extend(_check_power_net(ic, power_net, capacitors))
    return issues


def _check_power_net(ic: Component, power_net: str, capacitors: list[Component]) -> list[Issue]:
    candidates = [
        cap
        for cap in capacitors
        if power_net in cap.footprint.pad_nets
        and any(is_ground_net(n) for n in cap.footprint.pad_nets)
    ]

    if not candidates:
        return [
            Issue(
                category="decoupling",
                severity=Severity.HIGH,
                confidence=0.55,
                summary=f"No decoupling capacitor found on {ic.footprint.reference}'s {power_net} net",
                explanation=(
                    f"{ic.footprint.reference} draws power from {power_net} but no capacitor "
                    "bridges that net to ground — switching current transients will have to be "
                    "supplied from further away, increasing supply noise at the IC."
                ),
                principle="Every IC power pin needs a local decoupling capacitor bridging to ground.",
                suggested_fix=f"Add a decoupling capacitor (e.g. 100nF) between {power_net} and ground near {ic.footprint.reference}.",
                location=ic.footprint.position,
                refs=[ic.footprint.reference, power_net],
            )
        ]

    nearest = min(candidates, key=lambda cap: distance(ic.footprint.position, cap.footprint.position))
    gap = distance(ic.footprint.position, nearest.footprint.position)
    threshold = _MAX_DISTANCE_MM_BY_KIND.get(ic.kind, 4.0)
    if gap <= threshold:
        return []

    return [
        Issue(
            category="decoupling",
            severity=Severity.MEDIUM,
            confidence=0.5,
            summary=f"Decoupling capacitor {nearest.footprint.reference} is {gap:.1f}mm from {ic.footprint.reference}",
            explanation=(
                f"The nearest capacitor bridging {power_net} to ground is farther than "
                f"recommended for a {ic.kind}, lengthening the loop the transient current has "
                "to travel and reducing the capacitor's effectiveness at high frequency."
            ),
            principle="Decoupling capacitors should sit as close as possible to the pin they protect.",
            suggested_fix=f"Move {nearest.footprint.reference} within {threshold:.1f}mm of {ic.footprint.reference}, or add a closer one.",
            location=ic.footprint.position,
            refs=[ic.footprint.reference, nearest.footprint.reference, power_net],
        )
    ]
