# ZMN Bot -- Product Roadmap & Backlog (v4 merged)

**Last updated:** 2026-04-14 AEDT (post-recovery session)
**Structure:** trigger conditions + review dates (v3 structure adopted)
**Next scheduled review:** 2026-04-15 (after recovery + hardening session)

---

## HOW THIS ROADMAP WORKS

Every item has:
- **State:** IN-FLIGHT | READY | BLOCKED | DEFERRED | COMPLETED | DROPPED
- **Trigger:** the specific condition under which it becomes actionable
- **Next review:** date this item gets re-evaluated (nothing drifts forever)
- **Blocker:** what's stopping it (if any)

Items without a trigger condition get DROPPED instead of "next week'd."
Items that sit in DEFERRED for 30 days without progress get re-evaluated
for DROPPED or ACTUALLY-SCHEDULED.

---

## CURRENT BOT STATE (2026-04-14)

**Architecture:** 8 services on Railway. All services healthy.
signal_aggregator recovered 2026-04-14 ~11:40 UTC after 21-hour outage.
Now hardened with 5-attempt Redis retry + health heartbeat (commit 85768c5).

**Performance -- the corrected truth (259 clean trades):**
- Combined: 26.3% WR, 68 wins, +17.73 SOL (using corrected_pnl_sol)
- Pre-fix subset (id <= 3564): 218 trades, 46 wins (21.1% WR), -0.91 SOL
- Post-fix subset (id > 3564): 41 trades, 22 wins (53.7% WR), +18.65 SOL
- Pre-crash Apr 13 burst (30 trades): 50% WR, +5.44 SOL -- the bot was
  performing excellently when the pipeline died

**Paper balance:** 31.8592 SOL

**Key finding:** the bot was never as broken as the recorded numbers
suggested. The staged TP reporting bug (fixed in commit 5b92226) was
hiding real profits. Post-fix data shows the bot IS profitable when
the market has pumping tokens.

**Helius:** Credits exhausted until April 26. Webhook disabled.
`HELIUS_ENRICHMENT_ENABLED=false`. Treasury budget guard working.

**Nansen:** DRY_RUN on all services. Smart money labels don't exist at
pump.fun micro-cap scale (confirmed finding from 2026-04-12).

**CFGI:** 21 (Alternative.me Bitcoin F&G -- NOT Solana-specific).
Decision on data source pending Jay's review (B-001).

---

## RECENT FINDINGS (preserved from prior roadmap versions)

### Finding 1: Entry filter v3 had a logic bug (FIXED)
- Used `value > 0` for "data exists" check. Fix: commit 56421ab.

### Finding 2: Feature default bug (FIXED)
- `signal_aggregator.py` defaulted BSR/wallet_velocity to `0` instead
  of `-1`. Fix: commit a8a390b.

### Finding 3: Nansen smart money labels don't exist at pump.fun scale
- SM labels appear at $100k+ market cap. Pump.fun tokens trade at
  $4k-$30k. Architecture pivot: mine bot's own winners instead.

### Finding 4: HELIUS_DAILY_BUDGET=0 is cosmetic
- Only dashboard_api.py reads it. Other services bypass. Needs global
  `helius_call()` wrapper. Hard deadline: before April 26 credit reset.

### Finding 5: getTokenLargestAccounts pipeline is correct
- Just credit-starved. Will auto-populate after April 26 reset.

### Finding 6: Dashboard Tier 1 audit (2026-04-13)
- 15 panels audited. P/L widgets now use corrected_pnl_sol.
- CFGI source: Alternative.me Bitcoin F&G (not Solana-specific).
- Reference: DASHBOARD_AUDIT.md

### Finding 7: signal_aggregator 21-hour outage (2026-04-14) — FIXED
- Crashed at 13:38 UTC Apr 13 due to transient Redis DNS failure.
- No startup retry logic. Railway marked "Completed."
- Fix: restart + add retry loop + health heartbeat (commit 85768c5).
- Reference: STATE_AUDIT_2026_04_14.md

---

## IN-FLIGHT

(none currently)

### CFGI Stage 2 Cutover
- **State:** SCHEDULED (Stage 1 deployed 2026-04-14 ~22:25 AEDT)
- **Trigger:** 24h of dual-read observation data (earliest: 2026-04-15 ~22:25 AEDT)
- **What:** Cut bot_core and signal_aggregator from `market:health.cfgi`
  (Alternative.me BTC F&G) to `market:health.cfgi_sol` (cfgi.io SOL).
  Preserve historical BTC value as `market:health.cfgi_btc` for
  continuity. Update mode decision thresholds if SOL CFGI scale
  differs meaningfully from BTC.
- **Key finding from Stage 1:** BTC F&G = 21 vs SOL CFGI = 56.5.
  Cutover will likely unpause Analyst, increase Speed Demon sizing,
  and shift mode from HIBERNATE toward NORMAL.
- **Risk:** Analyst may unpause and Speed Demon may return to 1.0x
  sizing. This is expected behavior, not a bug.
- **Next review:** 2026-04-15
- **Session size:** 30-45 min

### Governance CFGI Hallucination Fix (B-010)
- **State:** READY
- **Trigger:** None
- **What:** Fix the governance LLM prompt to inject real CFGI value.
  Currently hallucinates "CFGI at 50" regardless of actual value.
- **Root cause:** Prompt template either injects a default or LLM
  confabulates a neutral value.
- **Impact:** Governance mode recommendations based on fabricated CFGI.
- **Next review:** 2026-04-16
- **Session size:** 30 min

---

## READY (prompts written, ready to paste -- in priority order)

### 1. TP Redesign (30/30/20/10/10 Option B2)
- **State:** READY
- **What:** Change staged TP allocation from "% of remaining" to "% of
  original". Stage triggers: +50%/+100%/+250%/+500%/+1000%. Allocations:
  30/30/20/10/10. All-out at +1000%.
- **Why:** Front-loads protection (60% sold by +100%), extends upper
  triggers to capture observed 10-15x peaks.
- **Trigger:** 24-48h of STAGED_TP_FIRE data (clock started 2026-04-14
  ~11:45 UTC when bot_core redeployed with instrumentation commit 40dadb6)
- **Next review:** 2026-04-16
- **Session size:** 75-90 min

### 2. ML Training Code Update (read corrected_pnl_sol)
- **State:** READY
- **What:** Update ml_engine training/labeling code to use
  `corrected_pnl_sol` instead of `realised_pnl_sol`.
- **Trigger:** Backfill complete (done) AND recovery complete
- **Next review:** 2026-04-15
- **Session size:** 30-45 min

### 3. Social Filter (Speed Demon, Option C strict)
- **State:** READY
- **What:** Twitter required for Stage 1, 90d age + 3k followers for
  Stage 2, fail-closed on API errors.
- **Trigger:** ML training update complete AND first stable day post-TP
- **Next review:** 2026-04-17
- **Session size:** 75-90 min

### CFGI Data Source Decision
- **State:** OBSERVATION — Stage 1 dual-read live since 2026-04-14
- **Finding:** BTC F&G = 21 (Extreme Fear) vs SOL CFGI = 56.5 (Neutral).
  The gap is massive — Solana market sentiment is much more favorable
  than Bitcoin's. This confirms the bot has been under-trading due to
  the wrong sentiment source.
- **Decision pending:** Stage 2 cutover after 24h observation.
  Option (a) cfgi.io SOL is the leading candidate now.
- **Reference:** DASHBOARD_AUDIT.md B-001
- **Next review:** 2026-04-15 (24h after Stage 1 deploy)

---

## NEAR-TERM SHORT LIST (scheduled within 14 days)

### 4. Helius Budget Enforcement (HARD DEADLINE)
- **State:** SCHEDULED -- must be done before April 26 credit reset
- **What:** Global `helius_call()` wrapper with Redis daily counter.
- **Trigger:** Calendar (latest: April 23)
- **Pairs with:** #5 (caching)
- **Next review:** 2026-04-20
- **Session size:** 60-90 min

### 5. Helius Enrichment Caching
- **State:** SCHEDULED -- paired with #4
- **What:** Per-token Redis cache (300s TTL) on 4 uncached enrichment
  functions.
- **Next review:** 2026-04-20

### 6. Broader Feature Default Cleanup
- **State:** READY
- **What:** Audit remaining features in `_build_features` for
  default-to-zero bug. Candidates: bonding_curve_progress,
  market_cap_usd, liquidity_velocity, holder_count.
- **Trigger:** Before ML retrain (#10)
- **Next review:** 2026-04-18
- **Session size:** 60-90 min

### 7. Telegram Yeezus Listener Audit
- **State:** READY
- **What:** Determine current Telethon integration state for
  `cryptoyeezuscalls`.
- **Blocker:** Telegram API credentials may need regeneration
- **Next review:** 2026-04-20
- **Session size:** 30 min

### 8. Telegram Yeezus Exit Schedule
- **State:** BLOCKED on #7
- **What:** Per-source exit schedule override per Jay's spec
  (+300%/+500%/+750%/+1000%/+2000%).
- **Session size:** 15-30 min

---

## MEDIUM-TERM (14-30 days)

### 9.5. Execution Path Audit (read-only forensics)
- **State:** READY -- highest-priority pre-live session
- **What:** Full read-only audit of `execution.py`, `paper_trader.py`,
  and buy/sell code paths. Answers six unknowns about the real
  execution pipeline (code sharing, priority fees, slippage config,
  wallet balance reads, latency budget, error handling).
- **Why:** Everything validated so far is PAPER. The live execution path
  is the single biggest unvalidated assumption.
- **Trigger:** 7 days of post-TP-redesign data + paper profitability
  confirmed
- **Next review:** 2026-04-20
- **Session size:** 60-90 min (writes EXECUTION_AUDIT.md)
- **Risk:** Zero -- read-only

### 9.6. Shadow Mode Implementation
- **State:** BLOCKED on #9.5
- **What:** `SHADOW_MODE` flag in `execution.py`. Constructs + simulates
  transactions without submitting. Logs to `shadow_tx:{mint}:{ts}`.
- **Trigger:** #9.5 complete AND critical issues fixed
- **Next review:** 2026-04-22
- **Session size:** 90-120 min

### 9.7. Micro-Live Validation (Stage 2)
- **State:** BLOCKED on #9.6
- **What:** Secondary wallet, 0.5 SOL, 0.01 SOL/trade, 50 trade cap.
- **Trigger:** #9.6 has 24h of clean shadow data
- **Next review:** 2026-04-24
- **Session size:** 60-90 min + 1-3 days monitoring

### 9.8. Real-Size Live on Main Wallet (Stage 3)
- **State:** BLOCKED on #9.7
- **What:** Flip TEST_MODE=false. Start with 0.05 SOL positions, scale
  up over 7-14 days.
- **Trigger:** #9.7 micro-live has 100+ real trades with success
  criteria met
- **Next review:** 2026-05-01 earliest
- **Absolute rule:** Do not skip stages.

### 10. ML Model Retrain (on corrected labels)
- **State:** BLOCKED on sample count + feature cleanup
- **Trigger:** Backfill done + ML training code updated + feature
  cleanup done + 500+ clean samples
- **Sample projection:** ~70 clean post-fix samples. ETA 2026-04-25
  to 2026-05-05.
- **Next review:** 2026-04-21

### 11. FEATURE_COLUMNS Pruning
- **State:** PAIRED with #10
- **What:** Prune from 55 to ~20 populated features.

### 12. Analyst CFGI Threshold Review
- **State:** READY
- **What:** Decision: keep / lower / remove the CFGI < 20 auto-pause.
- **Trigger:** Backfill complete (corrected data available)
- **Next review:** 2026-04-17
- **Session size:** 30 min analysis only

---

## LONG-TERM (30+ days or triggered by external events)

### 13. Smart Money Wallet Mining -- Sanity Check
- **State:** DEFERRED -- waiting for sample count
- **Trigger:** Winner count >= 50 AND backfill done
- **Next review:** 2026-04-25

### 14. Smart Money Wallet Mining -- Curation Pipeline
- **State:** BLOCKED on #13
- **Trigger:** #13 confirms dataset is dense enough
- **Session size:** 90-120 min

### 15. Smart Money Webhook Monitoring (Helius)
- **State:** BLOCKED on #14 AND Helius credit reset
- **Trigger:** #14 complete AND April 26 credit reset
- **Next review:** 2026-04-28

### 16. Smart Money Entry Trigger Rule
- **State:** BLOCKED on #15
- **Trigger:** #15 stable for 7 days
- **Next review:** 2026-05-05

### 17. Nansen Day-1 Enablement
- **State:** DEFERRED
- **Trigger:** Analyst unpauses OR #14 needs Nansen calls
- **Next review:** 2026-04-25

### 18. Analyst Personality Rework (50-100k pullback strategy)
- **State:** DEFERRED (large multi-session work)
- **Trigger:** #12 + Helius credits + #15 stable
- **Next review:** 2026-05-01
- **Session size:** 2-5 sessions

### 19. Vybe Investigation
- **State:** LOW priority, DEFERRED
- **Trigger:** Only if Helius + Nansen aren't enough
- **Next review:** 2026-05-10

### 20. Governance SQL Type Mismatch (cosmetic)
- **State:** LOW priority
- **Next review:** 2026-05-15
- **Session size:** 15 min

---

## DROPPED (explicitly removed, no longer in backlog)

- **Kronos Foundation Model Integration (ZMN):** Wrong latency, wrong
  pretraining domain. ZMN's edge is on-chain features not OHLCV.
- **Original "Subscribe to Nansen-labeled SM" Architecture:** Finding 3
  killed this. SM labels don't exist at pump.fun scale.
- **ML Feature Expansion:** Blocked until sample count >= 500. Returns
  as option after #10 retrain.
- **ML Score Cap at 65:** Symptom fix for the score inversion. Root cause
  is #10 retrain on corrected labels.
- **Kronos ASX Equities Bot:** PARKED as separate project.

---

## COMPLETED RECENTLY (last 7 days)

- **2026-04-07:** Paper trader price bug fix (9b880e1)
- **2026-04-08:** Tier 2 overnight -- 4 fixes
- **2026-04-09:** Exit strategy fix (bf57117)
- **2026-04-10:** API audit complete
- **2026-04-11:** Entry filter v4 (56421ab)
- **2026-04-12:** Feature default fix (a8a390b)
- **2026-04-12:** Staged TP reporting fix (5b92226)
- **2026-04-13:** Historical backfill (cf16627, 2f76a91)
- **2026-04-13:** Dashboard Tier 1 audit + P/L source fixes (dbbffd3,
  40dadb6, cac5202)
- **2026-04-14:** State audit -- pipeline outage diagnosed (fb8a389)
- **2026-04-14:** Recovery + hardening session -- pipeline restored,
  signal_aggregator hardened with retry + heartbeat (85768c5)
- **2026-04-14:** cfgi.io Stage 1 dual-read -- SOL CFGI = 56.5 vs
  BTC F&G = 21. Dashboard shows both. (146ca38, 859c0fa, 1ac9cb8)

---

## Open Bugs from Other Docs

The following bugs are tracked in dedicated files but referenced here
so the roadmap is the single source of truth for what's open:

- **Dashboard bugs:** DASHBOARD_AUDIT.md Known Bugs Registry
  (B-001 through B-009). Review date: 2026-04-16.
- **Pipeline bugs:** STATE_AUDIT_2026_04_14.md findings. All addressed
  in tonight's recovery session.
- **B-001 (CFGI source)** is cross-cutting -- affects bot_core trading
  behavior, not just dashboard display. Tracked as "CFGI Data Source
  Decision" item in READY section above.
- **B-010 (Governance CFGI hallucination):** Governance LLM consistently
  outputs "CFGI at 50" regardless of actual value. Either the prompt
  template injects a default, or the LLM confabulates. Needs prompt
  audit in a future governance session.

Any bug that sits unreviewed past its review date in those files
gets escalated into this roadmap's main backlog.

---

## THE BIG PICTURE (for Jay's sanity)

The last 7 days was a sequence of interdependent bug fixes that each
unblocked the next. You started with "bot is bleeding money." You end
with "bot is profitable but the reporting was lying." The work wasn't
wasted -- each fix was real, each one moved you forward, and the net
result is:

1. **The bot mechanically works on paper** -- entry, scoring, exit
   strategy all correct
2. **The reporting mechanically works** -- P/L is now recorded correctly
3. **The historical record is cleaned up** -- backfill done
4. **The ML model needs an update to use the cleaned record** -- next
5. **The TP allocation can be optimized** -- after recovery

**THE UNVALIDATED ASSUMPTION:** Everything so far is paper trading.
The real execution path in `execution.py` has never been exercised.
Items #9.5 through #9.8 are the progressive validation chain:

- **#9.5** (read-only audit): understand what the real code does
- **#9.6** (shadow mode): exercise real tx construction without submitting
- **#9.7** (micro-live): 0.5 SOL secondary wallet, 50 trades max
- **#9.8** (real-size live): main wallet, only after micro-live passes

Do not skip stages. No "just flip TEST_MODE=false" on the main wallet.

---

## REVIEW CADENCE

- **Daily during active deploy weeks** -- check top 3 priority items
- **Weekly when stable** -- review all READY + SCHEDULED items, re-date
- **Triggered** -- when an item hits its trigger condition, re-evaluate
  immediately

Items sitting in DEFERRED for 30+ days without status change get either
DROPPED or explicitly re-scheduled with a new trigger. No drift.

---

## SESSION ENERGY BUDGET

**Rules:**
- ONE substantive lever per session
- Verification windows BEFORE tuning (24h+ minimum)
- All deploys must have auto-revert conditions
- All thresholds env-var-configurable for kill switch
- Read-only diagnostic prompts BEFORE write prompts on ambiguous items

---

## REFERENCES

- `MONITORING_LOG.md` -- chronological session log
- `AGENT_CONTEXT.md` -- bot architecture reference
- `CLAUDE.md` -- agent instructions
- `DASHBOARD_AUDIT.md` -- panel-by-panel findings + Known Bugs Registry
- `STATE_AUDIT_2026_04_14.md` -- pipeline outage diagnosis
- `STAGED_TP_BACKFILL_REPORT.md` -- historical P/L correction
- `API_AUDIT_REPORT.md` -- Helius/Nansen/Vybe state
- `SMART_MONEY_DIAGNOSTIC.md` -- Nansen capability map
- `POST_TIER2_DIAGNOSIS.md` -- bot health snapshot post Tier 2
