# Engineering Validation Corpus

This is not a folder of demo files — it's a curated set of KiCad boards, each authored for a specific reason, that validates the parser, the deterministic analysis engine, the AI layer, and the dashboard end to end. Every board exists to prove something the others don't; there are no filler fixtures. See `docs/VALIDATION.md` for how to run the full validation flow (this corpus + `backend/scripts/validate_ai.py`) and how to interpret the results.

| Board | Primary purpose |
|---|---|
| `simple_board` | Parser smoke test — minimal hand-authored board exercising every S-expression construct the parser handles |
| `stm32_usb_dev` | Medium-quality realistic board — a substantial fixture for the analysis engine |
| `flawed_reference` | Deliberately poor board tripping nearly every check category at once |
| `high_quality_reference` | Clean reference board — demonstrates good engineering, the "everything's fine" counterpart to `flawed_reference` |
| `rf_clock_board` | Signal-integrity and differential-pair focus |
| `power_supply_board` | Power delivery and decoupling focus |
| `thermal_reference` | Thermal design focus |
| `manufacturing_reference` | DFM (manufacturability) focus |
| `parser_edge_cases` | Parser robustness — unicode, escaped quotes, hostile characters, not analysis-engine coverage |
| `mixed_realistic_board` | What an intermediate engineer's board actually looks like — mostly solid, a few realistic slips |

## simple_board

Hand-authored minimal two-layer board (`simple_board.kicad_pcb` + `.kicad_pro`) used as the Phase 0 parser fixture. Not a KiCad-exported file — written directly in KiCad's S-expression format to exercise every construct the parser needs to handle: board outline (`gr_rect` on `Edge.Cuts`), two copper layers, four footprints (`U1` MCU, `C1` decoupling cap, `R1` resistor, `J1` USB-C connector) covering the refdes-prefix classification table, three nets (`GND`, `+3V3`, `/SCLK`) with traces, a via, and a `GND` copper pour zone.

## stm32_usb_dev

A richer four-layer example board (`stm32_usb_dev.kicad_pcb` + `.kicad_pro`) — an STM32F103 USB dev board: MCU, AMS1117-3.3 LDO, 8&nbsp;MHz crystal with load caps, USB-C connector with a D+/D− pair and series resistors, an SWD header, decoupling caps, an LED, and GND / +3V3 / GND power-and-ground pours across the inner and back copper layers (18 components, 12 nets). It exists to exercise the analysis engine on a more substantial board than `simple_board` — PCBInsight scores it 98/100 with 8 findings across routing, power, and decoupling (a thin +3V3 trace, a decoupling cap placed a little far from the MCU, and several low-confidence dangling-trace-end warnings from partial routing).

> **AI-generated example board.** This `.kicad_pcb` was authored with AI assistance as synthetic test/demo data for the analyzer — not a hand-routed, fab-ready design and not a substitute for real KiCad layout work. It is intentionally only partially routed. Treat it as example input for the tool, not as reference PCB design.

## flawed_reference

A deliberately low-quality two-layer board (`flawed_reference.kicad_pcb` + `.kicad_pro`) — same STM32/USB/LDO component set as `stm32_usb_dev`, but routed to trip nearly every check category at once: acute-angle trace bends, thin power/ground traces (0.15mm), two disconnected ground nets with no copper pour on either, a decoupling cap placed tens of mm from the ICs it should serve, a regulator with no decoupling cap on its input net at all, undersized via annular rings, no thermal relief pour near the regulator, and an unnecessarily long/via-heavy clock net. PCBInsight scores it 83/100 with 24 findings across all 7 active check categories (routing, power, ground, decoupling, manufacturability, thermal, signal integrity) — this is the board to reach for when demonstrating that the tool actually catches problems, not just when it says everything's fine.

> **AI-generated example board.** Same caveat as `stm32_usb_dev` above: synthetic test/demo data, not a real design (in this case, deliberately a bad one on purpose).

## high_quality_reference

A clean two-layer board (`high_quality_reference.kicad_pcb` + `.kicad_pro`) — USB-C input, LM1117-3.3 regulator, STM32 MCU — routed and decoupled correctly: adequately wide power/ground traces, every IC's power pin has a decoupling cap within the recommended distance, a full ground pour, no acute-angle bends, and a connector placed at the board edge. PCBInsight scores it **100/100 with zero findings**. This is the deliberate counterpart to `flawed_reference`: proof the tool doesn't just find problems, it also correctly recognizes when there aren't any.

> **AI-generated example board.** Synthetic test/demo data, authored with AI assistance to hit exact deterministic-check thresholds cleanly.

## rf_clock_board

A two-layer board (`rf_clock_board.kicad_pcb` + `.kicad_pro`) built around an STM32 MCU driving a clock net and a `DATA_P`/`DATA_N` differential pair to a USB-C connector, purpose-built to trip the signal-integrity and differential-pair checks specifically: the clock net is routed through a three-way branch point, uses three vias (over the two-via warning threshold), and totals 58mm (over the 40mm warning length) — three separate signal-integrity findings. The differential pair is routed with mismatched lengths (8.1mm skew), asymmetric via count (one leg has a via, the other doesn't), and a segment-count mismatch (1 segment vs. 4) — three separate differential-pair findings. Power, ground, decoupling, and placement are all kept clean so these two categories are the whole story. PCBInsight scores it 98/100 with 7 findings (6 SI/diff-pair, 1 incidental low-confidence dangling-stub note from the branch).

> **AI-generated example board.** Synthetic test/demo data, authored with AI assistance to hit exact deterministic-check thresholds cleanly.

## power_supply_board

A two-layer board (`power_supply_board.kicad_pcb` + `.kicad_pro`) — USB-C input, LM1117-3.3 regulator, STM32 MCU load — purpose-built around power-delivery and decoupling mistakes: the regulator has no decoupling capacitor at all on its +5V input net (a missing-decoupling finding), a capacitor exists for the +3V3 output but is placed 10mm away — well past the recommended distance (a too-far finding), the +5V supply trace is 0.20mm (below the 0.30mm guideline), there's no ground copper pour anywhere on the board, and consequently no thermal relief near the regulator either. PCBInsight scores it 96/100 with 5 findings spanning decoupling, power, ground, and thermal — a realistic cluster of power-subsystem oversights rather than a single isolated defect.

> **AI-generated example board.** Synthetic test/demo data, authored with AI assistance to hit exact deterministic-check thresholds cleanly.

## thermal_reference

A two-layer board (`thermal_reference.kicad_pcb` + `.kicad_pro`) — LM1117-3.3 regulator and an N-MOSFET placed close together, both correctly decoupled, with a ground pour present on the board but positioned nowhere near either heat source. This isolates the thermal category cleanly: no copper pour within range of the regulator, no copper pour within range of the MOSFET, and the two heat sources are close enough together (5.4mm) to compound each other's thermal rise. PCBInsight scores it 99/100 with exactly 3 findings, all thermal.

> **AI-generated example board.** Synthetic test/demo data, authored with AI assistance to hit exact deterministic-check thresholds cleanly.

## manufacturing_reference

A tiny two-layer board (`manufacturing_reference.kicad_pcb` + `.kicad_pro`, 12mm × 12mm) built to trip every manufacturability (DFM) check: a 0.10mm trace segment (below the 0.15mm fab-minimum), two vias with a 0.025mm annular ring (below the 0.075mm fab-minimum), and eight stitching vias packed into the small board area to push via density over 5/cm². The dense via cluster also trips routing's excessive-via-count check on that net — a realistic secondary effect of the same root cause, not a separate story. PCBInsight scores it 95/100 with 6 findings, 4 of them manufacturability.

> **AI-generated example board.** Synthetic test/demo data, authored with AI assistance to hit exact deterministic-check thresholds cleanly.

## parser_edge_cases

A small two-layer board (`parser_edge_cases.kicad_pcb` + `.kicad_pro`) that exists to stress the **parser**, not the analysis engine — deliberately hostile but valid KiCad S-expression text: a component value with an escaped quote and a Greek letter (`Cap_100nF \"X7R\" Ω`), a net name with angle brackets (`VCC<3V3>`), unicode characters mixed into both a net name and a reference designator (`R&D_信号`, `J-长`), an ampersand and hyphen inside a reference designator, parentheses embedded inside a quoted net name, a ~90-character net name, and a lowercase reference designator (`u1`) to confirm case-insensitive component classification. All of it parses cleanly and classifies correctly — verified directly against the parsed `Board` object, not just "the CLI didn't crash."

> **AI-generated example board.** Synthetic test/demo data, authored with AI assistance specifically to exercise string/tokenizer edge cases.

## mixed_realistic_board

A two-layer board (`mixed_realistic_board.kicad_pcb` + `.kicad_pro`) meant to look like what an intermediate engineer actually ships — not a showcase of best practices (`high_quality_reference`) and not a pile of violations (`flawed_reference`). Power delivery, grounding, and most decoupling are done correctly; the realistic slips are a single decoupling cap placed too far from its MCU, one clock net that ran a bit longer than ideal (47mm, no other clock issues), one isolated trace segment that came in under the manufacturing minimum, and one incidental dangling-stub note. PCBInsight scores it 98/100 with 4 findings spread across four different categories — the board to reach for when you want "good work with a couple of real mistakes," not either extreme.

> **AI-generated example board.** Synthetic test/demo data, authored with AI assistance to hit exact deterministic-check thresholds cleanly.

---

Per `DESIGN.md`'s open questions, the fixture set should keep growing to include additional clean reference boards plus at least one intentionally-flawed board per check category — this corpus now covers that for the current check set, split into ten purpose-built boards rather than one board doing everything.
