# BITFOOT-2026-BASELINE — does the 2025 edge still exist in April 2026?

**Date:** 2026-04-23
**Verdict:** **BASELINE-A with strong caveats.** Bitfoot's 2-filter (top10 ≥30 + MC $50-300k) still picks a high-performing cluster in April 2026 trending data. But absolute hit rates are **substantially inflated by survivorship bias** in GT's trending_pools list. Directional edge: preserved. Magnitude: un-calibrated.
**Scope:** Measure whether Bitfoot's 2025-derived filter profile still concentrates winners on April 2026 Solana post-grad tokens. Complements yesterday's `session_outputs/bitfoot_analysis/BITFOOT_DIP_SAMPLE_DONE.md` (which showed Bitfoot labels are not reliable ground-truth).

---

## §1 Sample

| Item | Value |
|---|---|
| Source | GeckoTerminal `/networks/solana/trending_pools`, pages 1–10 (~200 pools) |
| Auth | `x-cg-demo-api-key` (CoinGecko Demo tier, existing `GECKOTERMINAL_API_KEY`) |
| Phase-1 filter | DEX ∈ {pumpswap, raydium, meteora-damm-v2}, `pool_created_at` ≤14 days ago, MC $20k–$500k |
| Phase-1 candidates | **42** (unique base_mints after dedupe) |
| Enrichment | Vybe `/v4/tokens/{mint}/top-holders` — summed `percentageOfSupplyHeld` for top 10 |
| Vybe base URL | `https://api.vybenetwork.xyz` (not `.com` — `CLAUDE.md` is wrong on this; `.com` 404s on every endpoint) |
| API cost | 0 credits (GT Demo free, Vybe free tier) |
| Date window | Pools with `pool_created_at` between 2026-04-10 and 2026-04-23 |
| DEX mix in phase-1 sample | pumpswap 33, meteora-damm-v2 9 (0 Raydium — notable) |

**Data-quality notes:**
- 100% of phase-1 candidates had non-null `market_cap_usd` from GT — no MC imputation needed.
- 100% of Vybe top-holders calls returned 200 (18 of 42 candidates had top-10 summing to valid values; no authentication failures).
- 0 × 401 or 429 on either API during the run.
- GT auth smoke tests per the 2026-04-23 dip-sample retry session (commit `e053448`) remained valid for this session.

## §2 Filter-match rate (selectivity)

The Bitfoot filter in 2025 had an estimated **~14% selectivity** on raw pings (from the roadmap entry for ANALYST-POST-GRAD-001). Applied to 2026 trending post-grad tokens:

| Filter variant | Passing | Rate |
|---|---:|---:|
| **2-filter (top10 ≥30 + MC $50–300k)** | **18 of 42** | **42.9%** |
| 3-filter (+ vol/MC <1.5) | 4 of 42 | 9.5% |

**Interpretation.** The 2-filter is **3× less selective on 2026 trending pools** than on 2025 raw pings (43% vs 14%). This is an artifact of the sampling frame, not a market-structure finding — `trending_pools` is GT's curated list of currently-active pools, already a heavily filtered subset. A Bitfoot-style gate over an already-trending population is less discriminating than the same gate over a broader raw pipe.

**Per-rule pass rates** (on the 42-candidate phase-1 set):

| Rule | Pass | Fail | Pass rate |
|---|---:|---:|---:|
| Top-10 ≥ 30% | 29 | 13 | 69% |
| MC $50k–$300k | 22 | 20 | 52% |
| Vol/MC < 1.5 (h24 proxy — see §7) | 5 | 37 | 12% |

The **vol/MC filter is the binding constraint**, but see §7 — it is **not directly comparable** between eras because 2025 measured *pre-graduation* turnover via Bitfoot channel visibility, and 2026 GT post-grad data only gives *post-graduation h24* activity. Kept as auxiliary, not primary.

## §3 Performance comparison

Computed peak multiple for each 2-filter-pass mint: reference price = open of first hourly candle ≥ `pool_created_at + 60s`; peak price = max(high) over forward window of up to 360 hours (GT's hourly OHLCV is capped at 720 candles = 30d but our candidates are all ≤14d old so window tops out at token age).

| Metric | 2025 baseline (from roadmap / dip-sample) | **2026 2-filter cohort (n=18)** | Delta |
|---|---|---|---|
| 2x+ hit rate | ~45% (per dip-sample revision) | **88.9% (16/18)** | ~2× higher |
| 5x+ hit rate | ~15–18% | **50.0% (9/18)** | ~3× higher |
| 10x+ hit rate | not called out separately | **44.4% (8/18)** | n/a |
| <0.5x (rug) rate | ~10% | **0.0% (0/18)** | zero observed |
| Median time-to-peak | 30 min (overall); 126 min (10–20x); 10 h (50–100x) | **33.3 h** (among 2x+ hitters, n=16) | anchor-difference — see §7 |
| Median MC (matched set) | $86k | **$95.9k** | within band |

### The 18 2-filter matches

| Name | t10% | MC ($k) | vol/MC h24 | Peak | TtP (h) | DEX |
|---|---:|---:|---:|---:|---:|---|
| ALIENPEPE | 33.8 | 117 | 7.07 | 1.68x | 2.0 | pumpswap |
| wif2 | 33.6 | 242 | 1.79 | 2.22x | 4.3 | pumpswap |
| WIngs | 79.4 | 159 | 353.9 | 2.87x | 43.5 | meteora-damm-v2 |
| BOY | 44.0 | 59 | 20.57 | 3.15x | 4.4 | pumpswap |
| NORMIE | 40.5 | 74 | 5.01 | **29.36x** | 23.0 | pumpswap |
| BRRR | 48.0 | 65 | 5.68 | 2.41x | 0.4 | meteora-damm-v2 |
| fsjal | 46.7 | 88 | 7.67 | 1.15x | 0.4 | meteora-damm-v2 |
| ?? | 57.3 | 102 | 1.03 | **26.23x** | 63.0 | meteora-damm-v2 (3-filter) |
| Nintondo | 34.1 | 173 | 2.08 | **33.44x** | 76.0 | pumpswap |
| RND | 56.7 | 82 | 5.91 | **17.39x** | 8.0 | pumpswap |
| ADHD | 39.3 | 56 | 7.99 | 3.73x | 3.7 | meteora-damm-v2 |
| AIRPUMP | 89.9 | 239 | 2.89 | 2.35x | 7.8 | pumpswap |
| roi | 33.8 | 238 | 1.38 | **25.61x** | 186.9 | meteora-damm-v2 (3-filter) |
| PVE | 52.6 | 124 | 3.34 | **18.10x** | 76.1 | pumpswap |
| ket | 36.7 | 61 | 6.07 | 2.47x | 7.1 | meteora-damm-v2 |
| FCS | 58.5 | 90 | 1.98 | **19.65x** | 55.3 | pumpswap |
| Rudi | 31.8 | 207 | 0.43 | 8.51x | 196.3 | pumpswap (3-filter) |
| Yuji | 41.2 | 66 | 0.56 | **13.87x** | 96.6 | meteora-damm-v2 (3-filter) |

3-filter subset (n=4): 100% 2x+, 75% 10x+, median peak 19.74x. Small-n confirmation that `vol/MC <1.5` on h24 still correlates with winners in our sample.

## §4 Verdict — **BASELINE-A (directionally), bias-inflated absolutely**

Under the spec's definitions:

- **BASELINE-A (edge persists, hit rates within ±20% of 2025):** 2026 2x+ hit rate 88.9% is 2× the 2025 baseline of ~45%. That is **way outside ±20%** — it's a 98% upward delta. The sign on the delta is wrong for a textbook BASELINE-A call.
- **BASELINE-B (edge weakened but positive, 30–60% lower):** No — 2026 is *higher*, not lower.
- **BASELINE-C (edge collapsed near generic baseline):** No — 2026 is far above the 2025 number, not near a generic null.
- **BASELINE-D (sample too small, <15 matches):** No — we have 18 matches (2-filter).

**None of the spec's canonical verdicts fits cleanly** because the spec assumed the 2026 sample would be a noisy/flat version of the 2025 distribution, not a higher version. The honest read:

> The Bitfoot 2-filter (top10 ≥30 + MC $50–300k) continues to concentrate winners in April 2026 trending post-grad data. 88.9% of matched mints hit 2x+ and 0% rugged in our 18-mint sample. **But this number is not ROI-usable.** The sampling frame (`trending_pools`) is itself a winner-filter: tokens that rugged are delisted from GT's index, tokens with no volume drop out of trending, and the list by construction selects survivors. The result is best read as "Bitfoot's filter CORRELATES with outperformance on the subset of 2026 tokens still actively traded and indexed." That is a directionally positive finding; it is not a claim about the 2026 rug rate (clearly not 0%) or the realizable ROI of a prospective strategy.

**Effective verdict: BASELINE-A directionally.** ANALYST-POST-GRAD-001 design can proceed on the assumption that the 2-filter still picks out relative winners. It CANNOT proceed on the assumption that 88.9% 2x+ is a forward-realizable hit rate.

## §5 Secondary findings

### §5a — Do the counterintuitive 2025 rules still hold?

| Rule | 2025 | 2026 (this session) | Verdict |
|---|---|---|---|
| Top-10 ≥ 30% outperforms <30% | Yes (32.2% vs 28.7% 2x hit rate) | **Consistent**: cannot test directly (we filtered to ≥30% in phase 2) but all 18 matches passed and 16 hit 2x+ | Not flipped. Not a clean re-validation either. |
| Vol/MC < 1.5 outperforms ≥1.5 | Yes (~35% vs ~18% 2x rate in 2025) | **3-filter subset (n=4, vol/MC h24 <1.5) peaks: 8.5x, 13.9x, 25.6x, 26.2x — all 2x+, 3 of 4 are 10x+.** Versus 2-filter-but-not-3-filter (n=14): 12 of 14 hit 2x+ (86%). **Rule still directionally right**, but caveat the eras-measure-different-things issue. | Not flipped. Weakly consistent. |
| Dex Paid 🔴 outperforms 🟢 | Yes (1.96x paid vs 2.79x unpaid mean peak in 2025) | **Cannot test** — GT does not expose `dex_paid` / `dex_status` on the trending endpoint. | Untested. |

No rule flipped; one (Dex Paid) was untestable.

### §5b — DEX mix shift — **real finding**

| DEX | 2025 (dataset) | 2026 (phase-1 sample of 42) | 2026 (2-filter pass of 18) |
|---|---:|---:|---:|
| PumpSwap | 51% | 33/42 = **79%** | 10/18 = 56% |
| Raydium | 39% | **0/42 = 0%** | 0/18 = 0% |
| Meteora | 10% | 9/42 = **21%** | 8/18 = **44%** |

**Two meaningful shifts:**
1. **Raydium is absent from 2026 post-grad trending pools.** In 2025, 39% of Bitfoot pings were Raydium; in our April-2026 sample it's 0 of 42. Pump.fun graduated tokens in 2025 routed via Raydium heavily; in 2026 the migration appears to be pumpswap-first-meteora-second. Not a rule flip, but a structural change in the post-grad LP market.
2. **Meteora is over-represented in the winner cohort.** 21% of phase-1 sample, 44% of 2-filter matches, and 4 of 8 the 10x+ winners. Meteora's DAMM v2 may have a share of the "concentrated holder + good performer" slice that's disproportionate. Small-n (n=9 → n=8); worth watching.

### §5c — Market-cap band shift — **no shift**

| Metric | 2025 | 2026 (2-filter) |
|---|---|---|
| Median MC | $86k | $95.9k |
| Min MC (matched) | $50k (filter floor) | $55.9k |
| Max MC (matched) | $300k (filter ceiling) | $241.9k |

2026 matched set sits inside the 2025 MC band. No bucket-drift. The $50–300k filter remains a live zone, not a dead one.

## §6 Implications for ANALYST-POST-GRAD-001

**Go/revise/pause verdict: PROCEED with revisions.**

1. **Proceed.** The directional edge is preserved — Bitfoot's top10 ≥30 + MC $50–300k 2-filter continues to correlate with outperformance in 2026 post-grad data. Design can use these as candidate entry gates.

2. **Revisions required.**
   - **Drop the `dex_paid` rule from the 2026 design** unless we wire up a DEX-paid signal source separately (not available on GT free tier, and the trending endpoint does not expose it). The 2025 "🔴 over 🟢" finding remains unvalidated in 2026 — don't rely on it.
   - **Drop "pre-graduation vol/MC < 1.5" as an entry gate.** 2025's version required pre-grad visibility via Bitfoot channel; we don't have that. A post-grad h24 vol/MC <1.5 proxy exists but measures a different phenomenon and binds on only 5 of 42 candidates (would reject most of the actual 2x+ hitters in our sample: NORMIE, Nintondo, RND, etc. all had h24 vol/MC > 1.5 but hit 10x+).
   - **Expect Meteora to be a meaningful share** of live-eligible candidates (44% in this sample vs 10% in the 2025 dataset). If the execution layer has DEX-specific limitations, verify Meteora routing works before enabling post-grad personalities.
   - **Do NOT use 88.9% as an expected 2x+ hit rate.** It's a biased-subset rate. For the design, assume the realized hit rate on prospectively-sampled (not-yet-trending) graduations will be substantially lower — somewhere between the dip-sample's 20.5% (biased toward non-winners) and this session's 88.9% (biased toward winners). A point estimate isn't defensible from either sample; set ROI expectations from the paper window, not the historical math.

3. **Measurements the live paper window must prospectively establish:**
   - Actual 2x+ hit rate on ALL matching pings (not trending-filtered, not retrospectively-curated).
   - Actual rug rate at the 2-filter gate (this session found 0/18, which cannot be forward-reality).
   - Time-to-peak distribution with a clean reference anchor (2025's "30 min median" vs this session's "33h median" likely reflects anchor drift — align the paper-window measurement to a consistent rule, e.g. "time from gate-pass to first 2x").

4. **Two pieces of 2026 structural evidence worth carrying into design:**
   - Raydium-graduated pump.fun tokens have vanished from the trending list. Don't allocate entry budget to Raydium for post-grad personalities unless the pipeline surfaces a specific pool there.
   - Meteora DAMM v2 is a bigger share of the winner slice than in 2025. Ensure Meteora is a first-class target in the execution layer.

## §7 Data quality + caveats

### The central bias
`trending_pools` is a curated list of tokens with **current activity and size**. Tokens that rugged or died within 14 days of graduation do not appear here — they're delisted from GT's index or drop out of trending rank. Our 42-candidate phase-1 set is therefore **already filtered for "still alive and being traded"**. This is the same survivorship-bias pattern that `BITFOOT_DIP_SAMPLE_DONE.md §8` identified yesterday, operating on a different axis (there: pools still indexed; here: pools still trending).

The 0 rugs in 18 matches is the single clearest bias tell: real Solana memecoin rug rates in first 14 days are typically high double-digits. Our sample cannot reflect that because GT de-curates the rugs.

### Vol/MC cross-era comparability
- 2025 Bitfoot: vol/MC measured **pre-graduation**, on the bonding-curve phase. Low pre-grad turnover correlated with later-outperformance. The Bitfoot channel provided pre-grad visibility via its Telegram signal.
- 2026 this session: vol/MC measured via GT h24 `volume_usd.h24 / market_cap_usd` at query time. Post-graduation activity over last 24h. Different phenomenon.
- Consequence: we cannot validate the 2025 vol/MC rule cross-era. Dropped from the primary filter; retained as auxiliary column only.

### Time-to-peak anchor
- 2025 baseline "median 30 min" anchored to Bitfoot ping timestamp (observed in real time as pings arrived).
- 2026 this session "median 33h" anchored to `pool_created_at + 60s` (graduation moment + 1-minute offset).
- These are different reference points. The 2026 anchor is earlier in the token lifecycle (at graduation) than a Bitfoot ping (which typically happened later as the ping triggered on volume/holder thresholds). 2026 therefore includes the full post-graduation run, which will naturally have later peaks than a mid-run ping.
- **Do not compare these medians directly.** The right cross-era comparison would be "time from signal-event to peak," but our 2026 signals are different events.

### Sample-size realism
- 18 matches (2-filter) vs spec BASELINE-D threshold of 15 — above the threshold, but at the low end of the meaningful range.
- 4 matches (3-filter) is too small for claims about vol/MC cross-era.
- The 10-page trending_pools coverage (~200 pools) is near the max — expanding to 15+ pages would likely not yield many new pools since GT caps pagination somewhere around 10 pages for most endpoints.

### What a cleaner replication would need
- **Prospective paper-mode monitoring.** Capture the gate-pass cohort as it happens over a 2–4 week window; measure outcomes without survivorship filtering. (This is BITFOOT-MONITOR-001 in the roadmap, tracked separately.)
- **Raw post-grad pipe access.** Direct Helius/PumpPortal-style feed of every graduation event (not GT's trending subset). Not zero-credit on most paid options.
- **Dex Paid signal source.** Separate integration if the `dex_paid` rule is to be revalidated.

### What this session can defensibly claim
- **The 2-filter Bitfoot gate still selects relatively-well-performing tokens** in 2026 post-grad trending data.
- **DEX mix has shifted:** Raydium absent, Meteora up.
- **MC band ($50–300k) remains live**, not drifted.
- **ROI numbers from this session are not forward-usable.** Both the 88.9% 2x+ rate and the 0% rug rate are bias-inflated; use them for directional signal only, not for sizing or go-live decisions.

---

## Session artifacts

- Sampling script: `.tmp_bitfoot2026/sample_2026.py` (local-only, gitignored)
- Results CSV: `.tmp_bitfoot2026/bitfoot2026_sample.csv` (local-only)
- Request log: `.tmp_bitfoot2026/bitfoot2026_sample.log` (local-only)
- Docs delta (committed): this file + `ZMN_ROADMAP.md` + `STATUS.md`

## Session ledger

- GT requests: 10 (trending pagination) + 18 (OHLCV per 2-filter match) = 28 total
- Vybe requests: 42 (top-holders per phase-1 candidate)
- 401 count: 0
- 429 count: 0
- Credits spent: 0 (both APIs free tier)
- Time to complete: ~12 min wall-clock (two runs — first 5-page probe at n=25 identified the 3-filter binding; second 10-page run at n=42 produced the landed numbers)

---

**One-line verdict:** BASELINE-A directionally — Bitfoot's 2-filter still picks winners in 2026 trending data (16 of 18 hit 2x+, 8 of 18 hit 10x+, 0 rugs) — but the 88.9% hit rate is survivorship-inflated and not forward-realizable; ANALYST-POST-GRAD-001 can proceed with revisions (drop dex_paid and pre-grad vol/MC gates; expect Meteora to be a meaningful share; calibrate ROI from live paper observation, not these numbers).
