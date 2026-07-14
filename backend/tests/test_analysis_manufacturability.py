from app.analysis import manufacturability
from tests.factories import make_board, make_net, make_trace, make_via


def test_thin_trace_flagged():
    net = make_net("SIG", traces=[make_trace("SIG", 0, 0, 5, 0, width=0.1)])
    board = make_board(nets=[net])
    issues = manufacturability.check(board)
    assert any("is 0.10mm wide" in i.summary for i in issues)
    assert all(i.severity.value == "high" for i in issues)


def test_trace_width_ok_no_issue():
    net = make_net("SIG", traces=[make_trace("SIG", 0, 0, 5, 0, width=0.2)])
    board = make_board(nets=[net])
    assert manufacturability.check(board) == []


def test_small_annular_ring_flagged():
    net = make_net("SIG", vias=[make_via("SIG", 0, 0, drill=0.28, diameter=0.3)])
    board = make_board(nets=[net])
    issues = manufacturability.check(board)
    assert any("annular ring" in i.summary for i in issues)


def test_annular_ring_ok_no_issue():
    net = make_net("SIG", vias=[make_via("SIG", 0, 0, drill=0.3, diameter=0.6)])
    board = make_board(nets=[net], width_mm=50, height_mm=40)
    assert manufacturability.check(board) == []


def test_high_via_density_flagged():
    vias = [make_via("SIG", k, 0, drill=0.3, diameter=0.6) for k in range(10)]
    net = make_net("SIG", vias=vias)
    board = make_board(nets=[net], width_mm=10, height_mm=10)
    issues = manufacturability.check(board)
    assert any("via density" in i.summary.lower() for i in issues)


def test_low_via_density_no_density_issue():
    vias = [make_via("SIG", k, 0, drill=0.3, diameter=0.6) for k in range(2)]
    net = make_net("SIG", vias=vias)
    board = make_board(nets=[net], width_mm=10, height_mm=10)
    issues = [i for i in manufacturability.check(board) if "via density" in i.summary.lower()]
    assert issues == []
