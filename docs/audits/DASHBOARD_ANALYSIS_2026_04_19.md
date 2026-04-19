# Dashboard analysis — frontend-design lens applied to known bugs

**Author:** Claude Opus 4.7 · **Date:** 2026-04-19 · **Status:** addendum to `DASHBOARD_REDESIGN_2026_04_19.md`.

This is a 3-paragraph addendum applying the `frontend-design` skill's lens to the existing dashboard bug list (`DASHBOARD_AUDIT.md`, B-001 through B-009 / B-014). The skill emphasizes intentional aesthetic direction, refined typography, cohesive color systems, atmospheric backgrounds, and meticulous spacing — and explicitly counsels against generic AI-slop aesthetics (Inter font, purple-on-white gradients, predictable card layouts).

---

## What the skill changes about the redesign concepts

The three concepts in `DASHBOARD_REDESIGN_2026_04_19.md` (Concept A "minimal command center", Concept B "data-rich Bloomberg terminal", Concept C "retro-green operator console") all stay valid as conceptual directions. But the `frontend-design` skill would push us harder on **distinctiveness within the chosen direction**. Concept C (retro-green) is closest to ZMN's current dashboard — and the skill's guidance is "if you commit to retro-CRT, commit fully": custom phosphor-glow CSS animations on number changes, scanline overlays, monospaced display font with characterful glyphs (e.g. JetBrains Mono Variable, IBM Plex Mono, Berkeley Mono), and atmospheric noise textures rather than flat black. The current dashboard is "retro-green-ish" — it gets the color but skips the aesthetic conviction. **Most of the B-* bugs are symptoms of half-commitment**: B-005 (panel alignment) reads as "designed with an assumption of a 12-col grid that the actual layout doesn't enforce"; B-007 (console errors) reads as "ad-hoc scripts added across sessions without a coherent JS module structure"; B-009 (404 assets) reads as "stale references from a prior theme". A frontend-design pass that committed to a single design system (CSS variables, design tokens, a single fonts.css, a single icons.svg sprite) would prevent the reappearance of these classes of bugs even after the existing instances are fixed.

## The bug delta the skill counsels

The skill's guidance is to *not* try to fix B-001 through B-014 piecemeal, because each fix risks adding to the design debt. Instead: build Concept C in a fresh `dashboard/v2/` directory using committed design tokens, a typography system, and a layout grid; route a feature flag (`?v=2`) that lets Jay toggle between current and new; let the new dashboard launch with **all known bugs absent by construction** (e.g. CFGI source labeling becomes a reusable `<DataSourceBadge>` component; MCAP columns are part of the table component definition not bolted on; Redis-vs-DB filtering is a query-builder primitive not a per-widget if/else). This is more work than fixing the bugs in place, but every dashboard bug fixed since 2026-04-13 has been re-introduced or partially reverted by a subsequent session — the cost of debt-paying is now higher than the cost of rebuild.

## Pairs naturally with `webapp-testing`

The skill explicitly points at "one well-orchestrated page load with staggered reveals" as a higher-impact moment than scattered micro-interactions. Pair this with the regression suite proposed in `DASHBOARD_TESTING_PLAN_2026_04_19.md` — the `test_dashboard_loads_under_3s` smoke test becomes the gate that protects the staggered-reveal moment from being broken by a future change. Two skills that compound: design intent + automated verification. Without either, the dashboard drifts; with both, every change is an explicit choice with a measurable verification.

---

## TL;DR for the optimization plan

- **Tier 3:** Adopt Concept C as the v2 build target. Use `frontend-design` skill conventions (committed typography, design tokens, atmospheric details). Build alongside, not on top of, the current dashboard.
- **Tier 2:** Once Playwright is stable, build the regression suite first against the *current* dashboard (cheap signal), then promote the same tests against v2 once it ships.
- **Tier 1 (cosmetic-only):** none. The bug fixes the abort report's scope might cover should not be cherry-picked individually — bundle into the v2 build.
