"""v1.1 item 5: explicit input boundary.

Ambiguous uploads (several boards) and unreadable files fail with a clear
error instead of a silent first match or an empty board that scores 100.
Constructs the parser skips or approximates produce a per-board limitation
note. Geometry tests cover rotated footprints and a board whose outline does
not start at the origin."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.analysis import placement
from app.main import app
from app.parser.kicad_project import (
    BoardParseError,
    MultipleBoardsError,
    TESTED_FORMAT_VERSIONS,
    find_project_files,
    parse_board,
)
from app.reports import html_report
from app.analysis.scoring import score as compute_score

_TESTED_VERSION = next(iter(TESTED_FORMAT_VERSIONS))


def _pcb(body: str = "", version: int | None = _TESTED_VERSION, outline: str | None = None) -> str:
    """A minimal but real-shaped .kicad_pcb: copper layers, nets, a 50 x 40 mm
    Edge.Cuts rectangle whose corner is at (100, 50), not at the origin."""
    if outline is None:
        outline = '(gr_rect (start 100 50) (end 150 90) (layer "Edge.Cuts"))'
    version_expr = f"(version {version})" if version is not None else ""
    return f"""(kicad_pcb {version_expr} (generator "pcbnew")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "") (net 1 "GND") (net 2 "VCC")
  {outline}
  {body}
)"""


_EDGE_CONNECTOR = (
    '(footprint "Conn:USB_C" (layer "F.Cu") (at 101 70 90)'
    ' (property "Reference" "J1") (property "Value" "USB_C") (pad "1" smd (at 0 0) (net 1 "GND")))'
)
_MIDDLE_CONNECTOR = (
    '(footprint "Conn:Header" (layer "F.Cu") (at 125 70 0)'
    ' (property "Reference" "J2") (property "Value" "Header") (pad "1" thru_hole (at 0 0) (net 2 "VCC")))'
)
_ODD_ANGLE_PART = (
    '(footprint "R:R_0603" (layer "F.Cu") (at 120 60 37)'
    ' (property "Reference" "R1") (property "Value" "10k") (pad "1" smd (at 0 0) (net 2 "VCC")))'
)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- geometry: rotated footprints and a non-zero board origin ---------------------


def test_rotated_footprint_keeps_position_and_rotation(tmp_path):
    board = parse_board(_write(tmp_path, "b.kicad_pcb", _pcb(_EDGE_CONNECTOR + _ODD_ANGLE_PART)))
    by_ref = {c.footprint.reference: c for c in board.components}
    assert by_ref["J1"].footprint.rotation == 90
    assert (by_ref["J1"].footprint.position.x, by_ref["J1"].footprint.position.y) == (101, 70)
    assert by_ref["R1"].footprint.rotation == 37
    flagged = [i for i in placement.check(board) if "non-orthogonal" in i.summary]
    assert [i.refs for i in flagged] == [["R1"]]  # 90 degrees is fine, 37 is not


def test_board_outline_away_from_origin_sets_origin_and_size(tmp_path):
    board = parse_board(_write(tmp_path, "b.kicad_pcb", _pcb()))
    assert (board.origin.x, board.origin.y) == (100, 50)
    assert (board.width_mm, board.height_mm) == (50, 40)


def test_edge_distance_is_measured_from_the_real_outline_not_the_origin(tmp_path):
    # J1 is 1 mm from the left edge (x=100); J2 is 25 mm in. Measured from
    # (0, 0) both would look 100+ mm away from any edge.
    board = parse_board(_write(tmp_path, "b.kicad_pcb", _pcb(_EDGE_CONNECTOR + _MIDDLE_CONNECTOR)))
    flagged = [i.refs[0] for i in placement.check(board) if "from the nearest board edge" in i.summary]
    assert flagged == ["J2"]


# --- malformed input ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "not a complete S-expression"),
        ('(kicad_pcb (version 20240108) (net 0 ""', "not a complete S-expression"),
        ('(kicad_pcb (net 1 "GND))', "not a complete S-expression"),
        ("hello world", "not a KiCad PCB file"),
        ("(kicad_sch (version 20231120))", "not a KiCad PCB file"),
        ("(kicad_pcb (segment (start a b) (end 1 2)))", "has a value the parser cannot read"),
        ("(kicad_pcb (net one GND))", "has a value the parser cannot read"),
    ],
)
def test_malformed_board_raises_a_clear_error_not_an_empty_board(tmp_path, text, message):
    with pytest.raises(BoardParseError, match=message):
        parse_board(_write(tmp_path, "bad.kicad_pcb", text))


def test_non_utf8_board_raises_a_clear_error(tmp_path):
    path = tmp_path / "bad.kicad_pcb"
    path.write_bytes(b"\xff\xfe\x00(kicad_pcb")
    with pytest.raises(BoardParseError, match="not UTF-8"):
        parse_board(path)


# --- several boards in one upload --------------------------------------------------


def test_multiple_boards_are_rejected_instead_of_picking_the_first(tmp_path):
    _write(tmp_path, "a.kicad_pcb", _pcb())
    _write(tmp_path, "b.kicad_pcb", _pcb())
    with pytest.raises(MultipleBoardsError, match="2 .kicad_pcb files .*a.kicad_pcb, b.kicad_pcb"):
        find_project_files(tmp_path)


def test_kicad_autosave_copy_is_not_counted_as_a_second_board(tmp_path):
    _write(tmp_path, "main.kicad_pcb", _pcb())
    _write(tmp_path, "_autosave-main.kicad_pcb", _pcb())
    assert find_project_files(tmp_path)["pcb"].name == "main.kicad_pcb"


# --- per-board limitation notes ----------------------------------------------------


def test_clean_tested_board_has_no_limitations(tmp_path):
    assert parse_board(_write(tmp_path, "b.kicad_pcb", _pcb(_EDGE_CONNECTOR))).limitations == []


def test_copper_arc_tracks_are_reported_as_not_parsed(tmp_path):
    arc = '(arc (start 110 60) (mid 115 55) (end 120 60) (width 0.25) (layer "F.Cu") (net 2))'
    board = parse_board(_write(tmp_path, "b.kicad_pcb", _pcb(arc + arc)))
    assert any("2 curved copper tracks (arc) were not parsed" in n for n in board.limitations)


def test_missing_outline_is_reported(tmp_path):
    board = parse_board(_write(tmp_path, "b.kicad_pcb", _pcb(outline="")))
    assert any("No Edge.Cuts board outline" in n for n in board.limitations)


def test_curved_outline_is_reported_as_approximate(tmp_path):
    outline = '(gr_circle (center 125 70) (end 145 70) (layer "Edge.Cuts"))'
    board = parse_board(_write(tmp_path, "b.kicad_pcb", _pcb(outline=outline)))
    assert any("outline has arcs or circles" in n for n in board.limitations)


def test_untested_or_missing_format_version_is_reported(tmp_path):
    old = parse_board(_write(tmp_path, "old.kicad_pcb", _pcb(version=20211014)))
    assert any("version 20211014 has not been tested" in n for n in old.limitations)
    none = parse_board(_write(tmp_path, "none.kicad_pcb", _pcb(version=None)))
    assert any("no format version" in n for n in none.limitations)


def test_schematic_next_to_the_board_is_reported_as_not_analyzed(tmp_path):
    _write(tmp_path, "b.kicad_sch", "(kicad_sch (version 20231120))")
    board = parse_board(_write(tmp_path, "b.kicad_pcb", _pcb()))
    assert any("no electrical rules check (ERC)" in n for n in board.limitations)


def test_html_report_shows_board_limitations(tmp_path):
    board = parse_board(_write(tmp_path, "b.kicad_pcb", _pcb(outline="")))
    html = html_report.render(board, [], compute_score([]))
    assert "Input limitations for this board" in html
    assert "No Edge.Cuts board outline" in html


# --- API -----------------------------------------------------------------------------

client = TestClient(app)


def test_api_rejects_upload_with_two_boards():
    files = [("files", ("a.kicad_pcb", _pcb().encode())), ("files", ("b.kicad_pcb", _pcb().encode()))]
    response = client.post("/api/review", files=files)
    assert response.status_code == 400
    assert "Ambiguous upload" in response.json()["detail"]


def test_api_rejects_non_board_file_named_kicad_pcb():
    response = client.post("/api/review", files=[("files", ("x.kicad_pcb", b"hello world"))])
    assert response.status_code == 400
    assert "not a KiCad PCB file" in response.json()["detail"]


def test_api_returns_limitations_with_the_board():
    response = client.post("/api/review", files=[("files", ("x.kicad_pcb", _pcb(outline="").encode()))])
    assert response.status_code == 200
    assert any("No Edge.Cuts" in n for n in response.json()["board"]["limitations"])
