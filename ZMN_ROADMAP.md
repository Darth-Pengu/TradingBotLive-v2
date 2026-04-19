# ZMN Roadmap

> **Single source of truth for all ZMN work items.** Last updated: 2026-04-19.
>
> All prior audit docs remain in `docs/audits/` as evidence and context; their
> actionable items are consolidated here. Update this roadmap at the end of every
> session that completes or changes an item's status. Append a changelog entry.
>
> Audit docs are linked in the **Source** column of each item below — open the
> audit for evidence; trust the roadmap for current status and priority.

---

## Current state snapshot — 2026-04-19

| Field | Value |
|---|---|
| Mode | `TEST_MODE=true` (paper). Live mode is now session-gated per CLAUDE.md "Live trading mode — session-gated" (no longer "non-negotiable"). |
| Trading wallet (on-chain) | **1.658 SOL** (`4h4pst…ii8xJ`) |
| Holding wallet (on-chain) | 0.098 SOL (`2gfHQ…ttWJ9`) |
| Paper portfolio balance | ~195 SOL (Redis `bot:portfolio:balance`) |
| 7-day Speed Demon perf | 2,256 trades · +428 SOL paper · 43.3% WR |
| Active personalities | Speed Demon (sole gating personality). Whale Tracker dormant-but-routing (+4.2 SOL on 11 trades 7d). Analyst hard-disabled. |
| Open positions | typically 0–3 paper |
| Latest commits | `cb45d6b` Sentry SDK, `1b40df3` forensics, `e9de6d7` rules refresh, `4a37598` deep recon, `d7ae512` Vybe MCP URL fix |
| Sentry integration | ✅ live across 8 services (8 projects in `rz-consulting` org); `zmn-signal-aggregator` actively capturing SocialData credit-exhaustion events |
| Blocking issues | None CRITICAL/HIGH. Outstanding MEDIUM: secret rotation (Redis/Postgres URLs in env are exposed via Railway MCP `list-variables`); Playwright headless instability blocks dashboard regression suite |

### Trading-tune env vars currently deployed (verified 2026-04-19)

| Variable | Service | Value |
|---|---|---|
| `STAGED_TAKE_PROFITS_JSON` | bot_core | `[[2.00, 0.20], [5.00, 0.375], [10.00, 1.00]]` |
| `TIERED_TRAIL_SCHEDULE_JSON` | bot_core | `[[0.30, 0.35], [0.75, 0.25], [2.00, 0.18], [5.00, 0.14], [10.00, 0.12]]` (BREAKEVEN_STOP fixed structurally — zero firings since 2026-04-16) |
| `MIN_POSITION_SOL` | bot_core | 0.05 |
| `MAX_SD_POSITIONS` | bot_core | 20 |
| `DAILY_LOSS_LIMIT_SOL` | bot_core | 4.0 |
| `ML_THRESHOLD_SPEED_DEMON` | signal_aggregator (gating) | 40 |
| `ML_THRESHOLD_SPEED_DEMON` | bot_core (unused) | 30 — see TUNE-003 |
| `TEST_MODE` | bot_core / all services | true |
| `ANALYST_DISABLED` | signal_aggregator | true |

---

## How to read this roadmap

**Status legend:** ✅ COMPLETED · 🟡 IN_PROGRESS · 📋 QUEUED · ⏸️ DEFERRED · ⛔ SUPERSEDED · ❓ UNKNOWN (needs verification)

**Tier semantics:**
- **Tier 1** — env-var / docs / single-file changes; low risk; ≤30 min sessions
- **Tier 2** — single-session MCP integrations or focused features; 30–180 min; medium risk
- **Tier 3** — multi-session projects; high scope; coordinated across weeks
- **Tier 4** — prerequisites that gate other tiers (handle first)

**ID scheme:** `TUNE-*` trading tuning · `DOCS-*` documentation · `OBS-*` observability · `INFRA-*` infrastructure · `DASH-*` dashboard structure · `DASH-B-*` specific dashboard bugs · `ML-*` model · `WHALE-*` smart-money · `MCP-*` MCP-build candidates · `LIVE-*` live-trading enablement · `SEC-*` security · `BUG-*` other known bugs · `CLEAN-*` cleanup · `TG-*` telegram

---

## Tier 4 — Prerequisites (gate-keepers)

| ID | Title | Status | Source | Notes |
|---|---|---|---|---|
| GATE-001 | Durable rules refresh (`TEST_MODE` flip session-gated) | ✅ COMPLETED `e9de6d7` | `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` Tier 4 | CLAUDE.md "Live trading mode — session-gated" replaces "Paper mode is non-negotiable". |
| GATE-002 | Live-trade forensics (resolve 2.07 SOL drain open thread) | ✅ COMPLETED `1b40df3` | `ZMN_LIVE_TRADE_FORENSICS_2026_04_19.md` | Verdict A — phantom drain. Real v4 cost ~3.4 SOL (not 1.32). All execution paths properly TEST_MODE-guarded. |
| GATE-003 | Sentry SDK integration (8 services) | ✅ COMPLETED `cb45d6b` | `session_outputs/ZMN_SENTRY_INTEGRATION_DONE.md` | 8 projects in rz-consulting; `zmn-signal-aggregator` capturing live events. |

**No outstanding Tier 4 items.** Tiers 1-3 are unblocked.

---

## Tier 1 — Immediate wins (env vars, docs, single-file)

| ID | Title | Status | Est | Impact | Depends on | Source |
|---|---|---|---:|---|---|---|
| TUNE-001 | Lower trail activation tier from `[[0.30, 0.35], …]` to `[[0.10, 0.30], …]` | 📋 QUEUED | 15m + 24h obs | **+20-30 SOL/wk paper** | none | `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` Tier 1 §1.1; `ZMN_RE_DIAGNOSIS_2026_04_19.md` pain 1 |
| TUNE-002 | `SD_EARLY_CHECK_SECONDS=60` + `SD_EARLY_MIN_MOVE_PCT=3.0` (60s momentum + 3% bar) | 📋 QUEUED | 15m + 24h obs | +5-15 SOL/wk paper | none | `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` §1.2 |
| TUNE-003 | Align bot_core `ML_THRESHOLD_SPEED_DEMON=40` (cosmetic — gate is signal_aggregator) | 📋 QUEUED | 5m | 0 (clarity) | none | `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` §1.3 |
| DOCS-001 | Correct v4 cost in CLAUDE.md and ZMN_POSTMORTEM_2026_04_16.md (~3.4 SOL not 1.32) | 📋 QUEUED | 15m | clarity for next live-enable | none | `ZMN_LIVE_TRADE_FORENSICS_2026_04_19.md` finding #2 |
| DOCS-002 | Remove stale "ML inverts above 40" Issue #1 in CLAUDE.md (already superseded by data block, but the original line still reads scary) | 📋 QUEUED (partially done in `e9de6d7`) | 15m | clarity | none | `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` §1.4 |
| DOCS-003 | Add Sentry MCP debugging recipe to CLAUDE.md (`search_issues` + `analyze_issue_with_seer` per service) | 📋 QUEUED | 15m | makes Sentry actually used | GATE-003 ✅ | `ZMN_SENTRY_INTEGRATION_DONE.md` |
| SEC-001 | Rotate Redis + Postgres passwords on Railway (currently exposed in env vars; secrets scan was clean for tracked files but env-var leakage is a separate axis) | 📋 QUEUED | 30m | security hygiene | none | `SECRETS_SCAN_2026_04_19.md` (preventive recommendation), inferred from session-by-session env exposure |
| SEC-002 | Pre-commit `detect-secrets` hook | 📋 QUEUED | 30m | prevents future leaks | none | `SECRETS_SCAN_2026_04_19.md` recommendation #1 |
| SEC-003 | Enable GitHub native secret scanning (settings toggle) | 📋 QUEUED | 5m | safety net | none (requires repo admin) | `SECRETS_SCAN_2026_04_19.md` recommendation #2 |
| BUG-010 | Governance CFGI hallucination fix (LLM outputs "CFGI at 50" regardless of actual) | 📋 QUEUED | 30m | governance correctness | Anthropic credits | prior `ZMN_ROADMAP.md` IN-FLIGHT, prior `DASHBOARD_AUDIT.md` B-010 |
| DASH-B-013 | `paper_trades.symbol` empty for all rows — populate via paper_trader fix + backfill | ⏸️ DEFERRED | 30m | dashboard "Recent Trades" symbol display | none | prior `ZMN_ROADMAP.md` |
| DASH-B-014 | Dashboard CFGI shows same value for BTC + SOL (cosmetic) — add `cfgi_btc` field | 📋 QUEUED | 10m | cosmetic | none | prior `ZMN_ROADMAP.md` |
| BUG-019 | Governance SQL type mismatch (`double precision > timestamp` in metrics query — cosmetic) | 📋 QUEUED | 15m | log noise | none | prior `ZMN_ROADMAP.md` #20 |
| INFRA-001 | Register postgres-mcp in `.mcp.json` (already pipx-installed; `--access-mode=restricted` mandatory) | 📋 QUEUED | 15m | replaces asyncpg shim in future sessions | none | `CC_TOOL_SURFACE_2026_04_19.md`; `docs/CLAUDE_TOOLING_INVENTORY.md` |
| LIVE-001 | Tier 1 trading-tune session bundle (TUNE-001 + TUNE-002 + TUNE-003 in one batch) | 📋 QUEUED | 30m + 24h obs | +25-45 SOL/wk paper combined | none (Tier 4 cleared) | `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` "Ranked next 5 sessions" #2 |

---

## Tier 2 — One-session MCP integrations / focused features

| ID | Title | Status | Est | Impact | Depends on | Source |
|---|---|---|---:|---|---|---|
| OBS-001 | DexPaprika fallback in exit-price cascade (5th-rank after Redis/BC/Jupiter/Gecko) | 📋 QUEUED | 45m + 24h obs | resilience for `stale_no_price` | none | `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` §2.2 |
| OBS-002 | Helius `getPriorityFeeEstimate` in `services/execution.py` (replace hardcoded tiers) | 📋 QUEUED | 90m (devnet test included) | live trial reliability | DEVNET-OK | `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` §2.3 |
| OBS-003 | Vybe pre-entry concentration measurement (metrics-only N days) | 📋 QUEUED | 60m + 7d obs + 45m analysis | TBD — measurement-first | none | `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` §2.4; `ZMN_RE_DIAGNOSIS_2026_04_19.md` pain 5 |
| WHALE-001 | Nansen-MCP-based `watched_wallets` refresh job | 📋 QUEUED | 120m | unblocks Whale Tracker entry-decision wiring | none | `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` §2.5; `ZMN_RE_DIAGNOSIS_2026_04_19.md` pain 4 (44 wallets, 0 active in 14d) |
| OBS-004 | Playwright headless triage on Win11 (unblocks dashboard regression suite) | 📋 QUEUED | 30m | unblocks DASH-T-001 | none | `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` §2.6; `DASHBOARD_TESTING_PLAN_2026_04_19.md` |
| OBS-005 | Live-trade table forensics + reconciliation (find why `trades` table writes in TEST_MODE) | ✅ COMPLETED `1b40df3` | — | answered: bot_core.py:793 unconditional INSERT for ML training audit | — | merged into GATE-002 |
| OBS-006 | Add real on-chain `getBalance` polling to `portfolio_snapshots` (mark `market_mode='LIVE_ONCHAIN'`) | 📋 QUEUED | 60m | prevents future "stale snapshot inherited as on-chain balance" confusion | none | `ZMN_LIVE_TRADE_FORENSICS_2026_04_19.md` finding #1 |
| ML-001 | ML training code update — read `corrected_pnl_sol` not `realised_pnl_sol` | 📋 QUEUED | 30-45m | model labels correct after backfill | none | prior `ZMN_ROADMAP.md` READY #2 |
| INFRA-002 | Helius budget enforcement — global `helius_call()` wrapper with Redis daily counter | 📋 QUEUED (HARD DEADLINE 2026-04-23) | 60-90m | prevents next budget exhaustion | none | prior `ZMN_ROADMAP.md` #4 |
| INFRA-003 | Helius enrichment caching (300s TTL on 4 uncached enrichment functions) | 📋 QUEUED | paired with INFRA-002 | reduces Helius spend | INFRA-002 | prior `ZMN_ROADMAP.md` #5 |
| ML-002 | Broader feature default cleanup — audit remaining features in `_build_features` for default-to-zero bug | 📋 QUEUED | 60-90m | prerequisites for ML retrain | none | prior `ZMN_ROADMAP.md` #6 |
| TG-001 | Telegram Yeezus listener audit — determine current Telethon integration state | 📋 QUEUED | 30m | unblocks TG-002 | Telegram credentials may need regen | prior `ZMN_ROADMAP.md` #7 |
| TG-002 | Telegram Yeezus per-source exit schedule override (+300/500/750/1000/2000%) | 📋 QUEUED | 15-30m | enables Yeezus calls | TG-001 | prior `ZMN_ROADMAP.md` #8 |
| ML-003 | Analyst CFGI threshold review (keep / lower / remove the CFGI<20 auto-pause) | 📋 QUEUED | 30m | inform Analyst revival | corrected data available ✅ | prior `ZMN_ROADMAP.md` #12 |
| ML-004 | Analyst re-enable investigation (3 trades id=3670/3879/3893 — all 0-2s holds, all stop_loss_20%) | 📋 QUEUED | 30-45m | go/no-go for Analyst revival | none | prior `ZMN_ROADMAP.md` IN-FLIGHT |
| OBS-007 | Shadow Trading Phase 2 analysis (`shadow:measurements` Redis list — latency dist, TP overshoot, peak gap) | 📋 QUEUED | 45-60m read-only | informs TP / trail tuning | 24h+ shadow data accumulated ✅ | prior `ZMN_ROADMAP.md` IN-FLIGHT |
| INFRA-004 | CFGI Stage 2 cutover — top up cfgi.io credits + verify SOL CFGI repopulates as primary | 📋 QUEUED | 30-45m | trading-mode accuracy | Jay tops up cfgi.io credits | prior `ZMN_ROADMAP.md` IN-FLIGHT |
| LIVE-002 | Supervised live-enable session (Steps A-I from `ZMN_LIVE_ENABLE_HANDOFF_2026_04_19.md`) | 📋 QUEUED | 3 hours incl. 30 min obs | begins live operation | LIVE-001 + DOCS-001 ideally first | `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` Tier 3 §3.7 + abort-report checklist |

---

## Tier 3 — Multi-session projects

| ID | Title | Status | Est | Impact | Depends on | Source |
|---|---|---|---:|---|---|---|
| DASH-001 | Dashboard v2 build (Concept C "Unified Cockpit" per `frontend-design` skill, in `dashboard/v2/` with `?v=2` flag) | 📋 QUEUED | 4-6 sessions × 3 hours | resolves B-001 to B-014 by construction | none | `DASHBOARD_REDESIGN_2026_04_19.md`; `DASHBOARD_ANALYSIS_2026_04_19.md` |
| DASH-T-001 | Dashboard regression suite (Playwright + webapp-testing skill) — covers B-001 to B-014 | 📋 QUEUED | 3-4 hours | prevents dashboard regression | OBS-004 (Playwright triage) | `DASHBOARD_TESTING_PLAN_2026_04_19.md` |
| WHALE-002 | Whale Tracker entry-signal wiring (after `watched_wallets.last_active_at` fresh) | 📋 QUEUED | 90m | activates Whale Tracker as entry-decision driver | WHALE-001 | `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` §3.2 |
| MCP-001 | PumpPortal MCP build (read-only tools: `getTokenStats`, `getRecentTrades`, `getNewLaunches`, `getBondingCurveState`) | 📋 QUEUED | 90-120m | unlocks per-mint forensics; Whale Tracker signal | none | `MCP_BUILDER_CANDIDATES_2026_04_19.md` #1 |
| SKILL-001 | Build `zmn-trade-analysis` skill (corrected_pnl_sol gotcha + 7d exit-reason / ML-band queries + wallet-drain forensics pattern) | 📋 QUEUED | 75m | future sessions skip rediscovery | none | `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` §3.4; `MCP_BUILDER_CANDIDATES_2026_04_19.md` |
| ML-005 | ML model retrain on corrected labels | 📋 QUEUED (BLOCKED) | 120m when unblocked | 70+ clean post-fix samples accumulating | 500+ clean samples (ETA 2026-04-25 to 05-05) | prior `ZMN_ROADMAP.md` #10 |
| ML-006 | FEATURE_COLUMNS pruning (55 → ~20 populated features) | 📋 QUEUED | paired with ML-005 | reduces noise pre-retrain | ML-005 | prior `ZMN_ROADMAP.md` #11 |
| WHALE-003 | Smart Money Wallet Mining sanity check (winner count >= 50 AND backfill done) | ⏸️ DEFERRED | TBD | trigger-gated | winner count >= 50 AND backfill done ✅ | prior `ZMN_ROADMAP.md` #13 |
| WHALE-004 | Smart Money Wallet Mining curation pipeline | ⏸️ DEFERRED | 90-120m | refines Whale Tracker source | WHALE-003 | prior `ZMN_ROADMAP.md` #14 |
| WHALE-005 | Smart Money Webhook Monitoring (Helius webhooks for watched wallets) | ⏸️ DEFERRED | TBD | real-time whale signals | WHALE-004 + Helius credit reset (April 26) | prior `ZMN_ROADMAP.md` #15 |
| WHALE-006 | Smart Money Entry Trigger Rule (ENTRY decision based on whale activity) | ⏸️ DEFERRED | TBD | trade off whale signal directly | WHALE-005 stable for 7 days | prior `ZMN_ROADMAP.md` #16 |
| WHALE-007 | Nansen Day-1 Enablement (re-enable Nansen for Analyst signal source) | ⏸️ DEFERRED | TBD | depends on Analyst revival | ML-004 unpauses Analyst OR WHALE-004 needs Nansen | prior `ZMN_ROADMAP.md` #17 |
| ML-007 | Analyst personality rework (50-100k pullback strategy) | ⏸️ DEFERRED | 2-5 sessions | rebuilds Analyst from scratch | ML-003 + Helius credits + WHALE-005 stable | prior `ZMN_ROADMAP.md` #18 |
| ML-008 | Vybe investigation (only if Helius + Nansen aren't enough) | ⏸️ DEFERRED | TBD | additional smart-money source | review 2026-05-10 | prior `ZMN_ROADMAP.md` #19 |
| ML-009 | Social filter (Speed Demon Option C strict — Twitter required Stage 1, 90d age + 3k followers Stage 2) | 📋 QUEUED | 75-90m | additive entry filter | ML-001 + first stable post-TP day | prior `ZMN_ROADMAP.md` READY #3 |
| MCP-002 | Jito MCP build (getBundleStatus, getRecentTipFloor, getValidatorList) | ⏸️ DEFERRED | 60-90m | partial overlap with Helius MCP — only if needed during live debugging | none | `MCP_BUILDER_CANDIDATES_2026_04_19.md` #2 |
| MCP-003 | SocialData MCP build | ⏸️ DEFERRED | 60-75m | low ROI until ML-009 ships | ML-009 | `MCP_BUILDER_CANDIDATES_2026_04_19.md` #3 |
| CLEAN-001 | Archive 30 root-level session-report `.md` files to `docs/archive/` | 📋 QUEUED | 30m | root directory readability | none | `DEPLOYMENT_BLOAT_2026_04_19.md`; `ORPHAN_FILES_2026_04_19.md` |
| CLEAN-002 | requirements.txt audit (find unused deps) — needs runtime introspection | ⏸️ DEFERRED | 60-90m | smaller container images | none | `DEPLOYMENT_BLOAT_2026_04_19.md` |

---

## Open threads (surfaced but not yet tiered — review each session)

| Thread | Status | Notes |
|---|---|---|
| `ML_THRESHOLD_SPEED_DEMON` env-var split (bot_core=30 unused vs signal_aggregator=40 gating) | merged into TUNE-003 | confirmed via Railway MCP `list-variables` |
| Birdeye MCP session expiry on first call | open | requires session-refresh story for any auto-loop using Birdeye; no current dependency |
| `bot_core.py:793` unconditional `INSERT INTO trades` (dual-write, not a security bug — recording duplication) | open (merged into LOW finding) | per `ZMN_LIVE_TRADE_FORENSICS_2026_04_19.md` finding #3 — either document the dual-purpose or add a `mode` column to `trades` |
| `live_trade_log` retention (9,044 historical errors from v4 era make "errors in last 7d" queries misleading) | open | per forensics LOW finding — TTL or docs note |
| Dashboard on-chain balance widget (forensics LOW finding #5) | open | bundle into DASH-001 |
| `2gfHQ…` holding wallet 0.098 SOL — does treasury sweep ever clear it? | open | low-priority unknown |
| Reconcile-on-mode-flip residual (CLAUDE.md flags as "discipline to codify") | open | sell-storm circuit breaker is the safety net; explicit codification deferred |
| ZMN-SIGNAL-AGGREGATOR-1 SocialData credits exhausted (Sentry-captured) | open | first triage decision: top up SocialData credits OR mark as known/wontfix in Sentry until ML-009 ships |

---

## Completed items (recent — for changelog reference)

| Date | ID | Title | Commit |
|---|---|---|---|
| 2026-04-19 | GATE-003 | Sentry SDK integration across 8 services (8 projects in rz-consulting org) | `cb45d6b` |
| 2026-04-19 | GATE-002 | Live trade forensics — Verdict A: phantom drain, real v4 cost ~3.4 SOL | `1b40df3` |
| 2026-04-19 | GATE-001 | Durable rules refresh — TEST_MODE flip is now session-gated | `e9de6d7` |
| 2026-04-19 | (audit) | Deep recon — 7 audit docs covering tool surface, re-diagnosis, optimization plan, handover, dashboard, mcp-builder candidates | `4a37598` |
| 2026-04-19 | (audit) | MCP fixes — Vybe MCP URL corrected to docs.vybenetwork.com/mcp | `d7ae512` |
| 2026-04-19 | (audit) | GitHub MCP PAT-based replaces Copilot MCP | `b6083ab` |
| 2026-04-19 | (audit) | 4 broken MCP registrations corrected | `41192b0` |
| 2026-04-17 | LIVE-pre-001 | Helius URL resolver (3-tier fallback) + sell-storm circuit breaker (cd266de) | `cd266de` |
| 2026-04-17 | (live trial) | Live trial v3 — signing verified on mainnet, 0 SignatureFailure / 83 attempts | `cd266de` |
| 2026-04-17 | (live trial) | Live trial v4 — 4+ TX_SUBMITs on-chain, wallet 5.0 → 1.6 SOL (~3.4 SOL traded) | `cd266de` |
| 2026-04-17 | DASH (Tier 1) | Dashboard mode filter + MCAP columns + LIVE view honest | (commits in roadmap COMPLETED RECENTLY section) |
| 2026-04-15 | BUG-011 | `paper_trades.outcome` column NULL — RESOLVED (backfill 2,966 rows) | `77d6a8a`, `429dd87` |
| 2026-04-14 | (recovery) | signal_aggregator restored after 21-hour outage; hardened with retry + heartbeat | `85768c5` |
| 2026-04-14 | INFRA (CFGI) | cfgi.io Stage 1 dual-read deployed | `146ca38`, `859c0fa`, `1ac9cb8` |
| 2026-04-13 | (audit) | Dashboard Tier 1 audit + P/L source fixes | `dbbffd3`, `40dadb6`, `cac5202` |
| 2026-04-13 | (data) | Historical paper_trades backfill | `cf16627`, `2f76a91` |
| 2026-04-12 | TUNE | Feature default fix (BSR/wallet_velocity) | `a8a390b` |
| 2026-04-12 | TUNE | Staged TP reporting fix | `5b92226` |
| 2026-04-11 | TUNE | Entry filter v4 | `56421ab` |
| 2026-04-09 | TUNE | Exit strategy fix | `bf57117` |
| 2026-04-07 | TUNE | Paper trader price bug fix | `9b880e1` |
| 2026-04-19 | CLEAN-pre | js/ orphan files deleted (~4.2 MB off every Railway deploy) | (in deep recon commit set) |

### Completed staged-progression items (#9.5 - #9.7)

| Original ID | Status | Notes |
|---|---|---|
| #9.5 Execution Path Audit | ✅ COMPLETED 2026-04-16 | `EXECUTION_AUDIT_2026_04_16.md` — found solders signing API drift, drove v1/v2 fix |
| #9.6 Shadow Mode Implementation | ⛔ SUPERSEDED | Shadow measurements collected via Redis instrumentation; formal `SHADOW_MODE` flag never built — v3 verified path directly on mainnet |
| #9.7 Micro-Live Validation | ✅ COMPLETED 2026-04-16/17 | Done on main wallet at 0.05 SOL position (skipped originally-planned secondary wallet) |
| #9.8 Real-Size Live on Main Wallet | 🟡 IN_PROGRESS | 1.32 SOL traded in v4 window so far; paused pending LIVE-001 + LIVE-002 |

---

## Deferred / Superseded items

| ID | Title | Reason | Source |
|---|---|---|---|
| DROPPED-001 | Kronos Foundation Model Integration | Wrong latency, wrong pretraining domain. ZMN's edge is on-chain features, not OHLCV. | prior `ZMN_ROADMAP.md` DROPPED |
| DROPPED-002 | Original "Subscribe to Nansen-labeled SM" architecture | SM labels don't exist at pump.fun scale (Finding 3) | prior `ZMN_ROADMAP.md` |
| DROPPED-003 | ML Feature Expansion (pre-retrain) | Returns as option after ML-005 retrain | prior `ZMN_ROADMAP.md` |
| DROPPED-004 | ML Score Cap at 65 | Was symptom-fix for "score inversion" claim now SUPERSEDED by data showing higher scores win more | prior `ZMN_ROADMAP.md`; `ZMN_RE_DIAGNOSIS_2026_04_19.md` ML band table |
| DROPPED-005 | Kronos ASX Equities Bot | Parked as separate project | prior `ZMN_ROADMAP.md` |
| ⛔ MCP-LETSBONK | LetsBonk MCP build | Low ROI; LetsBonk volume tiny fraction of pump.fun's ~$50M/day | `MCP_BUILDER_CANDIDATES_2026_04_19.md` #4 |
| ⛔ DASH-PATCH | Patch dashboard B-001 to B-014 individually | Per `frontend-design` skill: rebuild-not-patch (DASH-001) — every B-fix risks compounding the design debt that caused the bugs | `DASHBOARD_ANALYSIS_2026_04_19.md` |
| ⛔ MCP-RUGCHECK | Rugcheck MCP registration | Not on npm; current `services/signal_aggregator.py` calls rugcheck.xyz API directly with `RUGCHECK_REJECT_THRESHOLD=2000` env gate — no MCP needed | inferred from `.mcp.json` audit + env vars |
| ⛔ DOCKERIGNORE | Add `.dockerignore` | Nixpacks (current builder) ignores `.dockerignore` — no effect | `DEPLOYMENT_BLOAT_2026_04_19.md` |
| ⛔ ML_INVERSION | "ML inverts above 40" guidance | Pre-2026-04-12 claim, superseded by 7d data (every band 30→80+ profitable, WR climbs with score) | `ZMN_RE_DIAGNOSIS_2026_04_19.md` pain 2; CLAUDE.md ML-state block |
| ⛔ STAGED-CHAIN-RULE | "Do not skip stages" rule for live trading | Overtaken by events on 2026-04-16/17 (live trials v3+v4); replaced by CLAUDE.md "Live trading mode — session-gated" | `e9de6d7` rules refresh |

---

## Source audit cross-references

When investigating an item's evidence, open the linked audit doc:

| Audit doc | What it covers | Items it informs |
|---|---|---|
| `docs/audits/CC_TOOL_SURFACE_2026_04_19.md` | Per-MCP smoke tests, JSON-typing failure modes, skill descriptions | INFRA-001, MCP-001, OBS-004 |
| `docs/audits/ZMN_RE_DIAGNOSIS_2026_04_19.md` | 6 pain points re-examined with fresh data | TUNE-001/002/003, OBS-001/003, WHALE-001 |
| `docs/audits/ZMN_OPTIMIZATION_PLAN_2026_04_19.md` | Tier 1/2/3 ranked plan with expected SOL impact | TUNE-*, OBS-*, WHALE-001, LIVE-001/002, MCP-001 |
| `docs/audits/ZMN_CC_HANDOVER_2026_04_19.md` | Single-file context pack (state snapshot + open threads) | All — meta |
| `docs/audits/ZMN_LIVE_TRADE_FORENSICS_2026_04_19.md` | Wallet drain forensics — Verdict A | DOCS-001, OBS-006, GATE-002 |
| `docs/audits/ZMN_LIVE_ENABLE_HANDOFF_2026_04_19.md` | Abort report with paste-able Steps A-I checklist | LIVE-002 |
| `docs/audits/DASHBOARD_REDESIGN_2026_04_19.md` | Current state inventory + Concept A/B/C | DASH-001 |
| `docs/audits/DASHBOARD_ANALYSIS_2026_04_19.md` | frontend-design skill applied to dashboard bugs (rebuild-not-patch) | DASH-001 |
| `docs/audits/DASHBOARD_TESTING_PLAN_2026_04_19.md` | Playwright regression suite plan (blocked on stability) | DASH-T-001, OBS-004 |
| `docs/audits/MCP_BUILDER_CANDIDATES_2026_04_19.md` | 4 candidate MCPs scoped (PumpPortal/Jito/SocialData/LetsBonk) | MCP-001/002/003, MCP-LETSBONK |
| `docs/audits/DEPLOYMENT_BLOAT_2026_04_19.md` | Railway upload audit | CLEAN-001/002 |
| `docs/audits/ORPHAN_FILES_2026_04_19.md` | Orphan file scan | CLEAN-001 |
| `docs/audits/SECRETS_SCAN_2026_04_19.md` | Tracked-files secrets scan (clean) | SEC-002, SEC-003 |
| `session_outputs/ZMN_SENTRY_INTEGRATION_DONE.md` | Sentry SDK integration outcome | GATE-003 |
| `session_outputs/ZMN_SENTRY_DSNS.md` (gitignored) | DSN reference for the 8 Sentry projects | GATE-003 reference only |

---

## Operating principles (preserved from prior roadmap)

- **One substantive lever per session** — multiple parallel changes make failure attribution impossible
- **Verification windows BEFORE tuning** (24h+ minimum) — don't tune without observation data
- **All deploys must have auto-revert conditions** — `git revert <hash>` is the rollback
- **All thresholds env-var-configurable** for kill switch — never hardcode trading parameters
- **Read-only diagnostic prompts BEFORE write prompts** on ambiguous items
- **Never deploy multiple Railway services simultaneously** (per CLAUDE.md)
- **No `railway up` AND `git push` in the same session** (duplicate deploys waste build minutes)
- **Update this roadmap at the end of every session** — append a changelog entry

---

## Review cadence

- **Daily during active deploy weeks** — check top-3 priority Tier 1 items
- **Weekly when stable** — review all 📋 QUEUED + ⏸️ DEFERRED items, re-date or promote
- **Triggered** — when a `Depends on` clears, re-evaluate that item immediately

Items sitting in ⏸️ DEFERRED for 30+ days without a status change get either DROPPED or re-scheduled with a new trigger. No drift.

---

## Changelog

- **2026-04-19** — initial consolidated roadmap. Merged from prior `ZMN_ROADMAP.md` (20+ items) + 13 audit docs under `docs/audits/` + 1 session-output. All actionable items now use the unified ID schema and tier system. Audit docs retained as evidence (each gets a header pointing here for current status). Dashboard, forensics, rules-refresh, and Sentry sessions reflected in COMPLETED. Prior roadmap items #1–#20 + B-001/B-014 mapped to new IDs. No actionable items lost; superseded items moved to the Deferred / Superseded section with explicit reason.
