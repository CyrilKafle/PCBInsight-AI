from app.analysis import placement
from tests.factories import make_board, make_component


def _matching(issues, keyword):
    return [i for i in issues if keyword in i.summary]


def test_connector_far_from_edge_flagged():
    board = make_board(
        width_mm=50, height_mm=40,
        components=[make_component("J1", "USB_C", "connector", x=25, y=20)],
    )
    issues = _matching(placement.check(board), "nearest board edge")
    assert len(issues) == 1
    assert issues[0].severity.value == "low"


def test_connector_near_edge_no_edge_issue():
    board = make_board(
        width_mm=50, height_mm=40,
        components=[make_component("J1", "USB_C", "connector", x=2, y=20)],
    )
    assert _matching(placement.check(board), "nearest board edge") == []


def test_crowded_components_flagged():
    board = make_board(
        components=[
            make_component("R1", "10k", "resistor", x=10, y=10),
            make_component("R2", "10k", "resistor", x=10.5, y=10),
        ]
    )
    issues = _matching(placement.check(board), "apart")
    assert len(issues) == 1
    assert issues[0].severity.value == "medium"


def test_unused_space_flagged():
    board = make_board(
        width_mm=100, height_mm=100,
        components=[
            make_component("R1", "10k", "resistor", x=10, y=10),
            make_component("R2", "10k", "resistor", x=10.1, y=10),
        ],
    )
    issues = _matching(placement.check(board), "occupy only")
    assert len(issues) == 1


def test_non_orthogonal_rotation_flagged():
    board = make_board(components=[make_component("U1", "IC", "IC", x=10, y=10, rotation=45)])
    issues = _matching(placement.check(board), "non-orthogonal rotation")
    assert len(issues) == 1


def test_orthogonal_rotation_no_issue():
    board = make_board(components=[make_component("U1", "IC", "IC", x=10, y=10, rotation=90)])
    assert _matching(placement.check(board), "non-orthogonal rotation") == []
