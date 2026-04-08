# No-Trades Fix Report — 2026-04-09

## Outcome
**FIXED** — Paper trades are flowing again.

## Root Cause
`signal_aggregator.py:1669` had a hard gate that silently dropped ALL signals when
`market:mode:current == HIBERNATE`. The `AGGRESSIVE_PAPER_TRADING=true` env var only
lowered ML thresholds (via the scoring path at line ~2079) — it did NOT bypass the
HIBERNATE gate. With CFGI at 18.1 (extreme fear), market_health correctly reported
HIBERNATE, and every signal was discarded before reaching ML scoring.

The log was `logger.debug()` level, making it invisible in production logs.

## Diagnostic Findings

### Service Health (all 8 services)
| Service | Status | Notes |
|---------|--------|-------|
| signal_listener | UP | Flooding signals every 2-5s from PumpPortal + GeckoTerminal |
| signal_aggregator | UP (broken) | Only processing graduation events; main pipeline dead |
| bot_core | UP (idle) | Market mode = HIBERNATE, zero trades since Apr 7 |
| ml_engine | UP | Original engine, 4-model ensemble, 55 features |
| market_health | UP | HIBERNATE mode, Sentiment 18.1, SOL ~$84 |
| governance | UP | Latest decision: NORMAL mode, all personalities enabled |
| treasury | UP | (not checked — not relevant to signal flow) |
| web | UP | (not checked — dashboard is read-only) |

### Signal Flow Analysis
- signal_listener: ~10+ signals/minute arriving (PumpPortal + GeckoTerminal)
- signal_aggregator: signals:raw being consumed but ALL dropped at HIBERNATE gate
- Only graduation events processed (separate code path bypasses HIBERNATE check)
- Zero SCORED signals reaching bot_core
- Zero PAPER ENTERED since April 7

### Governance State
- Governance was publishing NORMAL/CONSERVATIVE — NOT HIBERNATE
- Governance was NOT the blocker (bot_core:544 checks governance, not market mode)
- Anthropic API still working for governance (200 OK responses)

### Market Mode
- market_health: HIBERNATE continuously since at least 07:39 UTC April 8
- Sentiment: 18.0-18.1 (extreme fear, CFGI ~18)
- SOL price: ~$84 (live, occasional null fetches but recovering)

### ML Scoring (inline AcceleratedMLEngine)
- Phase 3, AUC 0.8696 on 2,592 samples
- 16/68 features filled (24%)
- Scoring active after fix: scores ranging from 8.9 to 77.0
- Threshold for speed_demon: 40 (AGGRESSIVE_PAPER mode)

## Fix Applied

### Code Change (commit 47de1fa)
`services/signal_aggregator.py:1669`:
```python
# BEFORE:
if market_mode == "HIBERNATE":
    logger.debug("HIBERNATE mode — skipping %s", mint[:12])
    continue

# AFTER:
if market_mode == "HIBERNATE" and not AGGRESSIVE_PAPER:
    logger.debug("HIBERNATE mode — skipping %s", mint[:12])
    continue
elif market_mode == "HIBERNATE" and AGGRESSIVE_PAPER:
    logger.info("HIBERNATE mode but AGGRESSIVE_PAPER=true — processing %s for data collection", mint[:12])
    market_mode = "DEFENSIVE"  # downgrade to DEFENSIVE thresholds
```

### Deployment
- Deployed signal_aggregator only via `railway up -s signal_aggregator`
- Build time: 64.29 seconds
- Container started: ~14:27 UTC

## Verification
- Last paper trade before fix: April 5, 2026 (estimated — pre-libgomp crisis)
- First paper trade after fix: 2026-04-08 14:27:42 UTC (EmRPgzWNv9LQ, speed_demon)
- Trades in first 15 min after fix: 3+ entries, multiple exits
- Score distribution (last 20 ML scores): min=8.9, mean=~35, max=77.0
- 56 signals processed through HIBERNATE bypass
- 18 ML rejections (correct — low scores filtered)

## Structural Issues Found

### CRITICAL: Inline ML Engine Routing (Tier 2 — DO NOT FIX without Jay)
`signal_aggregator.py:1439` imports `AcceleratedMLEngine` inline and uses it for
ALL live scoring. The `ml_engine` Railway service (running "original" with 55
features, AUC 0.889) is NEVER consulted — the inline AcceleratedMLEngine runs
in signal_aggregator's process with its own training (AUC 0.8696, 25 features).

This means:
- ml_engine service is wasted compute (publishing to ml:score_request but nobody listens)
- ML_ENGINE=original on ml_engine service is irrelevant for live scoring
- ML_ENGINE=accelerated on signal_aggregator is what actually controls scoring
- Two different models with different feature sets and AUCs

**Recommendation:** Dedicated session to either:
(a) Remove inline ML and use pubsub to ml_engine service exclusively, OR
(b) Remove ml_engine service and keep inline scoring (simpler, saves Railway costs)

## Env Var Changes Made
None — no env var changes were needed. AGGRESSIVE_PAPER_TRADING=true was already set.

## Services Restarted
| Service | Time (UTC) | Reason |
|---------|-----------|--------|
| signal_aggregator | 2026-04-08 14:25 | Deploy HIBERNATE bypass fix |

## Recommendations for Jay
1. **Structural ML routing** — Schedule a dedicated session to resolve the inline vs service ML scoring. This is the biggest architectural issue in the bot.
2. **Exit pricing** — "price fetch failed" warnings still appearing on exits. The Redis-first pricing fix from April 5 may need verification on the new deployment.
3. **Feature coverage** — Only 16/68 ML features populated (24%). Many features are zero, reducing ML accuracy.
4. **Governance SQL bug** — `operator does not exist: double precision > timestamp` appears every governance cycle. Non-blocking but should be fixed.
5. **Market mode in paper trading** — Consider whether DEFENSIVE or a dedicated PAPER_TRAINING mode makes more sense as the HIBERNATE override. Currently we use DEFENSIVE thresholds.
