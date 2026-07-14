# Skills Log

Running log of tools, languages, and concepts learned while building this project. Feeds resume updates via the InternPilot project — copy new entries over when updating application materials.

Note: this log restarts for the AI PCB Design Review Platform (pivoted 2026-07-13 from a prior FPGA/PCB robotic-arm project — that project's own skills log covered SystemVerilog, Icarus Verilog, and closed-loop control simulation, and remains in this repo's git history).

## Phase 0 — parser + internal board model

- **KiCad `.kicad_pcb` file format**: modern KiCad board files are plain S-expressions (`(token child1 child2 ...)`), while `.kicad_pro` project files are JSON. Learned the grammar (footprints, `fp_text`/`property` refdes and value fields, `segment`/`via`/`zone`/`gr_rect` graphic and copper elements, per-net `(net id "name")` declarations referenced by id elsewhere in the file) well enough to write a parser without needing a KiCad install.
- **Hand-rolled S-expression parsing**: wrote a small tokenizer + recursive-descent reader (`app/parser/sexpr.py`) producing a plain nested-list tree, plus `find_all`/`find_first`/`child_values` helpers for walking KiCad's tag-first-element convention. Chose this over the `pcbnew` Python bindings specifically to avoid requiring a full KiCad desktop install as a runtime dependency — a deliberate "runs anywhere" tradeoff, not just the path of least resistance (`pcbnew` wasn't available on the dev machine either).
- **Pydantic v2 mutable defaults**: confirmed `list[X] = []` field defaults are per-instance (not shared) in Pydantic v2, unlike a plain dataclass — this simplified the `Net.traces`/`Net.vias` accumulation logic in the parser.
- **Test-fixture authoring for a binary-ish/DSL file format**: rather than depending on exporting a real board from a KiCad install, hand-authored a minimal-but-valid `.kicad_pcb` fixture (`examples/simple_board/`) covering every construct the parser needs (board outline, two copper layers, four component kinds, three nets, traces, a via, a copper pour) — deliberately exercises the parser's edge cases rather than being a realistic board.

## Phase 1 — deterministic engineering-check engine

- **PCB engineering heuristics as code**: translated real design-review judgment calls (acute-angle bends causing acid traps, decoupling-cap loop length, daisy-chained vs. planar power distribution, differential-pair skew, thermal relief copper, annular ring / trace-width fab minimums) into explicit, tunable thresholds in each `app/analysis/*.py` module — the kind of heuristics normally kept as tribal knowledge in a senior engineer's head.
- **Geometry from raw coordinates**: implemented endpoint-adjacency detection (shared trace endpoints within a tolerance) and bend-angle computation via the dot-product formula (`cos θ = (v1·v2)/(|v1||v2|)`) to detect acute-angle routing and branch points, without any CAD/geometry library.
- **Net-name convention parsing**: auto-identifying power/ground/clock nets and differential pairs from naming convention alone (`+3V3`, `_P`/`_N`, `NET+`/`NET-`) rather than requiring an explicit schematic-level declaration — a deliberate scope tradeoff, documented inline, since the parser doesn't carry full schematic semantics.
- **Deliberately transparent thresholds over ML**: every check is a named constant (e.g. `LONG_TRACE_WARN_MM = 60.0`) rather than a learned/black-box score — makes "why did this fire" a one-line answer, which matters for the project's "defensible in an interview" goal.
- **Honest scope boundaries**: manufacturability's silkscreen-over-pad / copper-sliver checks from `DESIGN.md`'s catalogue were *not* implemented, because the board model doesn't capture silkscreen text bounding boxes or full pour polygon shape — documented as a gap in the module docstring rather than stubbing a check that could never actually fire on real data.
- **Test design for heuristic checks**: each of the 9 categories gets synthetic-board unit tests (via a small `tests/factories.py` builder module) proving both the positive case (check fires on a deliberately bad board) and the negative case (stays silent on a clean one) — geometry hand-computed (e.g. constructing an exact 30° bend via `cos`/`sin`) rather than eyeballed.

## Phase 2 — scoring + first HTML report

- **Transparent scoring over ML**: implemented the engineering score as a plain, auditable deduction formula (start at 100, subtract `severity_weight × confidence` per issue, floor at 0, overall = average of subscores) rather than any kind of learned model — the explicit goal being that "how was this score computed" has a one-line, defensible answer.
- **Matplotlib in a headless/non-interactive context**: used the `Agg` backend (`matplotlib.use("Agg")` before importing `pyplot`) to render charts to an in-memory buffer with no display/GUI dependency, then embedded them as base64 `data:image/png;base64,...` URIs directly in the HTML — keeps the report a single self-contained file with no external asset references, which matters for emailing it or feeding it into a future PDF export step.
- **XSS-safe HTML generation without a templating engine**: every user/board-derived string (board name, issue text, refdes references) goes through `html.escape()` before interpolation into the report string — verified with a dedicated test that injects `<script>` into an issue summary and asserts it comes out escaped.
- **Visual QA on generated static HTML**: rather than trusting "tests pass" for a human-facing report, served the generated file over a local `http.server` and screenshotted it with Playwright to actually look at spacing, chart rendering, and color-coding before calling the phase done — caught nothing broken this time, but confirmed the practice is worth doing for any future UI-facing output.

## Not yet started

- FastAPI backend architecture.
- Claude API integration for structured-digest-based engineering review.
- React + TypeScript + Tailwind dashboard.
- ReportLab (PDF) export (Phase 4).
