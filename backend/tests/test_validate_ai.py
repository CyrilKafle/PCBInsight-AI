"""v1.1 item 7: honesty fixes in scripts/validate_ai.py (pure helpers only;
the script itself makes billed API calls and is run by hand)."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_ai.py"
_spec = importlib.util.spec_from_file_location("validate_ai", _SCRIPT)
va = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(va)


def test_unknown_model_price_is_unknown_not_zero():
    assert va.cost_usd({"input_tokens": 1000, "output_tokens": 1000}, "no-such-model") is None
    assert va.fmt_cost(None) == "unknown"


def test_known_model_price_is_computed():
    model = next(iter(va.PRICING_PER_MTOK))
    rates = va.PRICING_PER_MTOK[model]
    cost = va.cost_usd({"input_tokens": 1_000_000, "output_tokens": 1_000_000}, model)
    assert cost == pytest.approx(rates["input"] + rates["output"])


def test_any_unknown_part_makes_the_total_unknown():
    assert va.sum_costs([0.01, None, 0.02]) is None
    assert va.sum_costs([0.01, 0.02]) == pytest.approx(0.03)


@pytest.mark.parametrize(
    ("stop_reason", "text", "complete"),
    [("end_turn", "Done.", True), ("max_tokens", "Cut off mid", False), ("end_turn", "  ", False), ("refusal", "No.", False)],
)
def test_completeness_needs_a_normal_stop_and_text(stop_reason, text, complete):
    assert va.is_complete(stop_reason, text) is complete


def test_hedging_is_judged_per_finding_not_for_the_whole_text():
    text = (
        "RTE-001 is a real problem and must be fixed. "
        "RTE-002 may be a false positive, so verify it in KiCad. "
        "Please verify everything before fabrication."
    )
    result = va.hedging_by_finding(text, {"RTE-001", "RTE-002", "RTE-003"})
    # The old whole-text keyword search would have passed all three because
    # "verify" appears somewhere.
    assert result == {"RTE-001": "unhedged", "RTE-002": "hedged", "RTE-003": "not_mentioned"}


def test_hedging_requires_every_citing_sentence_to_hedge():
    text = "RTE-001 might be a stub, check it. Later: RTE-001 is definitely broken."
    assert va.hedging_by_finding(text, {"RTE-001"}) == {"RTE-001": "unhedged"}


def test_hedging_handles_withheld_review():
    assert va.hedging_by_finding(None, {"RTE-001"}) == {"RTE-001": "not_mentioned"}


def test_validation_boards_include_a_true_zero_finding_board():
    from app.analysis import run_all_checks

    counts = {label: len(run_all_checks(board)) for label, board in va.boards()}
    assert counts["zero findings (high_quality_reference)"] == 0
    # The hand-built "minimal" board is not clean, and is no longer labelled as if it were.
    assert counts["minimal (hand-built)"] > 0


def test_dry_run_makes_no_api_calls(monkeypatch, capsys):
    def no_calls(*args, **kwargs):
        raise AssertionError("dry run must not call the API")

    monkeypatch.setattr(va, "generate_checked_review", no_calls)
    monkeypatch.setattr(va, "answer_question", no_calls)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert va.main(["--dry-run"]) == 0
    assert "estimated total" in capsys.readouterr().out


def test_paid_run_refuses_unknown_price_without_override(monkeypatch):
    monkeypatch.setattr(va, "DEFAULT_MODEL", "no-such-model")
    with pytest.raises(SystemExit, match="No price entry"):
        va.main([])
