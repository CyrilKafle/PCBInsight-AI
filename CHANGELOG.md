# Changelog

All notable changes to this project are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- CLI (`backend/app/cli.py`): `pcbinsight review <path>` for a single board, with auto-detected batch mode for a folder of board projects (per-board reports plus a `summary.html` index). Packaged via `backend/pyproject.toml` so `pip install -e .` gives a real `pcbinsight` command.
- `docs/images/architecture.png`, a rendered pipeline diagram.
- README project-metrics table, computed from the codebase rather than estimated.
- `LICENSE` (MIT), this changelog, and a GitHub Actions workflow running the test suite on every push/PR.

### Changed
- AI review system prompts tightened: every recommendation must be backed by a supplied issue, and low-confidence findings must be explicitly hedged.
- `app/ai/summarizer.py`'s digest now carries a `schema_version` field.
- Corrected a stale "27 deterministic checks" figure to the actual count (28) throughout the docs.

### Added (validation)
- `app/ai/review.find_unsupported_citations()` — code-enforced check that any issue ID Claude cites in its review actually exists in the digest, logging a warning on mismatch rather than only relying on the system prompt.

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
