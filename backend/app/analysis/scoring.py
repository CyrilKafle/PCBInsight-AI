"""Phase 2: aggregate Issues from every check module into an EngineeringScore.

Deliberately a transparent, explainable weighted aggregate rather than a
black-box model — the scoring method must be defensible in an interview:
each subscore starts at 100 and loses points per issue, scaled by severity
and confidence. Overall score is the plain average of the subscores.
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

# "Documentation" has no Phase 1 check category feeding it yet (no check
# module inspects silkscreen labeling, README presence, etc.) — it always
# scores 100 until a future phase adds real documentation checks. Listed
# here (not omitted) so the report always shows all seven DESIGN.md
# subscores, with this one visibly neutral rather than silently missing.
_SUBSCORE_NAMES = [
    "Routing",
    "Power",
    "Signal Integrity",
    "Manufacturability",
    "Placement",
    "Thermals",
    "Documentation",
]


def score(issues: list[Issue]) -> EngineeringScore:
    totals = {name: 100.0 for name in _SUBSCORE_NAMES}

    for issue in issues:
        subscore_name = _CATEGORY_TO_SUBSCORE.get(issue.category)
        if subscore_name is None:
            continue
        deduction = _SEVERITY_DEDUCTION[issue.severity] * issue.confidence
        totals[subscore_name] = max(0.0, totals[subscore_name] - deduction)

    subscores = [SubScore(category=name, score=round(totals[name])) for name in _SUBSCORE_NAMES]
    overall = round(sum(s.score for s in subscores) / len(subscores))
    return EngineeringScore(overall=overall, subscores=subscores)
