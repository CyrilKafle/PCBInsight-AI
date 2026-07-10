# Phase 0 Notes

Running notes on non-obvious things found while building and simulating the
Phase 0 single-joint control datapath. Referenced from testbench comments so
the reasoning behind test tolerances/timeouts isn't just a magic number.

## P-controller steady-state error (p_controller.sv / p_controller_tb.sv)

A pure proportional controller does not fully cancel error at steady state
when combined with fixed-point (integer) truncation — once the computed
correction rounds to zero, further convergence stops even though a small gap
remains. Traced by hand with `target=3000`, `start_measured=500`, `KP_Q8=64`
(Kp=0.25), and a simulated plant settling 1/4 of the remaining distance
toward the commanded position each tick:

| tick | measured | command | gap  |
|------|----------|---------|------|
| 0    | 656      | 1125    | 2344 |
| 10   | 1767     | 2013    | 1233 |
| 20   | 2350     | 2480    | 650  |
| 40   | 2815     | 2852    | 185  |
| 60   | 2943     | 2955    | 57   |
| 80   | 2978     | 2982    | 22   |
| 100  | 2985     | 2988    | 15   |
| 120+ | 2985     | 2988    | 15   |

Convergence is smooth and geometric (each step roughly halves the remaining
gap on a log scale) up to ~tick 100, then locks permanently at a 15-count
gap out of 4096 (~0.4% of full range). This matches control theory for
P-only control: there's always some residual error a proportional term alone
can't close, and integer truncation turns "asymptotically approaches zero"
into "gets stuck at a small fixed offset once the correction term rounds
to zero."

**This is expected, not a bug.** It's exactly the reason PID controllers add
an integral term (accumulates error over time until it's forced to zero) —
planned for the Phase 2 multi-joint upgrade per DESIGN.md. `p_controller_tb.sv`
uses a 150-tick run and a +/-25 count tolerance, both derived from this trace
(150 ticks is comfortably past the ~100-tick settle point; 25 counts gives
margin above the observed 15-count settled gap without being loose enough to
mask a real divergence bug).

## spi_adc_reader.sv: one-cycle FSM race on back-to-back conversions

Original design had `XFER -> DONE -> IDLE`, with `busy` dropping to 0 in the
`DONE`-entry cycle. A caller that (correctly, per the `busy` contract)
re-triggers `start` as soon as `busy` clears ends up pulsing `start` one
cycle before the FSM's `case` statement actually evaluates `state == IDLE` —
because the `state <= IDLE` transition itself doesn't become visible to the
`case` comparison until the cycle *after* it's assigned. A single-cycle
`start` pulse issued right when `busy` clears lands entirely within that
dead cycle and is silently dropped, hanging the second conversion forever.

Fixed by collapsing `DONE` into the same cycle as the last data bit: the
final bit's falling-edge transition now sets `state <= IDLE` directly
(instead of `state <= DONE`), so `busy` dropping and the FSM actually being
ready for a new `start` happen in the same clock edge — no dead cycle.
