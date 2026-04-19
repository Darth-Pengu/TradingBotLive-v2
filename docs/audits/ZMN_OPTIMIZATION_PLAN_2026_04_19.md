# ZMN optimization plan (deep recon synthesis) — 2026-04-19

> **STATUS (2026-04-19):** This audit's actionable items are consolidated in `ZMN_ROADMAP.md`. Refer there for current status, priority, and dependencies. This doc is retained as evidence / deep-dive detail.


**Author:** Claude Opus 4.7 · **Status:** plan only, no execution this session.
**Inputs:** `CC_TOOL_SURFACE_2026_04_19.md` (what's possible now) + `ZMN_RE_DIAGNOSIS_2026_04_19.md` (what the data says).
**Constraint:** every Tier 1 item is gated on the rules-refresh prompt landing first (CLAUDE.md "Paper mode is non-negotiable" still in repo, blocks anything that touches live state).

---

## Important context: many "Tier 1" items from the abort report are already live

The abort report (2026-04-19 morning) proposed these env-var changes as the Tier 1 live-enable batch. Verified via Railway MCP `list-variables -s bot_core` this session:

| Var | Abort recommendation | Currently deployed | Status |
|---|---|---|---|
| `STAGED_TAKE_PROFITS_JSON` | `[[2.00, 0.20], [5.00, 0.375], [10.00, 1.00]]` | exactly that | ✅ done |
| `TIERED_TRAIL_SCHEDULE_JSON` | `[[0.30, 0.35], [0.75, 0.25], [2.00, 0.18], [5.00, 0.14], [10.00, 0.12]]` | exactly that | ✅ done |
| `MIN_POSITION_SOL` | 0.05 | 0.05 | ✅ done |
| `MAX_SD_POSITIONS` | 20 | 20 (bot_core) / 3 (signal_aggregator) | ✅ done (effective value is bot_core's) |
| `DAILY_LOSS_LIMIT_SOL` | 4.0 | 4.0 | ✅ done |
| `ML_THRESHOLD_SPEED_DEMON` | 40 | 30 (bot_core, unused) / **40 (signal_aggregator, the gating one)** | ✅ done at the gate; cosmetic mismatch on bot_core |

**The trading-tuning Tier 1 of the abort report is essentially complete.** The bot is operating with the recommended params on paper right now, and the BREAKEVEN_STOP exit-reason has stopped firing entirely since Apr 16 (zero new firings, vs. 39 on Apr 16 pre-deploy). What remains as "Tier 1" below is the **next-generation** of profit-edge tuning that this session's data analysis surfaced, plus housekeeping.

---

## Tier 1 — immediate, high-confidence, low-risk

Each item: env-var or single-file edit, clear evidence, rollback by reverting env var or `git revert <sha>`.

### 1.1 — Lower trail-activation tier from +30% to +10%

**Change:**
```bash
railway variables -s bot_core --set 'TIERED_TRAIL_SCHEDULE_JSON=[[0.10, 0.30], [0.50, 0.25], [1.00, 0.20], [2.00, 0.15], [5.00, 0.12]]'
```
**Evidence:** 272 stop_loss_35% trades in 7d, –56.35 SOL, avg peak only +28.3%. With the current schedule, the trail doesn't activate at peak +28% — these positions are caught only by the –35% stop. Lowering the activation tier to +10% means the trail engages, peak +28% × (1 – 0.30) = stop at +10%. Even if we capture 50% of the SOL bleed: ~+28 SOL/week.
**Rollback:** revert env var (the previous value is recorded in this doc).
**Confidence:** MEDIUM-HIGH. Risk: trail-activated positions may exit earlier on legitimate dips.
**Session size:** 15 min change + 24h observation window.

### 1.2 — Tighten 90s momentum check

**Change:**
```bash
railway variables -s bot_core --set SD_EARLY_CHECK_SECONDS=60
railway variables -s bot_core --set SD_EARLY_MIN_MOVE_PCT=3.0
```
**Evidence:** 775 no_momentum_90s trades in 7d, –41.42 SOL, avg peak +13.5%, avg hold 1.4 min. 24% peaked +10%+ before the 90s check killed them. 60s check + +3% bar would catch duds 30s earlier with –30s of accumulated loss per trade.
**Rollback:** revert env vars.
**Confidence:** MEDIUM. Risk: cuts some early-mover entries that would have run.
**Session size:** 15 min change + 24h observation.

### 1.3 — Cosmetic alignment: bot_core ML_THRESHOLD_SPEED_DEMON

**Change:**
```bash
railway variables -s bot_core --set ML_THRESHOLD_SPEED_DEMON=40
```
**Evidence:** signal_aggregator is the gating service (`signal_aggregator.py:133`). bot_core's value of 30 is read but never used as a gate. The mismatch confuses every CC session that audits env vars.
**Rollback:** revert.
**Confidence:** HIGH. Zero behavior change.
**Session size:** 5 min.

### 1.4 — CLAUDE.md docs refresh

**Change:** Remove the stale "ML inverts above 40" claim from the Known Issues section. Replace with the 7d ML-band table from `ZMN_RE_DIAGNOSIS_2026_04_19.md`. Update the "Operating Principles" section to reflect that BREAKEVEN_STOP was solved structurally (last firing 2026-04-16). Add a pointer to this optimization plan.
**Rollback:** `git revert`.
**Confidence:** HIGH. Docs only.
**Session size:** 30 min.

### 1.5 — Live trade forensics (read-only)

**Change:** None to live state. Pure investigation: where are the wallet-draining live attempts being recorded?
**Evidence:** Wallet went 3.677 SOL → 1.61 SOL between the abort report and this session (~30 min window). `paper_trades` has zero `trade_mode='live'` rows but `trades` table has 5,856 rows (vs. paper_trades' 5,833 — a 23-row delta). `live_trade_log` has 36 TX_SUBMIT buys + 33 TX_SUBMIT sells in 7d plus 9,044 errors. The bot has been spending real SOL outside the recorded `trade_mode='live'` path.
**Rollback:** N/A (read-only).
**Confidence:** HIGH that the answer exists in the DB; UNKNOWN what the answer is.
**Session size:** 30 min: list tables, query schemas, reconcile against on-chain wallet history via `helius.getWalletHistory`.

---

### Expected combined Tier 1 weekly impact (paper)

| Item | Trades affected (per 7d) | Expected SOL improvement |
|---|---:|---:|
| 1.1 trail activation | 272 stop_loss_35% | +20-30 SOL (capture half of -56 SOL bleed) |
| 1.2 60s momentum | 775 no_momentum_90s | +5-15 SOL (-41 SOL → -25 to -36) |
| 1.3 ML threshold cosmetic | 0 | 0 |
| 1.4 CLAUDE.md | 0 | 0 (clarity gain only) |
| 1.5 forensics | 0 | 0 (intel only — could reveal a live-trading bug worth +/-many SOL) |
| **Total** | | **+25-45 SOL/week paper, +0 SOL live (still TEST_MODE=true)** |

---

## Tier 2 — 1-session integrations leveraging MCPs

Each item: ~30 min to ~3 hours, supervised or autonomous after rules-refresh.

### 2.1 — Sentry SDK integration in services/

**Goal:** unlock the Sentry MCP that's already authed (`jay@rzconsulting.co`, org `rz-consulting`). Currently zero projects.
**Steps:**
1. Sentry MCP `create_project(name=zmn-bot-core, platform=python)` → DSN.
2. `pip install sentry-sdk` → add to requirements.txt.
3. In each `services/{bot_core,signal_aggregator,signal_listener,market_health,governance,treasury,ml_engine,dashboard_api}.py`: `import sentry_sdk; sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), traces_sample_rate=0.1, environment=os.getenv("RAILWAY_ENVIRONMENT"))`.
4. `railway variables -s <service> --set SENTRY_DSN=<dsn>` for each service.
**MCP used:** sentry (create_project, find_dsns), railway (set-variables).
**Validation:** trigger a test exception from each service, confirm it lands in Sentry.
**Risk:** low (SDK is mature). Cost: ~5,000 events/month free tier.
**Session size:** 45 min including validation.

### 2.2 — DexPaprika fallback in exit-price cascade

**Goal:** add a 5th-rank fallback to the price cascade for `stale_no_price` resilience.
**Steps:**
1. Add `_dexpaprika_token_price(mint)` helper in `services/bot_core.py` (HTTP call to `https://api.dexpaprika.com/networks/solana/tokens/{mint}`).
2. Insert as final fallback before `stale_no_price`.
3. Compare price with prior cascade output for 100 mints; log delta.
**MCP used:** dexpaprika (for measurement), Postgres MCP (for log inspection).
**Validation:** 24h dry-run logging only, then promote.
**Risk:** low (tail of cascade only).
**Session size:** 45 min + 24h observation.

### 2.3 — Helius `getPriorityFeeEstimate` in execution.py

**Goal:** replace hardcoded priority-fee tiers with real-time Helius estimates.
**Steps:**
1. Locate hardcoded tiers in `services/execution.py` (currently uses fixed micro-lamports per priority level).
2. Add `_get_priority_fee(account_keys, priority_level)` calling Helius `getPriorityFeeEstimate`.
3. Cache result in Redis with 30s TTL.
4. Fall back to existing hardcoded tier if Helius is unavailable.
**MCP used:** helius (`getPriorityFeeEstimate`), redis (caching).
**Validation:** measure inclusion rate for 50 trades pre/post.
**Risk:** medium — affects on-chain submission. Test on devnet first per CLAUDE.md devnet-test rule.
**Session size:** 90 min (devnet test included).

### 2.4 — Vybe pre-entry concentration measurement (metrics-only)

**Goal:** test the hypothesis that holder concentration separates winners from losers.
**Steps:**
1. Add `services/vybe_enrichment.py` calling Vybe `/v4/tokens/{mint}/top-holders`.
2. Wire pre-entry call in `signal_aggregator.py`; log to a new `signals_enriched` table.
3. After 7 days, bin winners vs losers by top10_pct and look for separation.
**MCP used:** vybe (top-holders, liquidity), Postgres MCP (table create + analysis).
**Validation:** measurement-only, no entry-decision change. After 7 days, decide whether to add a blocking filter.
**Risk:** low for measurement; medium if filter added later (could reject winners).
**Session size:** 60 min plumbing + 7-day observation + 45 min analysis.

### 2.5 — Nansen-MCP-based watched_wallets refresh job

**Goal:** make `watched_wallets` table actually fresh. Currently 44 rows, 0 active in 14 days.
**Steps:**
1. Refactor `services/nansen_wallet_fetcher.py` to use Nansen MCP (`nansen_score_top_tokens`, `token_who_bought_sold`, `wallet_pnl_summary`).
2. Job runs daily: pull last 7d top-50 SD winners by mint, find their early buyers, score those wallets, upsert top 100.
3. Don't wire to Whale Tracker entry decision yet (Tier 3).
**MCP used:** nansen (multiple tools), Postgres MCP (table update).
**Validation:** verify table populated; check `last_active_at` updates.
**Risk:** low. Nansen MCP has been DRY_RUN per env var; this exercise enables live calls within the 2000/day budget.
**Session size:** 120 min.

### 2.6 — Playwright headless triage

**Goal:** unblock dashboard regression testing.
**Steps:** see `DASHBOARD_TESTING_PLAN_2026_04_19.md` § "Gating issue".
**MCP used:** playwright (smoke test).
**Risk:** zero — investigation only.
**Session size:** 30 min.

### 2.7 — Live trade table forensics + reconciliation

**Goal:** answer the open thread from §1.5: where did the 2.07 SOL go?
**Steps:**
1. Inspect `trades` table schema and sample rows.
2. Reconcile `trades` row count delta vs `paper_trades` against on-chain wallet history.
3. Identify the code path that wrote to `trades` despite TEST_MODE=true.
4. Document in CLAUDE.md.
**MCP used:** Postgres MCP (asyncpg shim), helius (`getWalletHistory`, `parseTransactions`).
**Risk:** zero — read-only.
**Session size:** 60 min.

---

## Tier 3 — multi-session projects

### 3.1 — Dashboard v2 build (Concept C, retro-CRT operator console)

Adopt the `frontend-design` skill's "commit fully to the aesthetic direction" guidance. Build alongside current dashboard with `?v=2` flag. Use design tokens, single typography system, single icon sprite. Resolves B-001 through B-014 by construction. See `DASHBOARD_ANALYSIS_2026_04_19.md`.
**Sessions:** 4-6 (~3 hours each).
**Risk:** medium (parallel maintenance during transition).

### 3.2 — Whale Tracker entry signal wiring

Once 2.5 lands and `watched_wallets.last_active_at` shows fresh hits, wire `signal_aggregator.py` to fire Whale Tracker entries when a watched address shows up in the pumpportal stream.
**Sessions:** 1 (~90 min).
**Risk:** low (additive personality).

### 3.3 — PumpPortal MCP build

Use the `mcp-builder` skill. Read-only tools: `getTokenStats`, `getRecentTrades`, `getNewLaunches`, `getBondingCurveState`. Do NOT include trade-build/submit tools.
**Sessions:** 1-2 (~90-120 min).
**Risk:** low. See `MCP_BUILDER_CANDIDATES_2026_04_19.md`.

### 3.4 — ZMN-specific skill: `zmn-trade-analysis`

Use the `skill-creator` skill to package the `corrected_pnl_sol` vs `realised_pnl_sol` gotcha + the canonical 7d exit-reason / ML-band queries + the wallet-drain forensics pattern. So future CC sessions don't re-discover them.
**Sessions:** 1 (~75 min).
**Risk:** zero (skill, not service code).

### 3.5 — Analyst personality revival decision

Either rip Analyst out (currently `ANALYST_DISABLED=true`, last 10 trades all –ve in <7 min hold) or do the work to understand why (50-100k pullback strategy concept in `ZMN_ROADMAP.md` item 18).
**Sessions:** 1 (decision) → 2-5 (rewrite) if proceed.
**Risk:** medium.

### 3.6 — ML retrain on corrected labels

Existing `ZMN_ROADMAP.md` item 10. Blocked on 500+ clean samples. As of this session, the post-fix sample count is creeping toward that. Re-evaluate weekly.
**Sessions:** 1 (~120 min when unblocked).

### 3.7 — Live-enable supervised session

Re-attempt the abort report's plan, **with Jay supervising**. Update CLAUDE.md "Paper mode is non-negotiable" rule first (Step B3 in abort report). Then run Steps A-I with go/no-go after each.
**Sessions:** 1 (~3 hours including observation window).
**Risk:** highest of any item. Wallet exposure.

---

## Tier 4 — prerequisites that gate everything

### 4.1 — Rules-refresh prompt

**Status:** queued, not yet run.
**Why it's the gate:** `CLAUDE.md` says "Paper mode is non-negotiable. TEST_MODE=true stays true." Any session that proposes flipping `TEST_MODE` violates this rule. The prior session (abort report) refused execution on this rule. Until it's updated, **every session that touches live state will refuse**.

**Recommended new wording (from abort report Step B3):**
> Paper mode is the default; live mode is deliberate. Flipping TEST_MODE=false requires:
> 1. Wallet balance ≥ 3.0 SOL.
> 2. No active sell-storm.
> 3. Fresh portfolio_snapshots row inserted at on-chain balance.
> 4. market:mode:override=NORMAL with 24h TTL.
> 5. Supervised CC session.

**Session size:** 15 min docs edit + commit.
**Without this, Tiers 1.1/1.2/3.7 cannot proceed cleanly.**

---

## Ranked next 5 sessions

What Jay should run next, in order. Each row: prompt name (queue if doesn't exist), expected duration, expected deliverable, expected SOL impact.

| # | Session | Prompt file | Duration | Deliverable | SOL/week impact |
|---|---|---|---|---|---|
| 1 | Rules refresh | `prompts/rules_refresh_2026_04_19.md` (NEW) | 15 min | CLAUDE.md updated; commit | unblock — 0 direct |
| 2 | Tier 1 trading-tune (1.1 + 1.2 + 1.3) | `prompts/tier1_trading_tune_2026_04_19.md` (NEW) | 30 min change + 24h observation | env vars updated; observation report | **+25-45 SOL/week paper** |
| 3 | Live-trade forensics (1.5 + 2.7) | `prompts/live_trade_forensics_2026_04_19.md` (NEW) | 60 min | doc explaining the 2.07 SOL drain | informational — could reveal +/–many SOL |
| 4 | Sentry SDK integration (2.1) | `prompts/sentry_sdk_integration_2026_04_19.md` (NEW) | 45 min | sentry_sdk in 8 services; live error capture | 0 direct, big observability gain |
| 5 | Live-enable supervised (3.7) | `prompts/live_enable_supervised_2026_04_19.md` (NEW; based on abort report) | 3 hours | TEST_MODE=false on supervised session | depends on edge survival |

**Sessions 1-3 should land before any live attempt.** Session 4 makes any live attempt safer. Session 5 only after Sessions 1-4 pass cleanly.
