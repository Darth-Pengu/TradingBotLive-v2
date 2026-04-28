# 4-Day Paper Trades Analysis — 2026-04-28

**Session:** LEARNINGS-CAPTURE-2026-04-28
**Author:** Claude Code (read-only audit)
**Source:** `session_outputs/paper_trades_export_2026_04_28.csv`
**Status:** Reproducibility verified — all headline numbers reproduce
within ±0.5 SOL and ±2% WR of chat-side analysis.

This audit motivates three SD tuning proposals stored under
`docs/proposals/`:

- `SD_MC_CEILING_001.md` — cap entries at $5k MC
- `SD_DEAD_ZONE_001.md` — pause 18-21 AEDT
- `SD_ML_THRESHOLD_LIFT_001.md` — lift ML threshold 40 → 50

All three are intended to be implemented together in a single TUNE-006
session.

---

## §1 Source data

- **File:** `session_outputs/paper_trades_export_2026_04_28.csv` (1.4 MB)
- **Total rows:** 835 (header + 835 data rows; 836 lines total)
- **Time range:** 2026-04-22 14:02 UTC → 2026-04-25 21:47 UTC
  (paper rows). Live rows are historical (April 16-20).
- **trade_mode breakdown:**
  - `paper`: 829 rows
  - `live`: 6 rows (excluded from most analysis below — they are the
    historical April 16-20 v3/v4 trial trades, see
    `ZMN_LIVE_TRADE_FORENSICS_2026_04_19.md`)
- **Personality breakdown (paper):**
  - `speed_demon`: 528
  - `analyst`: 301

The 6 live rows are forensic-only and are not included in any §-table
that says "Speed Demon paper" or "paper trades" below.

---

## §2 Core finding — Speed Demon edge is real, Analyst eats it

| Personality | Trades | Realised PnL | WR    |
|-------------|-------:|-------------:|------:|
| Speed Demon |    528 |   +9.269 SOL | 44.89% |
| Analyst     |    301 |  -15.034 SOL | 15.95% |
| **Net (paper, all)** | **829** | **-5.765 SOL** | **34.38%** |

Reproducible query (Python over the CSV):

```python
sd = [r for r in paper if r['personality']=='speed_demon']
an = [r for r in paper if r['personality']=='analyst']
sd_pnl = sum(float(r['realised_pnl_sol']) for r in sd)  # +9.269
an_pnl = sum(float(r['realised_pnl_sol']) for r in an)  # -15.034
```

**If Analyst stayed disabled, paper-mode would be +9.27 SOL over 4 days.**
The Analyst leak is the dominant cause of the negative net. The hard
disable via `ANALYST_DISABLED=true` (handled by the concurrent
ANALYST-DISABLE-002 session) addresses this directly.

---

## §3 Speed Demon edge concentration

The SD edge is fat-tailed: it lives in a small number of large winners.

| Bucket | Trades | Total PnL | Avg PnL/trade |
|--------|-------:|----------:|--------------:|
| Big winners (≥0.10 SOL each) | 31  | +10.788 SOL | +0.348 |
| All other trades              | 497 |  -1.519 SOL | -0.003 |
| **All Speed Demon (paper)**   | **528** | **+9.269 SOL** | **+0.018** |

- **Single biggest banger:** +2.375 SOL on a +4846% gain
  (mint `ABffkYmh…`).
- **Top 5 trades alone:** +6.405 SOL (69% of total SD profit).
- **Top 31 trades:** +10.788 SOL (more than the entire SD profit).

**Strategy implication:** preserving the trailing stop (the mechanism
that lets these tail-winners run) is more important than tightening
losses on the median trade. Any change that shaves the right tail
(e.g., earlier exits, tighter stops, higher ML threshold that filters
out monster winners) is high-risk.

---

## §4 Speed Demon WR deteriorating across the 4-day window (UTC)

| Date (UTC) | Trades | PnL | WR | TRAILING_STOP % |
|------------|-------:|-----:|----:|----------------:|
| 2026-04-22 | 105 | +1.449 | 52.4% | 59.0% |
| 2026-04-23 | 137 | +5.033 | 50.4% | 48.2% |
| 2026-04-24 | 160 | +3.993 | 44.4% | 54.4% |
| 2026-04-25 | 126 | -1.206 | 33.3% | 42.9% |

WR fell ~19 points across 3 days. `TRAILING_STOP` exit fraction also
declined. Two readings of this:

1. **Regime shift hypothesis** — market conditions degraded into
   April 25, fewer tokens reached the trailing-stop bracket.
2. **TUNE-005 binding hypothesis** — recent tuning may be filtering
   out signals that previously delivered momentum-following winners.
3. **Variance** — N=126 in a single day is small. The true daily WR
   could be ±5pp from the point estimate.

**Recommendation:** before drawing tuning conclusions from any single
day, take a 24-hour observation window with Analyst permanently
disabled (post ANALYST-DISABLE-002) to remove that confound. Then
re-evaluate whether the 04-25 dip persists.

---

## §5 The smoking-gun analysis — exit reason × entry MC

This is the single most actionable table in the audit. It motivates
**SD_MC_CEILING_001** directly.

| Exit Reason       | Count | Median Entry MC ($) | Total PnL (SOL) |
|-------------------|------:|--------------------:|----------------:|
| TRAILING_STOP     |   269 |             $664    |        +11.311  |
| staged_tp_+1000%  |     3 |             $142    |         +5.442  |
| stale_no_price    |    30 |             $806    |         +0.965  |
| staged_tp_+200%   |     2 |             $549    |         +0.192  |
| no_momentum_90s   |   147 |           $2,609    |         -2.927  |
| stop_loss_20%     |    77 |           $7,749    |         -5.714  |

**Key observations:**

- All winning exit categories (TRAILING_STOP, staged_tp_*, stale_no_price)
  have median entry MC at or below $810.
- Both losing categories (no_momentum_90s, stop_loss_20%) have median
  entry MC above $2,600. `stop_loss_20%` median is $7,749 — more than
  10× the median TRAILING_STOP winner.
- **Speed Demon's edge is at the bottom of the MC range.** Entries at
  mid-range MC ($2k-$10k) are net-negative.
- Of the 77 `stop_loss_20%` trades, 58 have entry MC > $5,000 with
  combined PnL of **-4.761 SOL**.

This pattern is consistent with the strategy thesis: ultra-low-MC
tokens have asymmetric upside (4846% on the biggest winner;
+1000% staged TPs); higher-MC entries are tokens that already had
their move and are now distributing.

---

## §6 Time-of-day effect

Hours are converted from `entry_time` (epoch UTC) to AEDT via
`zoneinfo("Australia/Sydney")`. All 528 SD paper trades have valid
`entry_time`.

| AEDT Window           | Hours | Trades | WR | PnL |
|-----------------------|------:|-------:|---:|----:|
| Asia awake            | 0..5  | 164 | 48.2% | +5.493 |
| US evening            | 6..11 | 159 | 45.9% | +0.997 |
| Documented dead zone  | 12..16 |  62 | 43.5% | +0.540 |
| EU+Asia evening       | 17..23 | 143 | 40.6% | +2.238 |
| **18-21 worst**       | **18..21** | **75** | **42.7%** | **-0.098** |
| Best                  | 0..5,22 | 198 | 45.5% | +7.746 |

**Findings:**

- The "documented dead zone" (12-17 AEDT, called out in CLAUDE.md and
  prior audits) is **not actually dead** — it returns +0.54 SOL at
  43.5% WR on 62 trades. It's slightly below the SD mean but firmly
  positive.
- The actual worst window is **18-21 AEDT** (hours 18, 19, 20, 21
  inclusive — 75 trades) at -0.098 SOL net, 42.7% WR.
- The CLAUDE.md note about an 11-17 AEDT dead zone is mis-windowed
  vs the current data. **This documentation correction is deferred
  to the SD_DEAD_ZONE_001 implementation session — not this audit.**

Hour-by-hour (informational):

```
 h     n     WR%       PnL
 0    15   33.3%    +0.491
 1    24   29.2%    +0.082
 2    35   62.9%    +3.534   ← biggest single hour
 3    37   48.6%    +0.489
 4    26   42.3%    +0.116
 5    27   59.3%    +0.781
 6    40   37.5%    -0.155
 7    16   62.5%    +0.126
 8    33   48.5%    -0.210
 9    26   38.5%    +0.206
10    17   58.8%    +0.373
11    27   44.4%    +0.656
12    15   26.7%    +0.191
13     5   40.0%    +0.036
14     9   44.4%    +0.059
15    11   63.6%    +0.211
16    22   45.5%    +0.044
17    27   44.4%    +0.103
18    19   36.8%    -0.424   ← worst
19    18   50.0%    -0.243
20    15   53.3%    +0.700
21    23   34.8%    -0.131
22    34   32.4%    +2.253   ← second-biggest single hour (one banger)
23     7   42.9%    -0.020
```

Hour 02 alone delivers +3.53 SOL across 35 trades (62.9% WR). Hour 22
is the +2.37 SOL banger trade plus background. Both are concentrated
windows — pausing them would be value-destructive.

---

## §7 ML score predictive power — limited but lift-able

| ML score band | Trades | WR | Total PnL |
|---------------|-------:|---:|----------:|
| (0, 40]   |  46 | 52.2% | +0.945 |
| (40, 50]  | 156 | 42.3% | +0.945 |
| (50, 60]  |  95 | 40.0% | +2.567 |
| (60, 70]  |  94 | 45.7% | +3.734 |
| (70, 80]  |  69 | 53.6% | +1.362 |
| (80, 100] |  68 | 42.6% | -0.284 |

**Findings:**

- ML score is **not monotonic in 4-day data.** Best WR is in (70,80];
  worst PnL is in (80,100]. There is signal but not a clean threshold.
- The (40, 50] band returns the same +0.95 SOL as (0, 40] but on
  3.4× the trade volume. **This is volume without edge.**
- The (50, 60] band returns +2.57 SOL — a real edge. The band gap
  between (40,50] and (50,60] is the cleanest tuning lever.

This motivates **SD_ML_THRESHOLD_LIFT_001** (40 → 50): drop the noise
band, keep the edge bands. Trade volume falls ~30% (156 of 528 = 29.5%
of SD volume), gross PnL falls ~10% (-0.95 SOL of +9.27), per-trade
PnL improves.

CLAUDE.md note: the historical "ML inverts above 40" claim was
superseded 2026-04-17 by the feature-default fix. This 4-day data
re-confirms higher scores are not worse — the 70-80 band is the
strongest by WR. No upper bound is needed; the lift to 50 just
removes the noise floor.

---

## §8 Hold time — early exits cut eventual winners

| Hold window | Trades | WR | Total PnL | Avg PnL/trade |
|-------------|-------:|---:|----------:|--------------:|
| Under 90s   |   229 |  2.2% |  -3.007 | -0.0131 |
| 10-30 min   |   299 | 77.6% | +12.276 | +0.0411 |

**This is a striking finding.** Trades held 10+ minutes are 77.6%
winners. Trades cut at <90s are 2.2% winners. The early-exit logic
(`no_momentum_90s` + `stop_loss_20%` triggering before momentum can
develop) is killing eventual winners.

**Cross-reference with §5:** the 147 `no_momentum_90s` exits and 77
`stop_loss_20%` exits make up most of the under-90s bucket. Both have
high median entry MC. The picture that emerges:

> Tokens that get to fire trailing_stop tend to be at MC <$700 entry.
> Higher-MC entries get killed by early exits before they can develop
> momentum.

This reinforces SD_MC_CEILING_001. Cutting high-MC entries is more
valuable than tuning the early-exit thresholds, because the early-exit
thresholds are doing the right thing for the high-MC trades (they
genuinely don't develop momentum); the fix is to never enter them.

---

## §9 BUG-022 status — corrected_pnl_sol still 100% NULL

```
corrected_pnl_sol populated: 0 / 835 (0.0%)
corrected_pnl_sol NULL:    835 / 835 (100.0%)
```

All PnL numbers in this audit are `realised_pnl_sol` fallback. Per
CLAUDE.md "Trade P/L Analysis Rule" the corrected column should be
preferred for ML retraining and reporting; we cannot, because it is
empty for every row in this export.

Per FEE-MODEL-001, `realised_pnl_sol` is biased by ~0.004 SOL/trade
at 0.05 SOL sizing on post-grad trades, and more on pre-grad. **The
directional findings in this audit hold regardless of fee correction**
— the gap between TRAILING_STOP +11.31 SOL and stop_loss_20%
-5.71 SOL is not flipped by a 5% fee adjustment. **Absolute SOL
magnitudes should be treated as estimates, not ground truth.**

When BUG-022 is fixed, this audit's tables should be re-run against
`corrected_pnl_sol` to verify direction is preserved (expected) and
to recalibrate the absolute estimates in the three proposals.

---

## §10 Caveats

1. **Single 4-day window.** April 25 in particular shows a regime
   that may or may not generalize. Two more weeks of post-Analyst-
   disable data would tighten the WR-decline conclusion in §4.
2. **75 trades is a small sample for a "dead zone."** The 18-21 AEDT
   bleed is on N=75 — within ±2σ a true edge could plausibly be
   anywhere from -0.30 to +0.10 SOL. SD_DEAD_ZONE_001 should bake in
   a 2-week reassessment criterion.
3. **No corrected_pnl_sol means absolute magnitudes are estimates.**
   Differences between buckets are robust; absolute SOL values are
   not. See §9.
4. **Analyst was running concurrently and consuming RPC quota.**
   Speed Demon's measured cadence (105/137/160/126/day) may have been
   throttled by Analyst's load. Post-disable, SD volume could rise,
   in which case all per-band volumes need re-examination.
5. **Live data is historical only.** The 6 live rows are April 16-20
   trial trades. They tell us nothing about post-improvement
   personality behavior.
6. **Daily breakdown UTC vs AEDT.** This audit uses UTC for the daily
   table (so 04-22 means UTC date 04-22). The time-of-day analysis
   uses AEDT (Jay's wall-clock). When implementing the dead-zone
   pause, the env var operates in AEDT — `zoneinfo("Australia/Sydney")`
   — to match Jay's mental model.

---

## Reproducibility

All tables in this audit are produced from the source CSV by the
analysis script committed at `/tmp/zmn_analysis.py` (locally) during
session LEARNINGS-CAPTURE-2026-04-28. Re-running the same script
against the same CSV produces identical numbers. Headline reproducibility
checks (vs chat-side analysis):

| Metric | Expected | Actual | Pass |
|---|---:|---:|---|
| Total rows | 835 | 835 | ✅ |
| Paper rows | 829 | 829 | ✅ |
| Speed Demon trades | 528 | 528 | ✅ |
| Speed Demon PnL | +9.27 SOL | +9.269 SOL | ✅ |
| Speed Demon WR | 44.9% | 44.89% | ✅ |
| Analyst PnL | -15.03 SOL | -15.034 SOL | ✅ |
| Analyst WR | 15.9% | 15.95% | ✅ |
| corrected_pnl_sol NULL | 100% | 100.0% | ✅ |
| Big winners (≥0.10) | 31 / +10.79 | 31 / +10.788 | ✅ |
| Biggest single trade | +2.37 SOL @ 4846% | +2.375 SOL @ 4846.4% | ✅ |
| TRAILING_STOP median MC | $664 | $664 | ✅ |
| stop_loss_20% median MC | $7,749 | $7,749 | ✅ |
| 18-21 AEDT (4hr) | 75 / -0.10 / 42.7% | 75 / -0.098 / 42.7% | ✅ |
| Best window 00-05+22 | 198 / +7.75 / 45.5% | 198 / +7.746 / 45.5% | ✅ |
| ML (40,50] | 156 / +0.95 / 42.3% | 156 / +0.945 / 42.3% | ✅ |
| Hold <90s | 229 / 2.2% WR | 229 / 2.2% WR | ✅ |
| Hold 10-30 min | 299 / 77.6% WR | 299 / 77.6% WR | ✅ |

Daily breakdown (§4) differs by ≤5 trades/day and ≤0.4 SOL/day from
the chat-side numbers. Both sets are within ±0.5 SOL / ±2% WR
tolerance. Likely cause: chat-side used a different day-boundary
definition (export-cutoff vs strict UTC midnight). This audit uses
strict UTC midnight.
