# Changelog

All notable changes to this project are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed (explicit input boundary, v1.1 item 5)
- **Several boards in one upload are rejected** with an error that lists the `.kicad_pcb` files, instead of reviewing whichever sorted first. KiCad `_autosave-` copies are ignored.
- **Malformed input fails clearly.** Empty, truncated or unbalanced files, files that are not `kicad_pcb` (for example a renamed schematic), unreadable values and non-UTF-8 files raise `BoardParseError`; the API returns 400 with a plain message and the CLI prints it. Before, garbage text or a schematic parsed as an empty board that scored 100/100, and other cases crashed with `IndexError` or `UnicodeDecodeError`.
- **Per-board limitation notes** (`Board.limitations`) for input the parser skips or approximates: curved copper tracks (`arc`), a missing or curved Edge.Cuts outline, a schematic that is not analyzed, and an untested or missing file-format version. They appear in the HTML report, PDF, interactive demo, dashboard and the LLM digest. No board in `examples/` triggers one.
- New `docs/SUPPORTED.md`: tested format version, what is parsed, what is not, and how each gap is reported.
- New `tests/test_input_boundary.py` (23 tests): rotated footprints, a board outline away from the origin (edge distance measured from the real outline), malformed files, multiple boards, autosave copies, each limitation note, and the API responses. Backend tests: 212 passing (2 more cover the CLI error path).

### Changed ("confidence" is labeled as what it is, v1.1 item 4)
- The per-finding `confidence` value is a number from 0 to 1 that each rule's author set by hand. It scales the score deduction; it was never measured against labelled boards. Reports, the PDF, the interactive demo, the dashboard and the landing page now call it **rule weight** and say it is not a probability (the dashboard showed it as a percentage before). No numbers change.
- The field keeps the name `confidence` in the API, the `Issue` model and the LLM digest, so existing payloads stay valid and the LLM prompt is unchanged; `DESIGN.md`, the model and the report legends say that `confidence` is the rule weight.
- New test: no visible text in the HTML report or the interactive demo calls it "confidence", apart from naming the field. Backend tests: 187 passing.

### Changed (coverage-aware scoring, formula v2, v1.1 item 3)
- **Documentation is N/A, not 100.** A subscore that no check feeds now has `score: null`, shows "N/A" in every report, and is left out of the overall score. Before, it counted as a perfect 100 and lifted every board's average.
- **Overall is the mean of the unrounded subscores, rounded once.** Subscores carry an `unrounded` value and reports show the exact arithmetic. Float noise is stripped to 6 decimals before rounding half to even, in both Python and the demo's JavaScript; this fixes a latent mismatch where the JS what-if simulator rounded some x.5 values differently from the engine.
- **`formula_version: 2`** on every score. A score payload without the field is read as v1. The LLM digest moves to schema 2 (`score_formula_version`, `not_evaluated_subscores`; N/A subscores are not sent as numbers).
- **Most severe findings above the score** in the HTML report, the interactive demo, the PDF executive summary and the dashboard (the findings at the highest severity present, up to 3, with a count of the rest).
- **Effect on the corpus:** overall scores fall by 0 to 2 points (`flawed_reference` 83 to 81, `stm32_usb_dev` 98 to 97, `manufacturing_reference` 95 to 94, `mixed_realistic_board` 98 to 97, `thermal_reference` 99 to 98; the others unchanged). `examples/README.md` is updated and says which formula it uses. The try-it demo is regenerated; its AI review text was captured under v1 and still says 98/100. A notice directly above that text (and the overview note) says so. `interactive_report.render()` takes an optional `ai_note` for this.
- New tests: N/A handling, rounding once versus twice on a case where they disagree, top-findings order and cap, v1 payload default, and a node parity test that runs the demo's JS score simulator against `scoring.score()` on 201 random finding sets. Backend tests: 186 passing.

### Changed (citation enforcement, v1.1 item 2)
- The LLM review is now checked before it is shown. `generate_checked_review()` returns a `ReviewResult` with `status` `valid`, `repaired` or `withheld`. A response fails if it cites a finding ID the board does not have, is empty, or stopped for any reason other than finishing normally (for example `max_tokens`). A failed response gets one repair attempt that names the problem and lists the allowed IDs; if that also fails, the text is withheld and only the deterministic findings are shown. Previously an unknown ID was only logged and the text was still returned.
- `/api/review` adds `schema_version` (2) and `ai_review_status`; `ai_error.category` can now be `withheld` with a plain-language reason. The CLI uses the same check and prints a warning when it withholds a review. The dashboard shows the withheld reason.
- Scope of the check: it proves the cited IDs exist and the output was not cut off. It does not prove that every sentence is supported by those findings. `/api/chat` answers are not covered by this change yet (still log-only).
- 12 new tests with a fake client (unknown ID never returned as validated text, repair then pass, at most two calls, truncated and empty output withheld, refusal treated as incomplete, end-to-end API test). Backend tests: 176 passing.

### Changed (LLM failure handling)
- `/api/review` with `include_ai_review` now always returns 200 with the deterministic board, issues and score. If the optional LLM explanation fails, `ai_review` is null and a new `ai_error` object (`category`: `not_configured` or `provider_error`, plus a short message) says why. Previously this was a 502 that discarded the result. `/api/chat` still returns 502 on failure.

### Changed (accuracy of public wording)
- Public docs, the landing page, the demo and report labels now describe the LLM layer as an optional explanation layer, and the claims match current behavior: unknown cited issue IDs are detected and logged, not blocked, and the live AI run covered 5 inputs at v0.5.0. Removed the vendor badge. Model IDs, package names and the `ANTHROPIC_API_KEY` variable are unchanged.
- Architecture diagram label updated to match.
- Internal session-notes files are no longer tracked; the engineering content lives in `DESIGN.md` and `docs/`.

### Changed (interactive demo)
- **"Try it" is now a tabbed, interactive app** (`backend/app/reports/interactive_report.py`, rendered into `docs/try-it-demo.html`). Instead of one long page with anchor links, each tab (Overview, Scores, Findings, AI review, Board, Try it) is its own view, with a back button on every view, previous/next buttons, a landing-page link, browser back/forward support (hash routing) and arrow-key tab navigation. Every view opens with a plain-language "What is this?" box; findings can be filtered by severity, area and confidence and expanded or collapsed; a glossary defines the PCB terms.
- **What-if score simulator**: tick findings as fixed and the subscores recompute live using the exact `scoring.py` formula (half-to-even rounding matches Python).
- **Rule checker**: enter numbers (trace width, via pad and drill, capacitor distance, differential pair lengths, via density, and more) and see whether the engine would flag them, at what severity and confidence, and how many points it would cost; add the result to the what-if score. Thresholds are imported from the engine modules, not retyped.
- **Board map**: an SVG of the parsed board (parts, traces, vias, pours) with every finding pinned at its location, layer toggles, and a Show on board link from each finding.
- `backend/tests/test_interactive_report.py` (9 tests): view structure, escaping, script-tag safety, and a parity test that runs the checker's JavaScript under node against the real Python check functions on 122 cases. Backend tests: 159 passing.

### Changed
- **Report redesign** (`backend/app/reports/html_report.py`): the HTML report now uses the landing page's dark design system (IBM Plex Sans / JetBrains Mono, teal accent, purple reserved for AI content). Charts are native HTML bars instead of matplotlib PNGs (the PDF export still uses the matplotlib renderers). Findings with identical explanation and fix are grouped into one card. The AI review's markdown is rendered, and a cut-off trailing sentence is omitted with a note.
- **Score derivation shown in the report**: a "How the score is computed" block lists each deduction (severity points x confidence), reconciles every subscore and the overall mean, and defines what confidence is and is not. `scoring.py` now exposes `deduction`, `severity_points` and `subscore_for` for this; scoring behaviour is unchanged.
- Removed em dashes from three check explanations (decoupling, power, routing) and rewrote the demo banner to state that `stm32_usb_dev` is synthetic test data.
- Independent review loop: six rounds of external grading (74, 82, 84, 85, 87, 90) drove these changes.

### Added
- **"Try it" demo** (`docs/try-it-demo.html`), linked from the landing page nav and as the primary hero CTA — a real, unedited report for `examples/stm32_usb_dev`. `backend/scripts/generate_try_it_demo.py` re-runs the deterministic pipeline locally and reuses the AI review text already captured in `reports/ai_validation.json`, so regenerating it makes zero new LLM API calls. Carries a disclosure banner explaining what it is and linking back to the landing page and repo.
- **Demo GIF** (`docs/images/demo/demo.gif`), embedded at the top of the landing page's dashboard showcase — six real, screen-captured frames from a live run against `examples/stm32_usb_dev` (upload, deterministic score + AI review, board visualization, an expanded issue, a real AI chat answer, and PDF export). No synthetic or AI-generated visuals.

### Security
- Ran a real audit, not just a claim: `.env`/secrets were never committed (checked git history), no `eval`/`exec`/`pickle`/`shell=True` anywhere in the codebase, `npm audit` and `pip-audit` (against an isolated venv scoped to `backend/requirements.txt`, not the noisy global Python install) both report zero known vulnerabilities in every dependency the app actually uses.
- `.github/workflows/tests.yml` now declares `permissions: contents: read` explicitly instead of relying on the repo-default GITHUB_TOKEN scope.

## [v1.0.0] — 2026-07-16 — Engineering complete + public landing page

v1.0.0: the deterministic engine, AI review layer, validation corpus, live AI validation, and public-facing landing page are all complete. This is the first tagged release with a public site.

### Added
- `docs/ENGINEERING_DECISIONS.md` — the "why" behind the major architectural calls (deterministic-first, the AI can't-invent-findings boundary, code-enforced citations, the custom parser, the validation corpus, AI validation staying out of CI, transparent scoring over benchmark scores).
- **Landing page** (`docs/index.html`), **live at https://cyrilkafle.github.io/PCBInsight-AI/** (GitHub Pages enabled, served from `/docs`): dark-mode-first static page with a real design system (`docs/design-system.md` — IBM Plex Sans + JetBrains Mono, teal accent kept distinct from the AI-purple already used in the architecture diagram). Every screenshot is genuine output from a live run against `examples/stm32_usb_dev` (including a real the LLM review and a real chat answer) — no mockups.
- README: screenshot gallery (4 real dashboard images), a landing-page badge + link, recomputed metrics.
- **Live AI validation harness** (`backend/scripts/validate_ai.py`) — runs the real review/chat prompts against the live LLM API, tracks token usage and cost per call, and writes `reports/ai_validation.md`/`.json` as committed evidence (git commit/tag, per-board cost, hallucination check) that the AI layer was validated against a real model, not just the fake test client.
- `return_usage` flag on `generate_review()`/`answer_question()` (`backend/app/ai/review.py`) — opt-in token-usage capture with zero change to existing call sites.
- **Engineering Validation Corpus**: seven new purpose-built KiCad boards under `examples/` — `high_quality_reference` (clean board, 100/100, zero findings), `rf_clock_board` (signal-integrity + differential-pair focus), `power_supply_board` (power/decoupling focus), `thermal_reference` (thermal focus), `manufacturing_reference` (DFM focus), `parser_edge_cases` (unicode/escaped-quote/hostile-character parser stress test), and `mixed_realistic_board` (a believable "mostly good, a few real mistakes" board) — plus `flawed_reference` (committed for the first time). Ten boards total, each demonstrating exactly one thing; see `examples/README.md`.
- `docs/VALIDATION.md` — how the deterministic engine and the AI layer are each validated, and how to interpret a failure in either.
- `test_corpus_board_parses_and_scores_without_error` — regression guard parametrized over every board in the corpus.

### Changed
- `examples/README.md` reframed as the "Engineering Validation Corpus" with a per-board purpose table.
- Extracted `backend/app/reports/theme.py`: score-color bands, severity order/colors, and `score_color()` now live in one shared module instead of `pdf_report.py` importing `html_report.py`'s private (underscore-prefixed) state. `html_report.py`'s chart renderers are now public (`render_subscore_chart`/`render_severity_chart`) since another module legitimately imports them.
- README metrics table recomputed against the current codebase (147 tests, 2,957/1,386 LOC).

### Removed
- Unused frontend dependencies `plotly.js-dist-min` and `d3` (zero usages in `frontend/src` — the dashboard's charts are hand-rolled SVG).

### Changed (docs)
- Regenerated `docs/images/architecture.png` to reflect the full current pipeline (AI chat, board visualization, PDF export, the CLI as an alternate entry point) — it previously predated all three. Now backed by a real, editable source for the first time: `docs/images/architecture.mmd` (Mermaid) and `docs/images/architecture.excalidraw`.

## [v0.5.0] — 2026-07-14 — Phase 4 dashboard: board visualization, AI chat, PDF export

Completes Phase 4: a local FastAPI + React dashboard with an interactive board viewer, a grounded AI chat panel, and PDF export, plus the CLI and repo hygiene accumulated since v0.4.0. 135 backend tests passing; the full dashboard is verified end-to-end in a real browser.

### Added
- **FastAPI backend** (`app/main.py`, local-only): `POST /api/review`, `POST /api/chat`, `POST /api/report/pdf`.
- **React/TS/Tailwind dashboard**: drag-and-drop/folder upload, color-coded overall/subscore cards, and a searchable/filterable issue browser with expandable "why it matters" cards.
- **Interactive SVG board visualization**: board outline, copper pours, per-layer traces, vias, and components, with scroll-to-zoom, drag-to-pan, per-layer/component/via/label toggles, and severity-colored issue markers that cross-highlight the issue browser (click a marker to open its card, and vice versa).
- **Net-length histogram** and **issue-by-category chart**.
- **Grounded AI chat panel** — `POST /api/chat` reuses the Phase 3 `answer_question()`; conversation history is client-side; degrades gracefully when no API key is configured.
- **PDF report export** — `POST /api/report/pdf` via `app/reports/pdf_report.py` (ReportLab), reusing the HTML report's charts and score-color logic, with a page-numbered footer; "Download PDF" button in the dashboard.
- **CLI** (`app/cli.py`): `pcbinsight review <path>` single-board + auto-detected batch mode (`summary.html` index); packaged via `pyproject.toml` (`pip install -e .`).
- `find_unsupported_citations()` — code-enforced check that any issue ID the LLM cites actually exists in the digest.
- Repo hygiene: `docs/images/architecture.png`, README metrics table (computed, not estimated), `LICENSE` (MIT), this changelog, GitHub Actions CI, and `docs/devlogs/` session-continuity docs.

### Changed
- AI review system prompts tightened: every recommendation must be backed by a supplied issue; low-confidence findings must be explicitly hedged.
- Digest (`app/ai/summarizer.py`) now carries a `schema_version` field.
- Consolidated frontend severity ordering/colors into a single `src/severity.ts`.
- Corrected a stale "27 deterministic checks" figure to the actual count (28).

### Fixed
- Incomplete upload-filename guard: a bare `..` slipped the empty-name check (`Path("..").name` is `".."`, not `""`) and could target the temp directory itself (HTTP 500); now any name resolving to `.`/`..` falls back to a safe name. Regression-tested.
- Net-length histogram bars rendering at ~0px (percentage height against an auto-height parent); now deterministic pixel heights.
- Board view letterboxing; the SVG now fills the panel.

### Security
- Uploads are streamed to disk against a 50 MB total budget (413 before buffering) with a 100-file cap — resource-exhaustion guards for the local tool.
- Upload filenames flattened to their basename to defeat `../` path traversal; chat question length capped.
- CORS scoped to the local Vite dev origin, not wildcarded.
- AI failures (including a missing `ANTHROPIC_API_KEY`) map to a clean 502 instead of a raw 500 traceback.

## [v0.4.0] — AI Engineering Review Layer complete

- `app/ai/summarizer.py` builds the structured digest sent to the LLM: overall/subscores, a deterministically-computed evidence block (severity counts, highest-impact categories, most common recommendation), the issue list (with stable `PWR-004`-style IDs), and board statistics — never raw geometry.
- `app/ai/review.py` sends the digest to the LLM under a strict system prompt: no invented findings, cite issue IDs, treat the deterministic engine as authoritative. `answer_question()` grounds the future AI chat panel the same way.
- Issue IDs assigned once per run, in the `run_all_checks` orchestrator, category-prefixed and sequential.
- 115 tests passing, all via a dependency-injected fake LLM client (no live API key was available in the dev environment).

## [v0.3.0] — Deterministic review engine complete

- Custom S-expression parser for `.kicad_pcb` (`app/parser/sexpr.py`, `kicad_project.py`) — no `pcbnew`/KiCad-install dependency.
- Internal Pydantic board model (components, nets, traces, vias, copper pours, board dimensions).
- 27 deterministic engineering checks across all 9 categories from `DESIGN.md`'s catalogue (routing, power, ground, differential pairs, decoupling, placement, manufacturability, thermal, signal integrity) — later recounted as 28 (see Unreleased).
- Transparent, severity-weighted scoring engine (`app/analysis/scoring.py`).
- Self-contained HTML report renderer with embedded matplotlib charts (`app/reports/html_report.py`).
- 93 tests passing.
