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
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.response_text)],
            usage=SimpleNamespace(input_tokens=123, output_tokens=45),
        )


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


def test_generate_review_return_usage_returns_text_and_token_counts():
    client = FakeClient("This board looks solid overall.")
    result = generate_review(_DIGEST, client=client, return_usage=True)
    assert result == ("This board looks solid overall.", {"input_tokens": 123, "output_tokens": 45, "stop_reason": None})


def test_answer_question_return_usage_returns_text_and_token_counts():
    client = FakeClient("Because decoupling caps filter high-frequency noise close to the IC.")
    result = answer_question(_DIGEST, "Why?", client=client, return_usage=True)
    assert result == (
        "Because decoupling caps filter high-frequency noise close to the IC.",
        {"input_tokens": 123, "output_tokens": 45, "stop_reason": None},
    )


def test_generate_review_no_warning_when_citations_are_valid(caplog):
    client = FakeClient("This references a real finding (PWR-001).")
    with caplog.at_level(logging.WARNING):
        generate_review(_DIGEST, client=client)
    assert caplog.records == []


# --- v1.1 item 2: citation enforcement (generate_checked_review) ---------------

from app.ai.review import check_review_text, generate_checked_review  # noqa: E402


class SequenceMessages:
    """Returns one scripted (text, stop_reason) response per call."""

    def __init__(self, responses: list[tuple[str, str | None]]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text, stop_reason = self.responses.pop(0)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason=stop_reason,
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        )


class SequenceClient:
    def __init__(self, *responses: tuple[str, str | None]):
        self.messages = SequenceMessages(list(responses))


_GOOD = ("Power needs attention (PWR-001).", "end_turn")
_FAKE_ID = ("Check SIG-099 for skew.", "end_turn")


def test_checked_review_valid_passes_through_with_one_call():
    client = SequenceClient(_GOOD)
    result = generate_checked_review(_DIGEST, client=client)
    assert result.status == "valid"
    assert result.text == _GOOD[0]
    assert result.attempts == 1
    assert len(client.messages.calls) == 1
    assert result.usage == {"input_tokens": 100, "output_tokens": 20}
    assert result.stop_reasons == ["end_turn"]


def test_checked_review_unknown_id_is_never_returned_as_validated_text():
    client = SequenceClient(_FAKE_ID, _FAKE_ID)
    result = generate_checked_review(_DIGEST, client=client)
    assert result.status == "withheld"
    assert result.text is None
    assert result.unknown_ids == ["SIG-099"]
    assert result.first_attempt_unknown_ids == ["SIG-099"]
    assert result.attempts == 2


def test_checked_review_repairs_once_then_passes():
    client = SequenceClient(_FAKE_ID, _GOOD)
    result = generate_checked_review(_DIGEST, client=client)
    assert result.status == "repaired"
    assert result.text == _GOOD[0]
    assert result.problems == ["unknown_citations"]
    assert result.unknown_ids == ["SIG-099"]
    assert result.usage == {"input_tokens": 200, "output_tokens": 40}
    repair_prompt = client.messages.calls[1]["messages"][0]["content"]
    assert "SIG-099" in repair_prompt
    assert "The only issue IDs you may cite are: PWR-001" in repair_prompt


def test_checked_review_makes_at_most_two_calls():
    client = SequenceClient(_FAKE_ID, _FAKE_ID, _GOOD)
    generate_checked_review(_DIGEST, client=client)
    assert len(client.messages.calls) == 2


def test_checked_review_truncated_output_is_withheld():
    truncated = ("Power needs attention (PWR-001) because the regul", "max_tokens")
    client = SequenceClient(truncated, truncated)
    result = generate_checked_review(_DIGEST, client=client)
    assert result.status == "withheld"
    assert result.text is None
    assert result.problems == ["incomplete"]
    assert result.stop_reasons == ["max_tokens", "max_tokens"]
    assert "cut off" in client.messages.calls[1]["messages"][0]["content"]


def test_checked_review_empty_output_is_withheld():
    client = SequenceClient(("   ", "end_turn"), ("", "end_turn"))
    result = generate_checked_review(_DIGEST, client=client)
    assert result.status == "withheld"
    assert result.problems == ["empty"]


def test_checked_review_refusal_stop_reason_counts_as_incomplete():
    problems, _ = check_review_text("I can't help with that.", "refusal", _DIGEST)
    assert problems == ["incomplete"]


def test_check_review_text_accepts_missing_stop_reason():
    problems, unknown = check_review_text("Looks fine (PWR-001).", None, _DIGEST)
    assert problems == [] and unknown == []


def test_checked_review_no_issues_board_rejects_any_cited_id():
    digest = {"issues": []}
    client = SequenceClient(("Clean board, see PWR-001.", "end_turn"), ("Clean board.", "end_turn"))
    result = generate_checked_review(digest, client=client)
    assert result.status == "repaired"
    assert "cite no IDs" in client.messages.calls[1]["messages"][0]["content"]


def test_checked_review_provider_exception_propagates():
    class Boom:
        def create(self, **kwargs):
            raise ConnectionError("down")

    client = SimpleNamespace(messages=Boom())
    with pytest.raises(ConnectionError):
        generate_checked_review(_DIGEST, client=client)
