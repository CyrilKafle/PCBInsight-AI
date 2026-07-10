# Skills Log

Running log of tools, languages, and concepts learned while building this project. Feeds resume updates via the InternPilot project — copy new entries over when updating application materials.

## 2026-07-10 — Phase 0: simulation-first single-joint control

**Languages/tools learned or used:**
- **SystemVerilog** (RTL design): wrote synchronous FSMs (`always_ff`), parameterized modules, fixed-point arithmetic (Q8 fixed-point gain in `p_controller.sv`), signed/unsigned arithmetic handling.
- **Icarus Verilog** (`iverilog` + `vvp`): open-source HDL simulator toolchain — compiling SystemVerilog to a simulation executable and running it, `-g2012` mode for SystemVerilog-2012 language features.
- **Self-checking testbenches**: wrote testbenches with independent reference models (computing "expected" values in the testbench itself, separate from the RTL under test) rather than just eyeballing waveforms — the standard verification discipline in real ASIC/FPGA workflows.
- **Behavioral modeling**: wrote a behavioral SPI slave model (`mcp3208_model.sv`) standing in for a real MCP3208 ADC chip, to test the SPI master without needing real hardware yet.

**Concepts learned or reinforced:**
- **PWM (pulse-width modulation)** generation for hobby servo control: 50 Hz period, 1-2 ms pulse width mapping to position.
- **SPI protocol** (Mode 0): command/response shape for reading a 12-bit ADC conversion, MSB-first bit ordering, chip-select framing.
- **Closed-loop proportional (P) control**: discrete-time formula `command = measured + Kp*(target-measured)`, and its real limitation — non-zero steady-state error, which is exactly why real controllers add an integral term (PID). Traced this by hand in simulation rather than just reading about it — see `docs/PHASE0_NOTES.md`.
- **Fixed-point arithmetic in hardware**: using power-of-two shifts (`>>>`) instead of general dividers to keep arithmetic synthesizable, and the precision/truncation tradeoffs that come with it.
- **Classic FSM race condition**: a status flag (`busy`) that drops one cycle before the state machine can actually accept new input — found and fixed by tracing exact clock-cycle timing, not by guessing. Full writeup in `docs/PHASE0_NOTES.md`.
- **Verilog signed/unsigned gotcha**: mixing a signed and an unsigned operand in one expression silently makes the *entire* expression unsigned, which can turn a small negative result into a huge wrapped-around number. Hit this in a testbench comparison, not the RTL — a good reminder that verification code needs the same rigor as design code.
- **Windows dev environment**: installed a native Windows HDL toolchain (Icarus Verilog via `winget`) and safely diagnosed/repaired a Windows user PATH environment variable issue (`setx` doesn't expand `%PATH%` the way `cmd.exe` does when invoked from a non-cmd shell — learned to reconstruct and verify the correct value via the registry directly instead of trusting the naive one-liner).

**Not yet started (Phase 1+):**
- KiCad schematic capture / PCB layout.
- Real hardware bring-up on a Tang Nano 9K (or similar) FPGA board.
- PCB fabrication ordering (JLCPCB).
- Multi-joint custom communication protocol (Phase 2).
