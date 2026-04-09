# Tier 2 Follow-ups — Found During 2026-04-09 Fix Session

## Issue 1: Feature derivation timing bug
- Overnight report claimed "7 of 13 MemeTrans features derived from live data"
- Diagnostic confirmed: code exists in signal_aggregator but
  `token:stats:{mint}` is EMPTY at scoring time because PumpPortal
  trade subscriptions happen post-entry, not on signal arrival
- Result: features return -1 fill values in actual trade records
- Impact: ML model is training/scoring with mostly missing data for
  the 7 "live" features (tx_per_sec, sell_pressure, wash_ratio,
  sniper_0s_num, holder_gini, early_top5_hold_ratio, sniper_0s_hold_pct)
- Fix requires: moving subscription point from entry to signal
  arrival in signal_listener, OR computing features from a different
  source that's available at scoring time
- Estimated complexity: medium (touches subscription lifecycle)
- Priority: HIGH — this is wasted ML capacity

## Issue 2: Inline AcceleratedMLEngine vs ml_engine service
- signal_aggregator.py:1440 inline-imports AcceleratedMLEngine
- ml_engine service running ML_ENGINE=original is parallel-scoring
  but its scores never reach trade decisions
- Trades are actually scored by AcceleratedMLEngine inline (Phase 3,
  AUC 0.8696, 25 features), not by the original engine (AUC 0.889,
  55 features)
- Impact: the entire libgomp fix and original-engine effort doesn't
  affect live trading at all
- Fix requires: removing inline path, switching to pubsub-only
  scoring via ml:score_request
- Estimated complexity: small (delete inline path) but needs careful
  testing
- Priority: HIGH — this invalidates the recent ML work

## Issue 3: Governance SQL type mismatch
- Every governance cycle logs: `operator does not exist: double precision > timestamp with time zone`
- The metrics query is comparing a float to a timestamp column
- Non-blocking (governance still makes decisions via Anthropic API)
- Fix: cast the comparison properly in the SQL query
- Priority: LOW — cosmetic, governance works despite it

## Issue 4: Paper trader exit price fallback
- paper_trader.py falls back to entry price when Jupiter/Gecko fail
- This masks the real P/L — trades look like ~0% loss when they
  could be +30% or -50%
- The BC price seed fix helps but paper_trader should also check
  token:latest_price:{mint} before falling back to entry price
- Priority: MEDIUM — affects ML training data accuracy

## Issue 5: Analyst personality auto-paused in extreme fear
- CFGI 16.6 auto-pauses analyst (threshold: CFGI < 20)
- All signals routed only to speed_demon
- This is by design but means analyst gets zero training data
  during fear markets — which are exactly when it should learn
- Consider: in AGGRESSIVE_PAPER mode, should analyst collect
  data even in fear? (Tier 2 trading logic change)
- Priority: LOW — by design, but worth revisiting
