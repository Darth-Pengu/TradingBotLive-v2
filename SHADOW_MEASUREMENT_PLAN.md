# Shadow Trading Measurement Plan — Phase 1

## Purpose
Instrument paper trading to capture data needed for execution realism
comparison. Does NOT execute real trades. All measurements are paper-side.

## Measurement Points Implemented

### 1. ENTRY_FILL
- **Location:** bot_core.py, after paper_buy succeeds
- **Captures:** signal_age_s, ml_score, paper_fill_price, bc_price_usd,
  decision_to_fill_ms, size_sol, personality
- **Key insight:** decision_to_fill_ms measures how long from "bot decides
  to buy" to "paper fill recorded." Real execution would add 1-2 seconds
  of Solana latency on top.
- **Early finding:** 423-526ms decision-to-fill. Real execution adds ~1-2s.

### 2. EXIT_DECISION
- **Location:** bot_core.py _close_position, before paper_sell
- **Captures:** reason, sell_pct, decision_price, entry_price, peak_price,
  peak_gap_pct, remaining_pct, hold_s
- **Key insight:** peak_gap_pct shows how far price has dropped from peak
  by the time the bot fires the exit. This is the "reaction speed" metric.

### 3. STAGED_TP_HIT
- **Location:** bot_core.py, after STAGED_TP_FIRE log
- **Captures:** stage, nominal_trigger_x, actual_mult_x, overshoot_pct,
  sell_frac, remaining_before, remaining_after
- **Key insight:** overshoot_pct shows how far past the nominal trigger
  the actual fill happens. High overshoot means the 2-second exit checker
  cycle often catches the price well past the trigger.
- **Early finding:** 23-29% overshoot at +50% and +100% triggers — the
  bot fires staged TPs at 1.85x when trigger is 1.5x.

## Data Destination
- **Stdout:** `SHADOW_MEASURE <event> <json>` (INFO level, Railway logs)
- **Redis:** `shadow:measurements` list (48h TTL, 10k cap)

## NOT Implemented (Phase 2 Candidates)
- Real Jupiter quote comparison at fill time (API cost concern)
- Jito tip calibration (requires real tx submission)
- Network latency measurement (requires RPC timing)
- Slippage simulation under realistic bonding curve depth

## Analysis Queries (for Phase 2 session)

```sql
-- These run against the Redis shadow:measurements list.
-- Use Python to extract and analyze.
```

```python
# Extract shadow measurements from Redis
import redis, json
r = redis.from_url('redis://...', decode_responses=True)
entries = [json.loads(x) for x in r.lrange('shadow:measurements', 0, -1)]

# Decision-to-fill latency distribution
fills = [e for e in entries if e['event'] == 'ENTRY_FILL']
latencies = [e['decision_to_fill_ms'] for e in fills]
print(f'Avg decision-to-fill: {sum(latencies)/len(latencies):.0f}ms')

# Staged TP overshoot distribution
tps = [e for e in entries if e['event'] == 'STAGED_TP_HIT']
overshoots = [e['overshoot_pct'] for e in tps]
print(f'Avg staged TP overshoot: {sum(overshoots)/len(overshoots):.1f}%')

# Peak gap at exit (how much peak is lost before exit fires)
exits = [e for e in entries if e['event'] == 'EXIT_DECISION' and e['sell_pct'] == 1.0]
gaps = [e['peak_gap_pct'] for e in exits if e['peak_gap_pct'] > 0]
print(f'Avg peak gap at final exit: {sum(gaps)/len(gaps):.1f}%')
```
