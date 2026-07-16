"""Phase 0 tests: parser must correctly extract components/nets/traces/vias/
pours/footprints/board dimensions from real example KiCad projects in
examples/."""

from pathlib import Path

import pytest

from app.analysis import run_all_checks
from app.analysis.scoring import score as compute_score
from app.parser.kicad_project import classify_component, find_project_files, parse_board

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"
SIMPLE_BOARD_DIR = EXAMPLES_DIR / "simple_board"
CORPUS_BOARD_DIRS = sorted(d for d in EXAMPLES_DIR.iterdir() if d.is_dir())


@pytest.fixture(scope="module")
def simple_board():
    files = find_project_files(SIMPLE_BOARD_DIR)
    return parse_board(files["pcb"])


def test_find_project_files_locates_pcb_and_project():
    files = find_project_files(SIMPLE_BOARD_DIR)
    assert files["pcb"].name == "simple_board.kicad_pcb"
    assert files["project"].name == "simple_board.kicad_pro"


def test_find_project_files_raises_without_pcb(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_project_files(tmp_path)


@pytest.mark.parametrize("board_dir", CORPUS_BOARD_DIRS, ids=lambda d: d.name)
def test_corpus_board_parses_and_scores_without_error(board_dir):
    """Regression guard for the Engineering Validation Corpus: every board under
    examples/ must parse cleanly and run through the full deterministic engine
    without raising, regardless of how deliberately flawed its design is."""
    files = find_project_files(board_dir)
    board = parse_board(files["pcb"])
    issues = run_all_checks(board)
    result = compute_score(issues)
    assert 0 <= result.overall <= 100


def test_board_name_and_dimensions(simple_board):
    assert simple_board.name == "simple_board"
    assert simple_board.width_mm == pytest.approx(50.0)
    assert simple_board.height_mm == pytest.approx(40.0)
    assert simple_board.origin.x == pytest.approx(0.0)
    assert simple_board.origin.y == pytest.approx(0.0)


def test_component_pad_nets(simple_board):
    u1 = next(c for c in simple_board.components if c.footprint.reference == "U1")
    c1 = next(c for c in simple_board.components if c.footprint.reference == "C1")
    assert set(u1.footprint.pad_nets) == {"+3V3", "GND", "/SCLK"}
    assert set(c1.footprint.pad_nets) == {"+3V3", "GND"}


def test_layer_count(simple_board):
    assert simple_board.layer_count == 2


def test_components_extracted(simple_board):
    refs = {c.footprint.reference: c.kind for c in simple_board.components}
    assert refs == {
        "U1": "MCU",
        "C1": "capacitor",
        "R1": "resistor",
        "J1": "connector",
    }


def test_component_position_and_rotation(simple_board):
    r1 = next(c for c in simple_board.components if c.footprint.reference == "R1")
    assert r1.footprint.position.x == pytest.approx(20.0)
    assert r1.footprint.position.y == pytest.approx(20.0)
    assert r1.footprint.rotation == pytest.approx(90.0)


def test_nets_present(simple_board):
    net_names = {net.name for net in simple_board.nets}
    assert net_names == {"GND", "+3V3", "/SCLK"}


def test_trace_count_and_net_assignment(simple_board):
    gnd = next(n for n in simple_board.nets if n.name == "GND")
    sclk = next(n for n in simple_board.nets if n.name == "/SCLK")
    plus3v3 = next(n for n in simple_board.nets if n.name == "+3V3")

    assert len(gnd.traces) == 1
    assert len(sclk.traces) == 3
    assert len(plus3v3.traces) == 1


def test_via_extracted_on_gnd(simple_board):
    gnd = next(n for n in simple_board.nets if n.name == "GND")
    assert len(gnd.vias) == 1
    via = gnd.vias[0]
    assert via.position.x == pytest.approx(10.0)
    assert via.position.y == pytest.approx(25.0)
    assert via.drill == pytest.approx(0.3)
    assert via.diameter == pytest.approx(0.6)


def test_copper_pour_extracted(simple_board):
    assert len(simple_board.pours) == 1
    pour = simple_board.pours[0]
    assert pour.net == "GND"
    assert pour.layer == "B.Cu"
    assert len(pour.outline) == 4


@pytest.mark.parametrize(
    "reference,value,expected_kind",
    [
        ("U1", "ATmega328P-AU", "MCU"),
        ("U2", "ICE40UP5K", "FPGA"),
        ("U3", "LM7805", "regulator"),
        ("U4", "SN74LVC1G17", "IC"),
        ("C10", "1uF", "capacitor"),
        ("R5", "4.7k", "resistor"),
        ("J2", "Header_2x05", "connector"),
        ("Q1", "2N2222", "transistor"),
        ("D3", "1N4148", "diode"),
        ("L1", "10uH", "inductor"),
        ("Y1", "16MHz", "oscillator"),
        ("SW1", "Tactile", "switch"),
        ("TP1", "TestPoint", "other"),
    ],
)
def test_classify_component(reference, value, expected_kind):
    assert classify_component(reference, value) == expected_kind
