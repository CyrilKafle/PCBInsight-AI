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
from typing import Literal

from fastapi import FastAPI, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.ai.review import MissingApiKeyError, answer_question, generate_checked_review
from app.ai.summarizer import summarize
from app.analysis import run_all_checks
from app.analysis.scoring import score as compute_score
from app.models.board import Board
from app.models.issue import EngineeringScore, Issue
from app.parser.kicad_project import BoardParseError, MultipleBoardsError, find_project_files, parse_board
from app.reports import pdf_report

logger = logging.getLogger(__name__)

# Version of the /api/review response shape. 2 = adds ai_review_status and the
# "withheld" ai_error category (v1.1). One bump per release, not per change.
REVIEW_SCHEMA_VERSION = 2

MAX_UPLOAD_FILES = 100
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB total across all files
_READ_CHUNK_BYTES = 1024 * 1024
MAX_QUESTION_CHARS = 2000

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


class AiError(BaseModel):
    """Why the optional LLM explanation is missing. Never carries the raw
    exception text (it can echo request details); the full error is logged."""

    category: Literal["not_configured", "provider_error", "withheld"]
    message: str


class ReviewResponse(BaseModel):
    schema_version: int = REVIEW_SCHEMA_VERSION
    board: Board
    issues: list[Issue]
    score: EngineeringScore
    ai_review: str | None = None
    # valid / repaired: ai_review passed the citation and completeness checks
    # (on the first try, or after the single repair attempt). withheld: it did
    # not, so ai_review is None and ai_error explains why. None: no LLM text.
    ai_review_status: Literal["valid", "repaired", "withheld"] | None = None
    ai_error: AiError | None = None


class ChatRequest(BaseModel):
    # The dashboard sends back the board/issues/score it already holds from
    # /api/review, so the chat endpoint stays stateless -- no server-side
    # session store to grow or evict. Conversation history is kept in the
    # browser (each question is answered against the digest, not the thread).
    board: Board
    issues: list[Issue]
    score: EngineeringScore
    question: str


class ChatResponse(BaseModel):
    answer: str


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
        except FileNotFoundError:
            raise HTTPException(status_code=400, detail="No .kicad_pcb file was found in the upload.") from None
        except MultipleBoardsError as exc:
            raise HTTPException(status_code=400, detail=f"Ambiguous upload: {exc}.") from exc

        try:
            board = parse_board(project_files["pcb"], tmp_path)
        except BoardParseError as exc:
            raise HTTPException(status_code=400, detail=f"Could not parse KiCad project: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 -- an unexpected parser bug is still a clean 400, not a raw 500
            logger.warning("unexpected parser error: %s", type(exc).__name__)
            raise HTTPException(
                status_code=400, detail="Could not parse KiCad project: unexpected parser error."
            ) from exc

    issues = run_all_checks(board)
    score = compute_score(issues)

    ai_review = None
    ai_review_status = None
    ai_error = None
    if include_ai_review:
        try:
            digest = summarize(board, issues, score)
            checked = generate_checked_review(digest)
            ai_review = checked.text
            ai_review_status = checked.status
            if checked.status == "withheld":
                ai_error = AiError(
                    category="withheld",
                    message=_withheld_message(checked.problems),
                )
        except MissingApiKeyError:
            logger.warning("AI review skipped: ANTHROPIC_API_KEY is not set")
            ai_error = AiError(
                category="not_configured",
                message="ANTHROPIC_API_KEY is not set, so no LLM explanation was generated.",
            )
        except Exception as exc:  # noqa: BLE001 -- the deterministic result must survive any LLM failure
            # Log only the error type and HTTP status (if any): provider error text can echo request
            # content or credentials, so neither the message nor the traceback is logged.
            logger.warning(
                "AI review failed (%s, status=%s); returning deterministic result only",
                type(exc).__name__,
                getattr(exc, "status_code", None),
            )
            ai_error = AiError(
                category="provider_error",
                message="The LLM provider request failed. See the server log for details.",
            )

    logger.info(
        "reviewed %s: %d issues, score %d, ai=%s, %.2fs",
        board.name,
        len(issues),
        score.overall,
        ai_review is not None,
        time.perf_counter() - started,
    )
    return ReviewResponse(
        board=board,
        issues=issues,
        score=score,
        ai_review=ai_review,
        ai_review_status=ai_review_status,
        ai_error=ai_error,
    )


_PROBLEM_TEXT = {
    "unknown_citations": "cited finding IDs that this board does not have",
    "empty": "came back empty",
    "incomplete": "was cut off before it finished",
}


def _withheld_message(problems: list[str]) -> str:
    reasons = "; ".join(_PROBLEM_TEXT.get(p, p) for p in problems) or "failed its checks"
    return f"The LLM explanation was withheld because it {reasons}, even after one retry."


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Answer a grounded follow-up question about an already-reviewed board.

    Rebuilds the same digest summarize() feeds the review layer and hands it to
    the existing answer_question() -- the deterministic engine stays the sole
    source of findings; the LLM only narrates over the digest."""
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question must not be empty.")
    if len(question) > MAX_QUESTION_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Question exceeds the {MAX_QUESTION_CHARS} character limit.",
        )

    digest = summarize(request.board, request.issues, request.score)
    try:
        answer = answer_question(digest, question)
    except Exception as exc:  # noqa: BLE001 -- missing key (RuntimeError) or live API failure both map to 502
        raise HTTPException(status_code=502, detail=f"AI chat failed: {exc}") from exc

    return ChatResponse(answer=answer)


@app.post("/api/report/pdf")
def report_pdf(review: ReviewResponse) -> Response:
    """Render the already-computed review (board/issues/score/ai_review the
    dashboard holds) to a downloadable PDF. Reuses app/reports/pdf_report,
    which in turn reuses the HTML report's charts -- no re-analysis here."""
    pdf_bytes = pdf_report.render(review.board, review.issues, review.score, review.ai_review)
    filename = _safe_upload_name(f"{review.board.name}_report.pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
