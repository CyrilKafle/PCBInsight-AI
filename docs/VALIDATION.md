# Validation

PCBInsight is validated on two separate tracks, and it matters that they stay separate: the **Engineering Validation Corpus** proves the deterministic parser and analysis engine behave correctly, and the **AI validation harness** proves the AI layer stays inside its bounds (narrates, never invents). One is part of the standard test suite and runs on every push; the other needs a real API key and real spend, and is run manually.

## Why the corpus exists

A single "does it basically work" fixture isn't enough evidence for a tool whose whole pitch is a transparent, deterministic engine. `examples/` is a curated corpus — see `examples/README.md` for the full per-board writeups — where every board exists to demonstrate one thing:

| Board | Demonstrates |
|---|---|
| `simple_board` | The parser handles every S-expression construct it needs to |
| `stm32_usb_dev` | The engine holds up on a substantial, realistic board |
| `flawed_reference` | Nearly every check category fires correctly on a genuinely bad board |
| `high_quality_reference` | The engine doesn't invent problems on a genuinely clean board (100/100, zero findings) |
| `rf_clock_board` | Signal-integrity and differential-pair checks fire in isolation |
| `power_supply_board` | Power-delivery and decoupling checks fire in isolation |
| `thermal_reference` | Thermal checks fire in isolation |
| `manufacturing_reference` | DFM checks fire in isolation |
| `parser_edge_cases` | The parser survives unicode, escaped quotes, and hostile characters |
| `mixed_realistic_board` | A believable "mostly good, a few real mistakes" board scores sensibly |

## Running the corpus

Every board parses and scores as part of the normal test suite:

```sh
cd backend && python -m pytest -q
```

`tests/test_parser.py::test_corpus_board_parses_and_scores_without_error` is parametrized over every subdirectory of `examples/` — it's the regression guard that keeps the corpus honest as the parser and analysis engine evolve. To inspect a single board's findings directly:

```sh
cd backend
python -m app.cli review ../examples/<board_name>            # writes <board_name>_report.html
python -m app.cli review ../examples/<board_name> --ai        # + Claude narrative (needs ANTHROPIC_API_KEY)
```

**Interpreting a failure:** if the parametrized test fails for a board, either the parser broke on a construct that board relies on, or the analysis engine now raises on an input shape it used to handle — both are regressions worth fixing before touching anything else. If a board's *score* or *finding count* silently drifts (test still passes since it only asserts the score is in range, not a specific value), that means a check's behavior changed — expected when a threshold is deliberately tuned, worth double-checking otherwise. Re-run the CLI on the affected board and compare against the description in `examples/README.md`.

## Running the AI validation harness

Unlike the corpus, this needs a real `ANTHROPIC_API_KEY` and makes billed API calls — it is intentionally **not** part of CI.

```sh
# 1. Put your key in backend/.env:  ANTHROPIC_API_KEY=sk-ant-...
# 2. From the repo root:
python backend/scripts/validate_ai.py
```

It runs the real review + chat prompts (`backend/app/ai/review.py`) against five boards — two from the corpus plus three synthetic edge cases (a clean minimal board, a multi-issue board, and a board with adversarial/unicode net names) — and checks the properties that matter for a deterministic-first tool:

- **No hallucinated citations** — every issue ID Claude cites must actually exist in the digest (`find_unsupported_citations`, code-enforced, not just prompted for).
- **The clean board stays clean** — the AI must not invent findings when the deterministic engine reports zero.
- **Low-confidence findings are hedged** — anything below 0.5 confidence must read as "verify this," not as fact.
- **Adversarial net names don't break prompting** — XML-hostile and unicode strings must round-trip safely into the prompt and back.

### Expected output

Every run overwrites two evidence files at the repo root, which are committed (not gitignored) — this is the actual record that the AI layer was validated against the live model, not just the dependency-injected fake client the unit tests use:

- `reports/ai_validation.md` — human-readable table (score/cost/hallucination-count per board) plus the full AI prose for each board
- `reports/ai_validation.json` — the same data structured, plus `schema_version`, the model ID, the git commit/tag the run was against, and per-call token usage and cost

**Interpreting a failure:** the script exits non-zero if *any* board produced an unsupported citation — that's the signal to stop and look at the system prompts in `backend/app/ai/review.py` before shipping, not something to retry past. A hedging check reading "NO -- REVIEW" in the terminal output means a low-confidence finding was stated as fact; treat it the same way. Re-run after any change to the prompts, the digest schema (`backend/app/ai/summarizer.py`), or the model, and recommit the regenerated `reports/` files so the evidence stays current.
