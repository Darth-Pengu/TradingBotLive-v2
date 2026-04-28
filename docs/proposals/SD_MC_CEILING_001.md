# SD_MC_CEILING_001 — Speed Demon: Cap entries at $5,000 MC

**Status:** Proposed
**Created:** 2026-04-28 (LEARNINGS-CAPTURE-2026-04-28)
**Motivating audit:** `docs/audits/PAPER_TRADES_4DAY_ANALYSIS_2026_04_28.md` §5
**Group:** TUNE-006 (stack with SD_DEAD_ZONE_001 + SD_ML_THRESHOLD_LIFT_001)
**Estimated effort:** 15 min code + 24h paper observation

---

## Problem statement

Of 528 Speed Demon paper trades over the 4-day window 2026-04-22 →
2026-04-25, **77 (14.6%) exited via `stop_loss_20%`** and lost a combined
**-5.714 SOL** (median per-trade loss -0.056 SOL, median %loss -69.5%).
The median entry market cap of these losers was **$7,749**.

By contrast, the 269 trailing-stop winners (+11.311 SOL combined) had a
median entry MC of **$664** — more than 10× lower.

Of the 77 stop-out trades, **58 had entry MC > $5,000 with combined PnL
of -4.761 SOL.** Cutting these would reclaim ~83% of the stop-loss leak
without affecting the trailing-stop winners (which all entered at
sub-$1k MC).

**Speed Demon's edge is at the bottom of the MC range; mid-range MC
entries are net-negative.** This is consistent with the strategy
thesis: ultra-low-MC tokens have asymmetric upside (the +2.375 SOL /
+4846% biggest winner was a sub-$200 MC entry); higher-MC entries are
tokens that already had their move and are now distributing.

Total SD PnL split by MC band (4-day paper):

| MC band | Trades | Total PnL |
|---------|-------:|----------:|
| Entry MC ≤ $5,000 | 467 | **+14.167 SOL** |
| Entry MC > $5,000 |  61 | **-4.899 SOL** |

The MC > $5k segment is a clean negative-EV pocket. Closing it is the
single largest available paper-mode win.

---

## Proposal

Add a new env var **`SD_MC_CEILING_USD`** (default `5000.0`). At
entry-time in `services/signal_aggregator.py`'s Speed Demon branch,
reject any signal whose `market_cap_usd` at evaluation is above the
ceiling.

Pseudocode (location: SD entry gate in signal_aggregator):

```python
SD_MC_CEILING_USD = float(os.environ.get("SD_MC_CEILING_USD", "5000.0"))

# Inside SD entry gate, after existing rugcheck/ML filters:
mc_at_eval = features.get("market_cap_usd", 0.0)
if mc_at_eval > SD_MC_CEILING_USD:
    logger.info(
        "SD reject %s: MC %.0f > ceiling %.0f",
        mint[:8], mc_at_eval, SD_MC_CEILING_USD,
    )
    return None  # use existing reject path
```

The exact location depends on where the SD-specific gate currently
sits. Verify against `services/signal_aggregator.py` before writing
the patch.

---

## Expected impact (4-day window)

| Metric | Current | With ceiling | Δ |
|--------|--------:|-------------:|---:|
| Speed Demon PnL | +9.269 SOL | ~+13.0-+14.2 SOL | +3.7 to +4.9 SOL |
| Speed Demon trades | 528 | ~467 | -11.6% |
| Speed Demon WR | 44.9% | ~47-49% | +2 to +4 pp |

The 61-trade volume drop comes entirely from MC>$5k entries, which
combined for -4.899 SOL. **Reclaiming this is the headline win.**

---

## Risks

1. **Some legitimate winners enter at $5-7k MC.** The
   `BITFOOT_2026_BASELINE_2026_04_23.md` "missed_2x" examples
   included some MC>$5k tokens. We accept this trade-off — the
   wins forgone are smaller in aggregate than the losses avoided
   (in the 4-day data, MC>$5k is net -4.9 SOL across all exit
   reasons, not just stop-outs).
2. **MC measurement freshness.** The signal_aggregator's
   `market_cap_usd` feature comes from the enrichment pipeline; on
   fast-moving tokens it can lag actual entry-time MC by tens of
   seconds. If a token spikes from $4k → $8k between feature compute
   and trade execution, the bot enters at $8k despite the gate not
   firing. Mitigate by adding a freshness check: only apply the gate
   when the MC feature is ≤30s old.
3. **Sample limitation.** 4 days, 528 SD trades, single market regime
   (April 22-25). The MC×exit-reason pattern is consistent and large
   in magnitude, but a 2-week post-deploy review is warranted.
4. **Ceiling is a single linear cut.** A more sophisticated approach
   would model MC × ML score interaction (e.g., allow $5-10k MC entries
   if ML > 70). This proposal keeps it simple — one knob, one default.
   Per-cohort tuning is out of scope here and tracked under future
   work.

---

## Success criteria (measure 24h after deploy)

1. **Zero new `stop_loss_20%` exits with `market_cap_at_entry` > $5,000.**
   This is the deterministic correctness check — if any such trade fires,
   the gate is broken.
2. **Speed Demon `TRAILING_STOP` fraction stays ≥45% of exits.** Confirms
   we haven't accidentally filtered out the winning regime.
3. **Speed Demon WR ≥ 47% over the 24h window.** Confirms positive
   directional impact.
4. **Speed Demon trade count between -10% and -20% of the pre-deploy
   baseline.** Confirms volume reduction is in the expected band — not
   too aggressive (gate over-firing) or too passive (gate not firing).

If all four hold, the gate is performing as expected. If (1) fires
even once, halt and investigate the freshness path. If (2)-(4) miss,
re-run the audit against the next 4-day window to check for regime
shift before tuning the ceiling.

---

## Roll-back

Set `SD_MC_CEILING_USD=999999999` on signal_aggregator. Single env var,
no code change needed. Roll-back is instant (env var change triggers
auto-redeploy ~90s).

---

## Implementation effort

- **Code:** ~15 minutes (add env var read, gate check, info log)
- **Compile check:** `python -m py_compile services/signal_aggregator.py`
- **Deploy:** `git push` (Railway auto-deploys signal_aggregator)
- **Observation:** 24h paper window
- **Total:** 1 session of ~30-45 min including STATUS.md update

---

## Stacking with other TUNE-006 proposals

This proposal stacks cleanly with:

- **SD_DEAD_ZONE_001** — pauses 18-21 AEDT entries. Independent gate;
  no overlap.
- **SD_ML_THRESHOLD_LIFT_001** — lifts ML floor 40 → 50. Most
  high-MC trades cluster in mid-ML-score bands, so there is some
  overlap (a token rejected by ML 50 may also have been rejected
  by MC 5k). Stacked impact is sub-additive but still positive.

Combined estimated 4-day net effect (paper, vs current +9.27 baseline):
**+12.5 to +13.5 SOL** — see audit §10 caveats on absolute magnitudes.

---

## Out of scope for this proposal

- Per-personality ceiling differentiation (Analyst is hard-disabled)
- Dynamic ceiling tied to SOL price or CFGI
- MC×ML interaction models
- Live-mode ceiling (separate session — live needs different
  validation)
- Backfill simulation against historical paper data older than 4 days
