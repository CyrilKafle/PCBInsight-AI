# PCBInsight AI — Project Knowledge File

Purpose of this file: a complete, current snapshot of the project so a fresh work session can pick up with zero re-discovery. Everything below is factual and verified as of 2026-07-16.

> **Session continuity note:** `CLAUDE.md` at the repo root auto-loads every Claude Code session and points here. Keep this file current at the end of each session so a fresh session inherits state with zero re-discovery.

---

## 1. What the project is

**PCBInsight AI** — an automated PCB design review platform for KiCad projects. It parses `.kicad_pcb` files with a custom parser, runs 28 deterministic engineering checks across 9 categories, computes a transparent 0–100 engineering score, and generates professional HTML/PDF reports. Claude AI sits on top as a strictly-bounded "technical writer" layer that narrates the deterministic findings — it never analyzes the board itself and never sees raw geometry.

- **Repo (public):** https://github.com/CyrilKafle/PCBInsight-AI (renamed from the pre-pivot `SiliconArm`)
- **Landing page (live):** https://cyrilkafle.github.io/PCBInsight-AI/ — GitHub Pages, served from `/docs` on `master`, enabled 2026-07-16.
- **Owner:** Cyril Kafle, undergraduate; a portfolio project in the EE/PCB/EDA/embedded space.
- **Positioning (decided, in DESIGN.md):** personal/local tool, *not* a public multi-tenant service. No public upload endpoint (Claude API cost + an unhardened parser = two real reasons). The static landing page + GitHub repo are the public artifacts; the functional dashboard stays local-only. The honest and sufficient story is the tool itself.

## 2. Architecture (all implemented and working)

```
KiCad Project (.kicad_pcb)
  → S-Expression Parser (custom, zero pcbnew/CAD dependencies)  [backend/app/parser/sexpr.py, kicad_project.py]
  → Internal Board Model (Pydantic: components, nets, traces, vias, pours)  [backend/app/models/board.py]
  → Deterministic Analysis Engine — 9 category modules, 28 checks  [backend/app/analysis/*.py]
  → Issue list (each: id like PWR-004, severity, confidence, explanation, engineering principle, suggested fix, refs, board location)
  → Transparent Scoring (severity×confidence deductions from 100; overall = average of 7 subscores)  [analysis/scoring.py]
  → ├─ Self-contained HTML report (embedded matplotlib charts, XSS-escaped)  [reports/html_report.py]
    ├─ PDF report (ReportLab, reuses html_report's public chart renderers + reports/theme.py's score_color)  [reports/pdf_report.py]
    ├─ Structured AI Digest (schema_version, evidence block, issues, stats — NO raw geometry, test-enforced)  [ai/summarizer.py]
    │    → Claude review + grounded chat answers under strict system prompt + code-enforced citation validation  [ai/review.py]
    ├─ CLI: `pcbinsight review <path>` single-board + auto-detected batch folder mode  [app/cli.py]
    └─ FastAPI (local-only)  [app/main.py]: POST /api/review, /api/chat, /api/report/pdf
         → React/TS/Tailwind dashboard  [frontend/src/]: upload · score cards · issue browser ·
           SVG board view (zoom/pan, layer toggles, clickable issue markers) · net-length histogram ·
           issue-by-category chart · grounded AI chat panel · Download PDF
```

Architecture diagram: `docs/images/architecture.png`, regenerated 2026-07-16 from a real source for the first time — `docs/images/architecture.mmd` (Mermaid) + `docs/images/architecture.excalidraw` (editable). Reflects AI chat, board viz, PDF export, and the CLI as an alternate entry point. Edit the `.mmd` and re-render, never hand-edit the PNG.

Shared report styling lives in `backend/app/reports/theme.py` (`SEVERITY_COLORS`, `SEVERITY_ORDER`, `SCORE_BANDS`, `score_color()`) — extracted so `pdf_report.py` no longer imports `html_report.py`'s private state; `html_report.py`'s chart renderers (`render_subscore_chart`, `render_severity_chart`) are now public for the same reason.

## 3. Phase status

| Phase | Status | Notes |
|---|---|---|
| 0 — Parser + board model | DONE | Hand-rolled S-expression parser chosen over `pcbnew` bindings (portability + more original work; pcbnew wasn't even installable here). |
| 1 — Deterministic check engine | DONE | 9 modules, 28 individual checks, explicit named thresholds (no ML). Documented scope cut: silkscreen-over-pad / copper-sliver checks skipped (board model lacks that geometry). |
| 2 — Scoring + HTML report | DONE | Transparent deduction scoring; self-contained HTML report w/ base64 matplotlib charts. |
| 3 — AI Engineering Review Layer | DONE | Digest has `schema_version`; evidence block computed in Python, never by Claude; strict system prompt; `find_unsupported_citations()` code-checks citations. **Live-validated** (see §4) — a real bug was caught and fixed (model reused a hardcoded example issue ID from its own system prompt; fixed by removing concrete example IDs from the prompt). |
| CLI (bonus, pre-Phase-4) | DONE | Single + batch mode, `pip install -e .` gives real `pcbinsight` command via pyproject. |
| 4 — Dashboard | DONE (complete feature set) | FastAPI (`/api/review`, `/api/chat`, `/api/report/pdf`) + React dashboard: upload, score cards, issue browser, SVG board view, histogram, category chart, grounded AI chat, PDF export. Verified end-to-end in a real browser, including live screenshots for the landing page. |
| AI validation harness | DONE | `backend/scripts/validate_ai.py` — usage/cost tracking, writes committed evidence to `reports/ai_validation.{md,json}` (git commit/tag, per-board cost). Manual/live only, deliberately not in CI (see §6). |
| Engineering Validation Corpus | DONE | 10 purpose-built KiCad boards in `examples/`, each demonstrating exactly one thing. See `docs/VALIDATION.md` and `examples/README.md`. |
| Landing page | **DONE, live** | `docs/index.html`, dark-mode-first design system (`docs/design-system.md`: IBM Plex Sans + JetBrains Mono, teal `#2FD9C4` accent kept distinct from the AI-purple `#8A63D2`). Every screenshot is genuine (live dashboard run against `examples/stm32_usb_dev`, real Claude review + real chat answer). Served via GitHub Pages from `/docs`. README updated to link it + embed real screenshots. |

## 4. Verified state (as of 2026-07-16)

- **Backend: 147/147 tests passing** (pytest, ~3–7s). Includes a corpus-wide parametrized regression test (`test_corpus_board_parses_and_scores_without_error`) guarding all 10 example boards.
- **Frontend: `tsc -b` clean + `npm run build` succeeds.** `d3` and `plotly.js-dist-min` removed (zero usages — charts are hand-rolled SVG).
- **Live AI validation performed** (real `ANTHROPIC_API_KEY`, now present in `backend/.env` — no longer missing from the dev environment): zero hallucinated citations across 5 boards, $0.156 total run cost. Evidence committed at `reports/ai_validation.{md,json}`.
- **Repository fully pushed** — `origin/master` up to date, no unpushed commits, CI green on every push this session.
- **GitHub Pages live** at https://cyrilkafle.github.io/PCBInsight-AI/.
- Docs current: `DESIGN.md` (architecture rationale), `docs/ENGINEERING_DECISIONS.md` (the "why," interview-ready), `docs/VALIDATION.md` (how both validation tracks work), `docs/ARCHITECTURE.md`, `docs/design-system.md` (landing page visual system), `examples/README.md` (per-board corpus writeups).

## 5. Repo hygiene (all done)

MIT LICENSE · CHANGELOG.md (Keep-a-Changelog style) · GitHub Actions CI · README badges incl. a live landing-page badge · real-numbers metrics table in README (147 tests, 2,957/1,386 LOC, recomputed) · README screenshot gallery (4 real images, table layout) · regenerated architecture diagram with real source · CLI usage docs · `docs/ARCHITECTURE.md` · `docs/ENGINEERING_DECISIONS.md` · `docs/VALIDATION.md` · `docs/design-system.md` · live landing page.

Deliberately skipped (with reasoning): CONTRIBUTING.md (solo repo, reads as boilerplate), ROADMAP.md (DESIGN.md already is one), coverage badge (no live coverage tooling behind it), "estimated review time saved" metric (no deterministic basis).

## 6. Key decisions + rationale (the interview-defensible stuff)

Full writeup with code citations: `docs/ENGINEERING_DECISIONS.md`. Summary:

1. **Deterministic-first ordering** — the check engine was built and proven (Phases 0–2) before any AI code existed, so the AI layer can never become load-bearing.
2. **AI cannot invent findings** — never sees raw geometry; digest-only; system prompt explicitly forbids invented findings.
3. **Citations are code-enforced, not just prompted for** — `find_unsupported_citations()` diffs cited IDs against the real digest. This caught a real bug during live validation.
4. **Custom S-expression parser over pcbnew** — zero CAD-install dependency, more original engineering, `pcbnew` wasn't even installable in the dev env at the time.
5. **The Engineering Validation Corpus exists** because one fixture isn't enough evidence for a transparency-pitched tool — 10 boards, each proving one specific thing, guarded by a parametrized regression test.
6. **AI validation stays out of CI** — costs real money per run (~10 billed calls); CI must stay free/fast. Kept as a manual script with committed evidence instead.
7. **Transparent scoring over benchmark scores** — severity × confidence deduction, named constants, no black box. Same instinct behind skipping the coverage badge and the "time saved" metric — no fabricated numbers, ever.
8. **Local-only backend posture** — CORS scoped, path-traversal guarded, explicitly not hardened for public internet (deliberate; the landing page is static specifically to avoid needing to harden the real backend for public traffic).

## 7. Current milestone status — engineering AND productization both complete

**v1.0-ready.** Both the engineering milestone (deterministic engine, AI layer, validation corpus, live AI validation, repo audit) and the productization milestone (design system, landing page, real screenshots, GitHub Pages) are done. Per the user's explicit call: **stop adding engineering functionality.** What remains is entirely outside the codebase:

1. **Resume/portfolio integration** — PCBInsight as the flagship project.
2. **LinkedIn/write-up** — the engineering-decisions narrative is already written (`docs/ENGINEERING_DECISIONS.md`) and ready to adapt.
3. **Interview prep** — be ready to demo live; the "why not just let the LLM review it" answer is already documented.
4. **v1.0.0 tag** — not yet cut as of this writing; consider tagging once the user confirms the landing page is final.

Stretch backlog (documented in DESIGN.md, explicitly NOT next): review-session workflow, plugin SDK, threshold/measured-value structured fields, design-history comparison, multi-board compare, Altium/EasyEDA import. Do not start these unprompted — the user was explicit that presentation, not more features, is the highest-return work from here.

## 8. Constraints and cautions for whoever plans next steps

- **`ANTHROPIC_API_KEY` IS available** in `backend/.env` as of this session (stale note from earlier sessions said otherwise — corrected). `backend/app/main.py` does **not** auto-load `.env` — export the key into the shell environment before starting `uvicorn`, or live AI features 502.
- **User's stated preferences:** doesn't want everything done in one giant burst (checkpoint at natural phase boundaries); wants professional-not-AI-looking visuals; keep the "AI reviews, never designs" positioning intact; engineering-documentation voice over marketing copy in any user-facing text.
- **Windows dev machine**, Python 3.12, Node 24. `gh` CLI authenticated. gstack `browse` daemon available for real-browser screenshots (`~/.claude/skills/gstack/browse/dist/browse`) — used to capture every landing-page/README screenshot from the actual running dashboard, not mocked.
- **Honest pushback is expected and valued — don't rubber-stamp.** Past calls that held up: real (computed) metrics over estimates, no coverage badge without live coverage tooling, no fabricated numbers anywhere. Keep claims in the repo tied to what the code actually does.
- **GitHub Pages is live and public** — `docs/index.html` changes go live immediately on push to `master`. Treat edits there with the same care as any other public-facing change.
