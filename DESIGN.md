# Design: AI PCB Design Review Platform

Status: APPROVED (pivoted from a prior FPGA/PCB robotic-arm project on 2026-07-13)

## Problem Statement

Build a professional-quality software project for an electrical engineering / ASIC / PCB engineering resume that is *not* a chatbot wrapper around an LLM. The tool should automatically analyze KiCad PCB projects and generate an engineering design review report — mimicking the kind of higher-level review an experienced PCB engineer gives, which goes beyond what KiCad's own Design Rule Check (DRC) catches.

The differentiator over "just another AI PCB assistant": the deterministic engineering-analysis engine is the core of the project. AI augments that analysis with narrative judgment — it never replaces it, and it never sees raw PCB files, only a structured summary. This needs to be legible to a reviewer as real software engineering plus real PCB engineering knowledge, not prompt engineering.

## Why this replaces the prior project

The prior project (SiliconArm, an FPGA-controlled robotic arm on a custom PCB) required physical purchases, PCB fabrication turnaround (JLCPCB transit, historically the schedule risk flagged in that project's own design doc), and in-person hardware bring-up. This project is fully software, runs entirely locally, and can be finished end-to-end through Claude Code without waiting on shipping or lab time — a better fit for the timeline before internship applications. Phase 0 of the prior project (closed-loop control simulation) is preserved in git history if ever useful for reference, but is no longer the active project.

## What Makes This Cool

A tool that reads like something an actual hardware company would run in CI against every PCB submission — not a toy. The judgment call that makes it read as *engineering* rather than *AI demo*: dozens of deterministic checks (routing quality, power/ground integrity, decoupling placement, manufacturability, thermal risk, signal integrity) run first and produce structured, severity-ranked findings; Claude is only invoked afterward, on a compact structured digest of those findings plus board statistics, to produce the kind of narrative synthesis a senior engineer would write in a review comment. The AI never sees raw geometry — this is a defensible, explainable design decision worth being able to discuss in an interview.

## Constraints

- Must not read as "LLM wrapper" — the deterministic analysis engine must be substantial and independently valuable (i.e., useful even with the AI step disabled).
- Runs entirely locally: Python/FastAPI backend, React/TypeScript/Tailwind frontend, SQLite storage. No required cloud services other than the Claude API call itself.
- Must support real KiCad project files (`.kicad_pcb`, `.kicad_sch`, netlists, project metadata) parsed via KiCad's own Python tooling — not a hand-rolled format guess.
- AI analysis step must operate on a *summarized structured digest* (board size, layer count, trace statistics, via count, power/ground nets, detected problems, component summary, routing metrics, clock nets, connector locations, power tree) — never raw PCB files — both for cost/latency reasons and because that boundary is itself the interesting architectural decision to defend.
- Report output must be a professional HTML report, exportable to PDF (ReportLab), with charts (Matplotlib/Plotly) — this is a portfolio artifact, so the output quality matters as much as the analysis quality.
- Timeline: shorter and lower-risk than the prior project since there's no physical fabrication step; still executed in phases so there's always a working, demoable state, never an all-or-nothing finish line.

## Engineering Check Catalogue (Phase 1 scope)

Organized into categories, each producing structured `Issue` objects (category, severity, confidence, explanation, principle, suggested fix, board location):

- **Routing:** unnecessarily long traces, excessive bends, acute angles, excessive via count, inconsistent routing style, stubs/dead-ends.
- **Power:** thin power traces relative to estimated current, daisy-chained power distribution, weak power routing, poor decoupling placement, long supply paths.
- **Ground:** ground fragmentation, poor return paths, disconnected pours, ground islands/loops, current bottlenecks.
- **Differential pairs:** length matching, parallel routing, spacing consistency, via symmetry.
- **Decoupling capacitors:** auto-identify MCUs/FPGAs/ICs, measure distance from VCC pins, judge placement quality and connection efficiency.
- **Placement:** connectors far from board edge, crowded regions, large unused board space, poor functional-block grouping, rotated components that complicate routing.
- **Manufacturability:** minimum spacing/trace-width violations, silkscreen-over-pad conflicts, clipped text, copper slivers, small annular rings, high via density.
- **Thermal:** high-current regulators/MOSFETs/power ICs, thermal congestion, insufficient copper pour near power devices.
- **Signal integrity:** high-speed net identification, clock routing quality, stub length, branch points, unnecessary vias on critical nets.

## Scoring

Overall Engineering Score (0-100) plus subscores: Routing, Power, Signal Integrity, Manufacturability, Placement, Thermals, Documentation. Color-coded green/yellow/orange/red thresholds. Subscores are simple weighted aggregates of per-category issue severity — deliberately transparent/explainable rather than a black-box ML score, since "how was this score computed" needs a clean answer in an interview.

## AI Integration Architecture (Phase 3) — "AI Engineering Review Layer" (DONE)

Operating name for this feature is **AI Engineering Review Layer**, not "AI Integration" — the framing matters: Claude is a technical writer over the deterministic engine's output, never a second analysis engine. Implemented in `app/ai/summarizer.py` (digest) and `app/ai/review.py` (Claude calls), with 21 tests covering the digest shape, the raw-geometry boundary, and prompt/citation behavior via a dependency-injected fake client. Concretely:

- **Issue IDs.** Every `Issue` gets a stable, category-prefixed ID (e.g. `PWR-004`, `SIG-003`), assigned once per report generation in the orchestrator (`app/analysis/__init__.py`'s `run_all_checks`, not per check module, so numbering stays consistent across categories regardless of which checks fired). This is a real `Issue` model change, not just a display trick — makes every AI sentence traceable back to a specific deterministic finding.
- **Evidence-grounding block, computed deterministically — never by Claude.** Computed in `app/ai/summarizer.py`'s `_evidence()`: severity counts, highest-impact categories (subscores below 90, worst-first, capped at 3), most common recommendation (most frequent `suggested_fix` string among the issues). Travels in the digest alongside the raw issues; Claude synthesizes from it rather than inventing its own summary statistics.
- **Strict system prompt** (`REVIEW_SYSTEM_PROMPT` in `review.py`): "You are acting as a senior PCB design reviewer. You are NOT performing design analysis... Do not invent problems or recommendations that are not supported by the supplied data. Reference issue IDs... when discussing specific findings. Every recommendation you make must be directly supported by at least one supplied issue — if the evidence is insufficient to draw a conclusion, say so explicitly rather than guessing. When an issue's confidence value is low (below 0.5), say so and note that it should be manually verified rather than treated as certain." The chat prompt (`CHAT_SYSTEM_PROMPT`) carries the same grounding and confidence-hedging requirements for the (Phase 4) AI chat panel.
- **Digest shape sent to Claude** — never the board, never raw files. Carries a `schema_version` field so a future field rename/addition can't silently desync the prompt from what the digest actually contains:
  ```json
  {
    "schema_version": 1,
    "overall_score": 78,
    "subscores": {"routing": 63, "power": 55, "thermal": 94},
    "evidence": {
      "severity_counts": {"critical": 5, "medium": 12, "low": 4},
      "highest_impact_categories": ["power", "signal_integrity"],
      "most_common_recommendation": "Reduce unnecessary vias in clock routing"
    },
    "issues": [{"id": "PWR-004", "category": "power", "severity": "high", "confidence": 0.42, "summary": "..."}],
    "statistics": {"component_count": 42, "net_count": 18}
  }
  ```
- **Traceability requirement, enforced in code, not just prompt.** `review.find_unsupported_citations(review_text, digest)` regex-extracts issue-ID-shaped tokens (`[A-Z]{2,6}-\d{3}`) from Claude's output and diffs them against the digest's real issue IDs. `generate_review`/`answer_question` call this automatically and log a warning (not a hard failure — the review is still usable, but the mismatch is now observable) if the model cites an ID that doesn't exist. Same defense-in-depth pattern as the raw-geometry boundary: a prompt instruction plus a code-enforced check behind it, not one or the other alone.

## Approaches Considered

### Approach A: Deterministic-only tool, AI as a stretch layer
Effort: M | Risk: Low
Pros: Fully defensible, no LLM cost/latency dependency, still a strong portfolio piece on its own.
Cons: Loses the "thoughtful AI application" story the user explicitly wants to be able to discuss.

### Approach B: Deterministic engine core + AI narrative synthesis layer — CHOSEN
Summary: Build the full deterministic analysis engine first (Phases 0-2, no AI dependency), prove it works and is useful standalone, then add Claude as a synthesis/narrative layer on top of structured findings (Phase 3), plus an optional AI chat panel that answers questions grounded in the uploaded board's actual findings.
Effort: L | Risk: Med
Pros: Reads as genuine engineering + thoughtful, bounded AI use; each phase is independently demoable; the deterministic-engine-first sequencing is itself a good interview answer to "how did you scope AI into this."
Cons: More total scope than Approach A; requires discipline not to let the AI layer become a crutch for weak deterministic checks.

### Approach C: Full-scope build in one pass (parser + all checks + AI + full React dashboard + PDF export simultaneously)
Effort: XL | Risk: High
Pros: If it lands, most impressive single deliverable.
Cons: No working intermediate state — high risk of an unfinished, unpolished project if time runs short; violates the "always have a demoable state" principle that worked well in the prior project's phased approach.

## Recommended Approach

**Approach B, executed in five gated phases** (mirrors the prior project's discipline of "always bank a working deliverable before adding the next layer"):

**Phase 0 — Parser + internal board model.** Build the KiCad project parser (locate `.kicad_pcb`/`.kicad_sch`/netlist/project files automatically; extract components, nets, traces, vias, copper pours, footprints, board dimensions using KiCad's Python libraries) into clean Pydantic models. Prove it against a handful of real example KiCad projects in `examples/` with unit tests. No analysis, no AI, no UI yet — get the data model right first, since every later phase depends on it.

**Phase 1 — Deterministic engineering-check engine. (DONE)** Implemented the full check catalogue above as independent, testable analysis modules, each emitting structured `Issue` objects (severity, confidence, explanation, principle, suggested fix). This is the substantial, AI-independent core of the project's engineering-credibility story. One documented scope reduction: manufacturability's silkscreen-over-pad/copper-sliver checks were dropped in favor of what the current board model can actually support (trace width, annular ring, via density) — see `backend/app/analysis/manufacturability.py`'s docstring.

**Phase 2 — Scoring + first HTML report. (DONE)** Aggregated issues into the overall/subscore engineering scores; rendered a first professional, self-contained HTML report (board stats, warnings, recommendations, embedded matplotlib charts) with no AI involved yet, proving the deterministic pipeline end-to-end before adding any LLM dependency. See `docs/example_report.html` for a real generated example, visually verified via a Playwright screenshot rather than tests alone.

**Phase 3 — AI integration ("AI Engineering Review Layer"). (DONE)** Built the board-state summarizer (`app/ai/summarizer.py`, structured digest, not raw files) and the Claude-based narrative review layer (`app/ai/review.py`) per the architecture above (issue IDs, evidence-grounding block, strict system prompt, issue-ID traceability); `answer_question()` grounds the optional AI chat panel in the same digest so answers reference the actual uploaded board rather than generic explanations. Tested via a dependency-injected fake Anthropic client (no `ANTHROPIC_API_KEY` was available in this dev environment) — proves prompt construction and the raw-geometry boundary are correct without needing a live API call.

**Phase 4 — React/TypeScript dashboard.** Drag-and-drop upload, animated analysis progress, summary cards, board visualizations (routing/via/power-density heatmaps, net-length histograms, layer utilization), issue browser with search/filter (by refdes, net name, category), clickable board locations, and PDF export via the backend's ReportLab pipeline.

**Stretch (post-Phase 4):** multi-board comparison, revision history/git integration, BOM analysis, Altium/EasyEDA import support.

**Stretch — Phase 5: Design Rule Authoring SDK.** Replace the hardcoded `_CHECK_MODULES` list in `app/analysis/__init__.py` with dynamic discovery: define a `Check` base class/protocol (`name`, `run(board) -> list[Issue]`), drop check implementations into a `checks/` directory, and have the engine auto-discover and load every module there at startup. Lets third parties add a custom check (e.g. `my_signal_integrity_check.py`) without touching engine code. Demonstrates plugin-architecture/dynamic-module-loading/inversion-of-control design — genuinely interesting to build, but deliberately sequenced after Phases 2-4 so there's always a demoable, working state first.

**Stretch — Rule Explanation UI.** A "Why does this matter?" affordance on each issue card in the Phase 4 dashboard. Mostly already satisfied by the existing `Issue` model (`backend/app/models/issue.py`), which already carries both `explanation` ("why this matters") and `principle` (the engineering principle involved) on every issue emitted by every Phase 1 check — this is UI surfacing of data that already exists, not new backend logic. Confirms the `Issue` schema was designed right the first time.

**Stretch — Structured threshold/measured-value drill-down.** A step beyond the Rule Explanation UI above: clicking an issue shows *Threshold* (e.g. "expected < 25mm"), *Measured* (e.g. "62mm"), and the formula/logic used, not just prose. This requires a real model change the current `Issue` doesn't have — `measured_value: float | None` and `threshold_value: float | None` fields populated by each check module alongside the existing free-text `explanation`. Worth doing once there's a UI to show it (Phase 4), since it turns the deterministic engine into something closer to what commercial EDA review tools expose.

**Stretch — Design History Comparison.** Upload two revisions of the same board (`Board_v1.kicad_pcb`, `Board_v2.kicad_pcb`) and diff them: subscore deltas (e.g. Routing 72→88, Power 61→90), issues fixed vs. newly introduced, via count delta, total trace length change, ground pour coverage change. Mirrors an actual PCB design review workflow (comparing revisions) more directly than any single-board feature does — high demo value, but real scope: needs a diffing layer that matches components/nets across two independently-parsed boards, which isn't trivial when refdes or net names shift between revisions.

**Stretch — Review-session workflow.** Instead of a static report, let an engineer mark each issue Fixed / Ignored / False Positive on the dashboard, and recompute the score live as issues get dispositioned — closer to an internal engineering review tool than a one-shot report generator. Needs persistence (the `db/` SQLite layer already scaffolded but unused) and a real API surface (Phase 4's job), so this is naturally sequenced after the dashboard exists, not before.

**Stretch — Phase 4 visual direction.** Dashboard should read as professional engineering software, not a marketing site: dark theme, dense information layout, tables/filters/search, expandable issue cards, minimal animation — closer to GitHub/Linear/JetBrains IDEs/KiCad 8 than a typical AI-demo landing page. No glassmorphism, no large gradients. Noted here so it's a decision made in the design doc before Phase 4 starts, not an afterthought once component code already exists.

## Folder Structure

```
backend/
  app/
    parser/        KiCad project + file parsing (Phase 0)
    models/         Pydantic schemas: Board, Component, Net, Trace, Via, Issue, Score
    analysis/       Engineering check modules, one per category (Phase 1)
    reports/        HTML/PDF report generation (Phase 2)
    ai/             Board-state summarizer + Claude integration + chat (Phase 3)
    db/             SQLite persistence
    main.py         FastAPI app
  tests/
  requirements.txt
frontend/            React + TypeScript + Tailwind dashboard (Phase 4)
examples/            Sample KiCad projects for development/regression testing
docs/                Architecture notes, screenshots, example reports
```

## Success Criteria

- Phase 0 complete: parser correctly extracts components/nets/traces/vias/pours/footprints/board dimensions from real KiCad example projects, covered by unit tests.
- Phase 1 complete: check engine produces structured, severity-ranked issues across all nine categories on a real example board, with unit tests per category.
- Phase 2 complete: a generated HTML report with real scores/charts from a real board, no AI dependency.
- Phase 3 complete: AI narrative review reads as specific engineering commentary on the actual uploaded board, not generic text; chat panel answers reference the board's real findings.
- Phase 4 complete: a polished local dashboard a reviewer could plausibly mistake for an internal company tool; PDF export works.
- A public solo GitHub repo with commit history showing the phase-by-phase build, discussable in terms of architecture, parsing approach, engineering heuristics, and the AI-augments-not-replaces boundary.
- Running skills-log (`SKILLS_LOG.md`) tracking new tools/concepts learned, feeding resume updates into the InternPilot project.

## Open Questions

- ~~Exact KiCad Python parsing approach~~ — resolved at Phase 0 start: hand-rolled S-expression parsing (`backend/app/parser/sexpr.py` + `kicad_project.py`), no `pcbnew`/KiCad-install dependency. `pcbnew` bindings weren't even available on the dev machine, which settled it in practice; the "runs anywhere, zero extra deps" story and the more original parsing work were the deciding factors either way.
- How many example KiCad boards to curate for development/testing, and whether to include intentionally-flawed boards (to prove specific checks fire correctly) vs. only clean reference boards.
- Whether the AI chat panel needs conversation memory across a session or can be stateless per-question (grounded in the same board digest each time) — decide during Phase 3.
