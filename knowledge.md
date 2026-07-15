# PCBInsight AI — Project Knowledge File

Purpose of this file: a complete, current snapshot of the project for an outside reviewer (ChatGPT) to read and then propose the next work session's step-by-step plan. Everything below is factual and verified as of 2026-07-14.

> **Session continuity note:** `CLAUDE.md` at the repo root auto-loads every Claude Code session and points here. Keep this file current at the end of each session so a fresh session inherits state with zero re-discovery.

---

## 1. What the project is

**PCBInsight AI** — an automated PCB design review platform for KiCad projects. It parses `.kicad_pcb` files with a custom parser, runs 28 deterministic engineering checks across 9 categories, computes a transparent 0–100 engineering score, and generates professional HTML reports. Claude AI sits on top as a strictly-bounded "technical writer" layer that narrates the deterministic findings — it never analyzes the board itself and never sees raw geometry.

- **Repo (public):** https://github.com/CyrilKafle/PCBInsight-AI (renamed from the pre-pivot `SiliconArm`; description updated)
- **Owner:** Cyril Kafle, undergraduate, building this as the centerpiece resume project for EE/PCB/EDA/embedded internships
- **Positioning (decided, locked in DESIGN.md):** personal tool, *not* a public multi-tenant service. No public upload endpoint (Claude API cost + unhardened parser = two real reasons). Interview narrative: "I design PCBs as a hobby in KiCad and built my own AI-augmented reviewer to check them before fab — I built the reviewer myself." GitHub repo is the public artifact; interested parties email for access/demo.

## 2. Architecture (all implemented and working)

```
KiCad Project (.kicad_pcb)
  → S-Expression Parser (custom, zero pcbnew/CAD dependencies)  [backend/app/parser/sexpr.py, kicad_project.py]
  → Internal Board Model (Pydantic: components, nets, traces, vias, pours)  [backend/app/models/board.py]
  → Deterministic Analysis Engine — 9 category modules, 28 checks  [backend/app/analysis/*.py]
  → Issue list (each: id like PWR-004, severity, confidence, explanation, engineering principle, suggested fix, refs, board location)
  → Transparent Scoring (severity×confidence deductions from 100; overall = average of 7 subscores)  [analysis/scoring.py]
  → ├─ Self-contained HTML report (embedded matplotlib charts, XSS-escaped)  [reports/html_report.py]
    ├─ Structured AI Digest (schema_version, evidence block, issues, stats — NO raw geometry, test-enforced)  [ai/summarizer.py]
    │    → Claude review under strict system prompt + code-enforced citation validation  [ai/review.py]
    ├─ CLI: `pcbinsight review <path>` single-board + auto-detected batch folder mode  [app/cli.py]
    └─ FastAPI `POST /api/review` + React/TS/Tailwind dashboard (local-only)  [app/main.py, frontend/src/]
```

Architecture diagram image: `docs/images/architecture.png` (also embedded in README).

## 3. Phase status

| Phase | Status | Notes |
|---|---|---|
| 0 — Parser + board model | DONE | Hand-rolled S-expression parser chosen over `pcbnew` bindings (portability + more original work; pcbnew wasn't even installable here). Fixture board hand-authored in `examples/simple_board/`. |
| 1 — Deterministic check engine | DONE | 9 modules: routing, power, ground, differential pairs, decoupling, placement, manufacturability, thermal, signal integrity. 28 individual checks, explicit named thresholds (no ML). Documented scope cut: silkscreen-over-pad / copper-sliver checks skipped (board model lacks that geometry). |
| 2 — Scoring + HTML report | DONE | Transparent deduction scoring; self-contained HTML report w/ base64 matplotlib charts; visually QA'd via Playwright screenshot, example at `docs/example_report.html`. |
| 3 — AI Engineering Review Layer | DONE | Digest has `schema_version`; evidence block (severity counts, highest-impact categories, most common recommendation) computed in Python, never by Claude; strict system prompt (no invented findings, must cite issue IDs, hedge low-confidence <0.5); `find_unsupported_citations()` code-checks cited IDs against real ones and logs warnings. All tested via dependency-injected fake Anthropic client (no API key in dev env — plumbing proven, live prose quality not yet observed). |
| CLI (bonus, pre-Phase-4) | DONE | Single + batch mode, `pip install -e .` gives real `pcbinsight` command via pyproject. Batch keyed by folder name (not board name) to avoid collisions; per-board failure isolation. |
| 4 — Dashboard | **DONE (all Phase 4 features)** | Backend `POST /api/review` (multipart upload, streamed/capped uploads, path-traversal guard, CORS scoped). React dashboard: upload, score cards, searchable/filterable issue browser. **Now also done (session 2026-07-14, Opus):** (a) **AI chat panel** — `POST /api/chat` reuses `answer_question()` (stateless, client sends back board/issues/score; history client-side; graceful 502 when no key), `ChatPanel.tsx` with loading/suggestions/in-thread error. (b) **Board visualization** — `BoardView.tsx` SVG (outline/pours/traces-by-layer/vias/components), scroll-zoom + drag-pan, layer/component/via/label toggles, severity-colored issue markers with two-way cross-highlight to the issue browser; plus `NetLengthHistogram.tsx` and `IssueCategoryChart.tsx`. (c) **PDF export** — `POST /api/report/pdf` via `app/reports/pdf_report.py` (reuses html_report's charts + score-color logic, escapes all text, page-numbered footer), "Download PDF" button. All verified end-to-end in a real browser (gstack browse) against the running backend, no console errors. |
| Landing page | NOT STARTED | Decided: static professional page (GitHub/Linear/JetBrains aesthetic — dark, dense, no glassmorphism/gradients; NOT 3D/interactive — argued and user accepted). Dashboard is now feature-complete, so screenshots can be real. Could be served free via GitHub Pages from `/docs`. **This is the top candidate for the next session.** |

## 4. Verified state right now (end of session 2026-07-14, Opus)

- **Backend: 135/135 tests passing** (pytest, ~3s) — was 127; +8 new tests in `tests/test_api.py` covering the `/api/review` hardening, `/api/chat`, and `/api/report/pdf`.
- **Frontend: `tsc -b` clean + `npm run build` succeeds** (React 18 + TS + Vite + Tailwind).
- **No secrets in repo**; `.env` gitignored; still **no ANTHROPIC_API_KEY in the dev env** (AI paths tested via fake client / verified to return graceful 502 live).
- **CI live:** GitHub Actions runs pytest on every push to master.
- **8 unpushed commits on `master`** (ahead of `origin/master`). Last pushed commit is still `c5c8249`. **Nothing pushed this session** — see "next session" below. New commits, oldest first: backend hardening → `/api/chat` → dashboard frontend → board viz → viz fixes → PDF export → polish → severity dedup.
- **`CLAUDE.md`** (new, untracked) auto-loads each session and points at this file; **`knowledge.md`** kept current (this file).

### What this session did (2026-07-14, Opus 4.8)
- **Verified + hardened `/api/review`** and found a *real* incomplete-fix bug: the "." / ".." upload-name guard let bare `..` through (`Path("..").name` is `".."`, not `""`), which would write to the temp dir itself (500). Fixed + regression-tested.
- Built all three remaining Phase 4 features (chat, board viz, PDF) + a polish pass, each committed as its own checkpoint and browser-verified.
- Ran a final AI-smell review: consolidated triplicated frontend severity ordering/colors into `src/severity.ts`. Considered-and-kept: `pdf_report.py` importing a few underscore-private helpers from `html_report.py` (same package, documented, and the alternative is duplicating the matplotlib chart code) — a candidate for extracting a shared `app/reports/theme.py` later if desired.

## 5. Repo hygiene (all done)

MIT LICENSE · CHANGELOG.md (Keep-a-Changelog style, real release notes for v0.3.0/v0.4.0 + Unreleased) · GitHub Actions CI · README badges (live Tests badge + static Python/MIT/KiCad/Claude) · real-numbers metrics table in README (28 checks — corrected from a stale "27" that had propagated) · architecture diagram · CLI usage docs · `docs/ARCHITECTURE.md`.

Deliberately skipped (with reasoning): CONTRIBUTING.md (solo repo, reads as boilerplate), ROADMAP.md (DESIGN.md already is one; two files would drift), coverage badge (no live coverage tooling behind it), "estimated review time saved" metric (no deterministic basis — fabricated numbers contradict the project's whole transparency ethos).

## 6. Key decisions + rationale (the interview-defensible stuff)

1. **Custom S-expression parser over pcbnew API** — portability (zero CAD install), full control, more original engineering to discuss.
2. **Deterministic engine is authoritative; AI only narrates.** AI never sees coordinates (test-enforced boundary), receives pre-computed evidence, must cite issue IDs, citations validated in code not just prompt. Defense-in-depth, not prompt-trust.
3. **Transparent scoring** — named constants, severity×confidence deductions; "how was this computed" has a one-line answer.
4. **Honest scope cuts documented in docstrings** rather than fake checks that can't fire.
5. **Dependency injection for the Anthropic client** — entire AI layer tested without an API key or spend.
6. **Every phase ends demoable** — gated phases; v0.3.0 and v0.4.0 tags as rollback points.
7. **Local-only backend posture** — CORS scoped, path-traversal guarded, but explicitly NOT hardened for public internet (documented, deliberate).

## 7. What remains (candidate work for next session)

In rough dependency order:
1. **Push + release housekeeping (do first):** 8 commits are unpushed. Push `master`, update `CHANGELOG.md` (Unreleased → the Phase 4 features), and consider a `v0.5.0` tag. **Backend hardening polish items from the old list are now DONE** (upload size/count caps, chat question-length cap all shipped this session).
2. **README/DESIGN accuracy sweep:** README's roadmap still says "Phase 4 (in progress)... Still open: board visualizations, the AI chat panel, and PDF export" — that's now false, all three shipped. Update the Phase 4 line, the metrics table (test count 127→135), and the "Report format: PDF export planned" note. (README/DESIGN/SKILLS_LOG had uncommitted prior-session edits at session start — reconcile, don't clobber.)
3. **Landing page** (`docs/index.html`, static, professional; the dashboard is now feature-complete so screenshots can be real; free via GitHub Pages on `/docs`). Top feature candidate.
4. **Optional refactor:** extract the shared report theme (score-color bands + chart renderers) out of `html_report.py` into `app/reports/theme.py` so `pdf_report.py` stops importing privates. Low urgency.

Stretch backlog unchanged (see DESIGN.md): review-session workflow (Fixed/Ignored/False-Positive + live rescore), plugin SDK, design-history diffing, multi-board compare, Altium/EasyEDA import.

Stretch backlog (documented in DESIGN.md, not started): review-session workflow (mark Fixed/Ignored/False-Positive, live rescoring), plugin SDK (dynamic check discovery), threshold/measured-value structured fields, design history comparison (board-rev diffing), Markdown report export, multi-board compare, Altium/EasyEDA import.

## 8. Constraints and cautions for whoever plans next steps

- **No ANTHROPIC_API_KEY in the dev environment.** Anything needing live Claude output (e.g., observing real AI review prose quality, screenshotting the chat panel with a real answer) requires the user to set a key first — plan around it or ask the user.
- **User's stated preferences:** doesn't want everything done in one giant burst; wants professional-not-AI-looking visuals; keep the "AI reviews, never designs" positioning intact; static landing page (already argued and settled — don't re-litigate 3D).
- **Windows dev machine**, Python 3.12, Node 24. Playwright available for browser QA. gh CLI authenticated (repo rename/description already done with it).
- The user relays outside feedback (ChatGPT) each round; several of its past suggestions were adopted (issue IDs, evidence block, citation validation, schema_version, CLI, GIF/website ideas) and several were pushed back on with reasons (fake metrics, coverage badge before CI existed, CONTRIBUTING.md boilerplate). Honest pushback is expected and valued — don't rubber-stamp.
