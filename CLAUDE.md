# PCBInsight AI — session bootstrap

This file auto-loads at the start of every Claude Code session in this repo.
Its job: orient you fast, then point you at the real state so you don't have to
re-read the whole codebase (saves tokens, keeps the session sharp).

## What this project is
AI-augmented PCB design-review tool for KiCad projects. Custom S-expression
parser → deterministic engineering checks (9 categories) → transparent 0–100
score → Claude narrates the findings (Claude only writes *over* deterministic
results; it is never the analysis engine and never sees raw geometry).

## ⭐ Before doing any work, read `knowledge.md`
`knowledge.md` is the **single source of truth** for current state: phase status,
what's done, what's next, verified test counts, key decisions, and constraints.
It is kept current at the end of every session. Read it once per session before
starting work — you do NOT need to re-read README.md / DESIGN.md / the source to
get oriented; `knowledge.md` summarizes all of it.

Only reach for the deeper files when you actually need them:
- `DESIGN.md` — full architecture rationale + engineering-check catalogue
- `README.md` — public-facing overview + run instructions
- `SKILLS_LOG.md` — tools/concepts learned as the project progressed

## Layout
```
backend/app/      FastAPI service: parser, analysis engine, AI layer, reports, CLI
backend/tests/    pytest suite (source of the "N tests passing" number)
frontend/src/     React + TS + Tailwind dashboard
examples/         Sample KiCad board used as the test fixture
```

## How to run / verify
```sh
# Backend tests (fast, ~2.5s) — the truth check before/after any change
cd backend && python -m pytest -q

# CLI
python -m app.cli review ../examples/simple_board          # single board
python -m app.cli review ../examples/simple_board --ai     # + Claude review (needs ANTHROPIC_API_KEY)

# Web dashboard
cd backend && uvicorn app.main:app --port 8000             # terminal 1
cd frontend && npm run dev                                 # terminal 2 → http://localhost:5173
```

## ⚠️ End every session by updating `knowledge.md`
Before you finish, update `knowledge.md` so the next fresh session inherits
today's state with zero re-discovery. Update at minimum:
- Section 3/4 (phase status + verified state: test counts, last commit)
- Section 7 (what remains / candidate next work)
- The "verified as of <date>" line at the top

This is the whole point of the setup: keep `knowledge.md` current, and every new
session starts fresh (= maximally sharp) while knowing everything up to today.

## Working notes / preferences
- No `ANTHROPIC_API_KEY` in this dev env — anything needing live Claude output
  requires the user to set one first. Plan around it or ask.
- Positioning is locked: "AI reviews, never designs." Keep it intact.
- User wants professional, not-AI-looking visuals; doesn't want everything done
  in one giant burst; values honest pushback over rubber-stamping.
- Windows machine, Python 3.12, Node 24, `gh` CLI authenticated.
