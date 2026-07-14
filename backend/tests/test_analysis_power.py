from app.analysis import power
from tests.factories import make_board, make_net, make_pour, make_trace


def test_thin_power_trace_medium():
    net = make_net("+3V3", traces=[make_trace("+3V3", 0, 0, 5, 0, width=0.2)])
    board = make_board(nets=[net])
    issues = power.check(board)
    assert len(issues) == 1
    assert issues[0].severity.value == "medium"


def test_thin_power_trace_critical():
    net = make_net("+3V3", traces=[make_trace("+3V3", 0, 0, 5, 0, width=0.1)])
    board = make_board(nets=[net])
    issues = power.check(board)
    assert len(issues) == 1
    assert issues[0].severity.value == "high"


def test_power_trace_width_ok_no_issue():
    net = make_net("+3V3", traces=[make_trace("+3V3", 0, 0, 5, 0, width=0.4)])
    board = make_board(nets=[net])
    assert power.check(board) == []


def test_missing_plane_flagged_for_daisy_chain():
    traces = [make_trace("+5V", k, 0, k + 1, 0, width=0.4) for k in range(4)]
    board = make_board(nets=[make_net("+5V", traces=traces)])
    issues = power.check(board)
    assert any("no dedicated copper pour" in i.summary for i in issues)


def test_missing_plane_suppressed_when_pour_present():
    traces = [make_trace("+5V", k, 0, k + 1, 0, width=0.4) for k in range(4)]
    board = make_board(
        nets=[make_net("+5V", traces=traces)],
        pours=[make_pour("+5V", "B.Cu", [(0, 0), (10, 0), (10, 10), (0, 10)])],
    )
    assert power.check(board) == []


def test_long_supply_path_flagged():
    net = make_net("VIN", traces=[make_trace("VIN", 0, 0, 90, 0, width=0.4)])
    board = make_board(nets=[net])
    issues = power.check(board)
    assert len(issues) == 1
    assert issues[0].severity.value == "low"


def test_ground_net_ignored_by_power_check():
    net = make_net("GND", traces=[make_trace("GND", 0, 0, 5, 0, width=0.1)])
    board = make_board(nets=[net])
    assert power.check(board) == []
