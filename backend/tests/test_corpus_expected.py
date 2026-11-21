"""v1.1 item 6: every board in examples/ produces exactly the expected findings.

The older corpus smoke test (test_parser.py) only checks that each board
parses and scores within bounds. This pins, per board, the set of finding
IDs and for each one its severity, rule weight and summary (which carries the
measured value, e.g. "0.10mm wide"), plus the overall score. Expected values
are in corpus_expected.py; see its docstring for where they came from."""

from pathlib import Path

import pytest

from app.analysis import run_all_checks
from app.analysis.scoring import score as compute_score
from app.parser.kicad_project import find_project_files, parse_board
from tests.corpus_expected import EXPECTED

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


def test_every_corpus_board_has_expectations():
    boards = {d.name for d in EXAMPLES_DIR.iterdir() if d.is_dir()}
    assert boards == set(EXPECTED), "add or remove the board in corpus_expected.py"


@pytest.mark.parametrize("board_name", sorted(EXPECTED))
def test_corpus_board_produces_exactly_the_expected_findings(board_name):
    expected_score, expected_findings = EXPECTED[board_name]
    board = parse_board(find_project_files(EXAMPLES_DIR / board_name)["pcb"])
    issues = run_all_checks(board)

    actual = {i.id: (i.severity.value, i.confidence, i.summary) for i in issues}
    assert set(actual) == set(expected_findings), "finding IDs changed"
    for finding_id, expected in expected_findings.items():
        assert actual[finding_id] == expected, finding_id
    assert compute_score(issues).overall == expected_score
    assert board.limitations == [], "corpus boards are clean KiCad 8 files"
