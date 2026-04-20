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

---

## Appendix A — Full v4 timeline and findings catalog (added 2026-04-21)

Added during roadmap consolidation after FIX-1 + FIX-2 landed. Captures
the full set of v4 observations for future reference. Primary focus of
this doc (above) remains T5 redesign and `MAX_POSITION_SOL_FRACTION`.

### Timeline

- T+0 (20:44:30Z): flip effective, bot_core running with TEST_MODE=false
- T+6 to T+11: 5 reconcile-residual sell attempts on paper-inherited mints
  (no actual SOL at risk — mints don't exist on-chain)
- T+11:23 (20:55:53Z): live buy on `yh3n441...`, 0.365 SOL at $0.0000024098
- T+12:00 (20:56:30Z): T5 trigger fired — wallet read 1.284 (22.57% drawdown)
- T+12:17 (20:56:47Z): position exited at $0.0000024222 (+0.51% price) via
  `no_momentum_90s`. Wallet recovered to 1.564 SOL.
- T+13:42 (20:58:12Z): rollback flip submitted
- T+15:04 (20:59:22Z): TEST_MODE=true confirmed

### Finding catalog

1. **T5 false-positive on benign position state** — see primary sections above. Replaced by T5a/T5b (T5-DESIGN-001); paired with `MAX_POSITION_SOL_FRACTION`.
2. **FEE-MODEL-001 under-calibrated by ~96×** — observed -0.094 SOL vs predicted +0.002 SOL on 0.365 SOL pre-grad round-trip. Dominant gap is BC slippage (~22.5% of position), not fixed fees. Resolution: FIX-2 (`e078b4c`) landed corrected model; `PAPER_EDGE_REBASELINE_2026_04_20.md` re-baselined 7d Speed Demon paper edge under new model (edge does NOT survive at current sizing distribution; v5 needs `MAX_POSITION_SOL=0.25`).
3. **Reconcile-residual crosses TEST_MODE boundary** — 5 paper positions leaked into live-mode memory, causing 25 wasted Helius RPC calls. No SOL lost. Mitigated by CLEAN-003 (`scripts/live_flip_prep.sh`).
4. **ML threshold bypass (outcome C — actual bug)** — `AGGRESSIVE_PAPER_TRADING=true` overrides `ML_THRESHOLDS` at module load regardless of TEST_MODE. Verified: 113 speed_demon trades in 7d with `ml_score<40` despite floor=40. Diagnosis: `ML_BYPASS_INVESTIGATION_2026_04_20.md`. Fix required before v5.
5. **Rollback machinery validated** — trigger fired, TEST_MODE restored within 15 min, zero trapped positions, Redis sentinels clean. Safety system did its job even on a false-positive trigger (correct failure mode).
6. **Helius STAKED URL 522 recurred** — `ardith-mo8tnm-fast-mainnet.helius-rpc.com` returned Cloudflare 522 errors. Filed `ZMN-BOT-CORE-1` (medium) + `ZMN-BOT-CORE-2` (low, `ContentTypeError` consequence). Contributed to 15 "no Helius URL available" errors in `live_trade_log`. Known-flaky URL; has recurred.
7. **Railway auto-deploy latency** — `set-variables` took ~10 min to trigger redeploy vs typical 60-90s. Tracked as DEPLOY-DISCIPLINE-001. Not a rollback cause; affected session timing.

### Pre-Session-5-v5 gate checklist

- [x] **FEE-MODEL-001** fixes + historical rebaseline landed (commit `e078b4c`)
- [x] **CLEAN-003** script + CLAUDE.md procedure landed (FIX-1)
- [x] **MAX_POSITION_SOL_FRACTION** active in bot_core (via `e078b4c`)
- [ ] **T5a/T5b** trigger definitions in Session 5 v5 prompt (T5-DESIGN-001)
- [ ] **ML-012** landed — `AGGRESSIVE_PAPER_TRADING` override gated on `TEST_MODE`
- [ ] Position-size caps from rebaseline applied in Railway env
      (`MAX_POSITION_SOL=0.25`, `SPEED_DEMON_BASE_SIZE_SOL≈0.15`,
      `SPEED_DEMON_MAX_SIZE_SOL≈0.25`)
- [ ] SEC-001 waiver decision (apply v4-style single-window waiver OR rotate creds)

### New roadmap items from this consolidation

- **EXEC-005** (Tier 2) — Jito on pre-grad path. v4 evidence: MEV not the dominant factor for single-trade data point (slippage dominates). Marginal impact; re-prioritize from multi-trade live samples.
- **SLIPPAGE-CALIBRATION-001** (Tier 2, recurring) — ongoing monthly/per-10-trades recalibration of `SLIPPAGE_RANGES` from accumulated live data.
- **OBS-012** (Tier 3) — dashboard `ml_score` column source verification.
- **DEPLOY-DISCIPLINE-001** (Tier 3) — Railway variable-set-to-redeploy latency diagnostic.

FIX-1 landed earlier: T5-DESIGN-001, CLEAN-003 ✅, ML-012 diagnosis.
FIX-2 landed: FEE-MODEL-001 ✅ (escalated Tier 2 → Tier 1 PRE-LIVE BLOCKER).
