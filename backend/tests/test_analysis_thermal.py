from app.analysis import thermal
from tests.factories import make_board, make_component, make_pour


def test_regulator_without_pour_flagged():
    board = make_board(components=[make_component("U1", "LM7805", "regulator", x=10, y=10)])
    issues = thermal.check(board)
    assert any("No copper pour near heat source" in i.summary for i in issues)


def test_regulator_with_nearby_pour_no_issue():
    board = make_board(
        components=[make_component("U1", "LM7805", "regulator", x=10, y=10)],
        pours=[make_pour("GND", "B.Cu", [(5, 5), (20, 5), (20, 20), (5, 20)])],
    )
    assert thermal.check(board) == []


def test_mosfet_transistor_flagged():
    board = make_board(components=[make_component("Q1", "IRLZ44N MOSFET", "transistor", x=10, y=10)])
    issues = thermal.check(board)
    assert any("No copper pour near heat source" in i.summary for i in issues)


def test_plain_transistor_not_a_heat_source():
    board = make_board(components=[make_component("Q1", "2N2222", "transistor", x=10, y=10)])
    assert thermal.check(board) == []


def test_thermal_congestion_flagged():
    board = make_board(
        components=[
            make_component("U1", "LM7805", "regulator", x=10, y=10),
            make_component("U2", "LM7805", "regulator", x=15, y=10),
        ],
        pours=[make_pour("GND", "B.Cu", [(0, 0), (30, 0), (30, 30), (0, 30)])],
    )
    issues = [i for i in thermal.check(board) if "apart" in i.summary]
    assert len(issues) == 1
