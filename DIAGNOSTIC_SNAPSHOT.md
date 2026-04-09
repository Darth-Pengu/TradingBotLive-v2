# Diagnostic Snapshot — 2026-04-09 13:20 UTC

## TL;DR
- Bot trading: **NO** (last trade 2026-04-08 14:52 UTC, ~22.5 hours ago)
- Signal flow: **ALIVE** — signals scoring, SCORED reaching bot_core
- Funnel leak point: **bot_core** — EMERGENCY STOP active since 2026-04-08 14:55 UTC
- Most likely root cause: **Rug cascade emergency stop triggered after the HIBERNATE fix unblocked trades — 5 stop-loss exits in 30 minutes on junk tokens in extreme fear market**
- Secondary blocker: **Position sizing too small** — multiplier stack (0.7 personality x 0.35 rugcheck = 0.1256 SOL) falls below 0.15 minimum
- Recommended next prompt: **Reset emergency stop via Redis (DEL bot:emergency_stop, SET bot:consecutive_losses 0, DEL bot:loss_pause_until), restart bot_core only**

## Q1 Signal Flow
**ALIVE.** All three stages working:

| Stage | Status | Evidence |
|-------|--------|----------|
| signal_listener | HEALTHY | ~10+ signals/minute from PumpPortal + GeckoTerminal. Most recent: 13:17 UTC Apr 9 |
| signal_aggregator | HEALTHY | ML scoring active, HIBERNATE bypass working (from commit 47de1fa). Most recent SCORED: 13:17:03 UTC Apr 9 |
| bot_core | **EMERGENCY STOPPED** | Last activity: 14:55:38 UTC Apr 8 — "EMERGENCY STOP: Rug cascade detected" |

Signal listener WebSocket: active, no reconnect issues in visible logs.
Telegram: active (got channel updates).
Discord: 403 error on one channel read (non-blocking).

## Q2 Aggregator Funnel
From visible log window (~200 lines, ~13:16-13:17 UTC April 9):

| Stage | Count | Notes |
|-------|-------|-------|
| HIBERNATE bypass | many | Every signal processed through AGGRESSIVE_PAPER bypass |
| FILTER: PASS | ~15 | All passed primary filters |
| ML SCORE | 36 | All scored by inline AcceleratedMLEngine |
| ML reject | 24 | Scores 5-39.6 rejected (threshold=40) |
| SCORED | 15 | Scores 40.7-67.4 passed through |
| FILTER: REJECT | 1 | GMVdcEBpwSst — no_social_links |
| HARD REJECT | 0 | None seen |
| LIQ_REJECT | 0 | None seen |
| KOTH_REJECT | 0 | None seen |
| GRAD_REJECT | 0 | (separate processing path) |
| Tracebacks | 0 | None |

**Funnel is healthy.** ~42% of ML-scored signals pass threshold (15/36). 
All signals go to speed_demon only — analyst/whale_tracker not receiving signals.

Score distribution in visible window:
- 5.7, 8.7, 8.9, 12.4, 12.5, 13.1, 17.6, 20.0, 22.2, 22.2, 39.6 (rejected)
- 40.7, 42.2, 47.0, 48.4, 56.7, 67.4 (scored)

ML features filled: 18-20/68 (26-29%). AcceleratedMLEngine sees 9/25 (36%).

## Q3 bot_core Activity
**EMERGENCY STOPPED** since 2026-04-08 14:55:38 UTC.

Timeline on April 8 (after HIBERNATE fix deployed at ~14:27):
```
14:27:42 — PAPER ENTERED EmRPgzWNv9LQ (ML=70.6) → stop_loss_35% at 14:27:42 (-3.5%)
14:38:16 — PAPER ENTERED 72xnwSQg5dV4 (ML=77%)  → stop_loss_35% at 14:39:04 (-0.4%)
14:38:22 — PAPER ENTERED 7BRcLnYySCXC (ML=44%)  → stop_loss_35% at 14:39:13 (-0.8%)
14:48:06 — PAPER ENTERED BawC2r8XiKL4 (ML=??)   → no_momentum_90s at 14:51:50 (-1.4%)
14:51:25 — PAPER ENTERED Gnn5AyeBGxry (ML=65%)  → no_momentum_90s at 14:53:10 (-0.3%)
14:51:26 — PAPER ENTERED HNmA1UvYp61S (ML=70%)  → stop_loss_35% at 14:52:26 (-51.8%)
14:52:18 — PAPER ENTERED DFMUm9FWYdP1 (ML=76%)  → stop_loss_35% at 14:52:42 (-0.7%)
14:53:48 — REJECTED 75sqstw1B653: position 0.1256 SOL < 0.15 minimum
14:54:46 — REJECTED Faf4vfpnb4eP: position 0.1256 SOL < 0.15 minimum
14:55:38 — CRITICAL: EMERGENCY STOP: Rug cascade detected: 5 stop-loss exits in 30min
```

After emergency stop: only `Daily P/L reset` at midnight. Zero activity since.

Exit pricing issue: **massive** — nearly every exit shows "NO_EXIT_PRICE: all sources failed" repeatedly before eventual fallback. This is the known pricing bug still active.

## Q4 Governance
**Governance is CONSERVATIVE because of 4% win rate and neutral CFGI.**

All decisions since bot_core stopped (every 2-4h):
- mode=CONSERVATIVE, all personalities enabled, size_multiplier=1.0, max_concurrent=5
- Never enters HIBERNATE or PAUSE
- Anthropic API working (200 OK responses)
- Has SQL bug: `operator does not exist: double precision > timestamp` (non-blocking, every cycle)

**Governance is NOT blocking trades.** It's conservative but permissive.

## Q5 Market Mode
| Metric | Value | Updated |
|--------|-------|---------|
| Market mode | HIBERNATE | Continuous since at least Apr 7 |
| Sentiment | 16.6 | Apr 9 13:15 UTC |
| SOL price | $82.21 | Apr 9 13:15 UTC (live) |
| CFGI | ~16-17 | Extreme fear |

HIBERNATE is bypassed by AGGRESSIVE_PAPER=true in signal_aggregator (mode → DEFENSIVE for scoring).
DEFENSIVE would normally add +10 to thresholds, but AGGRESSIVE_PAPER sets floor at 30/20.

Effective thresholds with current config:
- speed_demon: 40 (ML trained, AGGRESSIVE_PAPER floor overridden by env var 50 → actually 40 because of DEFENSIVE paper floor logic)
- analyst: auto-paused at CFGI < 20 (CFGI is 16.6 → analyst paused by design)
- whale_tracker: no signals reaching it (no whale wallet triggers)

## Feature Derivation Claim Verification
**PARTIALLY FALSE.** The code exists but data sources are empty at scoring time.

| Feature | Code Exists? | Derived Live? | Why Not |
|---------|-------------|---------------|---------|
| holder_gini | Yes (line 710, 1864) | PARTIAL | Needs token_details.holder_gini from Helius/holder data — often empty |
| sniper_0s_num | Yes (line 1865) | NO | Reads `live_stats.snipers_0s` from `token:stats:{mint}` — not populated for new tokens (subscription happens post-entry) |
| sniper_0s_hold_pct | Yes (line 1867) | PARTIAL | Uses `bundled_supply_pct` from raw PumpPortal data — may be 0 |
| sniper_5s_ratio | N/A (line 1869) | NO | Hardcoded -1, no live equivalent |
| early_top5_hold_ratio | Yes (line 1871) | PARTIAL | Approximated from top10_holder_pct * 0.7 — requires holder data |
| wash_ratio | Yes (line 1875) | NO | Uses `bot_transaction_ratio` — not in PumpPortal raw data |
| tx_per_sec | Yes (line 1877) | NO | Requires `live_buys + live_sells > 0` — always 0 for new tokens |
| sell_pressure | Yes (line 1880) | NO | Same dependency on live trade stats |
| post_grad_holder_gini | N/A (line 1882) | NO | Hardcoded -1 |
| cluster_num | N/A (line 1883) | NO | Hardcoded -1 |
| cluster_holder_ratio | N/A (line 1884) | NO | Hardcoded -1 |
| top10_pct_delta | N/A (line 1885) | NO | Hardcoded -1 |

**Root cause of -1 values:** `token:stats:{mint}` is only populated AFTER signal_listener subscribes to a token's trade stream, which only happens AFTER a position is entered. At scoring time, no trade stats exist for new tokens.

The overnight report claiming "7 of 13 derived from live data" was inaccurate — the code paths exist but the data doesn't flow at the right time. Only ~2-3 features have any chance of being non-default.

## Service Status
| Service | Status | Last Log | Notes |
|---------|--------|----------|-------|
| signal_listener | UP | 13:17 Apr 9 | Active, flooding signals |
| signal_aggregator | UP | 13:17 Apr 9 | ML scoring, HIBERNATE bypass active |
| bot_core | UP (STOPPED) | 14:55 Apr 8 | EMERGENCY STOP: rug cascade |
| ml_engine | UP | (per Jay) | Original engine, not used for scoring |
| market_health | UP | 13:15 Apr 9 | HIBERNATE, Sentiment 16.6, SOL $82.21 |
| governance | UP | 12:45 Apr 9 | CONSERVATIVE mode, all enabled |
| treasury | UP | (presumed) | Not checked — not relevant |
| web | UP | (presumed) | Not checked — dashboard is read-only |

## Commits Since Last Trade
Last successful pre-libgomp trade: ~April 7. Commits since:

| Commit | Description | Services Affected |
|--------|-------------|-------------------|
| e74117c | Phase0: 8-layer Nansen safeguards in nansen_client.py v3 | all (client lib) |
| 81ea9d6 | Phase1.1: Add libgomp1 for ML model pickle loading | ml_engine |
| 3681388 | Phase2: Expand FEATURE_COLUMNS to 54 features + MemeTrans | ml_engine, signal_aggregator |
| 751680e | Phase3: Fix Vybe auth + holder fallback | signal_aggregator |
| a5e3086 | Phase4: Wire Nansen enrichment + SM DEX poller | signal_aggregator, signal_listener |
| 5b5ab93 | Phase6.iter1: Dead feature cleanup + MemeTrans defaults | signal_aggregator |
| 4256b8a | Phase6.iter2: Nansen credit usage in dashboard | dashboard_api |
| 794fe1c | Phase6.iter3: Derive tx_per_sec, sell_pressure, wash_ratio | signal_aggregator |
| 276a090 | Phase6.iter4: Fix SM poller endpoint | signal_aggregator |
| e88c893 | Phase6.iter5-6: /api/nansen-usage endpoint | dashboard_api |
| 9acdddc | Phase6.iter7: ML meta to Redis on startup | ml_engine |
| f0423d5 | Phase6.iter9-10: Auto-publish ML meta after retrain | ml_engine |
| 59c2ced | Phase6.iter11: Fix bot_core Nansen budget key | bot_core |
| 2b57ee0 | Phase6.iter13: Feature coverage logging | ml_engine |
| 7f534c6 | Phase6.iter14-15: Sniper tracking + sniper_0s_num | signal_aggregator |
| 38c7836 | Phase6.iter16: Derive holder_gini from Helius | signal_aggregator |
| f70d634 | Phase6.iter17-18: sniper_0s_hold_pct, early_top5_hold_ratio | signal_aggregator |
| b17179c | Phase6.iter19: Nansen cache hit counter | signal_aggregator |
| 41d166d | Phase6.iter20-25: Overnight report | docs |
| 6d59dff | Defensive lightgbm imports | ml_engine |
| c784f0f | Libgomp fix report | docs |
| 47de1fa | **Fix: bypass HIBERNATE hard gate** | signal_aggregator |
| c2ea2b9 | No-trades fix report | docs |

**None of these commits caused the no-trades issue.** The root cause was the HIBERNATE gate (existed before all these commits) combined with CFGI dropping to extreme fear territory.

## Top 3 Hypotheses

### 1. EMERGENCY STOP is the active blocker (HIGH CONFIDENCE)
**Evidence:** bot_core log 14:55:38 Apr 8 — "CRITICAL: EMERGENCY STOP: Rug cascade detected: 5 stop-loss exits in 30min". Zero activity since. The HIBERNATE fix unblocked signals, trades entered, but all immediately lost money in extreme fear market, triggering the cascade detector.
**Fix:** Reset emergency stop via Redis keys + restart bot_core.
**Risk:** Will happen again unless position sizing or cascade thresholds are adjusted for paper mode.

### 2. Position sizing falls below minimum (MEDIUM CONFIDENCE)  
**Evidence:** "Position 0.1256 SOL below minimum 0.15 — rejecting" at 14:53:48 and 14:54:46. Multiplier stack: 0.7 (speed_demon personality) × 0.35 (rugcheck medium) × 0.84 (confidence) = 0.1256 SOL. Even without emergency stop, many signals would be rejected because the position is too small.
**Fix:** Either lower MIN_POSITION_SOL from 0.15 to 0.10, or adjust rugcheck medium multiplier from 0.35 to 0.50+, or both. This is a Tier 2 trading logic change.

### 3. Exit pricing still broken — all exits fail price fetch (MEDIUM CONFIDENCE)
**Evidence:** "NO_EXIT_PRICE: all sources failed (Redis/BC/Jupiter/Gecko)" floods bot_core logs. Positions get price=0 for most of their hold time, then eventually hit a timeout exit. The April 5 "exit pricing fix" either wasn't deployed to bot_core or isn't working.
**Impact:** Even if trades flow, the exit pipeline is blind — no take-profits, no proper stop-losses. All exits are timeout-based, losing small amounts on every trade. This compounds into the rug cascade trigger.
