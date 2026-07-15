# Changelog

All notable changes to this project are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

_Nothing yet._

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
- `find_unsupported_citations()` — code-enforced check that any issue ID Claude cites actually exists in the digest.
- Repo hygiene: `docs/images/architecture.png`, README metrics table (computed, not estimated), `LICENSE` (MIT), this changelog, GitHub Actions CI, and `CLAUDE.md` + `docs/devlogs/` session-continuity docs.

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

- `app/ai/summarizer.py` builds the structured digest sent to Claude: overall/subscores, a deterministically-computed evidence block (severity counts, highest-impact categories, most common recommendation), the issue list (with stable `PWR-004`-style IDs), and board statistics — never raw geometry.
- `app/ai/review.py` sends the digest to Claude under a strict system prompt: no invented findings, cite issue IDs, treat the deterministic engine as authoritative. `answer_question()` grounds the future AI chat panel the same way.
- Issue IDs assigned once per run, in the `run_all_checks` orchestrator, category-prefixed and sequential.
- 115 tests passing, all via a dependency-injected fake Anthropic client (no live API key was available in the dev environment).

## [v0.3.0] — Deterministic review engine complete

- Custom S-expression parser for `.kicad_pcb` (`app/parser/sexpr.py`, `kicad_project.py`) — no `pcbnew`/KiCad-install dependency.
- Internal Pydantic board model (components, nets, traces, vias, copper pours, board dimensions).
- 27 deterministic engineering checks across all 9 categories from `DESIGN.md`'s catalogue (routing, power, ground, differential pairs, decoupling, placement, manufacturability, thermal, signal integrity) — later recounted as 28 (see Unreleased).
- Transparent, severity-weighted scoring engine (`app/analysis/scoring.py`).
- Self-contained HTML report renderer with embedded matplotlib charts (`app/reports/html_report.py`).
- 93 tests passing.
