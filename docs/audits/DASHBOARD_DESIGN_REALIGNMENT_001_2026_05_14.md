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

**Outcome:** **DESIGN COMPLETE.** Card set: **7** (was 6 — biggest-wins added per 2026-05-14 amendment; cap nudged 6 → 7, see §3 + §11). Build sessions: **3 × ~2.8h = ~8.5h** (was 7.5h — celebration FX + biggest-wins card + Card 2 expansion folded in). Verdict relative to STOPs: none fired (STOP-A weak, STOP-B passed, STOP-C did not trigger, STOP-D N/A, STOP-E none).

> **Amendment 2026-05-14 (Jay decisions + design amendment):** §9 open questions resolved (see §9). Four design additions folded in (cumulative P&L on Card 2; new biggest-wins card; in-app celebration FX on ≥3x wins; push-notification version explicitly deferred). See §11 for the amendment's scope-cap analysis and §5 for re-stated build breakdown.

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

## §3 The glanceable card set (7 cards)

Final card order — top to bottom on a phone:

| # | Card | Answers | Data status | Refresh | Mobile collapse |
|---|---|---|---|---:|---|
| 1 | Bot status | Q1 (alive?) | EXISTS — `/api/status` | 15s | no, sticky |
| 2 | P&L (today + all-time) | Q2 (money?) | EXISTS — `/api/session-stats` + `paper_trades` query | 30s | no |
| 3 | Active alerts | Q3 (on fire?) | PARTIAL — needs new endpoint | 20s | collapses to one-liner when clear |
| 4 | Wallet / balance | Q2 | EXISTS — `/api/status` + `/api/wallets` | 60s | no |
| 5 | Open positions | Q2 | EXISTS — `/api/positions` | 30s | collapsed by default |
| 6 | Recent trades | Q2 | EXISTS — `/api/trades?limit=5` | 45s | no |
| 7 | Biggest wins | Q2 (motivation) | PARTIAL — needs new endpoint | 60s | collapsed to top-3 by default |

**Card 1 — Bot status (sticky-top, color-coded pill):** alive / stopped / emergency / hibernate, mode chip (PAPER/LIVE), last-heartbeat freshness, market mode word. Sources `bot:status` Redis hash via `/api/status` (verified `dashboard_api.py:322-495`).

**Card 2 — P&L (large number + sub-line, amended 2026-05-14):** session today + **all-time cumulative** on the same card. Layout: one large headline number with a two-up split — "Today: +X SOL  |  All-time: +Y SOL" (or vertically stacked on narrow viewports). Both numbers use `COALESCE(corrected_pnl_sol, realised_pnl_sol)` per BUG-022 (verified `dashboard_api.py:2203-2208`). Sub-line with today's trade count + WR + best/worst. Mode-filtered.

> **Data-scoping for Card 2 all-time:** to avoid resurfacing the known paper/live log contamination (the fake ~+601 SOL lifetime figure tracked in `LIVE-TRADES-LOGGING-AUDIT-001`), the all-time number queries **`paper_trades` only** and excludes any aggregate-from-Redis path that may carry pre-cleanup lifetime totals. The session-stats endpoint already filters to `paper_trades` per CLAUDE.md's BUG-022 fix; the all-time addition extends that same query without a time floor. **NOT** to be widened to `trades` or `live_trades` until LIVE-TRADES-LOGGING-AUDIT-001's verdict is in and the contaminated rows are reconciled.

**Card 3 — Active alerts (conditional visibility):** when clear, a thin green "all systems nominal" line. When firing, one row per alert: EMERGENCY_STOP, consecutive_losses ≥ 5, daily_loss_limit, market_mode=HIBERNATE for >1h, F1+C1 filter rejection-count, optional Sentry-error count. Tap a row to copy suggested clear-command. This is the card that needs a backend addition — see §6.

**Card 4 — Wallet:** trading wallet SOL on-chain (primary number when mode=live), paper portfolio SOL (primary number when mode=paper), 24h delta on the active one, holding wallet sub-line. Verified `dashboard_api.py:374-403`.

**Card 5 — Open positions:** count + aggregate unrealized + oldest age. Tap to expand to ≤10-row list. Mode-filtered. Verified `/api/positions` at `dashboard_api.py:580`.

**Card 6 — Recent trades:** last 5 rows — time-ago, mint-short, entry → exit, `realised_pnl_sol`, `exit_reason` short tag. Tap to copy mint to clipboard. Footer: "Open full table →" links to legacy `dashboard.html` for analytical depth.

**Card 7 — Biggest wins (NEW 2026-05-14):** top wins ranked by `realised_pnl_sol` desc. Top 3 visible by default; tap "show more" to expand to top 10. Each row: token symbol (or 4-char mint prefix if symbol absent), `realised_pnl_sol`, `realised_pnl_pct` as Nx multiplier ("+412%" → "5.1x" — pick the more glanceable representation per row width), and the **mint / contract address** as a tap-to-copy chip (icon `bi-clipboard`). Long-press / secondary tap: opens DexScreener (`https://dexscreener.com/solana/<mint>`) in a new tab as the explorer. Per mobile-tap simplicity, **default tap = copy-to-clipboard; "↗" link icon = DexScreener** — copy is the more common action on a phone, link is one extra tap when needed. Mode-filtered.

> **CRITICAL data-scoping constraint for Card 7 (per amendment 2026-05-14):** queries **clean `paper_trades` data only**, filtered to: `trade_mode='paper'` AND `entry_time >= 1747104561.0` (2026-05-13 03:29:21Z UTC, the C1 deploy timestamp). **Note:** during this amendment session, `LIVE-TRADES-LOGGING-AUDIT-001` closed (commit `b867daa`) and added a `trade_mode` discriminator to the `trades` table; the live-side contamination angle Jay's amendment anticipated is reconciled there. This does NOT widen Card 7's scope — the C1 floor remains because it also guards pre-F1 / pre-C1 paper-side variance and pre-cliff archive accounting. See DASH-BIGGEST-WINS-SCOPING-001 for future revisit conditions. MUST NOT join, union, or fall back to `trades` / `live_trades` or any all-time Redis aggregate. The post-C1 paper window is the only verified-clean dataset until `LIVE-TRADES-LOGGING-AUDIT-001` reconciles the broader contamination (the fake ~+601 SOL lifetime figure from log-only / mis-classified rows). The endpoint should hardcode this lower-bound timestamp and reject query-string overrides of `since` (or accept overrides only to a *later* timestamp — never earlier). Future widening requires an explicit code edit and an audit-doc reference, so this constraint cannot drift silently. Tracked as **DASH-BIGGEST-WINS-SCOPING-001** — when LIVE-TRADES-LOGGING-AUDIT-001 closes with a clean reconciliation, the floor can be revisited.

Full card specs: `.tmp_dashboard_realignment/02_card_specs.md`.

### §3.1 Celebration FX on ≥3x wins (NEW 2026-05-14)

In-app celebration triggered when a closed trade with `realised_pnl_pct >= 200` (the ≥3x multiplier; column verified at `services/db.py:128-129`) appears in the polled `/api/trades` or `/api/top-wins` payload while the monitor is open.

**Trigger detection (client-side):** the dashboard JS keeps a small `seenTradeIds` Set in `sessionStorage` (clears on tab close). On each `/api/trades` poll, any trade whose `id` is new AND `realised_pnl_pct >= 200` fires the FX. Re-mounts of the page see seen-ids again on first poll; that's intentional (no re-fire on reload of an already-celebrated trade within the session).

**FX components:**
- **Confetti / particle burst:** lightweight canvas-confetti effect, vendored ~7 KB. 1.5-2s burst, then fades. Respects `prefers-reduced-motion` → on, falls back to a single static "🎉" emoji bloom.
- **Haptic buzz:** `navigator.vibrate([60, 30, 60, 30, 120])` if `'vibrate' in navigator` (Android + most non-iOS PWAs). Silent on platforms without support (iOS Safari).
- **Optional sound:** muted by default. A single thumbtack-toggle in Card 1 (or a settings popover) enables a short success chime (`<audio>` element, ≤20 KB MP3 or generated via WebAudio). Persisted in `localStorage`. Auto-respects iOS autoplay restriction (won't play until first user interaction in the session).

**Why ≥3x specifically (rationale documented for the threshold):** the C1 KEPT-slice winners cluster well above 1.5x; +200% (3x) cleanly separates a meaningful win from a routine TRAILING_STOP +20-50% close. Below the threshold: normal row render, no FX. At/above: full celebration. The threshold is a single JS constant — `BIG_WIN_PCT_THRESHOLD = 200` — and is **trivial to retune** in a follow-up after Jay sees the firing cadence in practice.

**Out of scope for in-app FX:** push notifications when the app is closed — see §3.2.

### §3.2 Push notifications when app is closed — DEFERRED (NEW 2026-05-14)

Explicitly deferred to **post-SD-validation** (post May 27 combined eval, post V5A flip stability). Rationale per Jay's amendment:

- Push notifications need a backend event emitter on the trade-close path (`services/bot_core.py:_close_position` or equivalent), which **must not be touched during SD validation** (don't confound the May 27 combined eval).
- Push also needs a notification subscription registry (Web Push API + VAPID keys + service-worker push handler + per-device subscription persistence) — that's a non-trivial backend addition with its own auth surface.
- v1 ships in-app-only celebration (§3.1). The PWA service worker is scaffolded for push during BUILD-2 (manifest + SW skeleton); the **push event handler is left as a TODO with a stub that logs to console**. No subscription, no server keys, no event emitter yet.

Tracked as **DASH-PUSH-NOTIFICATIONS-001** Tier 3 🟢. Scoping deliberately punted until SD validation completes AND a separate session can scope the backend emitter without colliding with V5A flip work.

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

## §5 Build-session breakdown (re-stated 2026-05-14 with amendment folded in)

**Total: 3 sessions × ~2.8h = ~8.5h** (was 7.5h pre-amendment; +1h for biggest-wins endpoint + Card 2 cumulative + celebration FX scaffolding). Still ~50% smaller than Concept C's 12-18h.

| Session | Scope | Effort | Depends on | Deliverable |
|---|---|---:|---|---|
| **DASH-001-BUILD-0** | **TWO new endpoints** in `services/dashboard_api.py`: (a) `/api/active-alerts` (~30 lines) aggregating Redis reads for emergency_stop / consecutive_losses / loss_pause_until / market_mode age / fill_mc_ceiling reject counter; (b) `/api/top-wins?limit=10` (~30 lines) querying `paper_trades` filtered to `trade_mode='paper'` AND `entry_time >= 1747104561.0` (C1 deploy floor — hardcoded per §3.1 scoping constraint), ordered by `realised_pnl_sol` desc. Also: a one-line addition to `/api/session-stats` (or a sibling `/api/lifetime-pnl`) returning the all-time `paper_trades` aggregate `SUM(COALESCE(corrected_pnl_sol, realised_pnl_sol))` filtered to `trade_mode='paper'` (no time floor) — see §3 Card 2 data-scoping note. | **1.0h** (was 0.5h) | none | curl returns valid JSON for all three; Redis + DB fixtures pass; hardcoded floor for top-wins verified |
| **DASH-001-BUILD-1** | `dashboard/m.html` scaffold: vanilla JS, JWT auth reuse, **Cards 1 + 2 (today + all-time both rendered) + 4 + 7 (biggest wins, top-3 default + tap-to-copy mint chip + DexScreener "↗" link)**, light/dark toggle, new `/m` route in `dashboard_api.py` (passthrough). Card 7 lands here (not BUILD-2) because both Card 2 and Card 7 are P&L-flavored and ship together motivationally. | **2.8h** (was 2.5h) | BUILD-0 (endpoint contracts) | live `https://zmnbot.com/m` on phone, 4 cards polling |
| **DASH-001-BUILD-2** | Cards 3 + 5 + 6, **celebration FX (canvas-confetti vendored, `navigator.vibrate` haptic, optional sound toggle in Card 1, ≥3x trigger on `realised_pnl_pct`, `prefers-reduced-motion` fallback)**, PWA `manifest.json` + service worker, install + offline shell test, **push-event-handler stub (logs to console only)** scaffolded per §3.2 deferral. | **2.8h** (was 2.5h) | BUILD-0 + BUILD-1 | all 7 cards live, FX fires on ≥3x trade, installable PWA, offline shell works, push handler stub present-but-inert |

**Testability per session:** BUILD-0 is curl-testable, no Playwright. BUILD-1 + BUILD-2 are phone-browser manual testable; full Playwright suite (DASH-T-001 realignment, see §7) lands separately when OBS-004 unblocks. **New BUILD-2 manual checks:** confetti renders on a synthetic ≥3x payload; haptic fires on Android Chrome; sound toggle persists across reloads; FX respects `prefers-reduced-motion`; FX does NOT re-fire when reloading a tab that's already seen the trade-id within the session.

**Sequencing:** BUILD-0 could ship as a standalone micro-session if F1+C1 observability is needed acutely before June (optional). Otherwise all three bundle as **June parallel-track work with Analyst Phase 0** — NOT in the May trading-logic critical path (C1 observation → combined eval ≥2026-05-27 → ML_THRESHOLD_RETUNE_002 → dip detection).

Full breakdown: `.tmp_dashboard_realignment/04_build_breakdown.md` (header-amended 2026-05-14; original 7.5h estimate retained inline as the pre-amendment baseline for traceability).

---

## §6 Backend dependencies (amended 2026-05-14)

**Three** backend additions in `services/dashboard_api.py` — all read-only, single-file, no DB migrations, no env changes:

1. **`/api/active-alerts`** (~30 lines). Returns JSON list of firing-alert rows. Aggregates:
   - `bot:emergency_stop` (Redis, exists)
   - `bot:consecutive_losses` (Redis, exists)
   - `bot:loss_pause_until` (Redis, exists)
   - `market:mode:current` + computed age (Redis, exists)
   - `bot:filter:fill_mc_ceiling:rejects:<date>` (Redis, written by `paper_trader.py` per `0f37e82` STOP-LOSS-20-RUG-FILTER-DEPLOY-001, 14d TTL; exists but no endpoint exposes it today — this is DASHBOARD-AUDIT-002 G-01 closed by construction)
   - Optionally Sentry-issue count via the Sentry MCP — **out of v1 scope, deferred** (Jay decision §9.4).

2. **`/api/top-wins`** (~30 lines, NEW per 2026-05-14 amendment). Query: `SELECT mint, symbol, realised_pnl_sol, realised_pnl_pct, exit_time FROM paper_trades WHERE trade_mode='paper' AND entry_time >= 1747104561.0 AND realised_pnl_sol IS NOT NULL ORDER BY realised_pnl_sol DESC LIMIT $1` (default LIMIT 10; max 50). The C1-deploy floor `1747104561.0` is **hardcoded as a module-level constant** named `BIGGEST_WINS_CLEAN_DATA_FLOOR_TS` with a comment referencing this audit doc (§3 Card 7 scoping constraint). The endpoint **does not accept a `since` query param earlier than the floor** — silently clamps to the floor or 400s, CC's call (clamp recommended for forward-safety). See DASH-BIGGEST-WINS-SCOPING-001 for revisitation conditions.

3. **`/api/lifetime-pnl`** (~10 lines, NEW per 2026-05-14 amendment) **OR** extension of `/api/session-stats` to include a `lifetime_pnl_sol` field. Either form acceptable — CC chooses during BUILD-0 based on response-shape impact. Query: `SELECT SUM(COALESCE(corrected_pnl_sol, realised_pnl_sol)) FROM paper_trades WHERE trade_mode='paper' AND realised_pnl_sol IS NOT NULL`. No time floor (the all-time number is the point) but **strictly `paper_trades` only** — no `trades` join, no Redis aggregate fallback (per §3 Card 2 data-scoping note). Returns `{"lifetime_pnl_sol": <float>, "trade_count": <int>}`.

**Cost:** ~70 lines total across all three (~30 + ~30 + ~10), ~1.0h. No services/* changes outside `dashboard_api.py`. No env changes. No Redis schema changes. No DB migrations.

All other cards (1, 4, 5, 6) and the today-side of Card 2 are fully backed by existing endpoints — verified by direct read of `services/dashboard_api.py` (route registrations 256-2548; per-endpoint payload structure verified for `/api/status`, `/api/session-stats`, `/api/wallets`, `/api/positions`, `/api/trades`).

**STOP-B result (revised post-amendment):** 3 of 7 cards need backend work (Card 2 all-time-half, Card 3, Card 7) ≈ 43% — still under the 50% threshold; UI remains the bulk of the work. Not a backend-heavy rebuild.

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

## §9 Open questions / decisions for Jay — ALL RESOLVED 2026-05-14

1. **Acceptance of the re-scope.** ✅ **ACCEPTED.** Concept C "Unified Cockpit" → mobile-first card monitor at `/m` is correct.
2. **Coexistence period for legacy `dashboard.html`.** ✅ **YES.** Keep `dashboard.html` at `/`, new monitor at `/m`, coexist ≥30 days. Deprecation decision after.
3. **Single accent in v1 (chartreuse) vs accent picker.** ✅ **SINGLE ACCENT.** It's a monitor, not a customization surface. No picker. (v1.5 picker remains a 6-line CSS change if Jay misses theme-switching later.)
4. **Sentry-error count in Card 3 alerts.** ✅ **DEFER.** Get the cards working first; Sentry health folds in v1.5.
5. **Active emergency-stop controls from phone.** ✅ **DEFER.** Monitor-only for v1. Letting a phone kill the bot is a security surface (auth-impact); separate, careful decision — not v1.
6. **Scheduling.** ✅ **JUNE PARALLEL-TRACK** with Analyst Phase 0, NOT the May trading-logic critical path.

All six resolved without amendment to the rest of the design. The 2026-05-14 amendment additions (Card 2 cumulative + Card 7 biggest wins + ≥3x celebration FX + push deferral) are tracked separately in §3.1, §3.2, §5, §6, and §11.

---

## §10 What this session did NOT do

- No dashboard HTML / JS / CSS written.
- No changes to `services/dashboard_api.py` or any backend service.
- No env changes, no Redis writes, no redeploys.
- No auth/access-control changes designed (flagged for separate session as DASH-AUTH-001 if/when wanted).
- No DASH-T-001 rewrite (just a sanity check; full refresh waits for OBS-004).
- No pulling of the dashboard rebuild into the May trading-logic critical path.

**Verdict:** **DESIGN COMPLETE** (re-confirmed post-amendment 2026-05-14). Ready for build sessions DASH-001-BUILD-0 / BUILD-1 / BUILD-2 to come off this spec in June.

---

## §11 2026-05-14 amendment — scope-cap analysis and rationale

The original spec stated a "**≤6 cards**" cap. The amendment introduces a new biggest-wins card (Card 7). This section documents the cap decision so a future session doesn't quietly re-creep beyond it.

### Was the cap raised or did a card merge?

**Raised: 6 → 7.** The biggest-wins card was evaluated against three merge candidates before choosing to nudge the cap:

| Merge candidate | Verdict |
|---|---|
| Fold biggest-wins into **Card 6 Recent trades** | REJECTED. Semantically different — "recent" is time-ordered (chronology), "biggest" is magnitude-ordered (motivation). Merging produces a confused card that does neither well; on a phone, the user has to mentally re-sort to read either signal. |
| Fold biggest-wins as a tap-to-expand inside **Card 2 P&L** | CONSIDERED. The cumulative-P&L addition already pushes Card 2 to two numbers + sub-line; a third surface (an expanded biggest-wins drawer) makes Card 2 fight for too much screen height. Rejected for cognitive density. |
| Make biggest-wins a footer-linked **separate page** (not a card) | REJECTED. Jay's amendment was explicit: "in the first build, not deferred." A footer link is a soft demotion; the celebration-FX engagement loop (§3.1) is reinforced by biggest-wins being **on the main scroll**, not tucked away. |

**Decision: 7 cards. Cap = 7.** The "≤6" wording in the original spec is superseded by this section.

### Why this is not Unified-Cockpit creep

The §3 STOP-C check at design time was about avoiding sub-pages, sub-tabs, and routes — the structural elements that turned Concept C into ~30 surfaces. Nudging from 6 to 7 cards on the same single-screen vertical scroll does NOT introduce any of those:

- Still one route (`/m`).
- Still zero tabs.
- Still zero sub-pages.
- Single-column vertical scroll preserved.
- Per-card scope unchanged (each card still answers one question or one closely-related pair).

Surface count went from 6 → 7 (≈+17%). Concept C → re-scope was 30 → 6 (≈80% smaller). Post-amendment: 30 → 7 (≈77% smaller). Still in the original spirit of the re-scope; not a creep back toward Concept C.

### Forward guardrail

Any future amendment proposing **>7 cards**, **a tab inside any card**, **a second route**, or **a sub-page** triggers a fresh STOP-C check and should be a new dashboard-design audit doc, not a quiet additive amendment to this one. The single-column / single-route / zero-tab discipline is the load-bearing constraint of the re-scope — that's what keeps the dashboard *glanceable* rather than analytical.

### New roadmap items introduced by this amendment

| Item | Tier | Status | Notes |
|---|---|---|---|
| `DASH-BIGGEST-WINS-SCOPING-001` | Tier 3 🟢 | OPEN (prereq closed) | Revisit Card 7's hardcoded post-C1 paper-only floor. **Update 2026-05-14 (during this amendment session):** `LIVE-TRADES-LOGGING-AUDIT-001` closed (commit `b867daa`) — the `trades` table now carries a `trade_mode` discriminator (9,480 paper / 41 live), so the live-side contamination angle Jay's amendment anticipated is reconciled. The post-C1 floor remains active because it ALSO guards pre-C1 paper-side variance (pre-F1 / pre-`BOT_CORE_FILL_MC_CEILING_USD`-deploy rows, pre-cliff accounting in `paper_trades_archive_20260421`). Card 7's scope is "verified-clean post-C1 paper data"; LIVE-TRADES-LOGGING-AUDIT-001 closing does not by itself widen that scope. Future revisit: after Jay reviews ≥30d of post-C1 sample and decides whether to relax the floor. |
| `DASH-PUSH-NOTIFICATIONS-001` | Tier 3 🟢 | OPEN | Push-notification version of the celebration FX. Deferred until post-SD-validation (post-May-27 combined eval, post-V5A flip stability). Backend emitter on the trade-close path must not be touched during SD validation. |
| `DASH-CELEBRATION-FX-THRESHOLD-TUNE-001` | Tier 3 🟢 | OPEN | After Jay sees the ≥3x fire-rate in practice (single JS constant `BIG_WIN_PCT_THRESHOLD`), optionally retune. Trivial follow-up; not a design issue. |

All three are documentation-only roadmap entries today; no V5A blocking, no May critical path impact.
