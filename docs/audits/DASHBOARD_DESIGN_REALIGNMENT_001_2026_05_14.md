# DASHBOARD-DESIGN-REALIGNMENT-001 — Re-scoping DASH-001 to a mobile-first monitor

**Session:** DASHBOARD-DESIGN-REALIGNMENT-001
**Author:** Claude Code (design session; NO code change, NO env change, NO redeploy)
**Date:** 2026-05-14 (AEDT)
**HEAD at session start:** `2703fdf` (DASHBOARD-AUDIT-002 — REAFFIRM REBUILD)
**Predecessors:**
- `docs/audits/DASHBOARD_AUDIT_002_2026_05_13.md` (the audit that triggered this re-scope)
- `docs/audits/DASHBOARD_REDESIGN_2026_04_19.md` (Concept A/B/C; Concept C "Unified Cockpit" is what's being re-scoped)
- `docs/audits/DASHBOARD_ANALYSIS_2026_04_19.md` (frontend-design lens, rebuild-not-patch rationale)
- `docs/audits/DASHBOARD_TESTING_PLAN_2026_04_19.md` (DASH-T-001 regression suite plan)

**Outcome:** **DESIGN COMPLETE.** Card set: 6. Build sessions: 3 × 2.5h. Verdict relative to STOPs: none fired (STOP-A weak, STOP-B passed, STOP-C did not trigger, STOP-D N/A, STOP-E none).

---

## §1 Re-scoped purpose

Jay's verbatim direction (the load-bearing design constraint):

> "Dashboard will be used for monitoring once live and doesn't need the depth we do now for analysis, patch/fix/coding/change logic etc until it's profitable and working. When it's profitable and working — dashboard I can check anywhere on the go is preferable. Especially on mobile — that would be awesome."

This narrows the dashboard's job from "operational hub + analytical surface" (where Concept C "Unified Cockpit" landed in 2026-04-19) to **a lightweight glanceable monitor that answers three questions on a phone**:

1. Is the bot alive?
2. Is it making or losing money?
3. Is anything on fire?

Analytical depth (ML calibration, exit-reason histograms, MC-band breakdowns, audit-pipeline state, signal funnel, governance, personality stats) stays in the **CSV-export → Claude analytical loop** that the audit history shows is already the working pattern. The dashboard does not replace it.

The legacy `dashboard.html` retro CRT continues to exist for desktop analytical inspection. The new mobile monitor is a complement, not a replacement — see §4 on this boundary.

---

## §2 Scope diff vs Concept C

Concept C was a 3-route, 3-tab desktop dashboard with a persistent sidebar, accent picker, and ~30 surfaces a user could navigate to. The re-scoped monitor is a single screen with 6 vertically-stacked cards.

| Concept C element | Re-scope verdict |
|---|---|
| Sidebar nav (Overview / Analytics / Wallet / Signals / Whales / Settings) | **CUT** — no routes, no sub-pages. One screen. |
| Tab system inside Overview (Now / Performance / Systems) | **CUT** — tabs invite analytical depth. |
| Equity curve, P/L distribution, exit analysis, win-rates × regime, signal funnel | **DEFER-TO-CLAUDE-LOOP** — these are CSV → Claude work. |
| ML status, governance, personality stats, whale activity, API health detail | **CUT** — debugging surfaces; Sentry/MCP/logs cover this. |
| Signal stream (live list) | **CUT** — Jay does not monitor individual signals on his phone. |
| Accent picker (6 presets), 8-theme heritage | **CUT** — single accent in v1. |
| Breadcrumb | **CUT** — no routes. |
| Topbar KPI chips (balance / treasury / PnL / SOL / CFGI / WR / ML / MODE) | **COLLAPSED** to ≤4 values folded into Cards 1+2+4. |
| Live-update timestamp, status pill | **KEEP** — fold into Card 1. |
| Mode toggle (paper / live) | **KEEP** — mixing risk per G-05 makes this load-bearing. |
| Light / dark mode | **KEEP** — daylight phone readability. |
| Recent trades (last 20 table) | **KEEP** — collapsed to last 5 with footer-link to legacy table. |
| Open positions table | **KEEP** — collapsed by default, tap to expand. |
| Wallet (route) | **KEEP** — folded into a single Card 4 (not a route). |

**Net result:** ~30 Concept C surfaces collapse to 6 cards on one screen — **5-7× smaller**. New element introduced by the re-scope: **Card 3 "Active alerts"**, the only card answering "is anything on fire?" — folds DASHBOARD-AUDIT-002 G-01 (F1+C1 filter visibility) and G-08 (rollback trigger surface) into one conditional surface.

Full scope-diff table: `.tmp_dashboard_realignment/01_scope_diff.md`.

---

## §3 The glanceable card set (6 cards)

Final card order — top to bottom on a phone:

| # | Card | Answers | Data status | Refresh | Mobile collapse |
|---|---|---|---|---:|---|
| 1 | Bot status | Q1 (alive?) | EXISTS — `/api/status` | 15s | no, sticky |
| 2 | Today's P&L | Q2 (money?) | EXISTS — `/api/session-stats` | 30s | no |
| 3 | Active alerts | Q3 (on fire?) | PARTIAL — needs new endpoint | 20s | collapses to one-liner when clear |
| 4 | Wallet / balance | Q2 | EXISTS — `/api/status` + `/api/wallets` | 60s | no |
| 5 | Open positions | Q2 | EXISTS — `/api/positions` | 30s | collapsed by default |
| 6 | Recent trades | Q2 | EXISTS — `/api/trades?limit=5` | 45s | no |

**Card 1 — Bot status (sticky-top, color-coded pill):** alive / stopped / emergency / hibernate, mode chip (PAPER/LIVE), last-heartbeat freshness, market mode word. Sources `bot:status` Redis hash via `/api/status` (verified `dashboard_api.py:322-495`).

**Card 2 — Today's P&L (large number):** session_pnl in SOL (color-coded), sub-line with trade count + WR + best/worst. Uses `COALESCE(corrected_pnl_sol, realised_pnl_sol)` per BUG-022 (verified `dashboard_api.py:2203-2208`). Mode-filtered.

**Card 3 — Active alerts (conditional visibility):** when clear, a thin green "all systems nominal" line. When firing, one row per alert: EMERGENCY_STOP, consecutive_losses ≥ 5, daily_loss_limit, market_mode=HIBERNATE for >1h, F1+C1 filter rejection-count, optional Sentry-error count. Tap a row to copy suggested clear-command. This is the one card that needs a small backend addition — see §6.

**Card 4 — Wallet:** trading wallet SOL on-chain (primary number when mode=live), paper portfolio SOL (primary number when mode=paper), 24h delta on the active one, holding wallet sub-line. Verified `dashboard_api.py:374-403`.

**Card 5 — Open positions:** count + aggregate unrealized + oldest age. Tap to expand to ≤10-row list. Mode-filtered. Verified `/api/positions` at `dashboard_api.py:580`.

**Card 6 — Recent trades:** last 5 rows — time-ago, mint-short, entry → exit, realised_pnl_sol, exit_reason short tag. Tap to copy mint to clipboard. Footer: "Open full table →" links to legacy `dashboard.html` for analytical depth.

Full card specs: `.tmp_dashboard_realignment/02_card_specs.md`.

---

## §4 Mobile-first technical shape

- **Layout:** single vertical column, 480px max-width centered on tablet/desktop (no multi-column anywhere). Status card sticky to viewport top.
- **Typography:** Geist (display + body), Geist Mono (numeric data). Two fonts only, Fontshare CDN.
- **Colour:** greyscale stack (`#09090B` → `#27272A` dark; `#FAFAFA` → `#F4F4F5` light), single chartreuse accent `#84CC16` for positive states + "alive" pill, `#EF4444` for negative, `#F59E0B` for warn/hibernate. No accent picker in v1.
- **Atmosphere:** flat surfaces, hairline borders at 6% opacity, no shadows except a single sticky-card subtle shadow. No grain, no gradients, no glow.
- **PWA:** install as PWA (`manifest.json` + minimal service worker). "Add to Home Screen" produces an app-like icon. SW provides offline shell + stale-data badge on flaky data. Push-notification capability scaffolded for a future v2 (deferred).
- **Polling vs WS:** stay polling. 6 cards × different intervals = ~6 req/min, ~1.5 MB/hr. WS overhead not justified for a monitor; instant-alert use case can be handled via PWA push later.
- **Performance budget:** ≤80 KB total page weight (HTML + CSS + JS + fonts + icons). FCP ≤2.5s on 3G. No JS framework. No analytical charting library (D3 / ECharts / etc are banned). Only Bootstrap Icons CSS (~12 KB) and Geist webfonts.
- **Auth:** reuse existing `DASHBOARD_SECRET` → JWT-in-localStorage pattern. No new auth design. (If a longer-lived / biometric-unlock token is wanted later, tracked as **DASH-AUTH-001** Tier 3, NOT V5a-blocking.)
- **Relationship to legacy dashboard:** new monitor lives at `/m`; legacy `dashboard.html` stays at `/` and `/dashboard.html`. Coexist for ≥30 days; deprecation decision after.

Full technical-shape doc: `.tmp_dashboard_realignment/03_technical_shape.md`.

---

## §5 Build-session breakdown

**Total: 3 sessions × ~2.5h = 7.5h** (vs Concept C's 4-6 × 3h = 12-18h).

| Session | Scope | Effort | Depends on | Deliverable |
|---|---|---:|---|---|
| **DASH-001-BUILD-0** | New `/api/active-alerts` endpoint in `services/dashboard_api.py` (~30 lines) aggregating Redis reads for emergency_stop / consecutive_losses / loss_pause_until / market_mode age / fill_mc_ceiling reject counter. | 0.5h | none | curl returns valid JSON; Redis fixtures pass |
| **DASH-001-BUILD-1** | `dashboard/m.html` scaffold: vanilla JS, JWT auth reuse, Cards 1/2/4, light/dark toggle, new `/m` route in `dashboard_api.py` (passthrough). | 2.5h | BUILD-0 ordering preferred (atomicity) | live `https://zmnbot.com/m` on phone, 3 cards polling |
| **DASH-001-BUILD-2** | Cards 3/5/6, PWA `manifest.json` + service worker, install + offline shell test. | 2.5h | BUILD-0 + BUILD-1 | all 6 cards live, installable PWA, offline shell works |

**Testability per session:** BUILD-0 is curl-testable, no Playwright. BUILD-1 and BUILD-2 are phone-browser manual testable; full Playwright suite (DASH-T-001 realignment, see §7) lands separately when OBS-004 unblocks.

**Sequencing:** BUILD-0 could ship as a standalone micro-session if F1+C1 observability is needed acutely before June (optional). Otherwise all three bundle as June parallel-track work with Analyst Phase 0 — NOT in the May trading-logic critical path (C1 observation → combined eval ≥2026-05-27 → ML_THRESHOLD_RETUNE_002 → dip detection).

Full breakdown: `.tmp_dashboard_realignment/04_build_breakdown.md`.

---

## §6 Backend dependencies

Only **one** backend addition is needed for the entire re-scoped UI:

- **New endpoint `/api/active-alerts`** in `services/dashboard_api.py`. Returns JSON list of firing-alert rows. Aggregates:
  - `bot:emergency_stop` (Redis, exists)
  - `bot:consecutive_losses` (Redis, exists)
  - `bot:loss_pause_until` (Redis, exists)
  - `market:mode:current` + computed age (Redis, exists)
  - `bot:filter:fill_mc_ceiling:rejects:<date>` (Redis, written by `paper_trader.py` per `0f37e82` STOP-LOSS-20-RUG-FILTER-DEPLOY-001, 14d TTL; exists but no endpoint exposes it today — this is DASHBOARD-AUDIT-002 G-01 closed by construction)
  - Optionally Sentry-issue count via the Sentry MCP — out of v1 scope, deferred.

**Cost:** ~30 lines, ~0.5h. No services/* changes outside `dashboard_api.py`. No env changes. No Redis schema changes. No DB migrations.

All other cards (1, 2, 4, 5, 6) are fully backed by existing endpoints — verified by direct read of `services/dashboard_api.py` (route registrations 256-2548; per-endpoint payload structure verified for `/api/status`, `/api/session-stats`, `/api/wallets`, `/api/positions`, `/api/trades`).

**STOP-B result:** 1 of 6 cards needs backend work, ≪50% threshold. Not a backend-heavy rebuild; UI is the bulk of the work.

---

## §7 Testability notes

DASH-T-001 (the 2026-04-19 Playwright regression-suite plan) stays valid as a plan but its **test list shrinks** under the re-scope:

- Smoke tests (load-under-3s, login-redirect, card-count) reusable with minor adaptation (`test_monitor_has_6_cards` replaces `test_dashboard_has_14_panels`).
- B-002 (corrected_pnl_sol), B-003 (open-positions Redis-skip in live), B-006 (treasury vs chain), B-007 (no console errors), B-009 (no 404 assets) — all reusable with `/m` as target URL.
- B-001 (CFGI source), B-004 (MCAP columns), B-005 (Speed Demon alignment), B-008 (WS), B-014 (BTC vs SOL CFGI) — N/A for the monitor (surfaces cut). If legacy `dashboard.html` remains in service, those tests stay scoped to it.
- **New tests** introduced by the re-scope: `test_active_alerts_collapses_when_clear`, `test_active_alerts_surfaces_emergency_stop`, `test_mode_toggle_persists`, `test_pwa_manifest_valid`, `test_service_worker_caches_shell`, `test_status_card_sticky_on_scroll`.

**Effort delta:** DASH-T-001 shrinks from 3-4h to ~2.5h. Does NOT need its own realignment doc — a 30-minute "DASH-T-001 test-list refresh" session (after OBS-004 unblocks Playwright) is sufficient. Build sessions are NOT blocked on DASH-T-001.

Full testability doc: `.tmp_dashboard_realignment/05_testability.md`.

---

## §8 References

- `docs/audits/DASHBOARD_AUDIT_002_2026_05_13.md` — most recent audit; REAFFIRM REBUILD verdict; PATCH-NOW count = 1; recommended promotion of DASH-001 from QUEUED → Tier 1
- `docs/audits/DASHBOARD_REDESIGN_2026_04_19.md` — Concepts A/B/C; Concept C "Unified Cockpit" being re-scoped here (a header note has been appended pointing to this doc)
- `docs/audits/DASHBOARD_ANALYSIS_2026_04_19.md` — frontend-design skill lens; rebuild-not-patch rationale (still valid)
- `docs/audits/DASHBOARD_TESTING_PLAN_2026_04_19.md` — DASH-T-001 Playwright plan (shrinks under re-scope, see §7)
- `docs/audits/NO_MOMENTUM_90S_AUDIT_001_2026_05_12.md` — origin of F1+C1 filter; rejection-counter Redis key
- `docs/audits/ML_SCORE_ATH_VALIDATION_001_2026_05_12.md` — reality input; ML retune pending
- `services/dashboard_api.py` — endpoint registration verified for §3 data availability

---

## §9 Open questions / decisions for Jay

1. **Acceptance of the re-scope.** The dashboard becomes meaningfully smaller — 6 cards, one screen, mobile-first, NOT a replacement for the legacy desktop dashboard. Concept C's "Unified Cockpit" framing is retired. Acceptable?
2. **Coexistence period for legacy `dashboard.html`.** Recommend ≥30 days; deprecate after if Jay never opens it. Acceptable?
3. **Single accent in v1 (chartreuse) vs accent picker.** Re-scope cuts the picker. If Jay misses theme-switching, it can come back in v1.5 — a 6-line CSS change. Default acceptable?
4. **Sentry-error count in Card 3 alerts.** Adds a small dependency on the Sentry MCP being queryable from `dashboard_api.py`. v1 ships without it; v1.5 fold-in. OK?
5. **Single-push button on Card 3 alert rows that calls `/api/emergency-stop` etc.** Re-scope spec is "tap to copy clear-command to clipboard" — passive. If Jay wants active controls (one-tap clear emergency_stop from his phone), that's an explicit auth-impact decision (live-trading kill switch on a mobile-cached JWT). Deferred to a separate session. OK?
6. **Scheduling.** Build sessions are June parallel-track with Analyst Phase 0, NOT May trading-logic critical path. Confirm timing window?

Any of these can be relaxed or tightened without affecting the rest of the design.

---

## §10 What this session did NOT do

- No dashboard HTML / JS / CSS written.
- No changes to `services/dashboard_api.py` or any backend service.
- No env changes, no Redis writes, no redeploys.
- No auth/access-control changes designed (flagged for separate session as DASH-AUTH-001 if/when wanted).
- No DASH-T-001 rewrite (just a sanity check; full refresh waits for OBS-004).
- No pulling of the dashboard rebuild into the May trading-logic critical path.

**Verdict:** **DESIGN COMPLETE.** Ready for build sessions DASH-001-BUILD-0 / BUILD-1 / BUILD-2 to come off this spec in June.
