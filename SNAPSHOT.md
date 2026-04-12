# ZMN Bot State Snapshot — 2026-04-12 13:40 UTC

## Service Health

| Service | Status | Notes |
|---------|--------|-------|
| signal_listener | UP | PumpPortal WS connected, early subscriptions working |
| signal_aggregator | UP | Redeployed 12:54 UTC with feature default fix (a8a390b) |
| bot_core | UP | Processing scored signals, exit monitoring active |
| ml_engine | UP | CatBoost + XGBoost ensemble, trained=True, scoring live |
| market_health | UP | CFGI=16, mode=HIBERNATE, SOL price tracking |
| governance | UP | Haiku-based, NANSEN_DRY_RUN=true |
| treasury | UP | Helius budget guard active (0 calls), balance tracking |
| web | UP | Dashboard at zmnbot.com |

## Trade Flow

| Metric | Value |
|--------|-------|
| Total paper trades | 3,563 |
| Total closed | 3,563 |
| Total wins | 213 (6.0% WR) |
| Total PnL | -27.51 SOL |
| Post-fix trades (30 min) | 5 |
| Post-fix wins | 0 (CFGI 16 extreme fear) |
| Post-fix PnL | -0.073 SOL |
| Open positions | 0 |

## Post-Fix Exit Reason Distribution (5 trades)

| Exit Reason | Count | Avg PnL |
|-------------|-------|---------|
| no_momentum_90s | 2 | -3.0% |
| TRAILING_STOP | 1 | -2.0% |
| stop_loss_35% | 1 | -39.6% |
| stale_no_price | 1 | -0.4% |

## Entry Filter State (post-fix)

| Metric | Before Fix | After Fix |
|--------|-----------|-----------|
| Pass rate | 0% | ~95%+ |
| Dominant reject | low_buy_sell_ratio_0.00 (97.7%) | ML reject (scores <40) |
| Filter C (retry) firing | Never | Yes (750ms retry on unknown) |
| BSR sentinel in features | 0 (ambiguous) | -1 (clear "unknown") |

## Signal Pipeline

```
PumpPortal WS → signal_listener → signals:raw → signal_aggregator
  → social filter (FILTER: PASS/REJECT) → HIBERNATE bypass (AGGRESSIVE_PAPER)
  → feature construction (BSR=-1 for unknown) → entry filter (passes unknown)
  → ML scoring (threshold 40) → SCORED → signals:scored → bot_core
  → paper_buy → exit monitoring → paper_sell
```

## Critical Redis State

| Key | Value |
|-----|-------|
| market:mode:current | HIBERNATE |
| CFGI | 16 (extreme fear) |
| bot:portfolio:balance | ~9.27 SOL |
| bot:emergency_stop | nil (not set) |
| bot:consecutive_losses | low |
| ml:engine:mode | original |
| nansen:disabled | nil (expired) |
| NANSEN_DRY_RUN | true (all services) |

## ML Model State

- Engine: CatBoost + XGBoost ensemble (original, 55 features)
- Training samples: ~128 clean (post-contamination filter)
- AUC: ~0.89
- Feature fill rate: 19/68 (28%)
- Current ML scores in CFGI 16: mostly 1-35 (few pass 40 threshold)

## API Status

| API | Status | Notes |
|-----|--------|-------|
| PumpPortal | ONLINE | Primary signal source |
| Jupiter | ONLINE | Price API v3, JUPITER_API_KEY set |
| GeckoTerminal | ONLINE | Trending pools, prices |
| RugCheck | ONLINE | Risk scoring active |
| Helius | EXHAUSTED | 10.09M/10M credits. Resets April 26 |
| Nansen | DRY_RUN | All services, 8 safeguard layers active |
| Vybe | BROKEN | 404 on all token endpoints |
| Anthropic | LOW | Governance using Haiku |

## Known Issues (Priority Order)

1. **CFGI 16 extreme fear** — memecoins don't pump, ML scores low, 0% WR expected
2. **Helius credits exhausted** — stale_no_price exits persist until April 26
3. **ML SCORE INVERSION at 70+** — 0% WR at highest scores (see POST_TIER2_DIAGNOSIS.md)
4. **Feature sparsity** — 42/55 FEATURE_COLUMNS always zero, model noise
5. **LightGBM not loading** — ensemble runs 2/3 models
6. **Nansen DRY_RUN** — no live smart money data flowing yet
7. **Vybe broken** — no holder/PnL data from Vybe

## Recent Commits

| Hash | Description |
|------|-------------|
| a8a390b | fix: feature defaults -1 not 0 for missing live_stats data |
| 56421ab | fix: entry filter v4 — use !=-1 not >0 for data existence check |
| 41c218b | docs: entry filter v4 report, smart money diagnostic |
| 4f4d4db | fix: redesign entry filter — only reject when data exists |
| 33244dd | fix: entry filter C too aggressive — retry refreshes BSR |
