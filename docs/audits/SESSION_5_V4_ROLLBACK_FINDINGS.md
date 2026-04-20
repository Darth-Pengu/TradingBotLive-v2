# Session 5 v4 — Rollback Findings + T5 Trigger Redesign Rationale

**Date:** 2026-04-20
**Incident doc:** `session_outputs/ZMN_LIVE_ROLLBACK.md`
**Related commits:** `e078b4c` (parallel FIX-2 session — MAX_POSITION_SOL_FRACTION code landed there; noted in Implementation section below).
**Status:** Findings documented. Code change: `MAX_POSITION_SOL_FRACTION` env var landed in `services/bot_core.py` via commit `e078b4c`.
Trigger-logic changes (T5a/T5b) belong to the next Session 5 prompt, not `services/`.

---

## Executive summary

Session 5 v4's live window rolled back at T+12:00 when trigger T5 (`(T0_wallet - now_wallet) / T0_wallet > 20%`) read 22.57% drawdown. The session logic executed correctly per prompt, but **the trigger fired on a benign state**: a single 0.365-SOL buy against a 1.658-SOL wallet was momentarily "below baseline" because the SOL was in the position, not lost. Fifty-three seconds later the position exited and the wallet recovered to 1.564 SOL — net loss 5.68%, not 22.57%.

This document captures the rationale for redesigning T5 and introduces `MAX_POSITION_SOL_FRACTION` to cap position size proportional to wallet, so the trigger stays meaningful at bounded wallet sizes.

---

## Why T5 (single balance-loss threshold) is inadequate

The old trigger:

```
(T0_wallet - now_wallet) / T0_wallet * 100 > 20%
```

treats SOL-in-a-position as SOL-lost. For wallet sizes where `MAX_POSITION_SOL / wallet ≥ trigger_threshold`, any single buy can false-positive the trigger.

**v4 arithmetic:**
- `MAX_POSITION_SOL = 1.50` (Railway default)
- Actual position opened: 0.365 SOL (multipliers came in under the cap)
- T0 wallet: 1.658 SOL
- Position / wallet: 22.02% — exceeds the 20% T5 trigger by itself

Even with no loss, the position alone can trip T5. Per the v4 data:
- Drawdown *at trigger*: 22.57% ← TRIGGER FIRED
- Drawdown *54s later after sell*: 5.68% ← REAL LOSS
- Ratio trigger/real: **~4× over-read** of actual loss

---

## Redesign: T5a + T5b (belongs in next Session 5 prompt)

**T5a — Position-adjusted drawdown (replaces old T5):**

```
effective_wallet = onchain_sol + SUM(open_position_cost_sol)
drawdown_pct = (T0_effective_wallet - effective_wallet) / T0_effective_wallet * 100
trigger: drawdown_pct > 15%
```

- Measures SOL actually gone from the *system* (on-chain + in-flight).
- 15% threshold vs old 20%, because it no longer has to buffer position-open noise.
- Meaningful at all wallet sizes — doesn't false-positive on normal position entries.

**T5b — Single-trade catastrophic loss (new):**

```
trigger: any closed live trade in last 5 monitoring cycles has
         realised_pnl_sol < -0.3 SOL
```

- Catches "one trade loses 0.3+ SOL on its own" regardless of total wallet state.
- Complementary to T5a — covers the "large bad trade lands before aggregate drawdown accrues" case.
- Bounded by `MAX_POSITION_SOL`: if max position is 0.5 SOL, a 60% loss on one trade fires it.

**Where these live:** Session 5 v5 prompt (monitoring loop), not in `services/`. Monitoring logic is session-prompt code that CC implements at live-window runtime. No services change needed for T5a/T5b themselves.

---

## Proportional sizing: `MAX_POSITION_SOL_FRACTION` (code change, this commit)

Independent of the trigger redesign, position sizes should scale with wallet so the bot doesn't routinely open positions that consume >10% of wallet.

**Env var (new):**
```
MAX_POSITION_SOL_FRACTION = 0.10  # default: position ≤ 10% of wallet
```

**Effective cap:**
```python
effective_max = min(MAX_POSITION_SOL, wallet_sol * MAX_POSITION_SOL_FRACTION)
```

**Numerics:**

| Wallet | `MAX_POSITION_SOL_FRACTION=0.10` | MAX_POSITION_SOL abs | Binding cap |
|---|---|---|---|
| 1.66 SOL (v4 state) | 0.166 SOL | 1.50 SOL | **fraction (0.166)** |
| 5.00 SOL | 0.500 SOL | 1.50 SOL | **fraction (0.500)** |
| 10.00 SOL | 1.000 SOL | 1.50 SOL | **fraction (1.000)** |
| 20.00 SOL | 2.000 SOL | 1.50 SOL | **abs (1.50)** |

Below 15 SOL wallet the fraction binds. Above 15 SOL the absolute cap binds. `0.10` picked to keep typical positions at ~10% of wallet; override per session if a larger position is desired.

**v4 comparison:** v4's actual 0.365 SOL would have been capped at **0.166 SOL** under `fraction=0.10`. T5 arithmetic: 0.166 / 1.658 = 10.0% — well under the 20% old-T5 threshold. Even the naïve pre-redesign T5 would not have fired on the position-open event.

---

## Implementation (landed in commit `e078b4c`)

Implementation landed in parallel-session commit `e078b4c` (FIX-2, FEE-MODEL-001). Identical changes were independently produced by this FIX-1 session and by FIX-2; FIX-2 committed first, so git saw FIX-1's edits as already present in HEAD. No conflict, no re-work needed — both sessions converged on the same implementation.

In `services/bot_core.py` (per `e078b4c`):
1. Added `MAX_POSITION_SOL_FRACTION = float(os.getenv("MAX_POSITION_SOL_FRACTION", "0.10"))` to module-level env var block.
2. Updated position-sizing path (L676-684 and L708-709 post-multiplier re-enforcement) to use `min(MAX_POSITION_SOL, wallet_sol * MAX_POSITION_SOL_FRACTION)` as the effective max.
3. Added startup log (in `main()`) emitting the three caps (`MIN_POSITION_SOL`, `MAX_POSITION_SOL`, `MAX_POSITION_SOL_FRACTION`) so Phase 6 can verify.

**Default = 0.10 is safe under current deployment:** at 1.66 SOL wallet, paper mode doesn't change because paper portfolio is `~195 SOL` (fraction binds at `19.5 SOL`, far above typical Speed Demon sizing). Paper cadence should be indistinguishable post-deploy. The fraction only binds when the live wallet is small.

Later tuning: if live wallet grows, `MAX_POSITION_SOL_FRACTION` can be raised (e.g., `0.15` for 15% of wallet). If a smaller cap is desired for a given live session, override per-session without touching the absolute `MAX_POSITION_SOL`.

---

## Related findings

See also:

- **CLEAN-003** (this session): reconcile-residual pre-flip cleanup. Addresses the 5 phantom mints that caused 25 wasted Helius RPC calls in the v4 window.
- **FEE-MODEL-001** (parallel FIX-2 session): paper fee model under-counts by ~96× for pre-grad pump.fun trades at 0.365-SOL sizing. The v4 single-trade "win" was actually a 25.8% on-chain loss.
- **ML bypass investigation** (this session): the v4 traded mint `yh3n441…` had `ml_score=31.5` with gate config `ML_THRESHOLD_SPEED_DEMON=40`. See `ML_BYPASS_INVESTIGATION_2026_04_20.md` in this directory for the diagnosis.

---

## Future Session 5 prompt TODO (not this commit)

When authoring Session 5 v5 prompt:

1. Replace T5 monitoring-loop logic with T5a + T5b per above.
2. Read `MAX_POSITION_SOL_FRACTION` in the pre-flight preconditions checklist; confirm it's the binding cap for the current wallet size.
3. Tighten `MIN_POSITION_SOL` floor check so bot_core doesn't try to open positions below the "meaningful against real fees" threshold once FEE-MODEL-001 lands.
4. Include `scripts/live_flip_prep.sh` as a pre-flight step before TEST_MODE flip (see CLAUDE.md CLEAN-003).

Items 1-4 are prompt changes, not services changes.
