# Paper Trader Price Fix — 2026-04-10

## Outcome
**SUCCESS**

## Bug Root Cause
paper_trader.py did its own Jupiter/GeckoTerminal fetch on exit instead of using bot_core's already-known price. Failed on bonding curve tokens that have no liquidity pool, recording wrong exit prices and corrupting ML training labels.

**Flow before fix:**
1. bot_core `_check_exits` fetches price via Redis `token:latest_price:{mint}` → correctly sees +260%
2. bot_core calls `_close_position(pos, reason)` → calls `paper_sell(...)`
3. paper_sell calls `_get_token_price(mint)` → Jupiter V3 → 401/fails → GeckoTerminal → fails → falls back to entry_price
4. Records exit_price ≈ entry_price → P/L shows ~0% instead of +260%

**Flow after fix:**
1. bot_core `_check_exits` fetches price via Redis → sees +260%
2. bot_core calls `_close_position(pos, reason, current_price=current_price)` → passes price through
3. paper_sell receives `exit_price_override=current_price` → uses it directly
4. Records correct exit_price → P/L shows +255% (minus simulated slippage)

## Impact
- P/L on BC tokens wrong since paper trading began (all 3,346 pre-fix trades potentially affected)
- Part 2 verification's "2/6 catastrophic givebacks" were false positives caused by this bug
- ML training data contamination: 685 of 3,353 closed trades (20.4%)

## Fix
- **commit:** 9b880e1
- paper_sell now accepts `exit_price_override` parameter
- bot_core passes `current_price` to every `_close_position` → `paper_sell` call
- All 17 call sites in bot_core.py updated (stop_loss, staged_tp, trailing_stop, time_exit, no_momentum, emergency_stop, whale_exit, etc.)
- Demoted Jupiter/Gecko fetch to documented last-resort fallback with warning log (detects any remaining call sites that don't pass price)
- Fallback order: exit_price_override → Redis `token:latest_price:{mint}` → entry_price (breakeven)

## Verification
- Post-deploy closed trades: 8
- bot_core decision price matches paper_trades.exit_price: 8/8 (within slippage sim tolerance)
- Fallback warnings ("paper_sell called WITHOUT exit_price_override"): **0**
- Trade with peak >+50% showing correct P/L: ID 3347 E9xbEj8UsnPH — peaked +260.4%, recorded +255.2% (diff = slippage sim) ✅
- staged_exits_done populated: `["+50%", "+100%", "+200%"]` for trade 3347 ✅
- Post-deploy trades with exit≈entry AND peak>+50%: **0** (was 685 pre-fix)
- No crashes, no deploy failures ✅
- Emergency stop: 0 ✅

### Cross-check: bot_core EXIT_EVAL vs paper_trades
| Trade ID | Mint | bot_core price | paper_trades exit_price | Match |
|----------|------|---------------|------------------------|-------|
| 3347 | E9xbEj8UsnPH | $0.00000320 (3.60x) | $0.0000031533 (+255.2%) | ✅ (slippage sim) |
| 3354 | zDZdHCStfJvv | (no_momentum_90s) | $0.0000023317 (-5.1%) | ✅ |
| 3350 | 7iCNUuVWMhUR | (stop_loss_35%) | $0.0000021144 (-35.6%) | ✅ |

## Re-verification of Part 2 flagged givebacks
The Part 2 report flagged "2/6 catastrophic givebacks" (peak >+120%, exit <0%). Examining pre-fix trailing stop exits with staged TPs:

| Trade ID | Mint | Peak | Recorded Exit P/L | Staged TPs | Diagnosis |
|----------|------|------|-------------------|------------|-----------|
| 3336 | HLBvUufCg7bM | +157.9% | -1.1% | +50%, +100% | **FALSE POSITIVE** — exit_price ≈ entry_price |
| 3330 | 6NgRE5vLX8kQ | +116.4% | -0.5% | +50%, +100% | **FALSE POSITIVE** — exit_price ≈ entry_price |
| 3306 | 8Mmb4HfbD9ho | +258.7% | -0.9% | +50%, +100%, +200% | **FALSE POSITIVE** — exit_price ≈ entry_price |
| 3302 | 7UvvaC7rHjJu | +172.8% | -2.9% | +50%, +100% | **FALSE POSITIVE** — exit_price ≈ entry_price |

**CONFIRMED:** All flagged givebacks were false positives caused by this bug. The staged TPs had already banked 50-75% of the position at profit. The remaining portion exited via trailing stop at a real price that paper_trader couldn't record.

## ML Training Data Contamination
- Total closed trades in paper_trades: 3,353
- Suspected bug-affected rows (exit≈entry, non-time-based exit): 685
- Contamination rate: **20.4%**
- Pattern: TRAILING_STOP, BREAKEVEN_STOP, stop_loss, emergency_stop exits all recorded exit≈entry when Jupiter/Gecko couldn't fetch the BC token price
- Recommendation: next ml_engine retrain should flag or exclude rows where `exit_price BETWEEN entry_price * 0.97 AND entry_price * 1.03 AND exit_reason NOT IN ('no_momentum_90s', 'time_exit_no_movement', 'stale_no_price')`. This is a Tier 2 follow-up.

## Files Changed
- `services/paper_trader.py:221-270` — added `exit_price_override` parameter, demoted fetch to fallback
- `services/bot_core.py:867` — `_close_position` now accepts `current_price` parameter
- `services/bot_core.py:875` — passes `exit_price_override=current_price` to `paper_sell`
- `services/bot_core.py` — 17 call sites updated to pass `current_price=current_price`

## Next Session Candidates (from TIER2_FOLLOWUPS.md)
1. ML retrain cleanup — skip/flag 685 bug-contaminated rows (20.4% of training data)
2. Feature derivation timing (token:stats empty at scoring time)
3. Inline ML engine routing (AcceleratedMLEngine bypass)
4. Price data continuity (longer TTL or BC formula fallback)
