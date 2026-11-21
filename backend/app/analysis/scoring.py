"""Phase 2: aggregate Issues from every check module into an EngineeringScore.

Deliberately a transparent, explainable weighted aggregate rather than a
black-box model — the scoring method must be defensible in an interview:
each subscore starts at 100 and loses points per issue, scaled by severity
and confidence. Overall score is the plain average of the evaluated subscores.

Formula version 2 (v1.1): a subscore no check feeds (Documentation today) is
N/A and excluded from the overall score, instead of counting as 100. The
overall is the mean of the unrounded subscores, rounded once.
"""

from __future__ import annotations

from app.models.issue import EngineeringScore, Issue, Severity, SubScore

_SEVERITY_DEDUCTION = {
    Severity.INFO: 1.0,
    Severity.LOW: 3.0,
    Severity.MEDIUM: 8.0,
    Severity.HIGH: 15.0,
    Severity.CRITICAL: 25.0,
}

# Every analysis/*.py check category rolls into one of these subscores.
# "ground" and "decoupling" fold into "Power" — DESIGN.md's subscore list
# doesn't carry a separate Ground row, and both are fundamentally power-
# delivery integrity concerns.
_CATEGORY_TO_SUBSCORE = {
    "routing": "Routing",
    "power": "Power",
    "ground": "Power",
    "decoupling": "Power",
    "differential_pairs": "Signal Integrity",
    "signal_integrity": "Signal Integrity",
    "manufacturability": "Manufacturability",
    "placement": "Placement",
    "thermal": "Thermals",
}

# "Documentation" has no check category feeding it yet (no check module
# inspects silkscreen labeling, README presence, etc.), so it is reported as
# N/A and left out of the overall score. Listed here (not omitted) so the
# report always shows all seven DESIGN.md subscores, with this one visibly
# not evaluated rather than silently missing or shown as a perfect 100.
_SUBSCORE_NAMES = [
    "Routing",
    "Power",
    "Signal Integrity",
    "Manufacturability",
    "Placement",
    "Thermals",
    "Documentation",
]


FORMULA_VERSION = 2

# Subscores at least one check category feeds. The rest are N/A.
EVALUATED_SUBSCORES = [name for name in _SUBSCORE_NAMES if name in set(_CATEGORY_TO_SUBSCORE.values())]

_SEVERITY_RANK = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]


def subscore_names() -> list[str]:
    """All seven subscores in display order, evaluated or not."""
    return list(_SUBSCORE_NAMES)


def subscore_for(category: str) -> str | None:
    """Name of the subscore an issue category rolls into, or None."""
    return _CATEGORY_TO_SUBSCORE.get(category)


def severity_points(severity: Severity) -> float:
    """Base points a finding of this severity takes off its subscore."""
    return _SEVERITY_DEDUCTION[severity]


def deduction(issue: Issue) -> float:
    """Points this issue takes off its subscore: severity points x confidence."""
    return severity_points(issue.severity) * issue.confidence


def score(issues: list[Issue]) -> EngineeringScore:
    totals = {name: 100.0 for name in EVALUATED_SUBSCORES}

    for issue in issues:
        subscore_name = _CATEGORY_TO_SUBSCORE.get(issue.category)
        if subscore_name is None:
            continue
        totals[subscore_name] = max(0.0, totals[subscore_name] - deduction(issue))

    # Strip float noise first (100 - 8*0.65 - ... can land on 43.4999999 instead
    # of 43.5), then round half to even. The JS simulator does the same.
    totals = {name: round(value, 6) for name, value in totals.items()}
    subscores = [
        SubScore(category=name, score=_round_score(totals[name]), unrounded=totals[name])
        if name in totals
        else SubScore(category=name, score=None)
        for name in _SUBSCORE_NAMES
    ]
    overall = _round_score(sum(totals.values()) / len(totals))
    return EngineeringScore(overall=overall, subscores=subscores, formula_version=FORMULA_VERSION)


def _round_score(value: float) -> int:
    return round(round(value, 6))


def top_findings(issues: list[Issue], limit: int = 3) -> tuple[list[Issue], int]:
    """The findings at the highest severity present, so an average can't hide
    them. Returns (up to `limit` of them, total count at that severity)."""
    if not issues:
        return [], 0
    worst = min(issues, key=lambda i: _SEVERITY_RANK.index(i.severity)).severity
    at_worst = [i for i in issues if i.severity == worst]
    at_worst.sort(key=lambda i: (-i.confidence, i.id or ""))
    return at_worst[:limit], len(at_worst)
