# TUNE-010 — `dex_paid` Feature Evaluation for Analyst / Whale Tracker

**Date:** 2026-04-30
**Session:** TUNE-010 (DEX-PAID-FEATURE-EVALUATION-2026-04-30)
**Type:** Read-only data study (no services touched, no env changes, no Redis writes)
**Verdict:** **DISCARD** for `dex_paid` (primary hypothesis); social/website features are near-misses but below deploy threshold

---

## TL;DR

Bitfoot Alpha Pings uses `dex_paid` (token has paid for DexScreener promotional placement) as a meta-signal in their token filters. We tested whether the same feature has signal for ZMN's **Analyst** (and **Whale Tracker**) personalities. Verdict: **DISCARD**.

- Sample: **304 Analyst closed trades** (2026-04-22 → 2026-04-28). Whale Tracker has zero historical trades — cannot evaluate.
- DexScreener `/orders/v1/{chainId}/{tokenAddress}` exposes `paymentTimestamp` per order/boost, enabling **timestamp-aware "paid AT entry time"** analysis (better than the current-state lookup the prompt envisioned).
- 318/318 mints looked up cleanly; 0 API errors.
- **`dex_paid_at_entry` shows the OPPOSITE of the hypothesis:** PAID tokens have **lower** WR (14.0%) than NOT_PAID (17.9%) — diff -3.83pp, fisher_p=0.43. Non-significant but inverted from Bitfoot's prior. Mean PnL/trade is essentially identical (-0.0495 vs -0.0496 SOL). The feature has zero discriminatory power for Analyst's PnL outcomes.
- **Base rate problem:** 76.6% of Analyst's tokens are dex_paid lifetime. A feature that is true for ¾ of the population can't discriminate well even with perfect signal — there's not enough variance to exploit.
- Best secondary feature (`social_count > 0`) shows +5.6pp WR diff but p=0.25; PnL/trade diff is +0.002 SOL — below all deploy thresholds.
- **0 of 14 SD big winners (≥0.10 SOL post-recovery) have any DexScreener footprint** — all have `no_pair=True`. Confirms Speed Demon enters and exits before any DEX promotion could exist; SD scope exclusion in the prompt was correct.

No deploy. No follow-up implementation prompt. The feature does not earn shelf space in `signal_aggregator.py`.

---

## §1 — Methodology

### Source API

**Chosen:** DexScreener
- `https://api.dexscreener.com/orders/v1/solana/{mint}` returns the **full timestamped history** of paid orders (tokenAd / tokenProfile / communityTakeover) with status (approved / cancelled / on-hold) AND boosts with paymentTimestamp + amount. The presence of `paymentTimestamp` per order is the critical methodological win — it lets us ask "was the token dex_paid AT the time the bot entered?", not just "is it dex_paid now?". This sidesteps the Step-4 Scenario A/B problem the prompt anticipated.
- `https://api.dexscreener.com/tokens/v1/solana/{mint}` returns the highest-liquidity pair's `info.socials` and `info.websites` for secondary features.
- Free, no auth, sufficient throughput at 5-concurrent + 100ms pacing.

**Birdeye (fallback)** not needed — DexScreener returned 0 errors on 318/318 mints.

### Sample

```sql
SELECT id, mint, personality, entry_time, exit_time,
       realised_pnl_sol, realised_pnl_pct, ml_score, market_cap_at_entry,
       hold_seconds, exit_reason, outcome
FROM paper_trades
WHERE personality IN ('analyst', 'whale_tracker')
  AND exit_time IS NOT NULL
ORDER BY entry_time DESC
```

| Personality | n_closed | Date range | WR | Total PnL |
|---|---:|---|---:|---:|
| analyst | 304 | 2026-04-22 → 2026-04-28 | 15.79% | -15.05 SOL |
| whale_tracker | **0** | — | — | — |

Whale Tracker is dormant (0 historical closed trades). Per Step 2 of the prompt's "If <50 rows for Whale Tracker" rule: **proceeded with Analyst only**. Sample size n=304 is well above the prompt's 100-trade threshold for valid statistical inference.

**Caveat on Analyst's sample:** all 304 trades are pre-disable (Analyst was hard-disabled at 2026-04-28 13:08 UTC via ANALYST-DISABLE-002). The 6-day window represents Analyst's behavior under one specific market regime. If Analyst is reactivated in a different regime, re-evaluation may be warranted.

### Statistical methodology

For each binary feature split (group A = feature_true, group B = feature_false):
- **Win rate (WR):** % of trades with `realised_pnl_sol > 0`
- **PnL stats:** mean, median, total, mean_pct
- **Win-rate test:** chi-square with continuity correction + Fisher's exact (always reported; Fisher's is the canonical for 2x2)
- **PnL distribution test:** Mann-Whitney U (non-parametric)
- **Effect sizes:** Cohen's h (proportion diff) and Cliff's delta (distribution diff)

Deploy thresholds (from prompt Step 5):
1. WR diff ≥ 8pp in favor of feature=true
2. PnL/trade diff ≥ +0.02 SOL/trade in favor of feature=true
3. p < 0.05 on at least one of WR or PnL test
4. n ≥ 30 in both groups
5. Doesn't require Scenario B exclusion (timestamp-aware methodology dodges this — always passes)

ALL must be true. Anything weaker is "interesting but not deploy-ready."

---

## §2 — Sample distribution

### Temporal validity (Step 4)

With timestamp-aware methodology, no Scenario A/B choice is needed. We report the distribution directly:

| State | n | % |
|---|---:|---:|
| dex_paid_at_entry (paid before bot's entry_time) | 164 | 53.9% |
| dex_paid_lifetime (any approved order or boost ever) | 233 | 76.6% |
| paid_post_entry_only (paid AFTER bot exited) | 69 | 22.7% |
| never paid | 71 | 23.4% |

**Key observation:** 76.6% of Analyst's tokens are paid lifetime. This is a high base rate — the feature is the norm, not the exception. A feature that is true for ¾ of the population provides limited discriminatory power even with perfect signal: there's not enough variance to exploit.

The 22.7% "paid post-entry only" subgroup is interesting — the team paid for promotion AFTER the bot was already in and out. This is consistent with the bot entering early (during initial pumpfun activity) and the team paying for promotion only after some traction.

---

## §3 — Statistical results (Step 5 — primary)

### Feature: `dex_paid_at_entry` (timestamp-aware)

| Group | n | WR | mean_pnl (SOL) | total_pnl (SOL) | mean_pnl_pct |
|---|---:|---:|---:|---:|---:|
| PAID_AT_ENTRY | 164 | 14.02% | -0.0495 | -8.12 | -19.0% |
| NOT_PAID | 140 | 17.86% | -0.0496 | -6.94 | +12.0% |

- **WR diff (PAID − NOT_PAID): -3.83 pp** ← inverted from hypothesis (PAID is worse)
- **Mean PnL diff: +0.0001 SOL/trade** ← essentially zero
- Win-rate test: chi2 = 0.571, chi_p = 0.4498, **fisher_p = 0.4306**, OR = 0.750
- PnL distribution test (Mann-Whitney U): u = 10842, **p = 0.4040**
- Cohen's h: -0.105 (below the 0.20 "small effect" threshold)
- Cliff's delta: -0.056 (well below the 0.147 "small effect" threshold)

**Interpretation:** the feature inverts vs Bitfoot's prior (paid is worse, not better, for Analyst), but the effect is non-significant and small. PnL outcomes are indistinguishable. mean_pnl_pct shows a curious split (-19.0% paid vs +12.0% not-paid) — driven by a few large-pct losers in the paid group; medians are far closer. Not a robust signal.

### Feature: `dex_paid_lifetime` (looser, regardless of timing)

| Group | n | WR | mean_pnl (SOL) | total_pnl (SOL) | mean_pnl_pct |
|---|---:|---:|---:|---:|---:|
| PAID_LIFETIME | 233 | 15.88% | -0.0487 | -11.34 | -12.1% |
| NEVER_PAID | 71 | 15.49% | -0.0523 | -3.72 | +19.4% |

- WR diff: +0.39 pp (negligible)
- Mean PnL diff: +0.0037 SOL/trade
- Win-rate test: fisher_p = 1.000 (literally identical proportions)
- Mann-Whitney U: p = 0.5082
- Cohen's h: +0.011, Cliff's delta: -0.052

Even looser definition shows no signal. Base rate is too high (76.6%) for the feature to discriminate.

---

## §4 — Secondary features (Step 6)

| Feature | n_A | n_B | WR_A | WR_B | WR diff (pp) | pnl diff (SOL/trade) | fisher_p | MWU_p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| social_count > 0 | 197 | 107 | 17.77% | 12.15% | **+5.62** | +0.0021 | 0.249 | 0.819 |
| website_present | 125 | 179 | 17.60% | 14.53% | +3.07 | +0.0005 | 0.524 | 0.890 |
| has_pair (DexScreener pair exists currently) | 235 | 69 | 16.60% | 13.04% | +3.55 | +0.0074 | 0.575 | 0.649 |
| team_active (paid OR socials OR website) | 233 | 71 | 15.88% | 15.49% | +0.39 | +0.0037 | 1.000 | 0.508 |

**Best secondary signal: `social_count > 0`** — 197 trades with at least one social link have WR 17.77% vs 12.15% for the 107 without (5.6pp difference). This is the largest WR gap of any feature tested AND it's directionally consistent with Bitfoot's "team marketing" intuition. But:
- p = 0.249 — not statistically significant
- PnL/trade diff = +0.0021 SOL — far below the 0.02 SOL/trade deploy threshold
- Cohen's h = 0.158 (below "small effect")
- Cliff's delta = -0.016 (essentially zero)

The WR gap exists but doesn't translate into meaningful PnL improvement, suggesting the few extra wins in the social group are small wins that don't change the trade-level economics.

`team_active` (the strongest combined signal — paid OR socials OR website) collapses back to the dex_paid_lifetime result because the union with paid (76.6% base) dominates. No combined signal emerges.

---

## §5 — Deploy threshold check

| Feature | WR diff ≥ 8pp | PnL diff ≥ +0.02 | p < 0.05 | n_min ≥ 30 | Pass? |
|---|:-:|:-:|:-:|:-:|:-:|
| dex_paid_at_entry | ❌ -3.83 | ❌ +0.0001 | ❌ 0.43 | ✅ 140 | **NO** |
| dex_paid_lifetime | ❌ +0.39 | ❌ +0.0037 | ❌ 1.00 | ✅ 71 | **NO** |
| social_count > 0 | ❌ +5.62 | ❌ +0.0021 | ❌ 0.25 | ✅ 107 | **NO** |
| website_present | ❌ +3.07 | ❌ +0.0005 | ❌ 0.52 | ✅ 125 | **NO** |
| team_active | ❌ +0.39 | ❌ +0.0037 | ❌ 1.00 | ✅ 71 | **NO** |

No feature passes any of the three quantitative thresholds simultaneously. dex_paid (the primary hypothesis) fails on direction (inverted), magnitude, and significance.

---

## §6 — SD big winners sanity check (Step 7)

The 14 Speed Demon trades with `realised_pnl_sol ≥ 0.10` post-recovery (entry_time > 2026-04-28 13:00 UTC):

| id | mint (prefix) | mc_at_entry | pnl_sol | hold_s | exit_reason | dex_paid_at_entry | dex_paid_lifetime | socials | website | no_pair |
|---:|---|---:|---:|---:|---|:-:|:-:|:-:|:-:|:-:|
| 7650 | DSmnAsq8AuWz... | 246 | +1.270 | 1.6 | staged_tp_+1000% | ❌ | ❌ | 0 | ❌ | ✅ |
| 7649 | BppgpQ2wA2kL... | 387 | +0.585 | 0.9 | staged_tp_+1000% | ❌ | ❌ | 0 | ❌ | ✅ |
| 7484 | 3uxLMKqWDeE5... | 776 | +0.500 | 1.1 | staged_tp_+500% | ❌ | ❌ | 0 | ❌ | ✅ |
| 7550 | HLBmKECRR2cN... | 461 | +0.224 | 602 | TRAILING_STOP | ❌ | ❌ | 0 | ❌ | ✅ |
| 7572 | AibGvoSZ6J7j... | 394 | +0.216 | 602 | TRAILING_STOP | ❌ | ❌ | 0 | ❌ | ✅ |
| 7642 | 9wQBQVsG2VD7... | 364 | +0.194 | 601 | TRAILING_STOP | ❌ | ❌ | 0 | ❌ | ✅ |
| 7663 | FnkXHUxBGMR7... | 425 | +0.186 | 602 | TRAILING_STOP | ❌ | ❌ | 0 | ❌ | ✅ |
| 7659 | 4Hko5Q3euQiq... | 381 | +0.173 | 603 | TRAILING_STOP | ❌ | ❌ | 0 | ❌ | ✅ |
| 7641 | 9LrRnATAXPa8... | 465 | +0.145 | 601 | TRAILING_STOP | ❌ | ❌ | 0 | ❌ | ✅ |
| 7679 | FTPCKSeTZaX1... | 426 | +0.144 | 601 | TRAILING_STOP | ❌ | ❌ | 0 | ❌ | ✅ |
| 7682 | 8JmU1rycpTgB... | 454 | +0.134 | 602 | TRAILING_STOP | ❌ | ❌ | 0 | ❌ | ✅ |
| 7662 | EP7obgTWxKn7... | 565 | +0.134 | 602 | TRAILING_STOP | ❌ | ❌ | 0 | ❌ | ✅ |
| 7653 | HzoWfch39eVJ... | 546 | +0.128 | 602 | TRAILING_STOP | ❌ | ❌ | 0 | ❌ | ✅ |
| 7678 | AFE8G6aUdjY6... | 366 | +0.127 | 601 | TRAILING_STOP | ❌ | ❌ | 0 | ❌ | ✅ |

**0 of 14 had any DexScreener footprint at all** — all have `no_pair=True`. These tokens never had a Raydium/Meteora pair created (or the pair was destroyed before our lookup). This is consistent with:
- Bot enters on pump.fun bonding curve at sub-$800 MC
- Token either rugs or fails to graduate to a Raydium pair
- No pair → no `info.websites`/`info.socials` → no opportunity for the team to pay for DexScreener promotion (paid promotion requires a pair to point at)

**Conclusion:** the prompt's SD scope exclusion was correct. SD's entry timing is so early that DexScreener as a data source has nothing to say about its winners. Even if `dex_paid` had signal for Analyst, it could not help SD.

---

## §7 — Verdict: **DISCARD**

The Bitfoot hypothesis ("paid promotion = team actively marketing = better outcomes") **does not transfer to ZMN's Analyst personality** in the 2026-04-22 → 2026-04-28 sample. Specifically:

1. **Direction:** `dex_paid_at_entry` shows WR -3.83pp (inverted from hypothesis). PnL diff is essentially zero. Direction inverted, magnitude trivial.
2. **Magnitude:** No feature passes the 8pp WR threshold. Best is `social_count > 0` at +5.62pp — still below.
3. **Significance:** No feature passes p < 0.05. Best is `social_count > 0` at p=0.249.
4. **Base-rate problem:** 76.6% of Analyst's tokens are paid lifetime. The feature is too prevalent in this population to discriminate even if it had signal. Bitfoot's filters operate on a different population (Solana ping channel) where base rates differ.
5. **SD irrelevance:** 0/14 SD big winners have any DexScreener footprint — feature can't help SD even hypothetically.

The signal Bitfoot reports may be real for their channel's token universe but doesn't reproduce on Analyst's pump.fun-discovered, pre-graduation token universe.

### What WOULD change the verdict

Re-evaluate TUNE-010 if:
- Analyst is reactivated and accumulates ≥200 new closed trades in a different market regime, AND the new sample shows a ≥+8pp WR difference for `dex_paid_at_entry` with p<0.05.
- A new personality (e.g., the planned ANALYST-POST-GRAD-001 rewrite at MC $50-300k) accumulates ≥200 trades. ANALYST-POST-GRAD-001 enters AFTER graduation when DEX-pair existence is the norm; that population could plausibly have non-trivial dex_paid variance and signal.
- Whale Tracker is reactivated and accumulates a meaningful sample.

For now: **closed**.

---

## §8 — What's NOT in this audit

- **No code changes.** No `signal_aggregator.py` edit. No env var. No Redis/DB writes.
- **No implementation prompt for follow-up.** Per prompt Step 8: the implementation outline section (§7 of the prompt) only applies to DEPLOY-* verdicts. DISCARD has no follow-up.
- **No re-run of TUNE-009 / TUNE-011** — separate sessions.
- **No analysis of `ml_score × dex_paid` interaction.** Could be a future evaluation if the feature is ever revisited; out of scope for a binary-feature DISCARD verdict.

---

## §9 — Operational notes

- DexScreener `/orders/v1/{chainId}/{tokenAddress}` is reliable and timestamp-aware. Future feature studies on DEX promo data should use this endpoint; the `info.boosts.active` field on `/latest/dex/tokens/{mint}` (referenced in the original prompt) does not exist in the current API shape.
- 318 mints in 180s wall time at 5-concurrent + 100ms pacing, 0 errors. The pacing was conservative; could go faster if needed.
- Temporary analysis files in `.tmp_tune010/`: `step2_data.json`, `step3_features.json`, `step5_results.json`, `sd_big_winners.json`, plus the Python scripts. Not committed; not deleted (kept for any future follow-up that wants to re-run analysis on the same sample).

---

## §10 — Audit metadata

- **Files committed:** this audit, `STATUS.md` prepend, `ZMN_ROADMAP.md` (TUNE-010 row added + changelog entry)
- **Lookup APIs called:** DexScreener (free, no auth) — 636 calls (2 per mint × 318 mints), 0 rate-limit triggers
- **Helius credits used:** 0 (read-only lookup against external API only)
- **Anthropic credits used:** 0 (no governance / LLM calls)
- **Total wall time:** ~3 min lookup + ~30 min analysis + audit writeup
- **Bot impact:** none (read-only against paper_trades and external API)
