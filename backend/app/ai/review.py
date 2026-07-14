"""Sends the board digest (from summarizer.py) to Claude for a senior-PCB-
engineer-style narrative review, and answers grounded follow-up questions for
the optional AI chat panel.

Claude is a technical writer over the deterministic engine's output here --
it never re-derives findings, only synthesizes prose from the structured
digest. Both system prompts below exist to enforce that boundary. See
DESIGN.md's "AI Integration Architecture (Phase 3)" section."""

from __future__ import annotations

import json
import logging
import os
import re

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
    'supported by the supplied data. Reference issue IDs (e.g. "PWR-004") '
    "when discussing specific findings. Every recommendation you make must "
    "be directly supported by at least one supplied issue -- if the "
    "evidence is insufficient to draw a conclusion, say so explicitly "
    "rather than guessing. When an issue's confidence value is low (below "
    "0.5), say so and note that it should be manually verified rather than "
    "treated as certain."
)

CHAT_SYSTEM_PROMPT = (
    "You are answering a question about a specific PCB board that has "
    "already been analyzed deterministically. Ground every answer in the "
    "supplied digest data, and reference issue IDs where relevant. If the "
    "question can't be answered from the supplied data, say so rather than "
    "speculating or inventing new findings. If the relevant issue has a low "
    "confidence value (below 0.5), note that it should be manually "
    "verified rather than treated as certain."
)


def generate_review(digest: dict, client: anthropic.Anthropic | None = None, model: str = DEFAULT_MODEL) -> str:
    client = client or _default_client()
    response = client.messages.create(
        model=model,
        max_tokens=_MAX_REVIEW_TOKENS,
        system=REVIEW_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(digest)}],
    )
    text = _extract_text(response)
    _warn_on_unsupported_citations(text, digest)
    return text


def answer_question(
    digest: dict,
    question: str,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
) -> str:
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
    return text


def find_unsupported_citations(review_text: str, digest: dict) -> list[str]:
    """Return every issue-ID-shaped token (e.g. "PWR-004") cited in
    `review_text` that isn't actually one of `digest`'s real issue IDs.

    The system prompt tells Claude to only cite real issue IDs, but a prompt
    alone can't guarantee that -- this is the code-enforced check, the same
    defense-in-depth approach used for the raw-geometry boundary in
    summarizer.py. Non-empty output means the model likely hallucinated a
    citation and the review text should be treated with suspicion."""
    known_ids = {issue["id"] for issue in digest.get("issues", [])}
    cited = set(_ISSUE_ID_PATTERN.findall(review_text))
    return sorted(cited - known_ids)


def _warn_on_unsupported_citations(review_text: str, digest: dict) -> None:
    unsupported = find_unsupported_citations(review_text, digest)
    if unsupported:
        logger.warning("AI review cited issue IDs not present in the digest: %s", unsupported)


def _default_client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Set it in the environment, or pass an "
            "explicit `client` argument (e.g. a fake/mock client for testing)."
        )
    return anthropic.Anthropic()


def _extract_text(response) -> str:
    return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
