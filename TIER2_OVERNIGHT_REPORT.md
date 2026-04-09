# Tier 2 Overnight — All 4 Fixes — 2026-04-10

## Outcome Summary
| Fix | Outcome | Commit | Impact |
|-----|---------|--------|--------|
| 1 — ML retrain cleanup | SUCCESS | f7ebc56 | 403 contaminated rows excluded, retrained on 128 clean samples |
| 2 — Feature timing | SUCCESS | cb53b7a | sniper_0s_num/tx_per_sec/sell_pressure: 0% → 70% population |
| 3 — ML routing | SUCCESS | 629c740 | All scoring via pubsub to 55-feature original engine, 0 timeouts |
| 4 — Price continuity | SUCCESS | da964ab | TTL 600s → 1800s, 1 stale_no_price in 50 trades (was ~10%) |

## Fix 1 — ML Retrain Cleanup

### Problem
852 trades in `trades` table had bug-corrupted exit prices (paper_sell fell back to entry_price for BC tokens). In the 7-day training window, 403 of 521 samples (77%) were contaminated — the model was trained on data where winning patterns were labeled as losses.

### Changes
- `services/ml_engine.py`: Added WHERE NOT clause to exclude rows where `closed_at < contamination_cutoff AND exit_price BETWEEN entry_price * 0.97 AND 1.03`
- `services/ml_model_accelerator.py`: Same contamination filter added to both `trades` and `paper_trades` queries
- Cutoff configurable via `ML_TRAINING_CONTAMINATION_CUTOFF` env var (default: 1775767260.0 = 2026-04-09 20:41 UTC)
- Both full retrain and incremental update paths filtered

### Results
- Emergency retrain triggered via Redis pubsub
- 403 contaminated rows excluded from 7-day window
- Trained on 128 clean samples (4.7% positive)
- CatBoost + XGBoost trained (LightGBM unavailable — libgomp)
- SHAP top 5: cfgi_score, token_age_seconds, hour_of_day, sol_price_usd, liquidity_velocity
- Pre-cleanup AUC: 0.8696 (on contaminated data, unreliable)
- Post-cleanup AUC: not computed (128 samples with 6 positives too small for reliable CV)
- Model saved to PostgreSQL, no crashes

## Fix 2 — Feature Derivation Timing

### Problem
7 MemeTrans-derived features (sniper_0s_num, tx_per_sec, sell_pressure, holder_gini, sniper_0s_hold_pct, early_top5_hold_ratio, wash_ratio) returned -1 in production because `token:stats:{mint}` was empty at ML scoring time. PumpPortal trade subscriptions only happened after bot_core entered a position — by then, scoring was already done.

### Changes
- `services/signal_listener.py`: On createEvent, immediately subscribe to token trades (`subscribeTokenTrade`)
- Added `_early_subscriptions` dict with 5-min TTL and max 200 concurrent
- Added `_early_sub_cleanup` periodic task (every 60s) to unsubscribe orphans
- `_token_subscribe_listener` claims early subs when bot_core subscribes
- `services/signal_aggregator.py`: Added 500ms retry if `token:stats` empty on first read

### Results
- Feature population rates (post-fix vs pre-fix):
  - sniper_0s_num: **70%** (was 0%)
  - tx_per_sec: **70%** (was 0%)
  - sell_pressure: **70%** (was 0%)
  - holder_gini: 0% (depends on Vybe holder data, not trade stats)
  - sniper_0s_hold_pct: 0% (depends on bundled_supply_pct from external data)
  - early_top5_hold_ratio: 0% (depends on top10_holder_pct from external data)
  - wash_ratio: 0% (depends on bot_transaction_ratio from external data)
  - sniper_5s_ratio: 0% (no live equivalent exists)
- No subscription limit errors
- No memory leaks observed

## Fix 3 — Inline ML Routing

### Problem
`signal_aggregator.py:1440` imported `AcceleratedMLEngine` inline and used it for all live scoring (~25 features). The `ml_engine` service running `ML_ENGINE=original` with 55 features was parallel-scoring but its predictions never reached trade decisions. The libgomp fix, original engine deployment, and 55-feature expansion were architectural decoration.

### Changes
- Removed `_get_ml_engine_async()`, `_get_ml_engine()`, and all AcceleratedMLEngine imports
- `_request_ml_score()` now exclusively uses Redis pubsub to `ml_engine` service
- Added 3-second timeout with circuit breaker (5 timeouts in 60s → default score)
- Graduation sniper also switched from inline to pubsub scoring

### Results
- Pubsub latency: ~69ms (tested before deploy)
- ML scores vary (5.5 to 77.3) — not defaults
- `trained=True` confirmed in all scoring logs
- Zero "AcceleratedMLEngine" mentions in post-deploy logs
- Zero pubsub timeouts
- Trades flowing normally
- Feature count in features_json: 68 (signal_aggregator sends all, ml_engine picks 55)

## Fix 4 — Price Data Continuity

### Problem
`token:latest_price:{mint}` TTL was 600s (10 min). When PumpPortal subscription drops or a token goes quiet, the cache expires and bot_core has no exit price source, causing `stale_no_price` exits.

### Changes
- `services/signal_listener.py`: All `ex=600` changed to `ex=1800` (30 min) for:
  - `token:latest_price:{mint}`
  - `token:price:{mint}`
  - `token:reserves:{mint}`
- BC formula fallback already existed in `bot_core._get_token_prices_batch()` STEP 2

### Results
- 14/32 price keys already using new 1800s TTL (rest transitioning)
- stale_no_price exits: 1 in 50 trades (2%, down from ~10% historically)
- No crashes, no regressions

## Aggregate Metrics (post all 4 fixes, ~1 hour window)
- Trades in last hour: 50
- Wins: 8 (16.0% WR)
- Total PnL: -0.9374 SOL
- Average ML score: 45.0
- Exit reason distribution:
  - no_momentum_90s: 25 (50%)
  - TRAILING_STOP: 13 (26%)
  - stop_loss_35%: 4 (8%)
  - BREAKEVEN_STOP: 4 (8%)
  - staged_tp_+50%: 1 (2%)
  - staged_tp_+100%: 1 (2%)
  - stale_no_price: 1 (2%)
  - time_exit_loss: 1 (2%)
- Emergency stops: 0
- Cascade triggers: 0
- Open positions: 2

## What Jay Should Check Tomorrow Morning
- Dashboard: are trades still flowing? (yes as of report time)
- Recent paper_trades: do P/L numbers look real? (confirmed, e.g. +138.6% TRAILING_STOP)
- ml_engine logs: any new errors? (clean at report time)
- signal_listener: subscription count stable? (early sub cleanup active)
- ML scores: varying correctly via pubsub? (confirmed 5.5-77.3 range)

## Failures and Reverts
None — all 4 fixes succeeded.

## Remaining Tier 2 Work
1. **LightGBM on ml_engine**: libgomp still missing, ensemble runs CatBoost + XGBoost only. Need NIXPACKS_APT_PKGS=libgomp1 on ml_engine service.
2. **Feature population for remaining 5 features**: holder_gini, sniper_0s_hold_pct, early_top5_hold_ratio, wash_ratio depend on external data (Vybe/rugcheck), not PumpPortal trades.
3. **ML AUC tracking**: Emergency retrain doesn't publish AUC to Redis. The `_publish_model_meta` call is missing from `_emergency_retrain_listener`.
4. **Governance SQL type mismatch**: Low priority, cosmetic.
5. **Analyst personality still paused in extreme fear**: By design, but collects no training data during fear markets.
6. **Training sample count**: Only 128 clean samples in 7-day window. As contaminated data ages out and clean trades accumulate, this will improve naturally.
