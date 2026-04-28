# SD_ML_THRESHOLD_LIFT_001 — Speed Demon: Lift ML threshold from 40 to 50

**Status:** Proposed
**Created:** 2026-04-28 (LEARNINGS-CAPTURE-2026-04-28)
**Motivating audit:** `docs/audits/PAPER_TRADES_4DAY_ANALYSIS_2026_04_28.md` §7
**Group:** TUNE-006 (stack with SD_MC_CEILING_001 + SD_DEAD_ZONE_001)
**Estimated effort:** 5 min env var change, no code

---

## Problem statement

The current Speed Demon ML threshold (`ML_THRESHOLD_SPEED_DEMON`) is
**40**. Of 528 SD paper trades over the 4-day window:

| ML score band | Trades | WR | Total PnL |
|---------------|-------:|---:|----------:|
| (0, 40]   |  46 | 52.2% | +0.945 |
| **(40, 50]**  | **156** | **42.3%** | **+0.945** |
| (50, 60]  |  95 | 40.0% | +2.567 |
| (60, 70]  |  94 | 45.7% | +3.734 |
| (70, 80]  |  69 | 53.6% | +1.362 |
| (80, 100] |  68 | 42.6% | -0.284 |

The (40, 50] band returns **+0.945 SOL on 156 trades** — the same
absolute PnL as the (0, 40] band on 3.4× the trade volume. Per-trade
PnL in (40, 50] is +0.006 SOL — barely profitable, well below the SD
overall mean of +0.018 SOL/trade.

The (50, 60] band, by contrast, returns **+2.567 SOL on 95 trades**
(+0.027 SOL/trade — 4.5× the per-trade PnL of (40, 50]).

**The (40, 50] band is volume without edge.** Lifting the threshold
removes 156 trades that combine to nearly zero per-trade contribution.

ML score is **not perfectly monotonic** in the 4-day window — best
WR is in (70, 80] (53.6%); worst PnL is in (80, 100] (-0.284 SOL).
But the threshold lift to 50 isn't trying to optimize the upper tail,
it's removing the noise floor at the bottom. The (50, 80] bands all
return positive PnL with WR between 40-54%.

---

## Proposal

Set **`ML_THRESHOLD_SPEED_DEMON=50`** on `signal_aggregator` (env var
only — no code change required, the threshold is already env-driven
per CLAUDE.md "ML threshold — corrected 2026-04-17" note).

```bash
railway variables --set "ML_THRESHOLD_SPEED_DEMON=50" -s signal_aggregator
```

(Variable name to confirm against `services/signal_aggregator.py` —
the CLAUDE.md note references `ML_THRESHOLD_SPEED_DEMON` but the
implementation session must verify the env var key in code before
deploying.)

---

## Expected impact (4-day window)

| Metric | Current (≥40) | Lifted (≥50) | Δ |
|--------|--------------:|-------------:|---:|
| Speed Demon PnL | +9.269 SOL | ~+8.32 SOL | -0.95 SOL |
| Speed Demon trades | 528 | ~370 | -29.9% |
| Speed Demon WR | 44.9% | ~45.7% | +0.8 pp |
| Avg PnL per trade | +0.018 SOL | +0.022 SOL | +22% |

**Gross PnL falls slightly. Per-trade PnL improves materially. Capital
exposure drops by ~30%.**

---

## Why this matters for V5a (live trading)

V5a (the upcoming live trading test) caps wallet exposure to a 5 SOL
test wallet. Concurrent live position count is constrained by both
wallet balance and `MAX_SD_POSITIONS`. Cutting noise trades without
losing edge is exactly what V5a needs:

- Fewer concurrent trades = lower drawdown variance
- Higher per-trade signal quality = higher live → paper edge retention
  (per FEE-MODEL-001, live PnL is dominated by per-trade fee floor;
  fewer trades with higher avg PnL is structurally more fee-efficient)
- Cleaner attribution if live diverges from paper (less variance in
  the comparison sample)

If V5a is going to make sizing or strategy claims based on early live
data, those claims are more interpretable when the entry filter is
stricter.

---

## Risks

1. **ML score isn't perfectly monotonic.** The (70, 80] band has the
   best WR (53.6%); (80, 100] is the worst PnL band. Setting threshold
   to 50 keeps both — it doesn't capture the per-band optimization. A
   future iteration could explore per-band thresholds (e.g., reject
   (80, 100] and (40, 50]) but that's higher complexity for marginal
   incremental value. **This proposal is the simplest first step.**
2. **Some of the (40, 50] band may have been cohort-specific.** Other
   market regimes may push that band higher-EV. The 4-day window is
   one regime sample.
3. **Per-trade PnL improvement is partly mechanical.** Removing 156
   marginal trades while keeping the $0.95 SOL total lifts the average
   trivially. The real economic question is whether the freed
   capital exposure is worth more elsewhere — for paper mode this is
   a non-issue (no scarcity), but for V5a live capital it's the
   point of the change.
4. **Threshold lift compounds with SD_MC_CEILING_001.** Many of the
   (40, 50] trades are also high-MC trades. The marginal volume cut
   from this proposal vs an MC-ceiling-only deploy may be smaller than
   the table suggests. Implementation session should re-measure post-
   stacking.

---

## Success criteria (measure 24h after deploy)

1. **Trade volume reduction in expected range** (-25% to -35%). Both
   tighter and looser is a sign the env var didn't propagate correctly
   or that the cohort has shifted.
2. **WR ≥ 45%** (no degradation from baseline 44.9%). If WR drops
   below 43%, halt — the assumption that the (40, 50] band is noise
   has broken in the new regime.
3. **Per-trade PnL flat or improving** vs baseline +0.018 SOL/trade.
   Should land at ~+0.022 to +0.025 SOL/trade if the cut is clean.
4. **No new gap in coverage.** Confirm via signal_aggregator logs
   that signals with ML score ≥50 are still being processed normally
   — the lift should drop signals 40-49 and pass everything ≥50
   unchanged.

---

## Roll-back

```bash
railway variables --set "ML_THRESHOLD_SPEED_DEMON=40" -s signal_aggregator
```

Single env var. Auto-redeploy ~90s. No code state to revert.

---

## Implementation effort

- **Code:** 0 minutes (env var only — verify the var name first)
- **Verification:** confirm new threshold appears in startup log
  (5 min)
- **Total:** ~5 minutes including verification

The simplest of the three TUNE-006 proposals — pure config change.

---

## Stacking with other TUNE-006 proposals

- **SD_MC_CEILING_001** — partial overlap. Many (40,50] band trades
  may also be high-MC. Stacked impact is sub-additive.
- **SD_DEAD_ZONE_001** — independent (time-based vs score-based).

**Recommended deploy order within TUNE-006:**

1. ML threshold lift (zero code, fastest verification).
2. Dead-zone pause (small code, simple gate).
3. MC ceiling (more code surface, needs MC freshness check).

Deploying in this order means each subsequent change layers on
verified-good baseline state.

Combined estimated 4-day net effect (paper, vs current +9.27 baseline):
**+12.5 to +13.5 SOL** with all three stacked.

---

## CLAUDE.md note

CLAUDE.md "ML threshold — corrected 2026-04-17" block currently says:

> `ML_THRESHOLD_SPEED_DEMON` floor = 40 (gated at signal_aggregator).
> No upper bound. Higher scores are better, not worse.

After implementation, this should be updated to:

> `ML_THRESHOLD_SPEED_DEMON` floor = 50 (lifted 2026-04-DD by
> SD_ML_THRESHOLD_LIFT_001 — see audit
> `PAPER_TRADES_4DAY_ANALYSIS_2026_04_28.md` §7). No upper bound.
> The (40, 50] band is filtered out as volume without edge.
> Higher scores remain better, not worse.

This doc edit lands with the implementation commit.

---

## Out of scope for this proposal

- Per-band ML thresholds (e.g., reject (80, 100])
- Personality-specific tuning beyond Speed Demon (Analyst is
  hard-disabled)
- ML model retraining (blocked on >500 clean samples per CLAUDE.md
  "ML retrain blocked on 500+ clean samples")
- Live-mode threshold differences from paper-mode (defer to V5a)
- Adaptive threshold based on recent WR (out of scope; complexity
  not justified by 4-day data)
