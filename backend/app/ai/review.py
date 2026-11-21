"""Sends the board digest (from summarizer.py) to the LLM for a senior-PCB-
engineer-style narrative review, and answers grounded follow-up questions for
the optional AI chat panel.

The LLM is a technical writer over the deterministic engine's output here --
it never re-derives findings, only synthesizes prose from the structured
digest. Both system prompts below exist to enforce that boundary. See
DESIGN.md's "AI Integration Architecture (Phase 3)" section."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Literal

import anthropic

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-5"
_MAX_REVIEW_TOKENS = 800
_MAX_ANSWER_TOKENS = 500
_ISSUE_ID_PATTERN = re.compile(r"\b[A-Z]{2,6}-\d{3}\b")

REVIEW_SYSTEM_PROMPT = (
    "You are acting as a senior PCB design reviewer. You are NOT performing "
    "design analysis -- that has already been completed deterministically. "
    "Your task is only to summarize the provided findings, identify "
    "recurring themes, explain engineering tradeoffs, and prioritize "
    "issues. Do not invent problems or recommendations that are not "
    "supported by the supplied data. When you discuss a specific finding, "
    "cite its issue ID exactly as it appears in that issue's id field. Only "
    "cite issue IDs that are present in the supplied issues -- never write an "
    "ID that is not in the data, and do not reuse any example ID shown in "
    "these instructions. Every recommendation you make must "
    "be directly supported by at least one supplied issue -- if the "
    "evidence is insufficient to draw a conclusion, say so explicitly "
    "rather than guessing. When an issue's confidence value is low (below "
    "0.5), say so and note that it should be manually verified rather than "
    "treated as certain."
)

CHAT_SYSTEM_PROMPT = (
    "You are answering a question about a specific PCB board that has "
    "already been analyzed deterministically. Ground every answer in the "
    "supplied digest data. Cite issue IDs exactly as they appear in the "
    "supplied data where relevant, and only IDs that are actually present -- "
    "never invent one. If the "
    "question can't be answered from the supplied data, say so rather than "
    "speculating or inventing new findings. If the relevant issue has a low "
    "confidence value (below 0.5), note that it should be manually "
    "verified rather than treated as certain."
)


def generate_review(
    digest: dict,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
    return_usage: bool = False,
) -> str | tuple[str, dict]:
    client = client or _default_client()
    response = client.messages.create(
        model=model,
        max_tokens=_MAX_REVIEW_TOKENS,
        system=REVIEW_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(digest)}],
    )
    text = _extract_text(response)
    _warn_on_unsupported_citations(text, digest)
    return (text, _extract_usage(response)) if return_usage else text


def answer_question(
    digest: dict,
    question: str,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
    return_usage: bool = False,
) -> str | tuple[str, dict]:
    client = client or _default_client()
    response = client.messages.create(
        model=model,
        max_tokens=_MAX_ANSWER_TOKENS,
        system=CHAT_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Board digest:\n{json.dumps(digest)}\n\nQuestion: {question}",
            }
        ],
    )
    text = _extract_text(response)
    _warn_on_unsupported_citations(text, digest)
    return (text, _extract_usage(response)) if return_usage else text


def find_unsupported_citations(review_text: str, digest: dict) -> list[str]:
    """Return every issue-ID-shaped token (e.g. "PWR-004") cited in
    `review_text` that isn't actually one of `digest`'s real issue IDs.

    The system prompt tells the LLM to only cite real issue IDs, but a prompt
    alone can't guarantee that -- this is the code-enforced check, the same
    defense-in-depth approach used for the raw-geometry boundary in
    summarizer.py. Non-empty output means the model likely hallucinated a
    citation and the review text should be treated with suspicion."""
    known_ids = {issue["id"] for issue in digest.get("issues", [])}
    cited = set(_ISSUE_ID_PATTERN.findall(review_text))
    return sorted(cited - known_ids)


# Stop reasons that mean the model finished its answer on its own. Anything
# else (max_tokens, refusal, pause_turn, ...) is treated as incomplete output.
# A response object with no stop_reason at all (e.g. a minimal test fake) is
# accepted, since only the text can be checked.
_NORMAL_STOP_REASONS = {"end_turn", "stop_sequence", None}

ReviewStatus = Literal["valid", "repaired", "withheld"]
ReviewProblem = Literal["unknown_citations", "empty", "incomplete"]


@dataclass
class ReviewResult:
    """Outcome of a checked LLM review.

    status:
      valid    -- the first response passed every check.
      repaired -- the first response failed, the single repair attempt passed.
      withheld -- both attempts failed; `text` is None and the caller must show
                  only the deterministic findings.

    Passing the checks means the text cites only real finding IDs and was not
    cut off. It does NOT prove every sentence is supported by those findings."""

    status: ReviewStatus
    text: str | None
    problems: list[ReviewProblem] = field(default_factory=list)
    unknown_ids: list[str] = field(default_factory=list)
    attempts: int = 1
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})


def check_review_text(text: str, stop_reason: str | None, digest: dict) -> tuple[list[ReviewProblem], list[str]]:
    """Return (problems, unknown_ids) for one model response. Empty problems = passes."""
    problems: list[ReviewProblem] = []
    if not text.strip():
        problems.append("empty")
    if stop_reason not in _NORMAL_STOP_REASONS:
        problems.append("incomplete")
    unknown = find_unsupported_citations(text, digest)
    if unknown:
        problems.append("unknown_citations")
    return problems, unknown


def generate_checked_review(
    digest: dict,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
) -> ReviewResult:
    """Generate the narrative review and enforce the citation/completeness
    checks: at most one repair attempt, then withhold the prose.

    Provider exceptions (including MissingApiKeyError) propagate unchanged;
    the caller keeps the deterministic result either way."""
    client = client or _default_client()
    usage = {"input_tokens": 0, "output_tokens": 0}
    base_content = json.dumps(digest)

    text, stop_reason = _review_call(client, model, base_content, usage)
    problems, unknown = check_review_text(text, stop_reason, digest)
    if not problems:
        return ReviewResult("valid", text, attempts=1, usage=usage)

    logger.warning("AI review failed checks %s (unknown ids: %s); trying one repair", problems, unknown)
    repair_content = base_content + "\n\n" + _repair_instruction(problems, unknown, digest)
    text, stop_reason = _review_call(client, model, repair_content, usage)
    repair_problems, repair_unknown = check_review_text(text, stop_reason, digest)
    if not repair_problems:
        return ReviewResult("repaired", text, problems=problems, unknown_ids=unknown, attempts=2, usage=usage)

    logger.warning("AI review withheld after repair: %s (unknown ids: %s)", repair_problems, repair_unknown)
    return ReviewResult(
        "withheld",
        None,
        problems=repair_problems,
        unknown_ids=repair_unknown,
        attempts=2,
        usage=usage,
    )


def _review_call(client, model: str, content: str, usage: dict) -> tuple[str, str | None]:
    response = client.messages.create(
        model=model,
        max_tokens=_MAX_REVIEW_TOKENS,
        system=REVIEW_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    call_usage = getattr(response, "usage", None)
    if call_usage is not None:
        usage["input_tokens"] += call_usage.input_tokens
        usage["output_tokens"] += call_usage.output_tokens
    return _extract_text(response), getattr(response, "stop_reason", None)


def _repair_instruction(problems: list[ReviewProblem], unknown: list[str], digest: dict) -> str:
    known = sorted(issue["id"] for issue in digest.get("issues", []))
    reasons = []
    if "unknown_citations" in problems:
        reasons.append(f"it cited issue IDs that are not in the data: {', '.join(unknown)}")
    if "empty" in problems:
        reasons.append("it was empty")
    if "incomplete" in problems:
        reasons.append("it was cut off before finishing; keep the review shorter")
    allowed = ", ".join(known) if known else "none (there are no issues, so cite no IDs)"
    return (
        "A previous draft of this review was rejected because "
        + "; ".join(reasons)
        + f". Write the review again. The only issue IDs you may cite are: {allowed}."
    )


def _warn_on_unsupported_citations(review_text: str, digest: dict) -> None:
    unsupported = find_unsupported_citations(review_text, digest)
    if unsupported:
        logger.warning("AI review cited issue IDs not present in the digest: %s", unsupported)


class MissingApiKeyError(RuntimeError):
    """Raised when no API key is configured. Subclasses RuntimeError for backward compatibility."""


def _default_client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise MissingApiKeyError(
            "ANTHROPIC_API_KEY is not set. Set it in the environment, or pass an "
            "explicit `client` argument (e.g. a fake/mock client for testing)."
        )
    return anthropic.Anthropic()


def _extract_text(response) -> str:
    return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")


def _extract_usage(response) -> dict:
    usage = response.usage
    return {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
