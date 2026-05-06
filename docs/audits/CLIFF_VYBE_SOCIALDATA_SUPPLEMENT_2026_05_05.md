# Cliff Investigation Supplement — Vybe URL + SocialData Time-Correlation

**Session:** CLIFF-VYBE-SOCIALDATA-SUPPLEMENT-001
**Author:** Claude Code (read-only)
**Goal:** Time-correlate two cliff candidates (VYBE-URL-CODE-DRIFT-001, SocialData credit drain) against the 2026-04-21 cliff. Pure git+log+DB archeology.
**Predecessor:** STRATEGY-CLIFF-INVESTIGATION-001 (audit doc not committed; recommendation lives at `.tmp_cliff_investigation/recommendation.md`). Parent verdict: cliff is a fee-model accounting artifact, not a strategy regression. **DO NOT REVERT.**

---

## §1 Executive summary

| Candidate | Time-correlation verdict | Evidence |
|---|---|---|
| Vybe URL drift (`signal_aggregator.py:753, 850, 2568`) | **🔴 NOT CLIFF** — drift pre-dates cliff by 13-17 days | `git blame` shows all three `.com` URLs introduced 2026-04-04 to 2026-04-08; bot's +598 SOL pre-cliff era ran with broken Vybe URLs throughout |
| SocialData credit drain | **🔴 NOT CLIFF** — drain started 5 days before cliff | DB temporal pattern: `pct_sentinel` (twitter_followers=-1) jumped 18.7% → 99.2% on 2026-04-16; commit `35bdfe6` (2026-04-19) explicitly stated "495/495 of most-recent 500 SD paper trades have twitter_followers=-1" |

**Synthesis:** Both candidates **predate the cliff**. Both were broken during the bot's +598 SOL pre-cliff era. Neither is the cliff cause. Strong negative evidence: pre-cliff sentinel-bucket trades (n=2101, sum +485.37 SOL) outperformed populated-bucket (n=883, sum +112.49 SOL) on mean per-trade PnL — Twitter feature was not load-bearing.

**Recommendation alignment with parent:** This supplement **REINFORCES** the parent's "DO NOT REVERT" recommendation. The cliff is the fee-model accounting artifact; neither Vybe nor SocialData were edge contributors during +598 SOL.

**Action carry forward:** VYBE-URL-CODE-DRIFT-001 (Tier 1 from yesterday's API-CREDITS-HEALTH-DIAGNOSTIC-001) and SOCIALDATA-AUTO-TOPUP-001 (ACTIVE) remain valid as **current-edge-restoration** items, NOT cliff-recovery items. Estimated lift from fixing them is bounded above by the (small) populated-vs-sentinel delta in the post-cliff sample, which is essentially noise (mean +0.0095 vs -0.0030 SOL/trade across n=923 vs n=271). Likely <0.5 SOL/day at current sizing.

**Bonus finding:** SocialData credits drained AGAIN starting **2026-05-03** (post-Jay-top-up of 2026-04-22 lasted ~10 days). Confirms yesterday's audit note (113 `out of credits` ERROR/11min on 2026-05-05). Strengthens case for SOCIALDATA-AUTO-TOPUP-001 auto-renewal mechanism.

---

## §2 Vybe URL git archeology

### §2.1 Blame the three drift sites

| Line | Commit | Author timestamp (AEDT) | Commit message |
|---|---|---|---|
| 753 (HOLDER fallback) | `751680e3` | 2026-04-08 00:07:51 | Phase3.3+3.4: Fix Vybe auth + add Vybe holder fallback |
| 850 (creator history) | `672eb8ac` | 2026-04-04 01:12:49 | feat(signal_aggregator): Speed Demon momentum hard-gates, fix Vybe URL |
| 2568 (KOL/MM holders) | `94b3c564` | 2026-04-04 12:18:16 | feat: ML label fix, governance JSON classification, graduation sniper, Bonk.fun detection, SocialData fallback |

All three timestamps are **PRE-cliff** (April 4-8, 2026 vs cliff April 21). Per §2.2 prompt classification: "URL was `.com` even during the +598 SOL period — NOT the cliff cause."

### §2.2 `.xyz` history in `signal_aggregator.py`

`git log -S 'vybenetwork.xyz' -- services/signal_aggregator.py` returned **zero hits**. The `.xyz` URL has **never appeared** in this file. The bug was that `signal_aggregator.py` was never migrated when the Vybe API switched between domains.

`git log -S 'vybenetwork.com' -- services/signal_aggregator.py` showed the introductory commits:
- `8ae90c6` — "fix: API correctness — ... **Vybe .com domain** ..."  (introduced `.com` for Vybe paths)
- `429b340` — "fix: seed_wallets Vybe endpoint + revert domain to .xyz (working)"  ← **revert was scoped to seed_wallets only, NOT signal_aggregator**
- `672eb8a` — "feat(signal_aggregator): Speed Demon momentum hard-gates, fix Vybe URL" ← claims "fix Vybe URL" in message but per blame, line 850 still uses `.com` after this commit (so the "fix" was a different aspect, not the domain)
- `751680e` — "Phase3.3+3.4: Fix Vybe auth + add Vybe holder fallback" ← introduced line 753 with `.com`
- `94b3c56` — added KOL/MM lookup at 2568 with `.com`

### §2.3 Sibling Vybe correctness

`services/nansen_wallet_fetcher.py:209` blame:
```
c9a30061 (Darth-Pengu 2026-03-29 01:48:42 +1100 209)     url = "https://api.vybenetwork.xyz/v4/wallets/top-traders"
```

That file used `.xyz` from creation (2026-03-29 — **before** any of the SA `.com` introductions). Even better, line 208 carries a comment:
```
# Vybe domain is .xyz with X-API-Key auth (not .com, not Bearer)
```

The developer explicitly knew `.xyz` was correct on 2026-03-29 but never migrated `signal_aggregator.py` paths. The two files have always disagreed — SA was wrong from `8ae90c6` onward (or from the original creation if `.com` was never re-introduced after `429b340`).

### §2.4 Implication

The bot's entire +598 SOL pre-cliff era ran with broken Vybe HOLDER fallback, broken creator-history lookup, and broken KOL/MM holder check. None of these features contributed to the pre-cliff edge. **Vybe URL drift cannot be the cliff cause.**

**Conclusion: Vybe URL drift = NOT CLIFF.** It is still a real bug worth fixing (silent feature degradation continues to harm current paper edge marginally) but the fix won't recover any "lost cliff edge" because that edge never existed via this path.

---

## §3 SocialData credit drain timeline

### §3.1 Searching for top-up commit

The session prompt referenced commit `512663b` for the 2026-04-22 SocialData top-up. **That hash is a typo.** The actual commit is `512643b` (`docs(roadmap+audits): HOLDER-DATA-PIPELINE-001 fix + BUG-021 partial + CLEAN-004 consolidation`, 2026-04-22 23:46 AEST). It is a roadmap-consolidation commit, not a top-up event. The **top-up itself was a Jay-side billing action** ("Jay topped up to $10 on 2026-04-22" per `ZMN_ROADMAP.md` Sentry note), with no corresponding code commit.

### §3.2 SocialData-related commit history

| Commit | Timestamp (AEDT) | Message |
|---|---|---|
| `4487d50` | 2026-03-29 23:25:25 | feat: Speed Demon pre-filters — social, bundle, rugcheck, position sizing |
| `3d41e0f` | 2026-03-29 23:26:40 | fix: SocialData rate limiting, error handling, cache normalization |
| `94b3c56` | 2026-04-04 12:18:16 | feat: ML label fix … SocialData fallback |
| `7457109` | 2026-04-05 23:53:51 | feat(aggregator): metadata URI fetch for social links, SocialData Twitter lookup |
| `4196ff6` | 2026-04-06 00:02:16 | feat(aggregator): ML floor=25, liquidity velocity gate, …, metadata socials |
| **`35bdfe6`** | **2026-04-19 21:00:30** | **docs(audit): Sentry triage — classify all captured issues + SocialData deep-trace** |
| `627f4c9` | 2026-04-30 23:33:45 | fix(signal_aggregator): SOCIAL-SCORING-001 — per-component social fields in features_json |

The `35bdfe6` commit message (2 days before cliff) is the smoking gun:

> "SocialData deep-trace concluded: Pattern B (soft scoring / silent no-op).
> Credits exhaustion returns -1, falls through every branch in Speed Demon
> position-size scoring. No entries rejected. **495/495 of most-recent 500 SD
> paper trades have twitter_followers=-1** and the bot traded all of them at
> 43.3% 7d WR — if SocialData were hot-path-blocking, count would be zero."

The credits were already exhausted by 2026-04-19. **Drain began before the cliff, not at it.**

### §3.3 Log retention

Railway log retention varies (typically days, not weeks). 2026-04-21 logs are not accessible from this session. Documented limitation; the DB temporal pattern in §3.4 substitutes effectively (every paper trade row carries a feature snapshot at signal-evaluation time).

### §3.4 DB temporal pattern (definitive)

Query: SD-paper rows from `paper_trades_archive_20260421` (PRE-cliff) and `paper_trades` (POST-cliff), bucketed by date, percentage of rows with `twitter_followers=-1` sentinel.

#### Archive (PRE-cliff)

| Date | n | with_features | sentinel_-1 | valid | pct_sentinel |
|---|---:|---:|---:|---:|---:|
| 2026-04-13 | 55 | 55 | 32 | 23 | 58.2 |
| 2026-04-14 | 392 | 392 | 88 | 304 | 22.4 |
| 2026-04-15 | 678 | 678 | 127 | 551 | **18.7** ← healthy |
| **2026-04-16** | **498** | 498 | 494 | 4 | **99.2** ← **drain start** |
| 2026-04-17 | 456 | 456 | 455 | 1 | 99.8 |
| 2026-04-18 | 87 | 87 | 87 | 0 | 100.0 |
| 2026-04-19 | 536 | 536 | 536 | 0 | 100.0 |
| 2026-04-20 | 282 | 282 | 282 | 0 | 100.0 |

**Drain transition: 2026-04-15 → 2026-04-16** (18.7% sentinel → 99.2% sentinel in one day). That is **5 days BEFORE the 2026-04-21 cliff**. By April 18 the entire feature was sentinel-only. Cliff impact on Twitter feature population = none (already at 100% sentinel before cliff).

#### Current (POST-cliff)

| Date | n | sentinel_-1 | pct_sentinel | notes |
|---|---:|---:|---:|---|
| 2026-04-22 | 105 | 26 | 24.8 | Jay top-up partial restore |
| 2026-04-23 | 137 | 14 | 10.2 | mostly populated |
| 2026-04-24 | 160 | 4 | 2.5 | best |
| 2026-04-25 | 126 | 10 | 7.9 | |
| 2026-04-28 | 170 | 18 | 10.6 | |
| 2026-04-29 | 102 | 6 | 5.9 | |
| 2026-04-30 | 168 | 19 | 11.3 | |
| 2026-05-01 | 52 | 8 | 15.4 | |
| 2026-05-02 | 8 | 0 | 0.0 | |
| **2026-05-03** | **17** | **17** | **100.0** | **second drain start** |
| 2026-05-04 | 35 | 35 | 100.0 | |
| 2026-05-05 | 61 | 61 | 100.0 | (yesterday's audit logged 113 ERROR/11min) |
| 2026-05-06 | 53 | 53 | 100.0 | continuing |

Post-cliff Jay top-up of 2026-04-22 lasted **10-11 days**, with a second drain starting 2026-05-03. As of today (2026-05-07) credits have been re-exhausted for 4+ days.

### §3.5 PnL impact estimate

#### Archive (PRE-cliff aggregate, 2026-04-13 to 2026-04-20)

| bucket | n | sum_pnl | mean_pnl | WR |
|---|---:|---:|---:|---:|
| sentinel_-1 (no Twitter) | 2101 | **+485.37 SOL** | **+0.231** | 40.8% |
| twitter_populated | 883 | +112.49 SOL | +0.127 | 46.8% |

**Surprise:** the sentinel subset has **higher mean per-trade PnL** than the populated subset (+0.231 vs +0.127). Populated subset has slightly higher WR (46.8% vs 40.8%) but smaller wins on average. **If Twitter feature were edge-positive, the populated subset would dominate.** It does not.

Note the n breakdown: 2101 sentinel + 883 populated = 2984 total = exactly the pumpportal-source archive total per cliff_confirmation.txt §5b1. Population correctly accounts for the entire archive sample.

#### Current (POST-cliff aggregate, 2026-04-22 to 2026-05-06)

| bucket | n | sum_pnl | mean_pnl | WR |
|---|---:|---:|---:|---:|
| sentinel_-1 | 271 | -0.81 SOL | **-0.0030** | 31.0% |
| twitter_populated | 923 | +8.78 SOL | **+0.0095** | 32.6% |

In post-cliff data, populated edges out sentinel by **+0.0125 SOL/trade mean delta**. That's a small effect but still suggests Twitter has *some* signal under the corrected fee model. Magnitude estimate at current sizing (~0.10 SOL avg) ≈ +0.4-0.5 SOL/day across full feed if SocialData credits restored. Bounded above by sample noise.

**Critical:** the +0.0125 mean delta in current data is what's available; the apparent **negative** delta in archive data (sentinel +0.231 > populated +0.127) reflects pre-cliff old-fee accounting bias, not real edge. Under realistic fees, populated would likely be modestly better in both eras — but neither was load-bearing for the +598 SOL pre-cliff number.

---

## §4 Synthesis

| Candidate | Verdict | Evidence anchor |
|---|---|---|
| Vybe URL drift | **NOT CLIFF** | Three `.com` introductions 2026-04-04 to 2026-04-08, all pre-cliff; bot's +598 SOL era ran with broken Vybe URLs throughout |
| SocialData drain | **NOT CLIFF** | DB shows drain start 2026-04-16 (98%+ sentinel by 04-18), 5 days before cliff; commit `35bdfe6` confirms 495/495 sentinel by 04-19; pre-cliff sentinel subset outperformed populated subset on mean PnL |

Both candidates pre-date the cliff. Both were already broken during the +598 SOL pre-cliff era. Neither is the cliff cause.

**The supplement reinforces parent's "DO NOT REVERT" recommendation:** the +598 SOL was an accounting artifact of the old fee model, not a strategy/feature edge. Vybe and SocialData fixes are useful for current edge marginal restoration, NOT for cliff recovery.

---

## §5 Recommended action

| Verdict | Action |
|---|---|
| Both candidates NOT CLIFF | **No new fix sessions justified by cliff analysis.** Existing items stand: |
| | • **VYBE-URL-CODE-DRIFT-001 (Tier 1)** — ship a 3-string-substitution session at low priority. Estimated lift bounded above by §3.5 magnitude (small in current sample). Current edge restoration only, not cliff recovery. |
| | • **SOCIALDATA-AUTO-TOPUP-001 (ACTIVE)** — Jay action: top-up + auto-renewal alerting. Recurrence on 2026-05-03 (10 days after 04-22 top-up) confirms manual top-up is fragile. Auto-renewal at < $2 threshold recommended per the existing roadmap entry. |

The parent investigation's other recommendations (BREAKEVEN-DECISION-001, TP-SCHEDULE-EVAL-001, SIGNAL-MIX-ANALYSIS-001) are unaffected by this supplement.

---

## §6 What this supplement does NOT cover

- **Other cliff candidates** (e.g., entry filter changes, MC-band concentration, signal-source distribution) — covered by parent investigation. Parent ruled out signal-source shift; MC-band shift is gate-driven (designed); exit-reason composition shift reflects intentional GATES-V5 deploy.
- **Fixing Vybe URL or topping up SocialData** — explicitly out of scope; separate session(s).
- **Live mode work** — not relevant to cliff investigation.
- **ML threshold tuning** — separate Tier 1 item (`ML-THRESHOLD-DATA-DRIVEN-RETUNE-002`, gated on 7d post-`ea0da2f` observation window through 2026-05-12).
- **Magnitude estimation under realistic fee model** — §3.5 used `realised_pnl_sol` directly. A more rigorous A/B would re-derive PnL under FEE-MODEL-001 from raw fields. Given the qualitative finding (sentinel didn't underperform populated pre-cliff), the rigorous estimate is unlikely to flip the verdict.

---

## §7 Decision Log entry (for ZMN_ROADMAP.md)

```
2026-05-07 CLIFF-VYBE-SOCIALDATA-SUPPLEMENT-001 ✅ INVESTIGATION COMPLETE — Targeted time-correlation of Vybe URL drift + SocialData credit drain against 2026-04-21 cliff. **Both NOT CLIFF.** Vybe: all three .com URLs introduced 2026-04-04 to 04-08 (13-17 days pre-cliff) per git blame; bot's +598 SOL era ran with broken Vybe URLs throughout. SocialData: DB temporal shows pct_sentinel(twitter_followers=-1) jumped 18.7% → 99.2% on 2026-04-16 (5 days pre-cliff); commit 35bdfe6 (2026-04-19) explicitly stated "495/495 of most-recent 500 SD paper trades have twitter_followers=-1". Pre-cliff sentinel-bucket trades (n=2101, sum +485.37) outperformed populated-bucket (n=883, sum +112.49) on mean PnL — Twitter feature was NOT load-bearing. **Reinforces parent's DO NOT REVERT recommendation:** the +598 SOL was a fee-model accounting artifact, not feature edge. Bonus finding: SocialData drained again starting 2026-05-03 (10 days after Jay's 04-22 top-up); strengthens SOCIALDATA-AUTO-TOPUP-001 auto-renewal case. Existing items VYBE-URL-CODE-DRIFT-001 and SOCIALDATA-AUTO-TOPUP-001 stand as current-edge-restoration items, NOT cliff-recovery items. Audit: docs/audits/CLIFF_VYBE_SOCIALDATA_SUPPLEMENT_2026_05_05.md. No code/env changes (read-only).
```

---

## §8 Reproducibility

```bash
# Vybe blame
git blame -L 750,756 services/signal_aggregator.py
git blame -L 847,853 services/signal_aggregator.py
git blame -L 2565,2571 services/signal_aggregator.py
git blame -L 207,213 services/nansen_wallet_fetcher.py
git log --all --oneline -S 'vybenetwork.xyz' -- services/signal_aggregator.py
git log --all --oneline -S 'vybenetwork.com' -- services/signal_aggregator.py

# SocialData commit history
git log --all --oneline -i --grep="socialdata"
git log --all --oneline -S 'twitter_followers' -- services/

# DB temporal (script committed for archival)
python .tmp_cliff_supplement/twitter_followers_temporal.py
```

DB DSN inherited from `.tmp_cliff_investigation/queries.py` (gondola.proxy.rlwy.net:29062, postgres user, internal Railway public proxy).
