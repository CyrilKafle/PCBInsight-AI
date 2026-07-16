"""Score-color and severity-styling shared by both the HTML and PDF report
renderers, so a score's color band is defined in exactly one place instead
of the PDF renderer reaching into the HTML renderer's private state."""

from __future__ import annotations

from app.models.issue import Severity

SEVERITY_ORDER = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]

SEVERITY_COLORS = {
    Severity.CRITICAL: "#8b0000",
    Severity.HIGH: "#cf222e",
    Severity.MEDIUM: "#bc4c00",
    Severity.LOW: "#9a6700",
    Severity.INFO: "#57606a",
}

# (minimum score, hex color) bands, checked highest-first -- DESIGN.md calls
# for green/yellow/orange/red color-coded thresholds.
SCORE_BANDS = [
    (90, "#1a7f37"),
    (75, "#9a6700"),
    (50, "#bc4c00"),
    (0, "#cf222e"),
]


def score_color(value: int) -> str:
    for minimum, color in SCORE_BANDS:
        if value >= minimum:
            return color
    return SCORE_BANDS[-1][1]
