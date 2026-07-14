from app.analysis import differential_pairs
from tests.factories import make_board, make_net, make_trace, make_via


def test_matched_pair_no_issues():
    board = make_board(
        nets=[
            make_net("USB_D+", traces=[make_trace("USB_D+", 0, 0, 10, 0)]),
            make_net("USB_D-", traces=[make_trace("USB_D-", 0, 1, 10, 1)]),
        ]
    )
    assert differential_pairs.check(board) == []


def test_length_mismatch_flagged():
    board = make_board(
        nets=[
            make_net("USB_D+", traces=[make_trace("USB_D+", 0, 0, 10, 0)]),
            make_net("USB_D-", traces=[make_trace("USB_D-", 0, 1, 10.5, 1)]),
        ]
    )
    issues = differential_pairs.check(board)
    assert any("length mismatch" in i.summary for i in issues)


def test_via_symmetry_flagged():
    board = make_board(
        nets=[
            make_net("USB_D+", traces=[make_trace("USB_D+", 0, 0, 10, 0)], vias=[make_via("USB_D+", 5, 0)]),
            make_net("USB_D-", traces=[make_trace("USB_D-", 0, 1, 10, 1)]),
        ]
    )
    issues = differential_pairs.check(board)
    assert any("asymmetric via count" in i.summary for i in issues)


def test_segment_consistency_flagged():
    positive_traces = [make_trace("D_P", k * 2, 0, k * 2 + 2, 0) for k in range(5)]
    board = make_board(
        nets=[
            make_net("D_P", traces=positive_traces),
            make_net("D_N", traces=[make_trace("D_N", 0, 1, 10, 1)]),
        ]
    )
    issues = differential_pairs.check(board)
    assert any("different segment counts" in i.summary for i in issues)


def test_unmatched_net_names_no_pair():
    board = make_board(
        nets=[
            make_net("SIG_A", traces=[make_trace("SIG_A", 0, 0, 10, 0)]),
            make_net("SIG_B", traces=[make_trace("SIG_B", 0, 1, 10.5, 1)]),
        ]
    )
    assert differential_pairs.check(board) == []
