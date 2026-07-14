from app.analysis import routing
from tests.factories import make_board, make_component, make_net, make_trace, make_via


def _matching(issues, keyword):
    return [i for i in issues if keyword in i.summary]


def test_clean_net_has_no_issues():
    board = make_board(
        components=[
            make_component("U1", "IC", "IC", x=0, y=0, pad_nets=["SIG"]),
            make_component("U2", "IC", "IC", x=5, y=0, pad_nets=["SIG"]),
        ],
        nets=[make_net("SIG", traces=[make_trace("SIG", 0, 0, 5, 0)])],
    )
    assert routing.check(board) == []


def test_long_trace_flagged_medium():
    board = make_board(
        components=[
            make_component("U1", "IC", "IC", x=0, y=0, pad_nets=["SIG2"]),
            make_component("U2", "IC", "IC", x=70, y=0, pad_nets=["SIG2"]),
        ],
        nets=[make_net("SIG2", traces=[make_trace("SIG2", 0, 0, 70, 0)])],
    )
    issues = routing.check(board)
    assert len(issues) == 1
    assert issues[0].category == "routing"
    assert issues[0].severity.value == "medium"


def test_critical_long_trace_flagged_high():
    board = make_board(
        components=[
            make_component("U1", "IC", "IC", x=0, y=0, pad_nets=["SIG3"]),
            make_component("U2", "IC", "IC", x=130, y=0, pad_nets=["SIG3"]),
        ],
        nets=[make_net("SIG3", traces=[make_trace("SIG3", 0, 0, 130, 0)])],
    )
    issues = routing.check(board)
    assert len(issues) == 1
    assert issues[0].severity.value == "high"


def test_excessive_via_count_flagged():
    net = make_net("PWR", vias=[make_via("PWR", 0, 0)] * 5)
    board = make_board(nets=[net])
    issues = routing.check(board)
    assert len(issues) == 1
    assert "5 vias" in issues[0].summary


def test_via_count_within_limit_no_issue():
    net = make_net("PWR", vias=[make_via("PWR", 0, 0)] * 4)
    board = make_board(nets=[net])
    assert routing.check(board) == []


def test_acute_angle_bend_flagged():
    traces = [
        make_trace("BEND", 0, 10, 10, 10),
        make_trace("BEND", 10, 10, 5.67, 12.5),
    ]
    board = make_board(nets=[make_net("BEND", traces=traces)])
    issues = _matching(routing.check(board), "Acute-angle")
    assert len(issues) == 1
    assert issues[0].severity.value == "medium"


def test_straight_continuation_not_flagged_acute():
    traces = [
        make_trace("STRAIGHT", 0, 0, 10, 0),
        make_trace("STRAIGHT", 10, 0, 20, 0),
    ]
    board = make_board(nets=[make_net("STRAIGHT", traces=traces)])
    assert _matching(routing.check(board), "Acute-angle") == []


def test_dangling_stub_flagged():
    board = make_board(nets=[make_net("STUB", traces=[make_trace("STUB", 0, 0, 5, 0)])])
    issues = _matching(routing.check(board), "dangling trace end")
    assert len(issues) == 2


def test_excessive_segment_count_flagged():
    traces = [make_trace("MANY", k * 10, 0, k * 10 + 1, 0) for k in range(9)]
    board = make_board(nets=[make_net("MANY", traces=traces)])
    issues = _matching(routing.check(board), "routed with 9 segments")
    assert len(issues) == 1
    assert issues[0].severity.value == "low"
