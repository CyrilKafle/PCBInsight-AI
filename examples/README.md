# Example KiCad Projects

Sample KiCad projects used to develop and regression-test the parser (Phase 0) and analysis engine (Phase 1).

## simple_board

Hand-authored minimal two-layer board (`simple_board.kicad_pcb` + `.kicad_pro`) used as the Phase 0 parser fixture. Not a KiCad-exported file — written directly in KiCad's S-expression format to exercise every construct the parser needs to handle: board outline (`gr_rect` on `Edge.Cuts`), two copper layers, four footprints (`U1` MCU, `C1` decoupling cap, `R1` resistor, `J1` USB-C connector) covering the refdes-prefix classification table, three nets (`GND`, `+3V3`, `/SCLK`) with traces, a via, and a `GND` copper pour zone.

## stm32_usb_dev

A richer four-layer example board (`stm32_usb_dev.kicad_pcb` + `.kicad_pro`) — an STM32F103 USB dev board: MCU, AMS1117-3.3 LDO, 8&nbsp;MHz crystal with load caps, USB-C connector with a D+/D− pair and series resistors, an SWD header, decoupling caps, an LED, and GND / +3V3 / GND power-and-ground pours across the inner and back copper layers (18 components, 12 nets). It exists to exercise the analysis engine on a more substantial board than `simple_board` — PCBInsight scores it 98/100 with 8 findings across routing, power, and decoupling (a thin +3V3 trace, a decoupling cap placed a little far from the MCU, and several low-confidence dangling-trace-end warnings from partial routing).

> **AI-generated example board.** This `.kicad_pcb` was authored with AI assistance as synthetic test/demo data for the analyzer — not a hand-routed, fab-ready design and not a substitute for real KiCad layout work. It is intentionally only partially routed. Treat it as example input for the tool, not as reference PCB design.

Per `DESIGN.md`'s open questions, the fixture set should keep growing to include additional clean reference boards plus at least one intentionally-flawed board per check category.
