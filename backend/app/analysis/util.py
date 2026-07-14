"""Small helpers shared by more than one app/analysis/*.py check module —
net-name classification and geometry used across routing, power, ground,
decoupling, thermal, and signal-integrity checks."""

from __future__ import annotations

import math
import re

from app.models.board import Board, Component, Net, Point

_GROUND_MARKERS = ("GND", "AGND", "DGND", "PGND", "GROUND", "0V")
_POWER_MARKERS = ("VCC", "VDD", "VBAT", "VIN", "VBUS", "PWR", "PWR_")
_VOLTAGE_PATTERN = re.compile(r"\d+V\d*\b")  # e.g. "3V3", "1V8", "12V"
_CLOCK_MARKERS = ("CLK", "CLOCK", "SCLK", "SCK", "XTAL", "OSC")

_IC_KINDS = {"MCU", "FPGA", "IC", "regulator"}


def distance(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def points_close(a: Point, b: Point, tolerance_mm: float = 0.01) -> bool:
    return distance(a, b) <= tolerance_mm


def is_ground_net(name: str) -> bool:
    upper = name.upper()
    return any(marker in upper for marker in _GROUND_MARKERS)


def is_power_net(name: str) -> bool:
    if not name or is_ground_net(name):
        return False
    upper = name.upper()
    if any(marker in upper for marker in _POWER_MARKERS):
        return True
    return bool(_VOLTAGE_PATTERN.search(upper))


def is_clock_net(name: str) -> bool:
    upper = name.upper()
    return any(marker in upper for marker in _CLOCK_MARKERS)


def net_length(net: Net) -> float:
    return sum(distance(t.start, t.end) for t in net.traces)


def ic_components(board: Board) -> list[Component]:
    return [c for c in board.components if c.kind in _IC_KINDS]


def capacitor_components(board: Board) -> list[Component]:
    return [c for c in board.components if c.kind == "capacitor"]
