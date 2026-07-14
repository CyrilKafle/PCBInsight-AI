import logging
from types import SimpleNamespace

import pytest

from app.ai.review import (
    CHAT_SYSTEM_PROMPT,
    REVIEW_SYSTEM_PROMPT,
    answer_question,
    find_unsupported_citations,
    generate_review,
)


class FakeMessages:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.last_call: dict | None = None

    def create(self, **kwargs):
        self.last_call = kwargs
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.response_text)])


class FakeClient:
    def __init__(self, response_text: str = "This board looks solid overall."):
        self.messages = FakeMessages(response_text)


_DIGEST = {"overall_score": 87, "subscores": {"Power": 70}, "issues": [{"id": "PWR-001"}]}


def test_generate_review_returns_model_text():
    client = FakeClient("The power subsystem needs attention (Issue PWR-001).")
    result = generate_review(_DIGEST, client=client)
    assert result == "The power subsystem needs attention (Issue PWR-001)."


def test_generate_review_uses_strict_system_prompt_and_sends_digest():
    client = FakeClient()
    generate_review(_DIGEST, client=client)
    call = client.messages.last_call
    assert call["system"] == REVIEW_SYSTEM_PROMPT
    assert "PWR-001" in call["messages"][0]["content"]
    assert "NOT performing design analysis" in call["system"]


def test_answer_question_uses_chat_system_prompt_and_includes_question():
    client = FakeClient("Because decoupling caps filter high-frequency noise close to the IC.")
    result = answer_question(_DIGEST, "Why does decoupling placement matter?", client=client)
    assert result == "Because decoupling caps filter high-frequency noise close to the IC."
    call = client.messages.last_call
    assert call["system"] == CHAT_SYSTEM_PROMPT
    assert "Why does decoupling placement matter?" in call["messages"][0]["content"]
    assert "PWR-001" in call["messages"][0]["content"]


def test_extract_text_concatenates_and_skips_non_text_blocks():
    client = FakeClient()
    client.messages.create = lambda **kwargs: SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Part one. "),
            SimpleNamespace(type="tool_use", text="ignored"),
            SimpleNamespace(type="text", text="Part two."),
        ]
    )
    result = generate_review(_DIGEST, client=client)
    assert result == "Part one. Part two."


def test_generate_review_without_client_or_api_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        generate_review(_DIGEST)


def test_system_prompt_requires_evidence_and_confidence_hedging():
    assert "directly supported by at least one supplied issue" in REVIEW_SYSTEM_PROMPT
    assert "confidence" in REVIEW_SYSTEM_PROMPT.lower()
    assert "confidence" in CHAT_SYSTEM_PROMPT.lower()


def test_find_unsupported_citations_flags_hallucinated_id():
    digest = {"issues": [{"id": "PWR-001"}, {"id": "GND-002"}]}
    text = "The regulator routing is long (PWR-001). Also check SIG-099 for skew."
    assert find_unsupported_citations(text, digest) == ["SIG-099"]


def test_find_unsupported_citations_empty_when_all_known():
    digest = {"issues": [{"id": "PWR-001"}, {"id": "GND-002"}]}
    text = "Findings PWR-001 and GND-002 both relate to power delivery."
    assert find_unsupported_citations(text, digest) == []


def test_find_unsupported_citations_empty_digest_and_no_ids_cited():
    assert find_unsupported_citations("General commentary with no citations.", {"issues": []}) == []


def test_generate_review_logs_warning_on_hallucinated_citation(caplog):
    client = FakeClient("This references a made-up finding (SIG-099).")
    with caplog.at_level(logging.WARNING):
        generate_review(_DIGEST, client=client)
    assert any("SIG-099" in record.message for record in caplog.records)


def test_generate_review_no_warning_when_citations_are_valid(caplog):
    client = FakeClient("This references a real finding (PWR-001).")
    with caplog.at_level(logging.WARNING):
        generate_review(_DIGEST, client=client)
    assert caplog.records == []
