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


def run_all_checks(board: Board) -> list[Issue]:
    """Run every category's check(board) and return the combined, unranked
    issue list. Scoring/severity-ranking is Phase 2's job (see scoring.py)."""
    issues: list[Issue] = []
    for module in _CHECK_MODULES:
        issues.extend(module.check(board))
    return issues
