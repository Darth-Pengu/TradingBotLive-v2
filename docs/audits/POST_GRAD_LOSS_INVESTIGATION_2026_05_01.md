# POST-GRAD-LOSS-INVESTIGATION-001 — Audit (2026-05-01)

> Session 3 of 6 in chained-prompt sequence. Investigation only — no code or env changes.

## §1 Executive summary

**Verdict: H2 REFUTED in original framing → reveals the REAL bleed source.** The bot's `graduation_*` exit reasons aren't from "tokens carrying through graduation" — they're from **the bot ENTERING already-graduated tokens (`bonding_curve_progress = 1.0` at entry)**. 145 of 145 `graduation_stop_loss` exits + 79/79 `graduation_time_exit` + 56/56 `graduation_tp_30pct` over 14d had bc=1.0 AT ENTRY.

**Total attributable SOL (last 14d, post-grad-entry trades):** −14.60 SOL on 280 trades (≈ **−7.3 SOL/week**). Roughly half of the −12.09 SOL/7d figure surfaced in STATE-RECONCILE; the 14d window picks up more sample. Either window confirms post-grad-entry as a structural bleed.

**Recommended #1 patch (PATCH A):** Gate out post-grad SD entries at `signal_aggregator` — reject SD signals where `features.bonding_curve_progress >= 0.99` (or 1.0). Single conditional, env-tunable threshold. Estimated ROI: **+7 SOL/week** (eliminates −7.3 bleed, loses small +0.45/14d upside from `graduation_tp_30pct`). Cost: S.

Investigation revealed two additional concerns worth tracking separately:
- `no_momentum_90s`: −8.48 SOL/14d on 423 trades — pre-grad, separate from the post-grad bleed. Tracked as `NO-MOMENTUM-90S-AUDIT-001`.
- Observability gap: `trailing_stop_active` is transient state (resets at exit). Tracked as `OBS-TRAIL-ENGAGEMENT-001`.

## §2 Hypothesis tests

### H1 — Threshold tightness

**Hypothesis:** stop_loss_20% fires too tight; many tokens recover above breakeven shortly after.

**Method:** Direct test (post-exit price recovery) requires data we don't have. Indirect: among TRAILING_STOP winners, how many exited below entry × 0.8 (drew past −20% before exit fired)?

**Query:**
```sql
SELECT
  COUNT(*) AS total_trail_winners,
  COUNT(*) FILTER (WHERE exit_price < entry_price * 0.8) AS exit_below_neg_20pct,
  ROUND(100.0 * COUNT(*) FILTER (WHERE exit_price < entry_price * 0.8) / NULLIF(COUNT(*),0)::numeric, 1) AS pct_below_neg_20
FROM paper_trades
WHERE exit_reason='TRAILING_STOP'
  AND COALESCE(corrected_pnl_sol, realised_pnl_sol) > 0
  AND entry_time > extract(epoch from NOW() - INTERVAL '14 days')
```

**Result (14d):** 300 TRAILING_STOP winners; 58 (19.3%) exited below entry × 0.8.

H1b counterpart (do stop_loss_20% rows have peak above entry?) — **UNTESTABLE**: `peak_price` is NULL on every stop_loss_20% row in the 14d window (peak_price not populated when trade fails to rise above entry).

**Verdict: PARTIAL.** 19.3% of winners drew past −20% before recovering — but stop_loss_20% has 0% trail_active rate (per H5), suggesting these stop_loss_20% rows are different trades that never showed upside, not amputated winners. The "stop_loss_20% amputates winners" thesis cannot be confirmed nor refuted from current data. Patch path: lower trail-stop activation OR widen stop_loss_20% — both are speculative absent more data. Adding intra-hold drawdown tracking would resolve this.

### H5 — Exit ordering

**Hypothesis:** stop_loss_20% fires before TRAILING_STOP has a chance to engage.

**Query:**
```sql
SELECT exit_reason, COUNT(*) AS n,
  SUM(CASE WHEN trailing_stop_active THEN 1 ELSE 0 END) AS n_trail_active,
  ROUND(100.0 * AVG(CASE WHEN trailing_stop_active THEN 1 ELSE 0 END)::numeric, 1) AS pct_trail_active
FROM paper_trades
WHERE entry_time > extract(epoch from NOW() - INTERVAL '14 days')
GROUP BY 1 ORDER BY n DESC
```

**Result (14d):**
- `stop_loss_20%`: 0/119 = **0.0%** trail_active
- `TRAILING_STOP`: 80/379 = 21.1% trail_active
- `graduation_stop_loss`: 5/145 = 3.4%
- `no_momentum_90s`: 0/423 = 0.0%

**Caveat:** `trailing_stop_active` is transient state — it gets reset (or never set) at exit. The 0% on stop_loss_20% rows could mean (a) trail never engaged OR (b) state was reset before write. The 21% on TRAILING_STOP rows confirms (b) — even when trail FIRES, the boolean only shows True for ~21% of rows.

**Verdict: UNTESTABLE.** The column doesn't carry the semantics required for this test. Indirect inference from 0% on stop_loss_20% is consistent with both "trail never engaged" and "state reset" — can't disambiguate without `trail_was_engaged: BOOLEAN` (sticky once True) column. Patch path "lower trail activation threshold" remains plausible but unsupported by this analysis. Tracked as `OBS-TRAIL-ENGAGEMENT-001`.

### H2 — Carry past graduation (REFUTED in original framing)

**Hypothesis:** Tokens entered pre-grad carry into post-grad regime; stop-loss fires post-graduation.

**Query:**
```sql
SELECT exit_reason,
  COUNT(*) AS n,
  ROUND(AVG(NULLIF((features_json::jsonb->>'bonding_curve_progress')::float, NULL))::numeric, 3) AS avg_bc_entry,
  COUNT(*) FILTER (WHERE (features_json::jsonb->>'bonding_curve_progress')::float >= 1.0) AS pre_already_grad
FROM paper_trades
WHERE exit_reason IN ('graduation_stop_loss','graduation_time_exit','graduation_tp_30pct',
                     'stop_loss_20%','TRAILING_STOP','no_momentum_90s')
  AND entry_time > extract(epoch from NOW() - INTERVAL '14 days')
  AND features_json IS NOT NULL
GROUP BY 1
```

**Result (14d):**
- `graduation_stop_loss`: 145/145 entries had bc=1.0 at entry → **all post-grad-ENTRY**
- `graduation_time_exit`: 79/79 had bc=1.0 → all post-grad-entry
- `graduation_tp_30pct`: 56/56 had bc=1.0 → all post-grad-entry
- `TRAILING_STOP`: 3/379 had bc=1.0 → 99% pre-grad-entry
- `no_momentum_90s`: 0/422 had bc=1.0 → 100% pre-grad-entry
- `stop_loss_20%`: 1/119 had bc=1.0 → 99% pre-grad-entry

**Verdict: REFUTED in original framing.** Tokens didn't "carry past graduation". The bot has a SEPARATE post-grad strategy (entries at bc=1.0 with `graduation_*` exit reasons), and that strategy is bleeding. The original H2 patch path (don't carry through graduation) doesn't apply. **The actionable patch is to gate out post-grad ENTRIES entirely (PATCH A).**

### H4 — Adverse selection on slow signals

**Hypothesis:** Tokens that survive long enough to graduate already attract enough volume that the bot's edge is gone.

**Query:**
```sql
SELECT exit_reason, COUNT(*) AS n,
  ROUND(AVG(hold_seconds)::numeric, 1) AS avg_hold_s,
  ROUND(SUM(COALESCE(corrected_pnl_sol, realised_pnl_sol))::numeric, 2) AS total_pnl
FROM paper_trades
WHERE entry_time > extract(epoch from NOW() - INTERVAL '14 days')
  AND hold_seconds IS NOT NULL
GROUP BY 1 ORDER BY avg_hold_s DESC
```

**Result (14d):**
- TRAILING_STOP winners: avg 600.5s (10 min)
- graduation_time_exit: avg 1273.2s (21 min!) — but these are post-grad ENTRIES timing out, not adverse selection on slow signals
- graduation_stop_loss: avg 87.7s — fast post-grad failures
- no_momentum_90s: avg 51s (90s exit-trigger by design, exits at 50-54s due to 2s eval interval)
- stop_loss_20%: avg 15.6s — very fast pre-grad drops
- staged_tp_+1000%: avg 0.7s — instant on-the-flop wins

**Verdict: REFUTED.** The hold-time patterns reflect strategy timeouts (graduation_time_exit's 1273s is the configured max-hold; no_momentum_90s's 51s is the configured 90s with 2s eval), not "adverse selection on slow signals". The original adverse-selection thesis doesn't apply to current data.

### H3 — Pricing artifact (Skipped)

**Verdict: UNTESTABLE this session.** Paper rows have synthetic `PAPER_xxxx` signatures; no on-chain transactions to query. Live mode rows (id 6580 only) require LIVE-FEE-CAPTURE-002 (Path B Helius parseTransactions) to land first; queued for Session 5.

## §3 Synthesis

(see `.tmp_post_grad_investigation/synthesis.md` for the full version; key points reproduced below)

**The bleed source is post-grad ENTRIES, not carry-through-graduation.** The bot has a post-grad strategy (entries at bc=1.0 with graduation_* exit family) that is structurally losing in current market: **−14.60 SOL on 280 trades / 14d (~−7.3 SOL/week)**.

**Top 3 patch paths:**
- **A — gate out post-grad SD entries** (PROPOSED, S, +7 SOL/week ROI)
- **B — `no_momentum_90s` audit** (PROPOSED, M, ROI uncertain pending investigation)
- **C — trail-engagement column** (PROPOSED, S, observability only)

## §4 Patch path proposals

### PATCH A — Gate out post-grad SD entries

- **File(s):** `services/signal_aggregator.py` — add a single conditional in the SD entry filter
- **Implementation cost:** S (single env-tunable conditional, mirroring SD_MC_CEILING gate pattern)
- **Estimated ROI:** **~+7 SOL/week** (eliminates −7.3 bleed, costs +0.45/14d=+0.23/week from `graduation_tp_30pct` upside)
- **Verification approach:** `verify_post_grad_patch_a.py` post-deploy:
  - Count `graduation_*` exits in 7d window pre vs post-deploy → expect ~95%+ drop
  - Total SD bleed reduces by ~7 SOL/week
  - SD trade throughput stays ≥ 30/day (otherwise gate is too aggressive)
- **STOP conditions for the patch session:**
  - SD trade count drops below 30/day post-gate (loses too much throughput)
  - The +0.45 SOL upside from `graduation_tp_30pct` had hidden value not captured here
  - bc_progress field reliability issue (verify-fields-before-coding via 100-row sample)
- **Dependencies:** None (independent of other Session 4-6 work)
- **Roadmap entry:** `POST-GRAD-ENTRY-GATE-001` Tier 1 🔴 PROPOSED

### PATCH B — `no_momentum_90s` audit

- **File(s):** TBD — likely `services/bot_core.py` (exit logic) and/or `services/signal_aggregator.py` (entry filter)
- **Implementation cost:** **M** — separate audit needed first (signal quality vs exit-timer tuning)
- **Estimated ROI:** Uncertain — could be 0 (signal quality issue, exit timing isn't the bug) or up to +4 SOL/week if exit-timer tuning helps
- **Verification approach:** dependent on patch chosen post-audit
- **STOP conditions:** sample insufficient; complete pre-grad-only re-analysis first
- **Dependencies:** None
- **Roadmap entry:** `NO-MOMENTUM-90S-AUDIT-001` Tier 1 🟡 PROPOSED (audit first, then decide)

### PATCH C — Trail-engagement tracking column

- **File(s):** `services/bot_core.py` (set the field), `paper_trader.py` if applicable, schema migration to add `trail_was_engaged: BOOLEAN DEFAULT FALSE`
- **Implementation cost:** S
- **Estimated ROI:** Zero direct; enables future H1/H5 retest with proper semantics
- **Roadmap entry:** `OBS-TRAIL-ENGAGEMENT-001` Tier 2 🟢 PROPOSED

## §5 Observability gaps to add to roadmap

1. **`OBS-TRAIL-ENGAGEMENT-001`** — `trailing_stop_active` semantics inadequate for backward analysis. Need a sticky `trail_was_engaged: BOOLEAN`. Tier 2 🟢 LOW.

2. **`OBS-INTRA-HOLD-DRAWDOWN-001`** — `peak_price` is high-water; no `min_price_during_hold` (low-water). Adding it would let us answer "did stop_loss_20% amputate winners" directly. Tier 2 🟢 LOW.

3. **`OBS-EXIT-TIME-BC-PROGRESS-001`** — features_json captured at entry only. If we ever need to detect tokens that DO carry through graduation in future, we need exit-time bc_progress capture. Tier 2 🟢 LOW (current data shows no such carry-through case).

4. **`NO-MOMENTUM-90S-AUDIT-001`** — pin down threshold and trigger logic; may be the largest tractable win after PATCH A. Tier 1 🟡 MEDIUM.

## §6 STOP conditions hit

None. Per session §6:
- ✗ §2 H1 / H5 (cheapest tests) both UNTESTABLE — H1 returned a PARTIAL signal (19.3% of winners drew past −20%); H5 was untestable as designed but indirect signal preserved. Investigation NOT a wash.
- ✗ DB connectivity issues: 0
- ✗ Single hypothesis runtime > 15 min: longest was schema_probe.py at < 30s
- ✗ §3 cannot identify highest-ROI patch with non-trivial impact: PATCH A at +7 SOL/week is well above 0.5 SOL/week threshold ✓

**Investigation completed within scope; no STOP triggered.**

## §7 Reproducibility

To re-run this analysis on a future date:

```bash
# 1. Set DATABASE_PUBLIC_URL env var (from Railway: railway variables -s Postgres --kv | grep DATABASE_PUBLIC_URL)
export DATABASE_PUBLIC_URL="postgresql://..."

# 2. Run the schema probe to confirm columns and feature populating
python .tmp_post_grad_investigation/schema_probe.py

# 3. Run all 5 hypothesis tests
python .tmp_post_grad_investigation/hypotheses.py

# 4. Compare outputs to .tmp_post_grad_investigation/hypotheses_output.txt for drift
```

Direction of finding (post-grad ENTRY = bleed source) is structural, not regime-dependent. Magnitudes will fluctuate with market mode and SD throughput.

## §8 Decision Log entry (mirrored to ZMN_ROADMAP.md)

```
2026-05-01 POST-GRAD-LOSS-INVESTIGATION-001 ✅ INVESTIGATION COMPLETE — Tested 5
hypotheses against the post-graduation bleed. Verdicts: H1 PARTIAL, H2 REFUTED
in original framing (REVEALS the real bleed: 280 post-grad-ENTRY trades sum
-14.60 SOL/14d), H3 SKIPPED, H4 REFUTED, H5 UNTESTABLE. Recommended patch:
POST-GRAD-ENTRY-GATE-001 (gate out SD signals where bonding_curve_progress >= 0.99).
Estimated ROI: ~+7 SOL/week. New roadmap items: POST-GRAD-ENTRY-GATE-001 (Tier 1),
NO-MOMENTUM-90S-AUDIT-001 (Tier 1, pending audit), OBS-TRAIL-ENGAGEMENT-001
(Tier 2), OBS-INTRA-HOLD-DRAWDOWN-001 (Tier 2), OBS-EXIT-TIME-BC-PROGRESS-001
(Tier 2). No code change this session.
```
