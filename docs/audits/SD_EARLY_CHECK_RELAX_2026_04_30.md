# SD-EARLY-CHECK-RELAX 2026-04-30 — verdict: Option Gamma (defer)

**Session:** SD-EARLY-CHECK-RELAX-2026-04-30
**Author:** Claude Code (read-only audit + decision)
**Tracking ID:** TUNE-009
**Status:** ⏸ DEFERRED — empirical data does not support a relaxation. No env-var change, no code change, no deploy.

---

## §1 Verdict — Option Gamma (defer, no change)

**Decision: do NOT relax `SD_EARLY_CHECK_SECONDS` or `SD_EARLY_MIN_MOVE_PCT` at this time.** Document and revisit after Sessions B/C/D land.

**Reasoning:**

1. The check is firing exactly where designed (window opens at 50s with `SD_EARLY_CHECK_SECONDS=60`).
2. **Zero of 123 post-recovery dead trades are slow-starters** that any of the proposed relaxations would have saved.
3. The dead population is deeply negative at exit time (mean -17.37%, median -16.12%, max -1.85%) — these tokens are not recovering with more time.
4. The 13 post-recovery big winners (≥0.10 SOL) all bypassed the check (2 hit `staged_tp_+1000%` at <2s, 11 hit `TRAILING_STOP` at ~600s after surviving the 50-90s window with ≥3% pnl).
5. The structural fix for the bleed is **upstream entry filtering** (Session C — `SD_MC_CEILING_USD`), not exit-logic relaxation. Filtering at entry prevents the trades from being opened; relaxing the exit logic just delays the inevitable.

**The session prompt's working hypothesis** ("the trade population that breaks out *after* 60s is being killed prematurely") is **not supported by the data**. The 14 big winners did not die at 50-90s — they survived because they had momentum. The 123 dead trades aren't almost-winners; they're deeply-negative high-MC tokens.

---

## §2 Code finding (Step 1)

**Location:** `services/bot_core.py:1590-1604`

**Function context:** position-monitoring loop (called from `_position_monitor_loop` or equivalent) — iterates over open positions and applies exit checks.

**Mechanism (verbatim, with prod env-var values):**

```python
# 90-second momentum check for speed_demon
# Skip if staged exits already fired (token proved itself)
early_check_sec = float(os.getenv("SD_EARLY_CHECK_SECONDS", "90"))   # env=60 — code default 90
early_min_move = float(os.getenv("SD_EARLY_MIN_MOVE_PCT", "2.0"))    # env=3.0 — code default 2.0
if pos.personality == "speed_demon" and current_price > 0 and entry > 0:
    if pos.staged_exits_done:
        pass  # Already hit TP — let trailing ride, skip momentum check
    else:
        hold_sec = time.time() - pos.entry_time
        if early_check_sec - 10 < hold_sec < early_check_sec + 30:   # window: (50, 90)s
            pnl_pct = (current_price - entry) / entry * 100
            if pnl_pct < early_min_move:                              # < 3.0%
                logger.info("NO MOMENTUM 90s: %s %.1f%%", pos.mint[:8], pnl_pct)
                await self._close_position(pos, "no_momentum_90s", current_price=current_price)
                continue
```

**Reconciliation of label vs. timing:**
- The label `no_momentum_90s` is a legacy artefact from when code default was 90s (window 80-120s).
- Production env vars `SD_EARLY_CHECK_SECONDS=60` + `SD_EARLY_MIN_MOVE_PCT=3.0` shift the window to (50, 90)s with a stricter 3% threshold.
- The label was never updated. Trades exit at ~50-52s — the first poll inside the window — but emit the legacy label.

**Single-check, single env-var path.** No separate 90s check exists. The label-vs-timing mismatch is purely cosmetic.

---

## §3 Hold-time distribution (Step 2)

Post-recovery sample (entry_time > 2026-04-28 13:00 UTC, personality=speed_demon, exit_reason=no_momentum_90s):

| hold bucket | n | avg_pnl | sum_pnl | wins | min_hold | max_hold |
|---|---:|---:|---:|---:|---:|---:|
| 50-60s | **123** | -0.0237 | **-2.915** | **0** | 50.03 | 51.97 |

**Total: n=123, sum_pnl=-2.915 SOL, wins=0, mean_hold=50.97s, median_hold=50.89s.**

100% of dead trades fall in the 50-60s bucket. Min hold 50.03s, max 51.97s. This is the exact signature of `early_check_sec - 10 < hold_sec` opening at 50s — trades exit at the first poll after the window opens, ~1-2s later.

---

## §4 Big winners' hold times (Step 3)

Post-recovery big winners (realised_pnl_sol ≥ 0.10 SOL, personality=speed_demon):

| id | mint | hold_s | pnl_sol | exit_reason | ml |
|---:|---|---:|---:|---|---:|
| 7649 | BppgpQ2wA2kL | 0.85 | +0.5852 | staged_tp_+1000% | 36.6 |
| 7650 | DSmnAsq8AuWz | 1.57 | +1.2701 | staged_tp_+1000% | 59.7 |
| 7641 | 9LrRnATAXPa8 | 600.96 | +0.1451 | TRAILING_STOP | 33.5 |
| 7679 | FTPCKSeTZaX1 | 600.97 | +0.1440 | TRAILING_STOP | 66.0 |
| 7678 | AFE8G6aUdjY6 | 601.47 | +0.1265 | TRAILING_STOP | 38.1 |
| 7642 | 9wQBQVsG2VD7 | 601.48 | +0.1944 | TRAILING_STOP | 32.8 |
| 7682 | 8JmU1rycpTgB | 601.68 | +0.1338 | TRAILING_STOP | 35.2 |
| 7572 | AibGvoSZ6J7j | 601.84 | +0.2158 | TRAILING_STOP | 37.8 |
| 7663 | FnkXHUxBGMR7 | 601.88 | +0.1864 | TRAILING_STOP | 67.4 |
| 7662 | EP7obgTWxKn7 | 602.18 | +0.1336 | TRAILING_STOP | 80.7 |
| 7653 | HzoWfch39eVJ | 602.20 | +0.1276 | TRAILING_STOP | 73.0 |
| 7550 | HLBmKECRR2cN | 602.49 | +0.2235 | TRAILING_STOP | 36.1 |
| 7659 | 4Hko5Q3euQiq | 602.73 | +0.1730 | TRAILING_STOP | 35.6 |

**13 big winners total. None in the 50-90s kill window:**
- 2 hit `staged_tp_+1000%` at <2s — rocket starters, immune to the check (it requires hold > 50s)
- 11 hit `TRAILING_STOP` at ~600s — they survived the 50-90s no_momentum window, meaning they had pnl_pct ≥ 3.0% by the time the check evaluated

**Implication:** The check is currently *not* killing big winners. Any big winner that reaches 600s necessarily passed the 50-90s gate with sufficient momentum.

---

## §5 Decisive empirical: dead trades' pnl_pct distribution (CRITICAL)

This is the data that flips the verdict from Option Alpha (the prompt's recommendation) to Option Gamma.

What was the gross `pnl_pct = (exit_price/entry_price - 1) × 100` of the 123 dead trades at exit? If they were "slow starters" near the 3% threshold, Alpha-A relaxation could save them. If they were deeply negative, no relaxation helps.

| pnl band | n | min_pct | max_pct | sum_pnl |
|---|---:|---:|---:|---:|
| A: <-20% (already past stop_loss threshold) | 39 | -39.15 | -20.05 | -1.97 |
| B: -20 to -10% (deeply negative) | 61 | -19.81 | -10.04 | -0.82 |
| C: -10 to -3% (moderately negative) | 22 | -9.85 | -4.13 | -0.13 |
| D: -3 to 0% (mildly negative) | 1 | -1.85 | -1.85 | -0.002 |
| E: 0-1% (would survive Alpha-A) | **0** | — | — | — |
| F: 1-3% (slow starter — Alpha-A target) | **0** | — | — | — |

**Summary statistics (gross pnl_pct):**
- n=123, mean = **-17.37%**, median = **-16.12%**, min = **-39.15%**, max = **-1.85%**
- Slow-starters (1-3%, would survive Alpha-A): **0**
- Deeply negative (<-10%): **100** (81% of population)
- Pre-stop-loss (<-20% but escaped early — likely no price tick yet): **39**

**This is the smoking gun.** The dead-trade population is not slow starters — they're already failed-momentum tokens. The maximum pnl_pct of any dead trade is -1.85%; even the "best" of them was below break-even.

**Implications by lever:**
- **Alpha-A** (drop `SD_EARLY_MIN_MOVE_PCT` 3.0 → 1.0): saves 0 trades. Every dead trade is at ≤ -1.85%, all below 1%.
- **Alpha-B** (raise `SD_EARLY_CHECK_SECONDS` 60 → 180): just delays exit. These tokens are at -17% mean; they're not recovering with 90 more seconds of hold.
- **Beta** (code change to disable the check): 39 trades would convert to `stop_loss_20%` (already past -20%). 84 would continue bleeding — some to stop_loss, some to stale_no_price. Net effect: bleed redistribution, likely worse total cost per CLAUDE.md FEE-MODEL note (-0.024/trade no_momentum vs typical -0.074/trade stop_loss).
- **Gamma** (no change): -2.915 SOL bleed continues. But the trades aren't almost-winners — they're real losses being efficiently truncated.

---

## §6 Entry MC distribution (cross-reference with 4-day audit §5)

| MC band | n | sum_pnl |
|---|---:|---:|
| <$800 (winner zone per 4-day audit) | 0 | 0 |
| $800-$3000 | **120** | -2.730 |
| $3000-$10000 | 3 | -0.185 |
| >$10000 | 0 | 0 |

**97.6% (120/123) of dead trades enter at MC $800-$3000.** This corroborates the 4-day audit §5 finding that `no_momentum_90s` median entry MC was $2,609 — ground-truth on this 35h sample.

**Session C (`SD_MC_CEILING_USD=3000`) will only filter 3/123 of these dead trades** because the bleed is concentrated below the ceiling. Most of the bleed remains. To fully cut this bleed at the entry filter, the ceiling would need to be ~$800 — but the 4-day audit shows winners also enter at $800-$3000, so a sharp cutoff there would lose winners.

This is a known structural problem and out of scope for this session. The right place to address it is **deferring** until Sessions B/C/D + observation provide more data.

---

## §7 Bonus — full post-recovery exit-reason mix

For context. Post-recovery SD totals: n=244, sum_pnl=+0.140 SOL, wins=57 (23.4% WR).

| exit_reason | n | sum_pnl | wins | mean_hold |
|---|---:|---:|---:|---:|
| no_momentum_90s | 123 | -2.915 | 0 | 50.97 |
| TRAILING_STOP | 69 | +2.794 | 55 | 601.73 |
| stop_loss_20% | 34 | -1.465 | 0 | 1.04 |
| stale_no_price | 16 | -0.129 | 0 | 611.75 |
| staged_tp_+1000% | 2 | +1.855 | 2 | 1.21 |

**Notes:**
- `stop_loss_20%` triggers at mean hold 1.04s — these are tokens that dump 20% within 1 second of entry. **Different population from `no_momentum_90s` (mean hold 51s).** The two exit reasons are not interchangeable; relaxing no_momentum doesn't simply convert these into stop_loss exits.
- `stale_no_price` at mean hold 612s — the natural alternative exit if no_momentum is disabled. -0.008 SOL/trade vs no_momentum's -0.024/trade. Cheaper but not free.
- `TRAILING_STOP` is the dominant winner channel at 79% of wins (55/57).

---

## §8 Change applied

**None.** No env-var change. No code change. No git commit beyond this audit + STATUS + ROADMAP.

---

## §9 Deploy verification

**N/A.** Skipped per Option Gamma (no deploy).

---

## §10 24h verification queued — what to track

The session does NOT redeploy, but the bleed is real and Sessions B/C/D may shift the population. Queue for re-evaluation after Session E + 24-48h observation:

1. **Has Session C (SD_MC_CEILING_USD=3000) reduced the no_momentum bleed?** Expected: only 3/123 of current bleed comes from MC > $3000 entries, so the bleed should shrink ~2-3% if everything else holds.
2. **Did the mean exit pnl_pct of dead trades shift?** If post-Session-C survivors are a different population (higher quality, lower MC), they might recover. Current mean -17.37% — if it moves toward 0%, the relaxation hypothesis becomes worth re-testing.
3. **Did winners' hold-time distribution change?** If some winners now appear in the 50-90s window with low pnl, the relaxation case strengthens.
4. **Did the absolute bleed amount change?** Post-recovery 35h showed -2.915 SOL on 123 trades. If this drops below -1.0 SOL on equivalent volume, the issue may be self-resolving via Session C.

Add a tracking marker to STATUS at next session's read.

---

## §11 Reproducibility

```python
# Step 2/3/5 queries — see .tmp_sd_early_check_relax/query.py and query2.py (gitignored)
RECOVERY_EPOCH = 1777384800.0  # 2026-04-28 13:00:00 UTC
DSN = "postgresql://postgres:<REDACTED>@gondola.proxy.rlwy.net:29062/railway"

# Mechanism location:
# services/bot_core.py:1590-1604 (get via Grep "SD_EARLY_CHECK_SECONDS")

# Production env (per ENV_AUDIT_2026_04_29.md §2.2):
#   bot_core SD_EARLY_CHECK_SECONDS = 60
#   bot_core SD_EARLY_MIN_MOVE_PCT  = 3.0
```

---

## §12 Footnote — what would change the verdict

I would revisit Alpha-A or Alpha-B if any of the following held:

1. The dead-trade pnl_pct distribution shifted to include a non-trivial slow-starter band (≥10% of trades in 1-3% range).
2. A direct measurement showed that current `no_momentum_90s` exits would have recovered to ≥+5% with 90 more seconds of hold (would require shadow-measure instrumentation; FEE-MODEL-001-style).
3. Post-Session-C, the bleed remains > -1.5 SOL on equivalent volume AND the dead-trade pnl distribution moved up.

None of these are true at audit time. Re-test after observation window.
