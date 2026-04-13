# ZMN Bot — Product Roadmap & Backlog
**Last updated:** 2026-04-13 AEDT (post dashboard Tier 1 audit)
**Previous version:** 2026-04-13 (post backfill, pre-dashboard audit)

---

## Where We Are Right Now

**Architecture:** Healthy. All 8 services UP. Zero crashes. Zero emergency stops. The Tier 2 overnight landed 4 clean fixes (f7ebc56, cb53b7a, 629c740, da964ab) + exit strategy fix (bf57117) + paper_trader price fix (9b880e1) + entry filter v4 (56421ab).

**P/L data:** Trustworthy. 20.4% of historical trades had corrupted exit prices biased toward winners — fixed. All pre-2026-04-09 20:41 UTC data flagged as contaminated.

**Performance baseline (259 clean trades since cleanup, using corrected_pnl_sol):**
- WR: 26.3% (68 wins) -- ABOVE 18.7% break-even threshold
- Total SOL: +17.73 (corrected from +13.83 using old buggy column)
- Pre-fix subset (id <= 3564): 21.1% WR, -0.91 SOL (corrected from -4.81)
- Post-fix subset (id > 3564): 53.7% WR, +18.65 SOL
- 19 trades reclassified loss->win after staged TP backfill (2026-04-13)

**Historical backfill -- COMPLETE (2026-04-13):**
- Added corrected_pnl_sol/pct columns to paper_trades
- 44 pre-fix staged trades recomputed, 215 clean trades passed through
- See STAGED_TP_BACKFILL_REPORT.md for full details

**Current state (CRITICAL):** Bot is in HIBERNATE mode at CFGI 16. Entry filter v4 deployed and rejecting 100% of signals because of an UPSTREAM feature default bug — `buy_sell_ratio_5min` and `unique_wallet_velocity` default to `0` when missing instead of `-1`. The filter correctly rejects "zero buyers" but cannot distinguish from "data not yet arrived." Fix is queued (see SNAPSHOT_AND_FEATURE_FIX.md).

**Helius:** Credits exhausted until April 26. Webhook disabled. `HELIUS_ENRICHMENT_ENABLED=false`. Treasury budget guard working.

**Nansen:** MCP works. DRY_RUN=true on all services. Smart money labels do NOT exist at pump.fun micro-cap scale (CRITICAL FINDING from SMART_MONEY_DIAGNOSTIC).

---

## NEW FINDINGS (since 2026-04-11 roadmap)

### Finding 1: Entry filter v3 had a logic bug (FIXED)
- **Bug:** Used `value > 0` for "data exists" check, treating zero values as missing data when they're actually the strongest reject signal
- **Impact:** Filter passed 98% of signals when it should have rejected ~75%
- **Fix:** Commit 56421ab — changed to `value != -1`
- **Status:** Deployed but blocked by Finding 2 below

### Finding 2: Feature default bug (PENDING FIX)
- **Bug:** `signal_aggregator.py` defaults `buy_sell_ratio_5min` and `unique_wallet_velocity` to `0` when missing from `live_stats`. Other features (sniper_0s_num, tx_per_sec, sell_pressure) correctly default to `-1`.
- **Evidence:** Trade 3558 features_json shows BSR=0.0 alongside sniper_0s_num=-1 (same row, two different defaults)
- **Impact:** v4 entry filter cannot distinguish "unknown" from "zero buyers." Rejects everything.
- **Same-bug-different-feature impact:** ML model is also training on rows where 0 means "unknown" — structured noise it can't learn around. This affects features beyond the filter (bonding_curve_progress, market_cap_usd, liquidity_velocity may have the same bug).
- **Fix prompt ready:** SNAPSHOT_AND_FEATURE_FIX.md
- **Status:** READY TO PASTE — highest priority

### Finding 3: Nansen smart money labels DON'T exist at pump.fun scale (CRITICAL ARCHITECTURE CHANGE)
- **Test results:** Smart money labels appear at $100k+ market cap. Pump.fun tokens trade at $4k-$30k. Nansen profiler doesn't track wallets that only trade pump.fun tokens.
- **What this kills:** The original "subscribe to Nansen-labeled smart money" architecture
- **What works instead:** Mine the bot's OWN winning trades for repeating wallets via `token_who_bought_sold` (works at any market cap, just returns generic labels like "GMGN bot user" / "deployer")
- **Build path change:** Wallet curation must come from bot's own winners, not Nansen's pre-labeled SM list
- **Timeline change:** Mining requires ~100+ winning trades for statistical confidence, not 28. At current rate that's 50-100 days, not weeks.
- **Reference:** SMART_MONEY_DIAGNOSTIC.md

### Finding 4: HELIUS_DAILY_BUDGET=0 IS A LIE
- **Bug:** Only `dashboard_api.py` reads HELIUS_DAILY_BUDGET. Signal_aggregator, treasury, market_health, execution all bypass it.
- **Impact:** This is how the bot burned 10M Helius credits while appearing "disabled"
- **Partial fix:** Treasury now has a budget guard. Other services still bypass.
- **Full fix needed:** Global `helius_call()` wrapper with Redis-based daily counter that ALL services use.
- **Deadline:** Must be deployed BEFORE April 26 credit reset, otherwise the new credits will burn the same way.
- **Reference:** API_AUDIT_REPORT.md

### Finding 5: getTokenLargestAccounts pipeline is correct, just credit-starved
- **Investigation result:** `_fetch_holder_data_helius` parses correctly, computes top10_holder_pct and holder_gini correctly, fails only because credits are exhausted
- **Implication:** When April 26 credits return, concentration features will auto-populate with ZERO code changes
- **Caveat:** Will burn credits fast unless Finding 4 fix is deployed first

### Finding 6: Dashboard Tier 1 audit (2026-04-13)
- **Result:** 15 panels audited. All P/L widgets now use corrected_pnl_sol with post-cleanup filter.
- **CFGI source:** Alternative.me Bitcoin F&G returns 12 (correct from API). Jay compared CMC (42). Different indices. Needs data source decision.
- **Impact:** HIBERNATE mode, Analyst paused, Speed Demon 0.75x sizing all driven by Bitcoin F&G index, not Solana-specific.
- **Reference:** DASHBOARD_AUDIT.md

---

## IN FLIGHT — RIGHT NOW

### CFGI Data Source Decision (NEEDS JAY REVIEW)
- **Status:** DIAGNOSED, awaiting Jay's decision
- **Options:** (a) Switch to CMC CFGI API, (b) Find Solana-specific index, (c) Keep Bitcoin F&G but adjust thresholds
- **Why it matters:** Changes HIBERNATE/NORMAL threshold, Analyst pause, Speed Demon sizing
- **Risk:** Changing index changes trading behavior immediately
- **Reference:** DASHBOARD_AUDIT.md B-001
- **Next review:** 2026-04-14

### Feature default fix + full state snapshot
- **Status:** Prompt ready, awaiting paste
- **File:** `/mnt/user-data/outputs/SNAPSHOT_AND_FEATURE_FIX.md`
- **Phases:** Filter state → forensics → snapshot → fix → verify → report
- **Expected outcome:** Pass rate 0% → some non-zero number, trades resume, bot can be honestly evaluated again
- **Runtime:** ~80 min including 30-min verification
- **Auto-revert:** Multiple conditions (zero trades for 30 min, volume above pre-fix baseline, crashes)

---

## SHORT-TERM — Next 1-2 weeks

### 1. Feature default fix verification (immediately after fix lands)
- **Trigger:** After SNAPSHOT_AND_FEATURE_FIX.md completes
- **Scope:** Wait 12-24 hours, observe what kind of trades flow now that filter can distinguish unknown from zero
- **Decision point:** If WR climbs above 18.7% break-even → continue. If still below → tune thresholds further.
- **Session size:** Read-only analysis on fresh CSV

### 2. Broader feature default cleanup
- **Trigger:** After Fix 1 verification confirms BSR/wallet_velocity fix worked
- **Scope:** Audit ALL features in `_build_features` for the same `default=0` bug pattern. Likely candidates: bonding_curve_progress, market_cap_usd, liquidity_velocity, holder_count
- **Why important:** Feeds clean data to ML model retrains
- **Session size:** Medium, 60-90 min
- **Risk:** Each fix is small but the cumulative effect could shift ML scores

### 3. Helius budget enforcement (HARD DEADLINE: before April 26)
- **Trigger:** Anytime in next 10-12 days
- **Scope:** Create shared `helius_call()` wrapper with Redis-based daily counter that ALL services use. Replace current bypass behavior across signal_aggregator, treasury, market_health, execution.
- **Why deadline:** Without this, new credits on April 26 will burn the same way the last batch did
- **Session size:** Medium, 60-90 min
- **Pairs with:** Fix 4 (caching)

### 4. Helius enrichment caching
- **Trigger:** Same session as Fix 3, OR standalone before April 26
- **Scope:** Add per-token Redis cache (300s TTL) to 4 uncached enrichment functions:
  - `_fetch_holder_data_helius` (signal_aggregator.py:686)
  - `_check_dev_wallet_sells` (:927)
  - `_check_bundle_detection` (:988)
  - `_get_jito_bundle_stats` (:1234)
- **Expected impact:** 70% reduction in enrichment RPC burn (250k → 75k credits/day)
- **Session size:** Medium, 60-90 min

### 5. Helius credit reset preparation (April 24-25)
- **Trigger:** ~2 days before April 26
- **Tasks:**
  - Confirm webhook stays disabled
  - Confirm Fix 3 + Fix 4 are deployed and working
  - Decide credit top-up amount (target: 2-3M/month, not 10M)
  - Verify `getTokenLargestAccounts` pipeline auto-recovers when credits return
  - Pre-write the env var changes needed when credits arrive
- **Session size:** 30 min verification

### 6. Nansen Day-1 enablement (after Fix 1 verified)
- **Trigger:** Once entry filter is producing real trade data
- **Scope:** Enable Nansen on signal_aggregator only, NANSEN_DAILY_BUDGET=200
- **Purpose:** ANALYST personality enrichment, NOT Speed Demon (Nansen has 1-5 min indexing latency, too slow for Speed Demon)
- **Session size:** Small, 15 min + monitoring
- **Dependencies:** None — ready

### 7. Wallet mining sanity check (BEFORE building wallet curation)
- **Trigger:** Once we have 50+ post-fix winning trades (could be weeks)
- **Scope:** Statistical check: how many unique buyer wallets across the winning sample? What's the baseline rate of "wallet appears on 3+ winners by chance"? If the dataset is too sparse to mine reliably, defer until more winners accumulate.
- **Session size:** Read-only analysis, 15-30 min
- **Output:** Go/no-go decision on Phase 8

### 8. Smart money wallet mining (Phase 1 of curation)
- **Trigger:** Only after Fix 7 confirms dataset is dense enough
- **Scope:** Use Nansen `token_who_bought_sold` on top 20-50 winners. Cross-reference buyer lists to find wallets appearing on 3+ winners. Manual review.
- **Session size:** Medium, 60-90 min
- **Cost:** ~50 Nansen calls
- **Output:** Curated `watched_wallets` table seed (probably 5-15 wallets initially, not 20-40)

### 9. Dashboard cleanup + analytics reset
- **Trigger:** Anytime, pure UI work, parallel to anything
- **Scope:** STILL NEEDS USER SPECS — Jay needs to specify 3-5 concrete items
- **Suggested items based on findings:**
  - Reset WR/P/L displays to post-contamination window only
  - Add per-personality breakdown
  - Show entry filter rejection metrics (passes/rejects/by reason)
  - Show last N trades on home page
  - Fix API status indicators (Helius shows real state, not stale)
  - Display feature population rates
- **Session size:** Read-only audit + small fixes

### 10. Telegram yeezus channel listener audit
- **Scope:** Determine current state of Telethon integration for `cryptoyeezuscalls`
- **Questions:** Is it running? Processing messages? API credentials still valid?
- **Session size:** Small diagnostic, 30 min
- **Dependencies:** Telegram API credential rotation may be needed first (credentials exposed in past conversation, regenerate at my.telegram.org)

### 11. Telegram yeezus exit schedule
- **Trigger:** ONLY after Fix 10 confirms listener can trigger trades
- **Scope:** Per-source exit schedule override for yeezus trades — config change, not new code
- **Schedule per Jay's spec:**
  - +300% → sell 50%
  - +500% → sell 25%
  - +750% → sell 10%
  - +1000% → sell 10%
  - +2000% → sell 5% (remainder rides)
- **Session size:** Trivial, 15-30 min

---

## MEDIUM-TERM — 2-4 weeks

### 12. Smart money wallet system (Phase 2: monitoring)
- **Trigger:** After Phase 1 wallet curation has at least 5 candidates AND Helius credits reset (April 26)
- **Scope:** Configure Helius webhook with curated whale wallets (NOT Raydium infrastructure this time). Monitor SWAP events only. Handler updates Redis counter `whale_buys:{mint}` with sliding 5-min window.
- **Session size:** Medium, 60-90 min
- **Cost estimate:** ~90k credits/day for webhook events (well within 10M plan)
- **Architecture note:** Bridge approach for next 14 days (before reset) is to piggyback on existing Nansen `_fetch_nansen_enrichment` flow with a Redis SET membership check. Zero additional API cost.

### 13. Smart money wallet system (Phase 3: entry trigger)
- **Trigger:** After Phase 2 stable
- **Scope:** Hardcoded entry rule that BOOSTS confidence when N or more watched wallets buy a token within a time window. NOT a hard pass-through trigger — bot still uses ML scoring AND entry filter, smart money signal is additive.
- **Initial rule:** `if sm_buy_count >= 2: confidence_boost = +30`
- **Critical caveat:** This rule is ANALYST-only. Speed Demon's timeframe (sub-second decisions) is incompatible with Nansen's 1-5 min indexing latency. Speed Demon's edge is the entry filter, not smart money.
- **Session size:** Medium, 60 min

### 14. Analyst personality rework (50-100k pullback strategy)
- **Trigger:** After entry filter is stable AND smart money Phase 2 is live AND Analyst CFGI threshold reviewed
- **Scope:** Entirely new strategy. Tokens with mcap $50k-$100k, recent severe upward momentum, 25-30% pullback from local peak, new holders entering with >0.5 SOL buys.
- **Required components:**
  - Price history tracker (per-token price arrays, not just latest)
  - Pullback detector (local maxima + drawdown calculation)
  - New-holder-entry tracker (requires working Vybe/Helius holder data — depends on Helius credits)
  - New scoring path dedicated to Analyst signals
  - Hold-time configuration for Analyst (longer than Speed Demon)
- **Session size:** LARGE — 2-5 sessions minimum
- **Blockers:** Helius credits reset, smart money Phase 2 live, Analyst CFGI threshold review

### 15. Analyst CFGI threshold review
- **Trigger:** Before Fix 14 is built
- **Question:** Is the CFGI < 20 auto-pause correct?
- **Evidence to review:** Currently 0 Analyst trades in 212-trade clean window. Tiny DEFENSIVE-mode sample (3 trades) showed 33% WR / +77% avg P/L.
- **Session size:** Analysis only, 30 min
- **Output:** Decision to keep, lower, or remove threshold

---

## LONG-TERM — After short + medium

### 16. ML model retrain with clean data + populated features
- **Trigger:** When clean training sample count exceeds 500 (projected after entry filter is fixed and producing real trades again)
- **Scope:** Full retrain of original 55-feature ensemble with:
  - All pre-2026-04-09 20:41 UTC data excluded
  - Concentration features populated (depends on Helius credit reset + caching deploy)
  - PumpPortal-derived features populated (already in place)
  - All 3 models if LightGBM fresh deploy works (still needs `railway up -s ml_engine`)
- **Session size:** Small — mostly waiting for retrain + comparing AUC

### 17. FEATURE_COLUMNS pruning
- **Trigger:** After Fix 16 retrain completes
- **Scope:** Based on populated-feature count, prune from 55 to ~20 features that actually reach the model
- **Risk:** Low — the 42 dead features contribute zero signal anyway
- **Session size:** Small, 30-45 min

### 18. External feature population (Vybe alternatives)
- **Trigger:** After smart money system is stable
- **Scope:** Vybe is currently dead (404 on all token endpoints). Decision: abandon, switch entirely to Helius+Nansen, or investigate why endpoints changed
- **Session size:** Small investigation, 30 min
- **Priority:** LOW — Helius + Nansen is strictly better

### 19. Governance SQL type mismatch (cosmetic)
- **Scope:** Fix `operator does not exist: double precision > timestamp with time zone` warning
- **Impact:** Cosmetic. Governance still makes correct decisions.
- **Priority:** LOW

---

## EXPLICITLY DEFERRED / DON'T BUILD

### 20. Kronos foundation model integration (ZMN) — DON'T DO IT
- Wrong latency, wrong pretraining domain, tokens die before context exists
- ZMN's edge is holder/smart money/sniper features, not OHLCV forecasting

### 21. Kronos ASX equities bot — SEPARATE PROJECT, parked
- Evaluation prompt at `/mnt/user-data/outputs/KRONOS_EVALUATION.md`
- 5-phase feasibility study, ~1 week of overnight sessions
- Park until ZMN is profitable
- DO NOT mix with ZMN codebase

### 22. ML feature expansion — DON'T BUILD until sample count >500
- Curse of dimensionality: 128 samples × 55 features is over-parameterized
- New data sources should be hardcoded entry rules, not ML features

### 23. ML score cap / inversion fix — TREATING A SYMPTOM
- The audit recommended capping at 65, but the real problem is training data quality
- Fix the feature default bug first (Finding 2), retrain with clean labels (Fix 16), then re-evaluate

### 24. Original "subscribe to Nansen-labeled SM wallets" architecture — DEAD
- Nansen SM labels don't exist at pump.fun scale (Finding 3)
- Replaced by mining-the-bot's-own-winners approach (Fix 7 + Fix 8)

---

## BLOCKED / WAITING

### Helius credit reset
- **Date:** April 26, 2026
- **Unblocks:** Concentration features auto-populate, smart money webhook architecture, treasury balance checks
- **Pre-reset requirement:** Fix 3 (budget enforcement) + Fix 4 (caching) MUST be deployed

### Telegram API credential rotation
- **Needed for:** Fix 10
- **Action:** Jay regenerates at my.telegram.org

### Sample accumulation for ML retrain + wallet mining
- **Current:** 212 clean trades, 28-30 winners
- **Needed for retrain:** 500+ clean trades
- **Needed for mining:** 100+ winners
- **Rate:** Currently 0 trades/hour due to feature default bug. After fix: estimated 1-3 quality trades/hour
- **Projection:** 500 samples in ~7-21 days post-fix

---

## PRIORITIZED EXECUTION ORDER

### Today / Tomorrow (April 12-13)
1. ✅ Paste SNAPSHOT_AND_FEATURE_FIX.md (in flight)
2. Read fix outcome, decide if more tuning needed
3. SLEEP between sessions

### This week (April 13-19)
4. Verify entry filter is now producing real trade data
5. Broader feature default cleanup (Fix 2)
6. Helius caching deploy (Fix 4) — start of pre-reset prep
7. Helius budget enforcement (Fix 3)
8. Dashboard cleanup (if specs provided)
9. Telegram yeezus audit (Fix 10)

### Next week (April 20-26)
10. Helius credit reset preparation
11. Nansen Day-1 enablement (Fix 6)
12. Wait for Helius credit reset April 26

### Week of April 27+
13. Verify post-reset behavior — features auto-populating
14. Wallet mining sanity check (Fix 7) — if sample count is enough
15. Smart money Phase 1 mining (Fix 8) — only if Fix 7 passes
16. Smart money Phase 2 webhook architecture (Fix 12)
17. ML retrain with clean data (Fix 16)
18. FEATURE_COLUMNS pruning (Fix 17)

### After (May+)
19. Analyst CFGI review (Fix 15)
20. Analyst rework (Fix 14) — multi-session
21. Smart money Phase 3 entry trigger (Fix 13)
22. Telegram yeezus exit schedule (Fix 11)

---

## SUCCESS METRICS — UPDATED TARGETS

| Metric | 2026-04-10 Baseline | 2026-04-12 Current | Target W1 | Target W2 | Target W4 |
|--------|---------------------|--------------------|-----------|-----------|-----------|
| WR | 16.3% | 13.3% (degraded) | 22%+ | 28%+ | 35%+ |
| Payoff ratio | 4.34x | 4.5x | 3.5x+ | 3.5x+ | 4.0x+ |
| Avg P/L per trade | -2.28% | -3.08% | 0% | +3%+ | +8%+ |
| Daily P/L SOL | -4.3 | unknown (0 trades) | 0 | +2 | +5 |
| Clean training samples | 172 | 212 | 500+ | 1000+ | 2500+ |
| Entry filter pass rate | N/A | 0% (broken) | 5-15% | 10-25% | 15-30% |
| Trade rate per hour | ~10 | 0 | 1-3 | 3-5 | 5-8 |
| no_momentum_90s % | 51% | 21% | <15% | <10% | <10% |
| stale_no_price % | 3.5% | 71% | 71% (Helius) | 71% | <5% (post Apr 26) |
| Emergency stops | 0 | 0 | 0 | 0 | 0 |
| Helius daily burn | 541k (broken) | 0 (exhausted) | 0 | <100k | <200k |

---

## OPEN QUESTIONS FOR JAY

1. **Dashboard cleanup items?** Still need 3-5 concrete issues to write a prompt
2. **Telegram listener current state?** Running? Broken? Never tested?
3. **Analyst CFGI 20 threshold — keep or lower?** Depends on whether the design predated trustworthy P/L data
4. **Nansen enablement timing?** This week (after fix verified) or wait?
5. **Helius plan tier at April 26 reset?** Current projections suggest 2-3M/month is enough; downgrade from 10M plan?
6. **Smart money wallet discovery — manual or algorithmic mining?** Mining requires more winners than we currently have
7. **Per-personality P/L breakdown on dashboard — before or after Analyst rework?**

---

## SESSION ENERGY BUDGET — REINFORCED

The last 48 hours validated this principle the hard way:
- The v3 entry filter shipped in one session, three commits, with a logic bug that made it inert for 24+ hours
- Caught only because Jay manually uploaded the CSV for offline analysis
- Tonight's "mega session" instinct was correctly resisted

**Rules:**
- ONE substantive lever per session
- Verification windows BEFORE tuning anything (24h+ minimum)
- All deploys must have auto-revert conditions
- All thresholds env-var-configurable for kill switch
- Read-only diagnostic prompts BEFORE write prompts on anything ambiguous
- Two checkpoints per session: Phase 1 findings (before code change) and Phase N verification (after deploy)

**Anti-patterns observed and avoided:**
- "Mega session" stacking 7+ unrelated changes
- Tuning thresholds based on a 1-hour sample
- Enabling paid APIs (Nansen, Helius) at bedtime when tired
- Treating Claude Code's "PARTIAL — KEEP running" as definitive
- Skipping read-only diagnostic in favor of "just fix it" prompts

---

## REFERENCES — KEY DOCS IN REPO

- `MONITORING_LOG.md` — chronological session log
- `AGENT_CONTEXT.md` — bot architecture reference
- `CLAUDE.md` — agent instructions
- `API_AUDIT_REPORT.md` — Helius/Nansen/Vybe state
- `SMART_MONEY_DIAGNOSTIC.md` — Nansen capability map (Finding 3)
- `ENTRY_FILTER_v4_REPORT.md` — v4 outcome (PARTIAL, blocked by Finding 2)
- `POST_TIER2_DIAGNOSIS.md` — bot health snapshot post Tier 2 fixes
- `TIER2_OVERNIGHT_REPORT.md` — 4 fixes overview

## REFERENCES — PROMPTS READY OR RECENT

- `/mnt/user-data/outputs/SNAPSHOT_AND_FEATURE_FIX.md` — IN FLIGHT (feature default fix + state snapshot)
- `/mnt/user-data/outputs/ENTRY_FILTER_V4_FIX.md` — DEPLOYED (commit 56421ab)
- `/mnt/user-data/outputs/KRONOS_EVALUATION.md` — PARKED (separate ASX project)
