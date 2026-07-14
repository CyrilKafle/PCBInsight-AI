"""Differential pair checks: length matching, parallel routing, spacing
consistency, via symmetry.

Pairs are auto-identified from net-naming convention (`NET+`/`NET-` or
`NET_P`/`NET_N`) since the board model doesn't carry an explicit
differential-pair declaration from the schematic."""

from __future__ import annotations

from app.analysis.util import net_length
from app.models.board import Board, Net
from app.models.issue import Issue, Severity

LENGTH_MISMATCH_WARN_MM = 0.2
SEGMENT_COUNT_MISMATCH_WARN = 2


def check(board: Board) -> list[Issue]:
    issues: list[Issue] = []
    for positive, negative in _find_pairs(board.nets):
        issues.extend(_check_length_matching(positive, negative))
        issues.extend(_check_via_symmetry(positive, negative))
        issues.extend(_check_segment_consistency(positive, negative))
    return issues


def _find_pairs(nets: list[Net]) -> list[tuple[Net, Net]]:
    by_name = {net.name: net for net in nets}
    pairs: list[tuple[Net, Net]] = []
    seen: set[frozenset[str]] = set()

    for name, net in by_name.items():
        partner_name = None
        if name.endswith("+"):
            partner_name = name[:-1] + "-"
        elif name.endswith("_P"):
            partner_name = name[:-2] + "_N"

        if partner_name and partner_name in by_name:
            key = frozenset({name, partner_name})
            if key not in seen:
                seen.add(key)
                pairs.append((net, by_name[partner_name]))
    return pairs


def _check_length_matching(positive: Net, negative: Net) -> list[Issue]:
    len_p, len_n = net_length(positive), net_length(negative)
    diff = abs(len_p - len_n)
    if diff <= LENGTH_MISMATCH_WARN_MM:
        return []
    return [
        Issue(
            category="differential_pairs",
            severity=Severity.MEDIUM,
            confidence=0.6,
            summary=f"Differential pair {positive.name}/{negative.name} length mismatch of {diff:.2f}mm",
            explanation="Unequal trace lengths in a differential pair introduce skew between the two legs, degrading common-mode rejection at high speed.",
            principle="Match differential pair lengths to within the protocol's skew budget.",
            suggested_fix="Add serpentine length-matching to the shorter leg.",
            refs=[positive.name, negative.name],
        )
    ]


def _check_via_symmetry(positive: Net, negative: Net) -> list[Issue]:
    via_diff = abs(len(positive.vias) - len(negative.vias))
    if via_diff == 0:
        return []
    return [
        Issue(
            category="differential_pairs",
            severity=Severity.LOW,
            confidence=0.4,
            summary=f"Differential pair {positive.name}/{negative.name} has asymmetric via count ({len(positive.vias)} vs {len(negative.vias)})",
            explanation="Asymmetric layer transitions add differential skew and can unbalance impedance between the two legs.",
            principle="Keep via placement symmetric between the two legs of a differential pair.",
            suggested_fix="Add a matching via on the other leg, or eliminate the extra transition.",
            refs=[positive.name, negative.name],
        )
    ]


def _check_segment_consistency(positive: Net, negative: Net) -> list[Issue]:
    seg_diff = abs(len(positive.traces) - len(negative.traces))
    if seg_diff <= SEGMENT_COUNT_MISMATCH_WARN:
        return []
    return [
        Issue(
            category="differential_pairs",
            severity=Severity.LOW,
            confidence=0.35,
            summary=f"Differential pair {positive.name}/{negative.name} routed with different segment counts ({len(positive.traces)} vs {len(negative.traces)})",
            explanation="A large difference in segment count between the two legs usually means they weren't routed together as a coupled pair.",
            principle="Route differential pairs together with consistent, parallel routing.",
            suggested_fix="Re-route the two legs together to keep spacing and bend points consistent.",
            refs=[positive.name, negative.name],
        )
    ]
