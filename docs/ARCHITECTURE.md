# Architecture

See `DESIGN.md` at the repo root for the full rationale and phased plan. This file will hold a diagram and deeper implementation notes once Phase 0 (parser) is underway.

## Pipeline

```
KiCad project upload
    -> parser (backend/app/parser)         builds Board model
    -> analysis engine (backend/app/analysis)  Board -> list[Issue]
    -> scoring (backend/app/analysis/scoring)  list[Issue] -> EngineeringScore
    -> AI summarizer (backend/app/ai/summarizer)  Board + Issues -> structured digest
    -> AI review (backend/app/ai/review)   digest -> narrative review (Claude)
    -> report (backend/app/reports)        Board + Issues + Score + review -> HTML/PDF
```

## Key boundary

Claude never receives raw KiCad files or geometry — only the structured digest produced by `app/ai/summarizer.py`. This keeps the AI layer bounded, auditable, and clearly additive rather than load-bearing.
