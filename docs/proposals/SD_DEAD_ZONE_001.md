# SD_DEAD_ZONE_001 — Speed Demon: Pause entries during 18-21 AEDT

**Status:** Proposed
**Created:** 2026-04-28 (LEARNINGS-CAPTURE-2026-04-28)
**Motivating audit:** `docs/audits/PAPER_TRADES_4DAY_ANALYSIS_2026_04_28.md` §6
**Group:** TUNE-006 (stack with SD_MC_CEILING_001 + SD_ML_THRESHOLD_LIFT_001)
**Estimated effort:** 10 min code; default reassessed at 14 days

---

## Problem statement

Across 528 Speed Demon paper trades over the 4-day window 2026-04-22 →
2026-04-25, the **18:00-21:00 AEDT window** (hours 18, 19, 20, 21 inclusive
— 75 trades) returned **-0.098 SOL net at 42.7% WR**. By contrast,
the strongest window (00:00-05:00 + 22:00 AEDT, 198 trades) returned
**+7.746 SOL at 45.5% WR** — and three of those concentrated hours
(2 AM, 5 AM, 10 PM) deliver almost half of total SD profit on their own.

The 18-21 AEDT window is the only contiguous AEDT band that is
**negative-EV** in the 4-day data:

| AEDT window | Hours | Trades | WR | PnL |
|-------------|------:|-------:|---:|----:|
| 00-06 (Asia awake)         | 0..5  | 164 | 48.2% | +5.493 |
| 06-12 (US evening)         | 6..11 | 159 | 45.9% | +0.997 |
| 12-17 (documented "dead")  | 12..16 | 62 | 43.5% | +0.540 |
| 17-24 (EU+Asia evening)    | 17..23 | 143 | 40.6% | +2.238 |
| **18-21 (worst, this proposal)** | **18..21** | **75** | **42.7%** | **-0.098** |
| 00-05 + 22 (best)          | 0..5,22 | 198 | 45.5% | +7.746 |

CLAUDE.md previously flagged **11-17 AEDT** as a dead zone — but the
4-day data does not support that window. 12-17 AEDT actually returns
+0.54 SOL at 43.5% WR. The real bleed is in 18-21, and CLAUDE.md
should be corrected when this proposal is implemented.

---

## Proposal

Add a new env var **`SD_PAUSE_HOURS_AEDT`** (default `18,19,20`). At
entry-time in the SD branch of `services/signal_aggregator.py`, reject
signals whose current AEDT hour matches any listed hour.

Pseudocode (location: same as SD_MC_CEILING_001 gate, immediately after
the MC ceiling check):

```python
import datetime
import zoneinfo

SD_PAUSE_HOURS_AEDT = [
    int(h) for h in os.environ.get("SD_PAUSE_HOURS_AEDT", "18,19,20").split(",")
    if h.strip()
]

# Inside SD entry gate:
now_aedt = datetime.datetime.now(zoneinfo.ZoneInfo("Australia/Sydney"))
if now_aedt.hour in SD_PAUSE_HOURS_AEDT:
    logger.info(
        "SD reject %s: pause hour %d AEDT",
        mint[:8], now_aedt.hour,
    )
    return None
```

**Default value rationale:** the env default is `18,19,20` (3 hours,
n=52, +0.033 SOL — barely positive). The audit shows the full 4-hour
window 18-21 (n=75, -0.098 SOL) is more clearly negative. Hour 21 is
borderline: 23 trades, 34.8% WR, -0.131 SOL. **The implementation
session can choose between conservative (3h) and aggressive (4h)
defaults; both are reasonable.** Setting `SD_PAUSE_HOURS_AEDT=18,19,20,21`
at deploy time captures the full bleed window. The env-var design
keeps this trivially adjustable post-deploy.

---

## Expected impact (4-day window)

Conservative (default `18,19,20`):

| Metric | Current | After pause | Δ |
|--------|--------:|------------:|---:|
| Speed Demon PnL | +9.269 SOL | ~+9.24 SOL | -0.03 (we're cutting a small +)  |
| Speed Demon trades | 528 | ~476 | -9.8% |
| Speed Demon WR | 44.9% | ~45.1% | +0.2 pp |

Aggressive (`18,19,20,21`):

| Metric | Current | After pause | Δ |
|--------|--------:|------------:|---:|
| Speed Demon PnL | +9.269 SOL | ~+9.37 SOL | +0.10 SOL |
| Speed Demon trades | 528 | ~453 | -14.2% |
| Speed Demon WR | 44.9% | ~45.4% | +0.5 pp |

**This is a small lever in absolute terms.** The real value is two-fold:

1. **It stacks with SD_MC_CEILING_001** to compound capital efficiency.
2. **It removes a documented losing window** before it can grow.
   75 trades is small; another month at the same rate could see
   -0.5 to -1.0 SOL bleed at this hour.

---

## Risks

1. **Sample size of 75 trades is small.** 4-hour worst-window finding
   on N=75 is within noise envelope of ±2σ. Worst case: the true edge
   in this window is actually neutral (-0.05 to +0.05 SOL) and we're
   idling the bot for 3-4 hours/day with no benefit.
2. **18-21 AEDT corresponds to specific market events** (US morning
   open, EU late-evening, Asia overnight quiet). The pattern may
   shift as market participants change behavior or as Solana
   activity concentrates differently.
3. **Hour 22 AEDT is a strong winner** (32.4% WR but +2.253 SOL —
   driven by the +2.375 SOL biggest banger). The pause window should
   NEVER be extended into hour 22 unless that's been re-validated
   with multi-week data — pausing there would be value-destructive
   given a single banger trade dominated that hour.
4. **AEDT vs AEST.** Australia/Sydney auto-handles DST. As of 2026-04-28
   Sydney is on AEDT (UTC+10 since April 6 DST end... actually Australia
   DST ends in early April, so Sydney is now AEST UTC+10). The
   `zoneinfo("Australia/Sydney")` lookup returns the correct local
   offset regardless of DST state. Implementation must use the
   zoneinfo path, not a hardcoded UTC+11 offset.

---

## Mitigation: 14-day reassessment criterion

Implement as feature flag with metrics. Track WR + PnL of the would-have-
been trades (i.e., signals received during pause hours that the gate
rejected) for 14 days post-deploy. The rejected signals can be observed
via the `SD reject … pause hour …` log lines and cross-referenced
against subsequent token outcomes via `services/signal_aggregator.py`
post-mortem features.

After 14 days:

- If WR of would-have-been trades trends to 40-45% (matches the
  prior baseline) → **keep pause** — the bleed is real.
- If WR trends to ≥50% → **remove pause** — the original 4-day signal
  was variance.

If keeping the pause, also re-evaluate whether to extend to
`18,19,20,21` (the audit's clearer bleed window) based on the 14-day
data.

---

## Success criteria (measure 24h after deploy)

1. **Zero SD entries fire when current AEDT hour is in
   `SD_PAUSE_HOURS_AEDT`.** Log inspection — if any do, the gate is
   broken.
2. **Speed Demon trade count drop in expected band** (-9% to -15%
   of pre-deploy baseline depending on default chosen).
3. **No degradation in non-paused-hour WR.** Baseline pre-deploy SD
   WR in 0-17 + 22-23 AEDT is ~45.4%; post-deploy that band's WR
   should hold within ±2 pp.

A 24h window is too short to see the full PnL impact (only ~3-4 hours
of pause time per day). The 14-day reassessment is the real test.

---

## Roll-back

Set `SD_PAUSE_HOURS_AEDT=` (empty string) on signal_aggregator. The
env var parser handles empty list as "no pause." Single env var, no
code change. Auto-redeploy ~90s.

---

## CLAUDE.md correction (deferred to implementation session)

The CLAUDE.md "11-17 AEDT dead zone" reference is mis-windowed vs the
current data. The implementation session that lands this proposal
should ALSO update CLAUDE.md to:

- Remove the "11-17 AEDT dead zone" claim (the 12-17 window is +0.54
  SOL at 43.5% WR — not dead).
- Add a new line documenting "18-21 AEDT bleed window — paused via
  SD_PAUSE_HOURS_AEDT env var; reassess at 14 days."

Both changes go in the same TUNE-006 commit so doc and code stay
in sync.

---

## Implementation effort

- **Code:** ~10 minutes (env var read, gate check, info log)
- **Compile check:** `python -m py_compile services/signal_aggregator.py`
- **Deploy:** `git push` (Railway auto-deploys)
- **Observation:** 24h immediate, 14-day reassessment
- **Total:** roll into same TUNE-006 session as SD_MC_CEILING_001

---

## Stacking with other TUNE-006 proposals

- **SD_MC_CEILING_001** — independent gate, no overlap.
- **SD_ML_THRESHOLD_LIFT_001** — independent (time-based vs score-based).

Combined estimated 4-day net effect (paper, vs current +9.27 baseline):
**+12.5 to +13.5 SOL** with all three stacked.

---

## Out of scope for this proposal

- Per-day-of-week pause windows (sample too small at 4 days)
- Auto-tuning pause hours from rolling N-day data
- Pausing other personalities (Analyst is hard-disabled)
- Live-mode pause windows (separate validation needed)
- Hard pause across services (this gates entries only — exits and
  position management still run normally)
