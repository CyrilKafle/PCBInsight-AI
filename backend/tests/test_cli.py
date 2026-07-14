import shutil
from pathlib import Path

from app.cli import main

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"
SIMPLE_BOARD_DIR = EXAMPLES_DIR / "simple_board"


def test_review_single_board_writes_report_and_prints_summary(tmp_path, capsys):
    out = tmp_path / "report.html"
    exit_code = main(["review", str(SIMPLE_BOARD_DIR), "--out", str(out)])

    assert exit_code == 0
    assert out.exists()
    assert "PCB Design Review Report" in out.read_text(encoding="utf-8")

    captured = capsys.readouterr()
    assert "simple_board" in captured.out
    assert "Overall Score:" in captured.out
    assert "Critical Issues:" in captured.out
    assert "Warnings:" in captured.out
    assert "Report saved:" in captured.out


def test_review_single_board_default_output_path(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    exit_code = main(["review", str(SIMPLE_BOARD_DIR)])

    assert exit_code == 0
    assert (tmp_path / "simple_board_report.html").exists()


def test_review_missing_path_errors(tmp_path, capsys):
    exit_code = main(["review", str(tmp_path / "does_not_exist")])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "no KiCad project" in captured.err


def test_review_batch_folder_writes_per_board_reports_and_summary(tmp_path, capsys):
    boards_dir = tmp_path / "boards"
    for name in ("board_a", "board_b"):
        shutil.copytree(SIMPLE_BOARD_DIR, boards_dir / name)

    out_dir = tmp_path / "out"
    exit_code = main(["review", str(boards_dir), "--out", str(out_dir)])

    assert exit_code == 0
    assert (out_dir / "board_a" / "report.html").exists()
    assert (out_dir / "board_b" / "report.html").exists()

    summary = out_dir / "summary.html"
    assert summary.exists()
    summary_text = summary.read_text(encoding="utf-8")
    assert "Batch Review Summary" in summary_text
    assert "board_a/report.html" in summary_text
    assert "board_b/report.html" in summary_text

    captured = capsys.readouterr()
    assert "Batch summary saved:" in captured.out


def test_review_batch_skips_unparseable_board_and_continues(tmp_path, capsys):
    boards_dir = tmp_path / "boards"
    shutil.copytree(SIMPLE_BOARD_DIR, boards_dir / "board_a")
    (boards_dir / "board_b").mkdir(parents=True)
    (boards_dir / "board_b" / "broken.kicad_pcb").write_text("(kicad_pcb (unbalanced", encoding="utf-8")

    out_dir = tmp_path / "out"
    exit_code = main(["review", str(boards_dir), "--out", str(out_dir)])

    assert exit_code == 0
    assert (out_dir / "board_a" / "report.html").exists()
    assert not (out_dir / "board_b" / "report.html").exists()
    assert (out_dir / "summary.html").exists()

    captured = capsys.readouterr()
    assert "warning: skipping" in captured.err
