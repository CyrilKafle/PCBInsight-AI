from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.main import app

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"
SIMPLE_BOARD_DIR = EXAMPLES_DIR / "simple_board"

client = TestClient(app)


def _project_files() -> list[tuple[str, tuple[str, bytes]]]:
    return [
        ("files", (f.name, f.read_bytes()))
        for f in sorted(SIMPLE_BOARD_DIR.iterdir())
        if f.is_file()
    ]


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_review_endpoint_with_valid_project():
    response = client.post("/api/review", files=_project_files())

    assert response.status_code == 200
    data = response.json()
    assert data["board"]["name"] == "simple_board"
    assert data["score"]["overall"] == 100
    assert len(data["issues"]) == 1
    assert data["issues"][0]["id"] == "SIG-001"
    assert data["ai_review"] is None


def test_review_endpoint_no_files_returns_422():
    # FastAPI's own request validation rejects a missing required field
    # before the handler runs -- 422 is correct here, not a bug.
    response = client.post("/api/review", files=[])
    assert response.status_code == 422


def test_review_endpoint_no_pcb_file_returns_400():
    response = client.post("/api/review", files=[("files", ("readme.txt", b"not a kicad file"))])
    assert response.status_code == 400
    assert "kicad_pcb" in response.json()["detail"]


def test_review_endpoint_malformed_pcb_returns_400():
    response = client.post(
        "/api/review", files=[("files", ("broken.kicad_pcb", b"(kicad_pcb (unbalanced"))]
    )
    assert response.status_code == 400
    assert "Could not parse" in response.json()["detail"]


def test_review_endpoint_ai_review_without_api_key_returns_502(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = client.post(
        "/api/review", files=_project_files(), data={"include_ai_review": "true"}
    )
    assert response.status_code == 502
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_review_endpoint_flattens_path_traversal_attempt():
    response = client.post(
        "/api/review",
        files=[("files", ("../../evil.kicad_pcb", b"(kicad_pcb)"))],
    )
    # ".name" flattening means this lands as a harmless top-level file in the
    # temp dir, not written outside it -- still a valid (if empty) board.
    assert response.status_code == 200


def test_review_endpoint_dotdot_filename_falls_back_to_upload_name():
    # A bare ".." has an empty Path.name; without the fallback we'd try to
    # open the temp directory itself for writing. It should be renamed to
    # "upload" (a .txt-style non-pcb file), so the run fails cleanly at the
    # "no .kicad_pcb" stage rather than raising an IsADirectoryError 500.
    response = client.post(
        "/api/review",
        files=[("files", ("..", b"(kicad_pcb)"))],
    )
    assert response.status_code == 400
    assert "kicad_pcb" in response.json()["detail"]


def test_review_endpoint_rejects_too_many_files():
    files = [
        ("files", (f"pad_{i}.txt", b"x")) for i in range(main.MAX_UPLOAD_FILES + 1)
    ]
    response = client.post("/api/review", files=files)
    assert response.status_code == 413
    assert "Too many files" in response.json()["detail"]


def test_review_endpoint_rejects_oversized_total_upload(monkeypatch):
    # Shrink the budget so the test stays fast; the streamed cap must trip
    # before the whole payload is buffered.
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 1024)
    oversized = b"x" * 4096
    response = client.post(
        "/api/review",
        files=[("files", ("big.kicad_pcb", oversized))],
    )
    assert response.status_code == 413
    assert "total limit" in response.json()["detail"]
