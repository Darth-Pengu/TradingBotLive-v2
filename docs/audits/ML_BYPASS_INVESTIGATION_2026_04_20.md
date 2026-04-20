# ML=31.5 Bypass Investigation — Session 5 v4 mint `yh3n441…`

**Date:** 2026-04-20
**Triggering question:** Session 5 v4 opened a live position on mint `yh3n441JD53HZUCh…` ("Bring back the asteroid") with displayed `ml_score=31.5`. Railway env var is `ML_THRESHOLD_SPEED_DEMON=40` on the signal_aggregator service. Either the display was wrong, a real bypass path existed, or the threshold wasn't being read correctly.

**Outcome: (C) Actual bug — threshold not read correctly.**

The `AGGRESSIVE_PAPER_TRADING=true` env var (signal_aggregator) unconditionally overwrites `ML_THRESHOLDS` at module load to `{"speed_demon": 30, "analyst": 30, "whale_tracker": 20}`, regardless of the explicit `ML_THRESHOLD_SPEED_DEMON=40` setting. The env var's name and surrounding comments say "paper," but its effect is global and applies during live trading too.

**Severity:** pre-live relevance — yes. Corrective action deferred to a future session (this session's scope is diagnosis only, per prompt).

---

## 1. DB row — confirms ml_score was the authoritative value

```sql
SELECT id, mint, personality, entry_time, entry_price, amount_sol,
       ml_score, ml_score_at_entry, signal_source, signal_type,
       platform, market_mode_at_entry, fear_greed_at_entry,
       trade_mode, exit_reason, realised_pnl_sol, corrected_pnl_sol
FROM paper_trades
WHERE mint LIKE 'yh3n441%' AND trade_mode='live'
ORDER BY entry_time DESC LIMIT 1;
```

Result:

| column | value |
|---|---|
| id | 6580 |
| mint | yh3n441JD53HZUChicA5giMRRv4rbGuVFP6nMH5Gyro |
| personality | speed_demon |
| entry_time | 1776718553.66 (2026-04-20 20:55:53 UTC) |
| entry_price | 2.409836938e-06 |
| amount_sol | 0.3652803 |
| **ml_score** | **31.5** |
| ml_score_at_entry | NULL |
| signal_source | pumpportal |
| **signal_type** | **standard** |
| platform | pump.fun |
| **market_mode_at_entry** | **NORMAL** |
| fear_greed_at_entry | 0.0 |
| trade_mode | live |
| exit_reason | no_momentum_90s |
| realised_pnl_sol | 0.001876 |
| corrected_pnl_sol | NULL |

**Finding:** Display (31.5) matches DB column (31.5). Not a display bug. The bot genuinely evaluated `ml_score=31.5` against the threshold and passed. `signal_type=standard`, `market_mode=NORMAL` — neither of the two commonly-known bypass paths applies (`trending/migration/graduation` sig type → threshold 10; `FRENZY` mode → threshold minus 5).

---

## 2. Threshold gate trace — `services/signal_aggregator.py`

### 2.1 Where the threshold is compared

L2202-2205:

```python
if ml_score < threshold:
    logger.info("ML reject %s for %s: %.1f < %d (trained=%s)",
                mint[:12], personality, ml_score, threshold, ml_trained)
    continue
```

### 2.2 Where `threshold` is sourced

L2186-2205:

```python
# ML threshold check — use bootstrap thresholds during cold start
if ml_trained:
    threshold = ML_THRESHOLDS.get(personality, 70)
else:
    threshold = ML_BOOTSTRAP_THRESHOLDS.get(personality, 45)

# Trending/migration signals have external validation — lower ML bar
if sig_type_local in ("trending", "migration", "graduation"):
    threshold = min(threshold, 10)

if market_mode == "FRENZY":
    threshold -= 5
elif market_mode == "DEFENSIVE" and ml_trained:
    threshold += 10  # Only raise in DEFENSIVE when model is trained
```

For `yh3n441`: `sig_type_local="standard"` (not in bypass list). `market_mode="NORMAL"` (no FRENZY or DEFENSIVE adjustment). So `threshold = ML_THRESHOLDS["speed_demon"]` (if trained) OR `ML_BOOTSTRAP_THRESHOLDS["speed_demon"]` (if not).

### 2.3 Where `ML_THRESHOLDS` is initialized

L132-140:

```python
ML_THRESHOLDS = {
    "speed_demon": int(os.getenv("ML_THRESHOLD_SPEED_DEMON", "65")),
    "analyst": int(os.getenv("ML_THRESHOLD_ANALYST", "70")),
    "whale_tracker": int(os.getenv("ML_THRESHOLD_WHALE_TRACKER", "70")),
}
ML_BOOTSTRAP_THRESHOLDS = {
    "speed_demon": int(os.getenv("ML_BOOTSTRAP_SPEED_DEMON", "40")),
    "analyst": int(os.getenv("ML_BOOTSTRAP_ANALYST", "45")),
    "whale_tracker": int(os.getenv("ML_BOOTSTRAP_WHALE_TRACKER", "45")),
}
```

Railway env on signal_aggregator at v4 time: `ML_THRESHOLD_SPEED_DEMON=40`. So at this point `ML_THRESHOLDS["speed_demon"]=40` and `ML_BOOTSTRAP_THRESHOLDS["speed_demon"]=40`.

### 2.4 **Where the override fires — L144-151**

```python
AGGRESSIVE_PAPER = os.getenv("AGGRESSIVE_PAPER_TRADING", "false").lower() == "true"
HAIKU_ENABLED = os.getenv("HAIKU_ENABLED", "false").lower() == "true"
ANALYST_DISABLED = os.getenv("ANALYST_DISABLED", "false").lower() == "true"
if AGGRESSIVE_PAPER:
    ML_THRESHOLDS = {"speed_demon": 30, "analyst": 30, "whale_tracker": 20}
    ML_BOOTSTRAP_THRESHOLDS = {"speed_demon": 30, "analyst": 30, "whale_tracker": 20}
    logging.getLogger("signal_aggregator").warning(
        "PAPER TRADING: ML threshold floor=30 SD/AN, 20 WT (data shows 25-30 loses money)"
    )
```

Railway env on signal_aggregator (verified via `railway variables -s signal_aggregator`): **`AGGRESSIVE_PAPER_TRADING=true`**.

So the effective `ML_THRESHOLDS["speed_demon"]` at runtime was **30**, NOT 40.

31.5 > 30 → signal passed → live buy executed.

---

## 3. Corroborating evidence from paper data

If the override fires only in paper mode, we'd expect zero speed_demon trades with `ml_score < 40` in the 7-day rolling window (since everything runs through the same gate before reaching bot_core). Query:

```sql
SELECT
  CASE
    WHEN ml_score < 30 THEN '1_below_30'
    WHEN ml_score < 40 THEN '2_30_to_40'
    WHEN ml_score < 50 THEN '3_40_to_50'
    ELSE '4_50_plus' END AS band,
  COUNT(*) as n,
  ROUND(AVG(COALESCE(corrected_pnl_sol, realised_pnl_sol))::numeric, 4) as avg_pnl
FROM paper_trades
WHERE personality='speed_demon'
  AND entry_time > EXTRACT(EPOCH FROM NOW() - INTERVAL '7 days')
  AND exit_time IS NOT NULL
GROUP BY 1 ORDER BY 1;
```

Result:

| band | n | avg_pnl (SOL) |
|---|---:|---:|
| below_30 | 0 | — |
| **30_to_40** | **113** | **+0.4280** |
| 40_to_50 | 804 | +0.1452 |
| 50_plus | 2014 | +0.1928 |

**Finding:** 113 speed_demon trades in the last 7 days have `ml_score < 40` despite `ML_THRESHOLD_SPEED_DEMON=40`. Zero trades below 30 confirms the 30-floor from the AGGRESSIVE_PAPER override IS the binding threshold. The 30-40 band is not a one-off; it's a daily occurrence.

(Separately interesting — the 30-40 band has the best avg_pnl of any band. The AGGRESSIVE_PAPER override has been accidentally helping paper performance. That's not a justification for leaving the bug — it's a signal that the existing `ML_THRESHOLD_SPEED_DEMON=40` policy may itself be suboptimal, and tuning should happen on an evidence basis not by side-effect of an unrelated env var.)

---

## 4. Classification and decision

**Is the override intentional-and-documented?** The variable name (`AGGRESSIVE_PAPER_TRADING`), its surrounding log line ("PAPER TRADING: ML threshold floor=30"), and the preceding `if TEST_MODE` block show that the intent was "lower thresholds while collecting paper data". But:

- The override is applied at module load time based on the env var alone.
- There is no gate on `TEST_MODE`.
- Once `signal_aggregator` is deployed with `AGGRESSIVE_PAPER_TRADING=true`, the thresholds are clamped to 30/30/20 for any mode — including live trading. `bot_core` trusts `signal_aggregator`'s gating and does not re-check the ML threshold itself.

**Classification:** outcome (C) — actual bug — with a (B)-like shape. A real, documented-looking env var exists, but its scope is broader than its name implies.

**Impact at v4 incident:** one live trade entered on `ml_score=31.5`. That trade exited +0.51% on price but was a 25.8%-of-position on-chain loss due to fees + slippage (see `ZMN_LIVE_ROLLBACK.md` fee-delta analysis). The trade probably shouldn't have fired at all under the intended 40-floor policy, and even if it had, a proper fee model would have caught the risk — but that's FEE-MODEL-001's problem, not this issue's.

**Pre-live relevance:** HIGH. Any future Session 5 live-enable that keeps `AGGRESSIVE_PAPER_TRADING=true` on signal_aggregator will silently run a 30-floor in live, not the 40-floor the Railway env var claims. Per prompt, **no fix this session** — flagged for follow-up. Below-threshold live trades are not a safety hazard by themselves (wallet is still bounded by `MAX_POSITION_SOL_FRACTION`, daily loss limit, and sell-storm circuit breaker), but the gate-policy drift undermines the trust model: if you tune the env var, you expect the behavior to follow.

---

## 5. Follow-up item for roadmap (ML-012)

Proposed roadmap addition (Tier 1, PRE-LIVE BLOCKER for any future supervised live window):

> **ML-012** — `AGGRESSIVE_PAPER_TRADING` gates ML threshold floor independent of `TEST_MODE`. Result: signal_aggregator ignores `ML_THRESHOLD_SPEED_DEMON` when `AGGRESSIVE_PAPER_TRADING=true`. Verified: 113 speed_demon trades in last 7d with `ml_score<40` despite floor policy = 40. During Session 5 v4 live window, mint `yh3n441…` entered at `ml_score=31.5` because effective live threshold was 30, not the 40 env var value.
>
> Fix shape: either (a) AND the `AGGRESSIVE_PAPER` branch with `TEST_MODE=True` at module load so the override only applies in paper mode, or (b) move the override inside the signal-processing loop and check `trade_mode` per signal, or (c) remove the `AGGRESSIVE_PAPER_TRADING` env var entirely and tune via `ML_THRESHOLD_SPEED_DEMON` directly since current policy is "thresholds are a function of data, not paper-vs-live". Recommend (a) for minimum blast radius; (c) for cleanest policy.
>
> Tier: 1 (single-file, ≤30m).
> Depends on: none.
> Source: this audit.

---

## 6. Closing notes

- Scope of this investigation is diagnosis. Any fix is a separate session.
- Dashboard column semantics (`ml_score` vs anything that might be displayed differently) is not at fault — the DB value matches the displayed value.
- The 30-floor override has been hiding the fact that `ML_THRESHOLD_SPEED_DEMON=40` is purely cosmetic on paper. TUNE-003 (roadmap) already flags a similar `ML_THRESHOLD_SPEED_DEMON=30` value on bot_core as cosmetic because the gate runs at signal_aggregator. ML-012 extends this observation: the signal_aggregator gate is ALSO partially cosmetic under the current env config.
- `corrected_pnl_sol=NULL` on row id=6580 means the post-fix correction pipeline hasn't run for this live row yet (correction applies to historical paper trades). Separate concern, low priority.
