"""Phase 1: deterministic engineering-check engine.

Each module implements one check category from DESIGN.md's Engineering Check
Catalogue and exposes a `check(board) -> list[Issue]` function. This engine
must be useful and demoable with zero AI dependency — the AI layer (Phase 3)
only summarizes and narrates what this engine already found.
"""

from app.analysis import (
    decoupling,
    differential_pairs,
    ground,
    manufacturability,
    placement,
    power,
    routing,
    signal_integrity,
    thermal,
)
from app.models.board import Board
from app.models.issue import Issue

_CHECK_MODULES = (
    routing,
    power,
    ground,
    differential_pairs,
    decoupling,
    placement,
    manufacturability,
    thermal,
    signal_integrity,
)

# Short, stable prefixes for Issue.id (e.g. "PWR-004"). Assigned here, once
# per full run, rather than inside each check module, so numbering stays
# consistent regardless of which categories actually fired -- needed for
# Phase 3's issue-ID traceability (see DESIGN.md's AI Integration Architecture).
_CATEGORY_PREFIX = {
    "routing": "RTE",
    "power": "PWR",
    "ground": "GND",
    "differential_pairs": "DIFF",
    "decoupling": "DECAP",
    "placement": "PLACE",
    "manufacturability": "MFG",
    "thermal": "THERM",
    "signal_integrity": "SIG",
}


def run_all_checks(board: Board) -> list[Issue]:
    """Run every category's check(board), assign each issue a stable ID, and
    return the combined, unranked issue list. Scoring/severity-ranking is
    Phase 2's job (see scoring.py)."""
    issues: list[Issue] = []
    for module in _CHECK_MODULES:
        issues.extend(module.check(board))
    _assign_issue_ids(issues)
    return issues


def _assign_issue_ids(issues: list[Issue]) -> None:
    counters: dict[str, int] = {}
    for issue in issues:
        prefix = _CATEGORY_PREFIX.get(issue.category, issue.category.upper()[:4])
        counters[prefix] = counters.get(prefix, 0) + 1
        issue.id = f"{prefix}-{counters[prefix]:03d}"
