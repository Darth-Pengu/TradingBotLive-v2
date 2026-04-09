# Exit Strategy Fix — 2026-04-09 evening

## Outcome
**PARTIAL SUCCESS** — Staged TPs and tiered trails are firing correctly, but paper_trader's independent price fetch records wrong exit prices for bonding curve tokens, making P/L look negative even when staged TPs fired at profitable levels.

## Before (baseline from cascade fix verification)
- 30% of trades peaked >+120% and exited below entry (9/30)
- Average peak-to-exit gap: 94.7pp
- Largest giveback: 205pp (peak +303%, exit -1.3%)
- Staged TPs at 2x/3x/5x never fired (unreachable for most tokens)
- Flat 4% trail (in HIBERNATE) caused late exits

## Changes Deployed
- Commit: bf57117
- Staged TPs: +50%/+100%/+200%/+400% (25% each) — configurable via STAGED_TAKE_PROFITS_JSON
- Tiered trail: breakeven at +30%, 25% at +50%, 20% at +100%, 15% at +200%, 12% at +500%
- Configurable via TIERED_TRAIL_SCHEDULE_JSON env var
- MIN_POSITION_SOL: 0.08 → 0.05 (positions were 0.0614 < 0.08)
- Files changed: services/bot_core.py

## After (verification window: 7 trades, 6 closed)

### Trade count
- Total closed: 6
- Peaked above +50%: 3
- Peaked above +100%: 3
- Peaked above +200%: 0

### Staged TP firing
- STAGED_TP +50% fired: 3 of 3 eligible (100%) ✅
- STAGED_TP +100% fired: 3 of 3 eligible (100%) ✅
- STAGED_TP +200% fired: 0 of 0 eligible (n/a)
- STAGED_TP +400% fired: 0 of 0 eligible (n/a)

### Peak-to-exit gap
**METRIC UNRELIABLE** — paper_trader fetches its own price via Jupiter/GeckoTerminal for exit recording, which fails on bonding curve tokens and falls back to ~entry price. Bot_core correctly sees +163% via Redis but paper_trader records ~-3%. The recorded gap is inflated by this bug.

- Recorded mean: 114.5pp (misleading — paper_trader price bug)
- Actual behavior observed in bot_core logs: staged TPs fire at correct levels

### Catastrophic givebacks (recorded)
- Count (peak >+120%, exit <0%): 2/6

**Important caveat:** These givebacks are from the REMAINING portion after staged TPs already sold 50%. The actual loss on each is ~50% of what it appears because half the position was already banked profitably. The paper_trader records the wrong exit price for the remaining portion.

### Exit reason distribution
| Reason | Count | Notes |
|--------|-------|-------|
| TRAILING_STOP | 2 | Remaining portion after staged TPs sold 50% |
| staged_tp_+100% | 1 | Position fully closed by staged TP |
| no_momentum_90s | 2 | No gain within 90s — correct behavior |
| stale_no_price | 1 | Price data disappeared (known issue) |

### Emergency / cascade
- New emergency stops: 0 ✅
- New cascade triggers: 0 ✅

## Known Limitations

### Paper trader exit price bug (CRITICAL for metrics, not for trading)
paper_trader.py does its own price fetch (Jupiter/GeckoTerminal) independently from bot_core's Redis-cached prices. For bonding curve tokens:
- bot_core EXIT_EVAL correctly shows +163% via Redis token:latest_price
- paper_trader.paper_sell tries Jupiter → fails, GeckoTerminal → fails → falls back to entry price
- Records exit_price near entry → P/L looks like -3% instead of +100%

This doesn't affect the TRADING DECISION (staged TPs fire correctly at the right time). It only affects the RECORDED P/L in the database. This means:
- ML training data has wrong exit prices → model learns incorrect patterns
- Dashboard shows wrong P/L
- Verification metrics are unreliable

**Fix (Tier 2):** paper_trader.paper_sell should use the price that bot_core already has (passed as parameter), not do its own independent fetch.

### Price data gaps on dead tokens
Tokens with no active trading still lose price data when token:latest_price TTL (600s) expires. The remaining portion after staged TPs can go blind and exit at stale/wrong prices.

### No +200% or +400% verification
Market conditions (CFGI 16.6, extreme fear) didn't produce any tokens that peaked above +200% in the verification window. The +200/+400 staged TPs and the 15%/12% trail tiers are untested.

## Tuning Iterations Applied
1. MIN_POSITION_SOL 0.08 → 0.05 (positions were 0.0614, below 0.08 minimum)

## Recommended Next Sessions
1. **Paper trader price fix** — Pass bot_core's current_price to paper_sell instead of independent fetch. This is the highest-impact fix for P/L accuracy and ML training data.
2. **Feature derivation timing** — Move PumpPortal subscription from entry to signal arrival (TIER2_FOLLOWUPS Issue 1)
3. **Inline ML engine routing** — Resolve AcceleratedMLEngine vs ml_engine service conflict (TIER2_FOLLOWUPS Issue 2)
4. **Price data continuity** — Cache last known price longer (e.g., 1800s TTL) or use bonding curve formula as persistent fallback
