from app.analysis import signal_integrity
from tests.factories import make_board, make_net, make_trace, make_via


def test_non_clock_net_ignored():
    net = make_net("SIG", traces=[make_trace("SIG", 0, 0, 100, 0)])
    board = make_board(nets=[net])
    assert signal_integrity.check(board) == []


def test_branch_point_flagged():
    traces = [
        make_trace("CLK", 0, 10, 10, 10),
        make_trace("CLK", 10, 10, 20, 10),
        make_trace("CLK", 10, 10, 10, 20),
    ]
    board = make_board(nets=[make_net("CLK", traces=traces)])
    issues = signal_integrity.check(board)
    assert len(issues) == 1
    assert "Branch point" in issues[0].summary


def test_sequential_path_no_branch_point():
    traces = [
        make_trace("CLK2", 0, 0, 10, 0),
        make_trace("CLK2", 10, 0, 20, 0),
    ]
    board = make_board(nets=[make_net("CLK2", traces=traces)])
    assert signal_integrity.check(board) == []


def test_excessive_vias_flagged():
    net = make_net(
        "CLK3",
        traces=[make_trace("CLK3", 0, 0, 5, 0)],
        vias=[make_via("CLK3", k, 0) for k in range(3)],
    )
    board = make_board(nets=[net])
    issues = [i for i in signal_integrity.check(board) if "vias" in i.summary]
    assert len(issues) == 1
    assert issues[0].severity.value == "low"


def test_long_clock_net_flagged():
    net = make_net("OSC1", traces=[make_trace("OSC1", 0, 0, 50, 0)])
    board = make_board(nets=[net])
    issues = [i for i in signal_integrity.check(board) if "totals" in i.summary]
    assert len(issues) == 1
