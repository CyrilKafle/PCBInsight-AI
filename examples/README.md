# Example KiCad Projects

Sample KiCad projects used to develop and regression-test the parser (Phase 0) and analysis engine (Phase 1).

## simple_board

Hand-authored minimal two-layer board (`simple_board.kicad_pcb` + `.kicad_pro`) used as the Phase 0 parser fixture. Not a KiCad-exported file — written directly in KiCad's S-expression format to exercise every construct the parser needs to handle: board outline (`gr_rect` on `Edge.Cuts`), two copper layers, four footprints (`U1` MCU, `C1` decoupling cap, `R1` resistor, `J1` USB-C connector) covering the refdes-prefix classification table, three nets (`GND`, `+3V3`, `/SCLK`) with traces, a via, and a `GND` copper pour zone.

Per `DESIGN.md`'s open questions, this should grow to include additional clean reference boards plus at least one intentionally-flawed board per check category once Phase 1's checks need fixtures to prove they actually fire.
