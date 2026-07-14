from app.analysis import decoupling
from tests.factories import make_board, make_component


def test_no_ics_no_issues():
    board = make_board(components=[make_component("R1", "10k", "resistor", x=0, y=0)])
    assert decoupling.check(board) == []


def test_ic_with_no_capacitor_flagged_high():
    ic = make_component("U1", "ATmega328P", "MCU", x=0, y=0, pad_nets=["+3V3", "GND"])
    board = make_board(components=[ic])
    issues = decoupling.check(board)
    assert len(issues) == 1
    assert issues[0].severity.value == "high"
    assert "No decoupling capacitor" in issues[0].summary


def test_ic_with_far_capacitor_flagged_medium():
    ic = make_component("U1", "ATmega328P", "MCU", x=0, y=0, pad_nets=["+3V3", "GND"])
    cap = make_component("C1", "100nF", "capacitor", x=10, y=0, pad_nets=["+3V3", "GND"])
    board = make_board(components=[ic, cap])
    issues = decoupling.check(board)
    assert len(issues) == 1
    assert issues[0].severity.value == "medium"
    assert "10.0mm" in issues[0].summary


def test_ic_with_close_capacitor_no_issue():
    ic = make_component("U1", "ATmega328P", "MCU", x=0, y=0, pad_nets=["+3V3", "GND"])
    cap = make_component("C1", "100nF", "capacitor", x=1, y=0, pad_nets=["+3V3", "GND"])
    board = make_board(components=[ic, cap])
    assert decoupling.check(board) == []


def test_capacitor_without_ground_leg_not_counted():
    ic = make_component("U1", "ATmega328P", "MCU", x=0, y=0, pad_nets=["+3V3", "GND"])
    cap = make_component("C1", "100nF", "capacitor", x=1, y=0, pad_nets=["+3V3"])
    board = make_board(components=[ic, cap])
    issues = decoupling.check(board)
    assert len(issues) == 1
    assert "No decoupling capacitor" in issues[0].summary


def test_ic_with_no_power_pad_nets_no_issue():
    ic = make_component("U1", "ATmega328P", "MCU", x=0, y=0, pad_nets=["SCLK"])
    board = make_board(components=[ic])
    assert decoupling.check(board) == []
