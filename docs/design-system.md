# Design System — Landing Page & Dashboard Accent

This is the visual system for `docs/index.html` (the public landing page) and the accent layer applied on top of the existing dashboard (`frontend/src`). It is separate from `DESIGN.md` (the project's engineering design rationale) on purpose — different document, different audience.

**The memorable thing:** PCBInsight shows its work. Every score has a reason, every AI sentence traces back to a specific finding. The design should make that verifiability *visible* — real numbers rendered as data, not decoration; citations and issue IDs never hidden; nothing claimed that can't be pointed at.

**Reference class:** GitHub, Linear, Vercel, JetBrains, Rust, Bun — verified by inspecting the actual computed styles of linear.app and bun.sh rather than assumed. Finding: none of them are actually monospace-leaning (Linear runs Inter, Bun runs system-ui, Rust runs Fira Sans on a light background) despite the "technical" reputation. That's the gap — PCBInsight can lean into monospace more deliberately than any of its own references do, which is a genuine differentiator, not just an aesthetic preference.

## Typography

| Role | Typeface | Why |
|---|---|---|
| Body, UI, headings | **IBM Plex Sans** | Open (OFL), technical/engineering heritage (IBM's own brand face), distinct from Inter/Roboto/system-ui — the fonts every generic AI-product site defaults to. |
| Stats, code, labels, nav | **JetBrains Mono** | Open (OFL), directly ties to the JetBrains reference point, and gives numbers (28 checks, 147 tests, 10 boards) the "instrument readout" treatment instead of just sitting in prose. |

Both load from Google Fonts (`fonts.googleapis.com`) or self-hosted `.woff2` — no paid license, no CDN dependency risk.

**Rule:** monospace is for things that are literally data — stat numbers, issue IDs, code, section eyebrows/labels (`HOW IT WORKS`, small-caps, letter-spaced). Body copy and headlines stay in Plex Sans — a hero headline set entirely in monospace reads clunky at large sizes, and paragraph-length monospace hurts reading speed. This is also how the actual reference sites behave in practice (mono reserved for code/data, sans for prose), even though none of them push it as far as PCBInsight will.

Type scale (rem, 16px base): `0.75` (label) / `0.875` (small) / `1` (body) / `1.125` (lead) / `1.5` (h3) / `2` (h2) / `3` (h1) / `4` (hero, desktop only — clamp down on mobile).

## Color (dark-mode-first; no light mode planned for the landing page)

```css
--bg:          #0A0E14;  /* near-black, cool-toned */
--surface:     #10151C;  /* cards, panels */
--surface-alt: #151B24;  /* nested/hover surface */
--border:      #232B36;
--text:        #E6EDF3;  /* primary */
--text-muted:  #8B96A5;  /* secondary/caption */

--accent:      #2FD9C4;  /* teal/cyan -- brand, CTAs, links, primary emphasis */
--accent-dim:  #1B8F82;  /* accent on hover/pressed, or as a subtle border */

--ai-accent:   #8A63D2;  /* reserved for AI-specific UI only -- matches the
                             existing README AI badge and the architecture
                             diagram's AI-layer purple. Never used as a
                             general brand color -- doing so would blur the
                             "AI narrates, never analyzes" boundary the whole
                             project is built around. */
```

The existing severity scale (`backend/app/reports/theme.py`: critical `#8b0000`, high `#cf222e`, medium `#bc4c00`, low `#9a6700`, info `#57606a`) is untouched — those are report/dashboard semantics, tuned for a light report background, and out of scope here. The landing page shows severity via real screenshots of the actual report, not by re-implementing the color scale against a dark background.

**Why teal over the alternatives considered:** amber/copper was the more literal "PCB" choice but sits too close to the existing medium-severity orange — a CTA button and a warning badge in near-identical colors on the same screenshot reads as accidental. Blue was the safest choice but also the most generic — it's what every dev-tool SaaS already uses, and this project's whole differentiator is that it *isn't* generic. Teal reads as "signal" — an oscilloscope trace, a readout — which fits a signal-integrity-checking tool specifically, and is nobody else's default.

## Spacing & density

4px base unit: `4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96 / 128`. Dense by default — this is engineering software, not a marketing site with generous decorative whitespace. Whitespace is used to separate sections and establish hierarchy, not to pad content out.

## Motion

Minimal. No scroll-jacking, no parallax, no auto-playing hero video. The only animation is a short (150–200ms) opacity/transform fade on section entry and standard hover/focus states. Matches `DESIGN.md`'s already-settled call: "Deliberately static rather than a fully 3D/interactive experience... loads fast, and doesn't risk reading as style-over-substance for a project whose whole pitch is engineering rigor."

## What this explicitly rejects

No glassmorphism, no gradients (including purple-to-blue "AI startup" gradients), no stock illustrations, no 3D renders, no particle backgrounds, no centered-everything layouts, no rounded-everything soft-SaaS aesthetic. Corners stay mostly square or very slightly rounded (2–4px), matching GitHub/Linear's actual density rather than the rounded-pill aesthetic of consumer SaaS.
