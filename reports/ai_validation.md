# AI Validation Report

Generated 2026-07-16T02:13:32.626367+00:00 against `claude-sonnet-5` via `backend/scripts/validate_ai.py`.
Repo state: commit `20a2000f35c1`, tag `v0.5.0`.

This is evidence the AI review layer was validated against the real Anthropic API (not just the dependency-injected fake client used in the unit tests) -- see `backend/scripts/validate_ai.py` for what each check verifies.

| Board | Score | Issues | Hallucinated citations | Low-conf. hedged | Review cost | Chat cost |
|---|---:|---:|---:|:---:|---:|---:|
| example simple_board | 100 | 1 | none | yes | $0.0140 | $0.0091 |
| example stm32_usb_dev | 98 | 8 | none | yes | $0.0191 | $0.0142 |
| clean minimal | 100 | 3 | none | yes | $0.0156 | $0.0108 |
| messy (multi-issue) | 95 | 15 | none | yes | $0.0223 | $0.0175 |
| weird net names + unicode | 98 | 9 | none | yes | $0.0193 | $0.0141 |

**Total cost this run:** $0.1560  |  **Boards with hallucinated citations:** 0/5

## Per-board detail

### example simple_board

Deterministic: score 100, 1 issues (SIG-001).

**AI review:**

# PCB Design Review Summary — simple_board

## Overall Assessment
This is a small, simple 2-layer board (50.0mm × 40.0mm, 4 components, 3 nets) that scores very well across all review categories, with an overall score of 100/100. The design shows no critical, high, or medium severity issues. Only a single **low-severity** finding was identified.

## Findings

### SIG-001 — Clock net length (Low severity, Low confidence)
- **Summary:** The clock net `/SCLK` totals 40.0mm in length.
- **Explanation:** Longer clock traces increase propagation delay and raise susceptibility to noise pickup and skew relative to other signals.
- **Principle:** Clock/high-speed net length should stay within the propagation-delay budget for the target frequency.
- **Suggested fix:** Shorten the route or reposition the source/load components closer together.

**Note on confidence:** This finding has a confidence value of 0.4, which is below the 0.5 threshold — it should be treated as tentative and **manually verified** rather than accepted as certain. Without knowing the actual clock frequency /SCLK operates at, it's not possible to independently confirm whether 40.0mm is actually problematic; the reviewer should check the timing budget for the specific application before acting on this.

## Recurring Themes
With only one issue reported, there isn't a pattern of recurring problems to analyze. The "most common recommendation" field simply reflects this single finding (shorten the route / reposition components).

## Prioritization
Given the evidence:
1. **SIG-001** is the only item requiring attention, and even this is low-severity and low-confidence. There is no urgency indicated by the data.
2. No other categories (Routing, Power, Manufacturability, Placement, Thermals, Documentation) have flagged issues, and all subscores are at or near maximum (99–100).

## Recommendation
Based solely on the supplied data, the only actionable recommendation is to review the `/SCLK` net length (SIG-001) and confirm — given the actual target clock frequency — whether 40.0mm falls within an acceptable propagation-delay budget. If confirmed acceptable, no further action is needed. I cannot make additional recommendations, as no other issues were supplied in the evidence.

**Chat -- What is the single most important thing to fix on this board, and why?**

Based on the board digest, this board is in excellent shape overall (score: 100/100), with only **one low-severity issue** identified — and no critical, high, or medium severity issues at all.

**The single issue to address: SIG-001**

- **Summary:** The clock net `/SCLK` has a total routed length of 40.0mm.
- **Why it matters:** Per the stated principle, clock and high-speed nets should be kept within the propagation-delay budget for their target frequency. A long clock trace increases propagation delay and makes the signal more susceptible to noise pickup and skew relative to other signals.
- **Suggested fix:** Shorten the route, or reposition the source/load components closer together to reduce the /SCLK trace length.

**Important caveat:** This issue has a **confidence score of 0.4**, which is below the 0.5 threshold — meaning it should be **manually verified** rather than treated as a certain finding. The actual impact depends on the clock frequency being used; without knowing the target frequency's timing budget, it's unclear whether 40.0mm is actually problematic in practice.

Given that this is the only flagged issue on an otherwise clean board, it is by default "the most important thing to fix" simply because it's the only thing flagged — but given its low severity and sub-threshold confidence, it should be treated as a minor, worth-checking item rather than an urgent design flaw.

### example stm32_usb_dev

Deterministic: score 98, 8 issues (DECAP-001, PWR-001, RTE-001, RTE-002, RTE-003, RTE-004, RTE-005, RTE-006).

**AI review:**

## PCB Review Summary — stm32_usb_dev

**Overall score: 98/100** — a strong result. No critical or high-severity issues were found; the deterministic analysis surfaced only 2 medium and 6 low-severity items across a 4-layer, 18-component board.

### Recurring Theme: Possible Dangling Trace Stubs
Six of the eight findings (RTE-001 through RTE-006) share the identical pattern — a trace endpoint that doesn't clearly terminate at a pad, via, or same-net trace within tolerance. These span several functionally distinct nets: USB differential pair (/USB_DP, /USB_DM), crystal lines (/XTAL_IN, /XTAL_OUT), and SWD programming/debug lines (/SWDIO, /SWCLK).

- All six carry the same low severity and the same **confidence of 0.4**, which is below the 0.5 threshold — **these should be treated as unverified and manually checked**, not as confirmed defects. It's plausible some or all are false positives from endpoint-detection tolerance rather than actual unterminated stubs.
- If genuine, stubs on /USB_DP and /USB_DM are worth checking first among this group, since USB differential signaling is more sensitive to impedance discontinuities than the crystal or SWD lines, though no signal-integrity issue was actually flagged for these nets (Signal Integrity subscore is 100).
- The common recommendation across all six is consistent: verify the endpoint lands on a pad, then extend or remove the stub as needed.

### Power Delivery Observations
Two medium-severity findings, both related to power delivery robustness:

- **PWR-001** (confidence 0.65): the +3V3 rail includes a 0.25mm-wide trace segment, flagged as thin relative to current-carrying needs. This is the higher-confidence item in the batch and warrants attention — widening to at least 0.30mm is the supplied recommendation.
- **DECAP-001** (confidence 0.5): decoupling capacitor C1 sits 3.2mm from U1 on +3V3, slightly beyond the recommended proximity for effective high-frequency decoupling at the MCU pin. At exactly the 0.5 confidence boundary, this is plausible but should still be confirmed against the actual layout before committing to a fix.

Both findings point to the same rail (+3V3), which aligns with the Power

**Chat -- What is the single most important thing to fix on this board, and why?**

**Most important fix: PWR‑001 – widen the +3V3 power trace (currently 0.25 mm).**

Reasoning:
- This is one of only two **medium‑severity** issues on the board (the highest severity present — there are no critical or high findings), and it directly affects the **Power** subscore, which at 91 is the second‑lowest category (after Routing at 93).
- The issue flags a 0.25 mm trace on the +3V3 rail, which the digest notes is

### clean minimal

Deterministic: score 100, 3 issues (PLACE-001, RTE-001, RTE-002).

**AI review:**

## PCB Design Review Summary

**Overall Assessment:** This is a very clean, minimal design — overall score of 100 with only low/info-level findings. No critical, high, or medium severity issues were identified across any category (Routing, Power, Signal Integrity, Manufacturability, Placement, Thermals, Documentation all scored 100, with Routing at 98).

### Findings

**1. Possible dangling trace stubs (RTE-001, RTE-002)**
Both issues flag trace endpoints on net **N1** that don't clearly terminate at a pad, via, or another trace within tolerance. These are the recurring theme in this review — the only two non-info findings, and both point to the same underlying pattern (unterminated stub endpoints) on the same net, which is also reflected in the "most common recommendation" field: verify each endpoint actually lands on a pad, then extend or remove the stub as needed.

- Both carry **confidence of 0.4**, which is below the 0.5 threshold — these should be treated as **unverified/manually-checked items**, not confirmed defects. Given the board has only 1 trace and 1 net per the statistics, it's possible these two findings refer to the two ends of that single trace, but that correlation isn't stated explicitly in the data, so I won't assert it as fact.
- Severity is low in both cases, consistent with the overall Routing subscore of 98 (the only subscore not at 100).

**2. Board area utilization (PLACE-001)**
Flagged as **info** severity with **low confidence (0.35)** — components reportedly occupy 0% of board footprint area on a 50mm x 40mm board with only 1 passive component and 2mm of total trace length. This suggests a very sparse/minimal layout, possibly a test board or a design with placeholder geometry. Given the low confidence, this should be manually confirmed rather than acted upon — it may simply reflect deliberate margin, a stub/test project, or a data-extraction quirk rather than an actual design inefficiency.

### Prioritization

1. **RTE-001 / RTE-002** — Low severity, low confidence, but should be manually verified first since they are the only actionable routing findings and share the same root cause pattern on net N1.
2. **PLACE-001** — Info-only, low confidence; worth a quick sanity check but not a priority given severity and lack of supporting detail (no component_kinds breakdown beyond a single passive, no connector or

**Chat -- What is the single most important thing to fix on this board, and why?**

Based on the digest, this board is in very good shape overall (score 100/100, no critical/high/medium severity issues). The only findings are:

**Most important item to check: RTE-001 and RTE-002** — both flag a possible dangling/unterminated trace stub on net **N1**. These are the highest-severity issues present (severity: low), and the principle at stake is fundamental: every trace should terminate at a pad, via, or another trace on its net. An unterminated stub could mean either a harmless routing artifact or an actual open connection on N1.

**Caveat:** Both RTE-001 and RTE-002 have confidence of only 0.4 (below the 0.5 threshold), so these should be manually verified rather than treated as confirmed defects — the tool is uncertain whether the trace end truly lands off-pad or whether it's just within its detection tolerance. The suggested fix is the same for both: "Verify this endpoint actually lands on a pad; extend or remove the stub."

The only other item, PLACE-001 (unused board area, info severity, confidence 0.35), is lower priority

### messy (multi-issue)

Deterministic: score 95, 15 issues (GND-001, GND-002, GND-003, GND-004, GND-005, PWR-001, RTE-001, RTE-002, RTE-003, RTE-004, RTE-005, RTE-006, RTE-007, SIG-001, SIG-002).

**AI review:**

# PCB Design Review Summary

**Overall Score: 95/100** — a strong result overall, with a single notable weak spot in the Power subscore (74) that pulls down an otherwise clean board (Placement, Thermals, Documentation, Manufacturability all at 100; Signal Integrity at 97).

## Overall Severity Profile
No critical or high-severity issues were found. The findings consist entirely of **6 medium** and **9 low** severity items — this is a board with polish work to do, not fundamental flaws.

## Recurring Themes

### 1. Power/Ground Return-Path Quality (the dominant theme, medium severity)
This is flagged as the highest-impact category and accounts for most of the medium-severity findings:
- **Undersized traces**: The 3V3 supply trace is only 0.25mm (**PWR-001**), and both ground traces are thin — GND at 0.20mm (**GND-004**) and GNDA at 0.25mm (**GND-005**). All three findings recommend widening to at least 0.30mm.
- **Missing copper pours**: Neither GND nor GNDA has a ground pour (**GND-002**, **GND-003**), meaning all return current currently rides on those same thin traces — compounding the width issue above.
- **Split ground nets**: The board has two separate ground-like nets, GND and GNDA (**GND-001**), which is common for analog/digital isolation but needs to be confirmed as intentional and properly star-tied rather than an accidental fragmentation.

These five findings reinforce each other: thin ground traces plus no pour plus a two-ground-net split all point to the same underlying risk — a return path that is higher-impedance and more loop-prone than ideal. I'd treat this cluster as the top priority for follow-up, even though individually each is only medium severity. Note that confidence on **GND-001** (0.4) is below the 0.5 threshold — the "unintentional split" interpretation should be manually verified rather than assumed.

### 2. Dangling Trace Stubs (low severity, low confidence)
Seven separate findings (**RTE-001, RTE-002, RTE-003, RTE-004, RTE-005, RTE-006, RTE-007**) flag possible unterminated trace stubs across nets GND, GNDA, CLK, and 3V3. This is also the single most common recommendation across the whole report. **All seven carry only 0.4 confidence

**Chat -- What is the single most important thing to fix on this board, and why?**



### weird net names + unicode

Deterministic: score 98, 9 issues (PLACE-001, PWR-001, RTE-001, RTE-002, RTE-003, RTE-004, RTE-005, SIG-001, SIG-002).

**AI review:**

# PCB Design Review Summary

## Overall Assessment
This board scores **98/100** overall, indicating a generally clean design. The subscores show Routing (94) and Power (95) as the lowest-scoring categories, with all others at or near maximum. The severity distribution is light: 0 critical, 0 high, 1 medium, 7 low, and 1 info-level finding — no urgent blockers, but a few items warrant verification.

## Recurring Themes

**1. Dangling trace stubs (5 instances — the dominant pattern)**
The most common finding by far is a set of possible unterminated trace stubs: **RTE-001, RTE-002** (both on net `<VCC>`), **RTE-003, RTE-004** (both on net `R&D_NET`), and **RTE-005** (on net `信号CLK`). All five share identical logic — a trace end that doesn't clearly land on a pad, via, or same-net trace within tolerance — and all carry the same confidence of 0.4, which is **below the 0.5 threshold**. This means none of these should be treated as confirmed defects; they should be manually verified against the actual pad geometry before any fix is applied. The suggested action for all five is consistent: confirm whether the endpoint truly lands on a pad, and extend or remove the stub if not. Given that this pattern touches all three nets in the design, it's worth a single geometric-tolerance review pass rather than five separate investigations.

**2. Power delivery margin**
**PWR-001** flags a 0.25mm trace on the `<VCC>` net as thin for its current-carrying role, recommending a widen to at least 0.30mm (more for high-current rails). This is the only medium-severity issue in the report and, at confidence 0.65, is the most trustworthy finding here — it's the top priority for action.

**3. Clock net quality**
Two low-severity findings both concern the `信号CLK` net: **SIG-001** notes it uses 3 vias (layer transitions add inductance/return-path risk), and **SIG-002** notes a total length of 46.0mm (propagation delay/skew risk). These are related facets of the same net's routing and could reasonably be addressed together by re-routing on a single layer with a more direct path. Confidence on both is low (0.45 and 0.4 respectively), so these should also be manually confirmed against actual timing/impedance requirements before committing engineering effort.

**4. Board utilization**
**

**Chat -- What is the single most important thing to fix on this board, and why?**

Based on the digest, the single most important thing to fix is **PWR-001**: the power trace on net `<VCC>` is only **0.25mm wide**, which is the sole medium-severity issue on this board (everything else is low or info severity).

**Why it matters:** A trace this thin limits current-carrying capacity and increases IR drop along the supply path, which can starve downstream components under load — this is a functional power-integrity risk rather than a cosmetic or minor routing concern. The recommended fix is to widen the trace to at least 0.30mm (more if this is a higher-current rail).

Note: confidence on this finding is 0.65, which is reasonably solid but still worth a quick manual check against your actual current requirements for the `<VCC>` rail before committing to a fix width.

Everything else in the digest (RTE-001 through RTE-005 dangling-stub warnings, SIG-001/SIG-002 clock via-count and length notes, PLACE-001 board utilization) is low-severity or info-level, and several of those carry low confidence (0.4–0.45), so they're secondary and should only be verified after addressing the power trace width.
