"""FastAPI backend: wires the existing parse -> analyze -> score -> (optional
AI review) pipeline to an HTTP API for the React dashboard.

Local-only tool by design (see DESIGN.md's "Public Positioning & Audience")
-- not hardened or intended for public multi-tenant hosting. CORS is scoped
to the local Vite dev server, not opened wide. The upload caps below are
resource-exhaustion guards (a runaway upload shouldn't OOM the process),
not multi-tenant security."""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.ai.review import generate_review
from app.ai.summarizer import summarize
from app.analysis import run_all_checks
from app.analysis.scoring import score as compute_score
from app.models.board import Board
from app.models.issue import EngineeringScore, Issue
from app.parser.kicad_project import find_project_files, parse_board

logger = logging.getLogger(__name__)

MAX_UPLOAD_FILES = 100
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB total across all files
_READ_CHUNK_BYTES = 1024 * 1024

app = FastAPI(
    title="PCB Design Review Platform",
    description="Automated engineering design review for KiCad PCB projects.",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ReviewResponse(BaseModel):
    board: Board
    issues: list[Issue]
    score: EngineeringScore
    ai_review: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _safe_upload_name(filename: str | None) -> str:
    """Flatten any directory components (defeats ../ traversal) and reject
    names that resolve to a directory reference rather than a file -- writing
    to those would target the temp directory itself instead of a file inside
    it. Note `Path(".").name` is "" but `Path("..").name` is ".." (and "a/.."
    collapses to ".."), so an empty-check alone isn't enough."""
    name = Path(filename or "").name
    if not name or name in {".", ".."}:
        return "upload"
    return name


async def _write_upload_capped(upload: UploadFile, dest: Path, budget: int) -> int:
    """Stream one upload to disk, aborting with 413 if it would exceed the
    remaining byte budget -- never buffers the whole file in memory first."""
    written = 0
    with dest.open("wb") as fh:
        while chunk := await upload.read(_READ_CHUNK_BYTES):
            written += len(chunk)
            if written > budget:
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB total limit.",
                )
            fh.write(chunk)
    return written


@app.post("/api/review", response_model=ReviewResponse)
async def review(files: list[UploadFile], include_ai_review: bool = Form(False)) -> ReviewResponse:
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=413, detail=f"Too many files (limit {MAX_UPLOAD_FILES}).")

    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        budget = MAX_UPLOAD_BYTES
        for upload in files:
            dest = tmp_path / _safe_upload_name(upload.filename)
            budget -= await _write_upload_capped(upload, dest, budget)

        try:
            project_files = find_project_files(tmp_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            board = parse_board(project_files["pcb"])
        except Exception as exc:  # noqa: BLE001 -- a malformed upload should be a clean 400, not a raw 500 traceback
            raise HTTPException(status_code=400, detail=f"Could not parse KiCad project: {exc}") from exc

    issues = run_all_checks(board)
    score = compute_score(issues)

    ai_review = None
    if include_ai_review:
        try:
            digest = summarize(board, issues, score)
            ai_review = generate_review(digest)
        except Exception as exc:  # noqa: BLE001 -- missing key (RuntimeError) or live API failure both map to 502
            raise HTTPException(status_code=502, detail=f"AI review failed: {exc}") from exc

    logger.info(
        "reviewed %s: %d issues, score %d, ai=%s, %.2fs",
        board.name,
        len(issues),
        score.overall,
        ai_review is not None,
        time.perf_counter() - started,
    )
    return ReviewResponse(board=board, issues=issues, score=score, ai_review=ai_review)
