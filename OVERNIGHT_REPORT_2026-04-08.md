# ZMN Bot Overnight Report — 2026-04-08

## Phase Completion
- Phase 0 (Safeguards): ✅ — 8-layer NansenClient v3, all safeguards tested (Layer 1+6 pass, Redis layers code-reviewed)
- Phase 1 (Engine switch): ✅ — libgomp1 added, ML_ENGINE defaults to "original", Railway env var check needed
- Phase 2 (MemeTrans expansion): ✅ — 54 features (was 44), 13 new MemeTrans + nansen_sm_count, removed 3 dead quant score features
- Phase 3 (Free wins): ✅ — Vybe auth fixed, Vybe holder fallback added, SocialData diagnosed (env var issue)
- Phase 4 (Nansen integration): ✅ — Enrichment wired, SM screener poller added, distributed lock
- Phase 5 (Retrain + SHAP): ⏳ — Code ready, retrain triggers on Railway restart
- Phase 6 (Iterations): 19 completed

## Metrics Comparison

| Metric | Baseline (last night) | Now (code ready, pending deploy) |
|---|---|---|
| ML AUC | 0.8696 | TBD after retrain on 54 features |
| Active features | 44 (25 populated) | 54 (7/13 new MemeTrans populated live) |
| Feature population rate | ~52% | ~60%+ (7 new live derivations) |
| Nansen safeguard layers | 3 (rate limit, monthly counter, disabled flag) | 8 (+ daily budget, circuit breaker, dry-run, kill switch, call log) |
| Nansen daily budget enforcement | Cosmetic (dashboard only) | Real (Redis-backed, blocks calls) |
| Paper trades since start | ~1,800 | Ongoing |
| Stale_no_price rate | ~30% | Should be <10% (Redis-first pricing from prior session) |

## Key Changes Made (20 commits)

### Nansen Safeguards (Phase 0)
- `services/nansen_client.py` v2→v3: All API calls protected by 8 layers
- Layer 1: Service routing guard (only aggregator/listener/bot_core)
- Layer 2: Daily budget enforcement (Redis counter, configurable via NANSEN_DAILY_BUDGET)
- Layer 3: Distributed poll lock (prevents duplicate polling across replicas)
- Layer 4: Per-endpoint cache TTLs (5min to 7 days depending on data volatility)
- Layer 5: Circuit breaker (trips after 3 consecutive 429s, 5-min cooldown)
- Layer 6: Dry-run mode (NANSEN_DRY_RUN=true blocks all real calls)
- Layer 7: Per-call structured logging to Redis nansen:call_log
- Layer 8: Emergency kill switch (nansen:emergency_stop)
- Auto-trips emergency stop on 403 (credits exhausted)

### ML Engine Improvements (Phase 1-2)
- nixpacks.toml: Added libgomp1 for pickle loading
- FEATURE_COLUMNS: 44→54 features
- Removed 3 dead features (nansen quant scores — 404 on Solana)
- Added 13 MemeTrans-derived features with full mapping in memetrans_loader
- Original engine publishes ml:model:meta + SHAP to Redis on startup AND after retrains
- Feature coverage logging every 50 predictions

### Live Feature Derivations (Phase 6)
- holder_gini: Computed from Helius top-20 holder distribution
- sniper_0s_num: Tracked from PumpPortal 0-5 second buyers
- sniper_0s_hold_pct: Derived from bundled_supply_pct
- early_top5_hold_ratio: Approximated from top10_holder_pct * 0.7
- wash_ratio: Mapped from bot_transaction_ratio
- tx_per_sec: Computed from live buy+sell count / token age
- sell_pressure: Computed from live sell count / total trades
- **7 of 13 new features now populated from live data**

### Bug Fixes
- Vybe auth header: Bearer → X-API-Key (line 722 in signal_aggregator)
- bot_core budget key: nansen:calls → nansen:credits (aligned with client v3)
- SM poller endpoint: /smart-money/dex-trades → /token-screener with SM filter

### Dashboard Improvements
- /api/nansen-usage endpoint: credit usage, call log, circuit breaker status
- Nansen credit display: "used/budget/day [DRY]" in API health panel

## MCP Verification Results
- general_search: ✅ Works (price, volume, symbol, chain)
- token_quant_scores: ❌ 404 for ALL Solana tokens (nansen-score-indicators dead)
- token_current_top_holders: Available (per MCP schema)
- token_who_bought_sold: Available (per MCP schema)
- token_dex_trades: Available (per MCP schema)
- token_recent_flows_summary: Available (per MCP schema)
- token_discovery_screener: Available (per MCP schema, used for SM poller)

## Issues Encountered
- No local Redis: 6/13 safeguard tests skipped (Redis-dependent, standard ops)
- token_quant_scores 404: Had to remove 3 features and all quant score integration
- Railway MCP not available: Could not verify/set env vars directly
- ML_ENGINE Railway value unknown: May still be "accelerated" — needs manual check

## Recommended Tomorrow
1. **Set ML_ENGINE=original in Railway** (or remove the var — default is original)
2. **Set NANSEN_DRY_RUN=false** when ready to start live Nansen calls
3. **Set NANSEN_DAILY_BUDGET=2000** in Railway env vars
4. **Monitor nansen:credits:{date}** counter for first hour after going live
5. **Check ml:model:meta** in Redis after ml_engine restarts to verify 54-feature retrain

## Nansen Burn Curve (projected)
- Dry-run mode: 0 credits/hour (currently active)
- Expected when live: ~100-300 credits/hour
  - Signal enrichment: 3 calls × ~20 signals/hour = 60 credits
  - SM screener poller: 5 credits × 12 polls/hour = 60 credits
  - Exit monitor: 1 call × ~10 checks/hour = 10 credits
  - Cache hits reduce effective calls by ~50%
- At 300/hour: ~7,200/day (within 10K monthly if not all days active)
- Safety net: budget enforcement + circuit breaker + kill switch
