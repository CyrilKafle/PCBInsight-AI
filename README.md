# PCBInsight AI

### PCB Design Review Platform

[![Tests](https://github.com/CyrilKafle/PCBInsight-AI/actions/workflows/tests.yml/badge.svg)](https://github.com/CyrilKafle/PCBInsight-AI/actions/workflows/tests.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![KiCad](https://img.shields.io/badge/KiCad-.kicad__pcb-orange.svg)](https://www.kicad.org/)
[![AI](https://img.shields.io/badge/AI-Claude%20Sonnet%205-8A63D2.svg)](https://www.anthropic.com/)

An AI-augmented engineering design review tool for KiCad PCB projects — a lightweight, local analog of the automated design-review tooling used inside hardware companies (NVIDIA, AMD, Apple, Intel). It does not replace KiCad's Design Rule Check (DRC); it sits a level above DRC, producing the kind of higher-level engineering judgment an experienced PCB reviewer would give in a design review: *why* something could be a problem, *what engineering principle* is involved, a *suggested fix*, a *severity*, and a *confidence level*.

Full design rationale, phased plan, and engineering-check catalogue: [`DESIGN.md`](DESIGN.md).

## Status: Phase 3 complete (AI Engineering Review Layer) + CLI; Phase 4 (web dashboard) next

This is a from-scratch rebuild of what was previously a separate FPGA/PCB robotic-arm project. See [`DESIGN.md`](DESIGN.md) for the full phased plan and [`SKILLS_LOG.md`](SKILLS_LOG.md) for tools/concepts learned as the project progresses.

## What it does

1. **Parse** — drag-and-drop a full KiCad project (`.kicad_pcb`, `.kicad_sch`, netlist, project metadata); the parser builds an internal representation of components, nets, traces, vias, copper pours, footprints, and board dimensions.
2. **Analyze** — run dozens of deterministic engineering checks across routing, power, ground integrity, differential pairs, decoupling placement, component placement, manufacturability, thermal risk, and signal integrity.
3. **AI review** — send a *summarized structured digest* of the board (never raw PCB files) to Claude for a senior-engineer-style narrative review that explains and contextualizes what the deterministic checks found.
4. **Score** — compute an overall 0-100 engineering score plus subscores (routing, power, signal integrity, manufacturability, placement, thermals, documentation), color-coded green/yellow/orange/red.
5. **Report** — generate a professional HTML report (exportable to PDF) with an executive summary, board statistics, engineering metrics, warnings, recommendations, the AI review, and charts/visualizations.

## Architecture

![Architecture diagram](docs/images/architecture.png)

```
backend/    FastAPI service: parser, analysis engine, AI integration, report generation, SQLite storage
frontend/   React + TypeScript + Tailwind dashboard: upload, board visualizations, issue browser, AI chat panel
examples/   Sample KiCad projects used for development and regression-testing the analysis engine
docs/       Architecture notes, screenshots, example reports
```

See [`DESIGN.md`](DESIGN.md) for the full architecture rationale and the catalogue of engineering checks.

## Project metrics

Real numbers, computed from the codebase as of this commit — not estimates:

| Metric | Value |
|---|---|
| Analysis categories | 9 |
| Deterministic checks | 28 |
| Unit tests (all passing) | 120 |
| Lines of Python — `backend/app/` | 2,489 |
| Lines of Python — `backend/tests/` | 1,176 |
| KiCad parser | Custom S-expression parser, 0 `pcbnew`/CAD dependencies |
| Supported input format | KiCad `.kicad_pcb` |
| Interfaces | CLI (`pcbinsight review`, single-board or batch-folder) today; web dashboard in Phase 4 |
| AI model | Claude Sonnet 5 (narrative review layer only — never the analysis engine) |
| Report format | Self-contained HTML (embedded charts, no external assets); PDF export planned for Phase 4 |

## Running it

The CLI is runnable end-to-end today (parse → analyze → score → report); the web dashboard/API is Phase 4, not yet built.

```sh
cd backend
pip install -r requirements.txt

# Analyze one board
python -m app.cli review ../examples/simple_board
# -> simple_board_report.html in the current directory

# Analyze every board in a folder (auto-detected batch mode)
python -m app.cli review path/to/boards/ --out reports/
# -> reports/<board-folder-name>/report.html for each, plus reports/summary.html

# Add --ai to also generate a Claude narrative review (requires ANTHROPIC_API_KEY)
python -m app.cli review ../examples/simple_board --ai

# Or install it as a real `pcbinsight` command:
pip install -e .
pcbinsight review ../examples/simple_board
```

```sh
# Frontend (once Phase 4 lands)
cd frontend
npm install
npm run dev
```

## Roadmap

- **Phase 0 (done):** Hand-rolled S-expression parser for `.kicad_pcb` (no `pcbnew`/KiCad-install dependency), internal Pydantic board model, proven against an `examples/` fixture board with unit tests.
- **Phase 1 (done):** Deterministic engineering-check engine — all nine categories (routing, power, ground, differential pairs, decoupling, placement, manufacturability, thermal, signal integrity) implemented as independent `check(board) -> list[Issue]` modules, orchestrated by `app/analysis/run_all_checks`. 78 tests passing (24 parser + 54 analysis), each check proven on a synthetic bad-case board and silent on a clean one. Manufacturability intentionally covers only trace width / annular ring / via density — silkscreen-over-pad and copper-sliver checks are deferred since the board model doesn't yet capture silkscreen text geometry or full pour polygon shape.
- **Phase 2 (done):** Transparent scoring engine (`app/analysis/scoring.py` — severity-weighted deductions per subscore, overall = average) and a self-contained HTML report renderer (`app/reports/html_report.py`) with embedded matplotlib charts, color-coded score badges, and a full issues table. No AI dependency yet — see [`docs/example_report.html`](docs/example_report.html) for a real generated report off the `examples/simple_board` fixture. 93 tests passing.
- **Phase 3 (done):** AI Engineering Review Layer — `app/ai/summarizer.py` builds a structured digest (scores, a deterministically-computed evidence block, issue list, board statistics; never raw geometry) and `app/ai/review.py` sends it to Claude under a strict system prompt that forbids inventing findings and requires citing issue IDs (e.g. `PWR-004`, assigned by `run_all_checks`). Claude is a technical writer over the deterministic engine's output, never a second analysis engine. `answer_question()` grounds the (Phase 4) AI chat panel the same way. The digest carries a `schema_version`, and `find_unsupported_citations()` code-checks (not just prompt-asks) that any issue ID Claude cites actually exists, logging a warning otherwise. 115 tests passing, all using a dependency-injected fake Anthropic client — no live API key needed to prove the code is correct, since none was available in this environment. See `DESIGN.md`'s "AI Integration Architecture" section for the full spec.
- **CLI (done):** `app/cli.py` — `pcbinsight review <path>` runs the full parse → analyze → score → (optional AI) → report pipeline for one board, or auto-detects a folder of boards and batch-processes all of them into per-board reports plus a `summary.html` index. Installable as a real command via `backend/pyproject.toml`'s `[project.scripts]`. Batch mode catches per-board failures so one malformed `.kicad_pcb` doesn't abort the run. 120 tests passing.
- **Phase 4 (next):** React/TypeScript dashboard (drag-and-drop upload, board visualizations, issue browser, search/filter, AI chat) and PDF export.
- **Stretch:** multi-board comparison, revision history, BOM analysis, Altium/EasyEDA import support, plugin architecture (see `DESIGN.md` for the full stretch list, including the review-session workflow and Design Rule Authoring SDK).
