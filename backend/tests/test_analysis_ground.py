from app.analysis import ground
from tests.factories import make_board, make_net, make_pour, make_trace


def test_fragmentation_flagged_for_multiple_ground_nets():
    board = make_board(
        nets=[
            make_net("GND", traces=[make_trace("GND", 0, 0, 5, 0, width=0.4)]),
            make_net("AGND", traces=[make_trace("AGND", 0, 0, 5, 0, width=0.4)]),
        ],
        pours=[
            make_pour("GND", "B.Cu", [(0, 0), (10, 0), (10, 10), (0, 10)]),
            make_pour("AGND", "B.Cu", [(0, 0), (10, 0), (10, 10), (0, 10)]),
        ],
    )
    issues = ground.check(board)
    assert any("separate ground-like nets" in i.summary for i in issues)


def test_missing_pour_flagged():
    net = make_net("GND", traces=[make_trace("GND", 0, 0, 5, 0, width=0.4)])
    board = make_board(nets=[net])
    issues = ground.check(board)
    assert any("No copper pour found" in i.summary for i in issues)


def test_single_ground_net_with_pour_no_issues():
    net = make_net("GND", traces=[make_trace("GND", 0, 0, 5, 0, width=0.4)])
    board = make_board(
        nets=[net],
        pours=[make_pour("GND", "B.Cu", [(0, 0), (10, 0), (10, 10), (0, 10)])],
    )
    assert ground.check(board) == []


def test_ground_islands_flagged():
    net = make_net("GND", traces=[make_trace("GND", 0, 0, 5, 0, width=0.4)])
    board = make_board(
        nets=[net],
        pours=[
            make_pour("GND", "B.Cu", [(0, 0), (10, 0), (10, 10), (0, 10)]),
            make_pour("GND", "B.Cu", [(20, 20), (30, 20), (30, 30), (20, 30)]),
        ],
    )
    issues = ground.check(board)
    assert any("split into 2 separate pours" in i.summary for i in issues)


def test_thin_ground_trace_flagged():
    net = make_net("GND", traces=[make_trace("GND", 0, 0, 5, 0, width=0.1)])
    board = make_board(
        nets=[net],
        pours=[make_pour("GND", "B.Cu", [(0, 0), (10, 0), (10, 10), (0, 10)])],
    )
    issues = ground.check(board)
    assert any("Thin ground trace" in i.summary for i in issues)
