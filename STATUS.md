# ZMN STATUS — operational journal

> Newest entry at top. Append-only. Never rewrite history.
> Every CC session appends an entry. Upload this to every Claude chat.
>
> See CLAUDE.md § "STATUS.md — single-file state tracker" for the convention.

---

## 2026-04-30 — TUNE-010 DEX-PAID-FEATURE-EVALUATION (Verdict: DISCARD, no deploy)

**Committed (this session):** `<hash>` docs(audit): TUNE-010 dex_paid feature evaluation — verdict DISCARD. Files: `docs/audits/TUNE_010_DEX_PAID_EVALUATION_2026_04_30.md` (NEW, 10 sections) + STATUS.md prepend + ZMN_ROADMAP.md (TUNE-010 row added). **Docs-only. No services/, no env vars, no Redis writes, no Railway deploys.**

**State changes:** none. Read-only Postgres asyncpg via `DATABASE_PUBLIC_URL`. 636 DexScreener API calls (2 endpoints × 318 mints), 0 rate-limits, 0 errors. ~5 SQL queries on `paper_trades`.

**Bot state:** unchanged from prior entry. TEST_MODE=true on bot_core, signal_aggregator, all services except treasury (TREASURY-TEST-MODE-002 🟡). 0 paper open. On-chain wallet 0.064 SOL. Bitfoot's `dex_paid` filter does not reproduce on Analyst's token universe.

**Verdict: DISCARD.** No env-var change. No code change. No deploy. Hypothesis ("paid DEX promotion correlates with team marketing → better outcomes for higher-MC personalities") is **not supported by the data** for Analyst:

- **Sample:** 304 closed Analyst trades (2026-04-22 → 2026-04-28); Whale Tracker has zero historical trades (dormant). Sample n=304 is well above the 100-trade threshold for valid inference.
- **DexScreener `/orders/v1/{chainId}/{tokenAddress}` exposes `paymentTimestamp`** — enabled timestamp-aware "paid AT entry time" analysis. Sidesteps the Step-4 Scenario A/B problem the prompt anticipated. 318/318 mints looked up cleanly (0 errors).
- **Primary feature `dex_paid_at_entry` (timestamp-aware) inverts vs hypothesis:** PAID (n=164) WR=14.0% vs NOT_PAID (n=140) WR=17.9%. Diff -3.83pp. PnL/trade diff = +0.0001 SOL (zero discriminatory power). fisher_p=0.43, MWU p=0.40. Cohen's h=-0.105 (below "small effect"); Cliff's delta=-0.056.
- **Base-rate problem:** 76.6% of Analyst's tokens are paid lifetime, 53.9% paid at entry. Feature too prevalent to discriminate well — there's not enough variance to exploit.
- **Best secondary feature `social_count > 0`: WR diff +5.62pp** but p=0.25 (not significant) and PnL/trade diff +0.0021 SOL (far below the 0.02 deploy threshold). Below all deploy criteria.
- **SD scope exclusion was correct:** 0/14 SD big winners (≥0.10 SOL post-recovery) have any DexScreener footprint — all 14 have `no_pair=True` (rugged or never-graduated). SD enters and exits before any DEX promotion could exist.

**No deploy criterion is met by any feature tested.** Verdict-changing conditions documented in audit §7: (a) Analyst reactivated + 200 new trades in a different market regime; (b) ANALYST-POST-GRAD-001 (post-graduation MC $50-300k personality) accumulates a sample where DEX-pair existence is the norm and dex_paid variance is non-trivial; (c) Whale Tracker activated with a meaningful sample.

**Whale Tracker has zero closed historical trades — cannot evaluate.** Documented as a study limitation, not a blocker.

**Blockers cleared:** none structurally — TUNE-010 evaluated and resolved as DISCARD.

**Blockers new/active:** All carry blockers unchanged from BUG-022-FIX entry below: TREASURY-TEST-MODE-002 🟡, ML-THRESHOLD-DRIFT-2026-04-29 🟡, LIVE-FEE-CAPTURE-001 🔥, LIVE-PNL-FEE-FORMULA-001 🔥. TUNE-009 ⏸ DEFERRED (revisit conditions in SD-EARLY-CHECK audit §10).

**Stop-condition check:** N/A (no deploy). 0/4 stop conditions tripped (DexScreener returned dex_paid data; sample n=304 ≥ 30 threshold; not Scenario B by methodology; failed_lookups.txt empty).

**Next prompt:** No follow-up implementation prompt — DISCARD verdict. TUNE-011 (Bitfoot speed-tests vs Helius latency) remains separately scoped per session prompt's "Chain followup" note. ANALYST-POST-GRAD-001 design session unblocked — independent of TUNE-010 outcome.

**Pending Claude-chat prompts not yet pasted:** carry — `SESSION_SD_MC_CEILING_DEPLOY_2026_04_29` (gate on 24h-post-recovery threshold).

**Verdict:** TUNE-010 ❌ DISCARD. dex_paid feature does not earn shelf space in `signal_aggregator.py` for Analyst. SD scope exclusion confirmed correct. Whale Tracker un-evaluable.

---

## 2026-04-30 — BUG-022-FIX-2026-04-30 (Option A landed — backfill + inline write + CLAUDE.md updates)

**Committed (this session):** `<hash>` fix(paper_trader): BUG-022 backfill + inline write; CLAUDE.md updates. Files: `services/paper_trader.py` (close UPDATE extended with corrected_*) + `services/bot_core.py` (staged-TP correction UPDATE extended with corrected_* for paper branch only) + `CLAUDE.md` (P/L rule rewrite + wallet-drift note appended) + `docs/audits/BUG_022_FIX_2026_04_30.md` (NEW, 8 sections) + STATUS.md prepend + ZMN_ROADMAP.md (BUG-022 ✅ + WALLET-DRIFT ✅).

**State changes:**
- DB: 1111 closed paper_trades rows backfilled with `corrected_pnl_sol = realised_pnl_sol, correction_method='pass_through', correction_applied_at=NOW()`. Single transaction, max_diff = 0.0 (identity preserved).
- Code: `services/paper_trader.py:392-407` close UPDATE now writes corrected_* inline. `services/bot_core.py:1059-1078` staged-TP correction UPDATE now writes corrected_* in TEST_MODE branch (split conditional to keep trades-table branch identical).
- CLAUDE.md: "Trade P/L Analysis Rule" rewritten to reflect post-FEE-MODEL-001 + post-BUG-022 reality (both columns interchangeable; live writes `live_estimated_v1`). "Live trading mode" block appended with 2026-04-21 1.5 SOL transfer note (Branch 1 confirmed).
- No env vars touched. No Redis writes. Single git push triggers bot_core redeploy.

**Bot state:** RUNNING (verified pre-fix via Redis MCP — bot:status.status=RUNNING, test_mode=true, 0 open positions, signals:scored=0, consecutive_losses=1). Daily PnL -0.02 SOL, market_mode=DEFENSIVE, portfolio 24.35 SOL (paper).

**Pre-conditions verified:** signals:scored=0 (well below 200 STOP); bot not EMERGENCY_STOPPED; 1111 NULL closed rows (work to do).

**Verification (Step 2 SQL):**
```
BEFORE: total_closed=1111  null_closed=1111  pre_pass_through=0
AFTER:  total_closed=1111  null_closed=0  pass_through=1111
        max(|corrected - realised|) = 0.0
```

Spot-check 3 most recent rows: id 7740/7741/7742, all show `corrected_pnl_sol = realised_pnl_sol` exactly, method=pass_through, applied 2026-04-30 07:18:09 UTC.

**Compile check:** `python -m py_compile services/paper_trader.py services/bot_core.py` → OK.

**Step 8 verification queued:** post-deploy poll Railway MCP for bot_core SUCCESS, wait 90s, query last 5 closed rows for inline corrected_* population. Result will be appended to audit doc §5.

**Blockers cleared:**
- ✅ **BUG-022 fix execution** — Option A landed (backfill + inline write at both close-time UPDATE sites). Re-evaluate via 24h check that fresh post-deploy rows write corrected_* correctly.
- ✅ **WALLET-DRIFT-2026-04-29** — CLAUDE.md note now reflects Branch 1 confirmation. Mechanical layer (top-up) remains as a V5a precondition tracked separately.

**Blockers new/active:**
- 📋 **TUNE-009 (DEFERRED)** — carry from Session A; re-evaluate post Session C + observation.
- All other carry blockers unchanged: TREASURY-TEST-MODE-002 🟡, ML-THRESHOLD-DRIFT-2026-04-29 🟡, LIVE-FEE-CAPTURE-001 🔥 (Session D), LIVE-PNL-FEE-FORMULA-001 🔥 (Session D).

**Stop-condition check:** 0 of 4 STOP conditions tripped at this point. Backfill assertion passed (null=0, max_diff=0). bot_core deploy verification still pending.

**Next prompt:** **SESSION C (SD_MC_CEILING_DEPLOY)** — proceeding immediately. C touches signal_aggregator (different service from B's bot_core), so deploy queues are independent. Per chain prerequisite, C requires "Sessions A/B completed and bot_core stable for ≥30 min" — A had no deploy, B's deploy will be in flight when C is committed; C's deploy queues independently on signal_aggregator.

**Pending Claude-chat prompts not yet pasted:** Sessions C, D, E queued and pasted in this CC session — proceeding through chain.

**Verdict:** BUG-022 ✅ COMPLETED 2026-04-30 via Option A. CLAUDE.md rules rewritten + wallet-drift note appended.

---

## 2026-04-30 — SD-EARLY-CHECK-RELAX-2026-04-30 (Verdict: Option Gamma — DEFER, no deploy)

**Committed (this session):** `<hash>` docs(audit): SD-EARLY-CHECK-RELAX-2026-04-30 verdict Gamma. Files: `docs/audits/SD_EARLY_CHECK_RELAX_2026_04_30.md` (NEW, 12 sections) + STATUS.md prepend + ZMN_ROADMAP.md (TUNE-009 row added). **Docs-only. No services/, no env vars, no Redis, no Railway deploys.**

**State changes:** none. Read-only Postgres asyncpg via `DATABASE_PUBLIC_URL`. ~5 SQL queries on `paper_trades` (post-recovery window > 2026-04-28 13:00 UTC).

**Bot state:** unchanged from prior entry. TEST_MODE=true on bot_core, signal_aggregator (verified via Railway MCP at session start). Bot RUNNING (signal_aggregator health within last few minutes per env audit). 0 paper open at audit time.

**Verdict: Option Gamma — DEFER.** No env-var change. No code change. No deploy. The session prompt's working hypothesis ("the check kills winners that break out *after* 60s") is **not supported by the data**:

- **Mechanism confirmed (`services/bot_core.py:1590-1604`):** single-check, env-driven. Window opens at 50s with `SD_EARLY_CHECK_SECONDS=60`, closes at 90s. Threshold `SD_EARLY_MIN_MOVE_PCT=3.0`. Label `no_momentum_90s` is legacy from when code default was 90s — purely cosmetic mismatch.
- **123 dead trades clustered exactly in 50.03-51.97s window** (perfect signature of the check firing at first poll after window opens). 0% WR, -2.915 SOL bleed.
- **DECISIVE: dead-trade pnl_pct distribution rules out all relaxation options.** Mean exit pnl = -17.37%, median -16.12%, max -1.85%, min -39.15%. **Zero trades in the 1-3% slow-starter band that Alpha-A would save.** 100/123 (81%) are deeply negative (<-10%); 39/123 are already past the -20% stop_loss threshold (escaped early due to no price tick).
- **13 big winners post-recovery (≥0.10 SOL) all bypassed the check:** 2 hit `staged_tp_+1000%` at <2s (rocket starters, immune); 11 hit `TRAILING_STOP` at ~600s (survived 50-90s window with ≥3% pnl). **Zero big winners in the kill window.**
- **Structural fix is upstream (Session C SD_MC_CEILING_USD=3000):** 97.6% (120/123) of dead trades enter at MC $800-$3000, but Session C's $3k ceiling only filters 3/123 of current bleed. Most bleed is below the ceiling. Out of scope for this session — defer to post-observation.

**Why not Alpha (relax)?** Every relaxation option (drop min_move 3.0 → 1.0, raise check_seconds 60 → 180, disable check) would either save zero trades or convert -0.024/trade no_momentum exits into larger stop_loss exits (per CLAUDE.md FEE-MODEL note: ~-0.074/trade typical stop_loss). Net effect of relaxation on this population: neutral-to-worse.

**Why not Beta (code change)?** Same conclusion. The check is a single env-driven mechanism. There's no separate hardcoded 90s check to disable.

**Why Gamma (defer)?** The check is doing its designed job efficiently — cutting failed-momentum tokens at 50-52s with -0.024/trade cost vs the alternative -0.074/trade if they continued to stop_loss. The bleed is real but the check is not the cause; high-MC entry is. Re-evaluate after Session C lands and 24-48h observation.

**Blockers cleared:** none structurally — TUNE-009 evaluated and resolved as DEFERRED.

**Blockers new/active:**
- 📋 **TUNE-009 (DEFERRED)** — re-evaluate SD_EARLY_CHECK relaxation after Sessions B/C/D + 24-48h observation window. See audit §10 for the four conditions that would re-trigger evaluation.
- All other carry blockers unchanged (TREASURY-TEST-MODE-002 🟡, ML-THRESHOLD-DRIFT-2026-04-29 🟡, LIVE-FEE-CAPTURE-001 🔥, LIVE-PNL-FEE-FORMULA-001 🔥, BUG-022 fix execution 📋, WALLET-DRIFT 🟢 Branch 1 confirmed by Jay → resolved).

**Stop-condition check:** N/A (no deploy).

**Next prompt:** **SESSION B (BUG_022_FIX)** — proceeding immediately. Per chain prerequisites, B requires "Session A committed and bot_core redeploy SUCCEEDED". Since A is Gamma (no redeploy), the spirit of the prerequisite is satisfied: A is committed, no destabilizing change to wait on. Continuing.

**Pending Claude-chat prompts not yet pasted:** Sessions C, D, E queued and pasted in this CC session — proceeding through chain.

**Verdict:** TUNE-009 ⏸ DEFERRED. Empirical evidence rules out relaxation; structural fix lives at entry filter (Session C scope).

---

## 2026-04-30 — WALLET-DRIFT-INVESTIGATION-2026-04-29 (Outcome C — pending user confirmation)

**Committed (this session):** `<hash>` docs(audit): WALLET-DRIFT-INVESTIGATION-2026-04-29 reconciliation [outcome C]. Files: `docs/audits/WALLET_DRIFT_INVESTIGATION_2026_04_29.md` (NEW, 9 sections) + STATUS.md prepend + ZMN_ROADMAP.md (WALLET-DRIFT-2026-04-29 row updated + changelog entry). Read-only. No services/, no env, no Redis, no DB writes, no Railway deploys.

**State changes:** none. Read-only Helius MCP (`getBalance`, `getTransactionHistory mode=signatures`, `parseTransactions`) + Postgres asyncpg via `DATABASE_PUBLIC_URL` (read-only). Helius credit cost: ~210 (1 getBalance + 10 getTransactionHistory + 100 parseTransactions × 1 batch of 8 + 100 budget for retries).

**Bot state:** unchanged from 2026-04-29 12:39 UTC entry. TEST_MODE=true on bot_core, signal_aggregator, all services except treasury (still TEST_MODE=false — TREASURY-TEST-MODE-002 still 🟡). `paper:positions:*` = 0. `bot:open_positions:*` = 0. `bot:consecutive_losses=1`. On-chain wallet `4h4pstXd…ii8xJ` = **0.064095633 SOL** (Helius getBalance — unchanged from env audit, no movement in 9 days). On-chain wallet idle since 2026-04-21 10:05:55 UTC.

**Verdict: Outcome C — drain explained by trades + UNDOCUMENTED transfer.** Reconciliation gap = **0 lamports** (sub-1e-9 SOL). Eight on-chain transactions in window 2026-04-19 → present; six are documented (1 ELONX dust sale, 4 yh3n441 entries/exits/related, 1 failed 3rd-party tx with no balance impact); **one is undocumented**:

- **2026-04-21 10:04:48 UTC** (= 20:04:48 AEDT, ~13h after Session 5 v4 rollback flip-back). Sig `42dnuS1xv…`. Type: System Program TRANSFER. **−1.50008 SOL** outgoing from `4h4pstXd…ii8xJ` to **`7DSQ3ktYiirRfs4YQojyDTqUM9Cwj9YgzwwegyiCAgUy`**. Fee payer = trading wallet (signed with its private key). Destination address has **zero references** in the repo (`grep -r 7DSQ3ktY .` returns no matches; not in CLAUDE.md, AGENT_CONTEXT.md, STATUS.md, ROADMAP, audits, services, .env). Holding wallet is `2gfHQvyQ…` — not a match.

**Critical clarification on `paper_trades` "live" rows:** the session prompt's working hypothesis was that the 6 live rows summing to −3.21 SOL realised PnL would explain the drain. **5 of those 6 rows have NULL entry/exit signatures** — they are reconcile-residual paper-position force-closures from the Session 5 v4 live window (per `session_outputs/ZMN_LIVE_ROLLBACK.md` lines 96-122). They had **no on-chain SOL effect**. Only id 6580 (`yh3n441J`) was a real on-chain round-trip — net −0.094245 SOL, exactly matching `ZMN_LIVE_ROLLBACK.md`'s "Final wallet" delta. The drain math required a separate non-trade explanation; the 1.5 SOL transfer is it.

**Walk-forward sanity check (3 independent reference points all match to sub-lamport precision):**
- `1b40df3` deep-recon (2026-04-19 ~04:40 UTC): 1.610 SOL ← matches predicted starting balance 1.610389092 (gap < 0.001, rounding)
- `ZMN_LIVE_ROLLBACK.md` T0 (1.658400592) and Final (1.564155614) ← match walk-forward exactly
- `ENV_AUDIT_2026_04_29.md` §7 (0.064095633) ← matches walk-forward exactly

**3 dust-phishing txs at 10:05:38 + 10:05:55 UTC** observed (50s + 67s after the 1.5 SOL transfer). One sender's address (`7DSQVNcXR…AgUy`) shares both prefix `7DSQ` and suffix `AgUy` with the 1.5 SOL destination — vanity-address mimicry consistent with on-chain dust-phishing. Combined inbound dust: 0.000020019 SOL. **No security impact** (write-only attacker operation), but flagged as a hygiene note: never copy-paste a destination from this wallet's tx history without verifying the full address.

**V5a wallet-blocker disposition: 🔥 → 🟡 PENDING_USER_CONFIRMATION.** Two layers:
1. **Mechanical:** wallet 0.064 SOL << `MIN_POSITION_SOL=0.05/0.15` × wallet-fraction floor; needs top-up to ≥ 1.5-2.5 SOL before V5a can open positions (per `LIVE_FEE_MODEL_AUDIT_2026_04_29.md` §6).
2. **Confirmation pending:** Jay confirms intent on the 2026-04-21 1.5 SOL outflow before any further V5a-chain sessions. Three branches:
   - **Branch 1 (benign — Jay's wallet / consolidation / exchange deposit):** blocker collapses to layer 1 only (top-up). STATUS gets a backfill entry with what the transfer was for.
   - **Branch 2 (intentional but to a ZMN-related address Jay doesn't remember at the moment):** same as Branch 1 functionally; STATUS backfill should record both the address's role + why it wasn't logged at the time.
   - **Branch 3 (unintended/unauthorized):** escalate to Outcome D treatment. Halt V5a discussion; next session is security investigation (rotate `TRADING_WALLET_PRIVATE_KEY`, audit machine that signed the tx between 2026-04-20 21:00 and 2026-04-21 10:05 UTC, enumerate other wallets from same seed). 9-day post-transfer idle period is mildly reassuring but not conclusive.

**Recommendation:** confirm Branch before any further V5a-chain sessions (BUG-022 fix, LIVE-FEE-CAPTURE-001 Path A, LIVE-PNL-FEE-FORMULA-001). Other sessions don't depend on the wallet being topped up, but starting them while wallet security state is unconfirmed adds risk-surface without benefit.

**Blockers cleared:** none structurally — drain is reconciled but disposition pending Jay.

**Blockers new/active:**
- **WALLET-DRIFT-2026-04-29** 🔥 → 🟡 PENDING_USER_CONFIRMATION (status flipped). Awaiting Branch 1/2/3 confirmation from Jay.
- All other carry blockers unchanged: TREASURY-TEST-MODE-002 🟡 (env audit), ML-THRESHOLD-DRIFT-2026-04-29 🟡 (env audit), LIVE-FEE-CAPTURE-001 🔥, LIVE-PNL-FEE-FORMULA-001 🔥, BUG-022 fix execution 📋.

**Side findings (not action items):**
- 5 of 6 `paper_trades.trade_mode='live'` rows are reconcile-residual paper closures, not real on-chain trades. Implications for `LIVE-ROW-BACKFILL-001`: only id 6580 needs FEE-MODEL-001-style backfill; the other 5 are already-correct accounting fictions (the SOL was spent at v4 entry into the `trades` table; the `paper_trades` rows just record the close).
- CLAUDE.md "Live trading mode — session-gated" block currently says "Wallet moved 5.0 → ~1.6 SOL via real trades (~3.4 SOL net cost)." That covers v4 (2026-04-16/17). Does not cover the 2026-04-21 1.5 SOL outflow. Recommend a 5-min Tier 1 docs session to append: "Wallet then moved 1.564 → 0.064 SOL on 2026-04-21 10:04:48 UTC via a single 1.5 SOL outgoing transfer to `7DSQ3ktY…AgUy` (sig `42dnuS1…`); see `WALLET_DRIFT_INVESTIGATION_2026_04_29.md`. Awaiting transfer-intent confirmation." Defer execution of this until Jay's branch confirmation.

**Stop-condition check:** 0 of 4 STOP conditions tripped. Helius RPC stable (1 getBalance + 1 getTransactionHistory + 1 parseTransactions, no rate-limits); total signatures in window = 8 (≪ 500 threshold); reconciliation gap < 0.5 SOL; getTransaction data returned cleanly on all 8 sigs.

**Next prompt:** Jay confirms Branch on the 2026-04-21 1.5 SOL transfer. After that:
- Branch 1/2 → `SESSION_BUG_022_FIX_2026_04_29` (next), then `SESSION_LIVE_FEE_CAPTURE_PATH_A`, then top-up + MC-ceiling deploy + V5a flip per `ENV_AUDIT_2026_04_29.md` §8 priority order.
- Branch 3 → security investigation prompt (drafted only after Jay confirms unintended).

**Pending Claude-chat prompts not yet pasted:** carry — `SESSION_BUG_022_FIX_2026_04_29`, `SESSION_SD_MC_CEILING_DEPLOY_2026_04_29` (wait until ≥ 2026-04-30 13:00 UTC for 24h-post-recovery threshold).

---

## 2026-04-29 12:39 UTC — ENV-AUDIT-2026-04-29 (read-only ground truth)

**Committed (this session):** `<hash>` docs(audit): ENV-AUDIT-2026-04-29 ground-truth Railway/Redis/DB inventory. Files: `docs/audits/ENV_AUDIT_2026_04_29.md` (NEW) + STATUS.md prepend + ZMN_ROADMAP.md (3 new Tier 1 rows + changelog entry). Read-only. No services/ touch, no env changes, no Redis writes, no Railway deploys.

**State changes:** none. Read-only audit via Railway MCP `list-variables` (8 services), Redis MCP via Python (REDIS_PUBLIC_URL), Postgres via asyncpg (DATABASE_PUBLIC_URL), Helius MCP `getBalance` for trading + holding wallets.

**Bot state:** RUNNING. TEST_MODE=true on bot_core, signal_aggregator, all services EXCEPT treasury (which is `false` — flagged below). bot_core started 2026-04-29 09:48:27 UTC; signal_aggregator health TS=12:39:11 UTC. 0 paper open. bot:consecutive_losses=1. market:mode:override=NORMAL TTL ~38 min. (Confirms the LIVE-FEE-MODEL-AUDIT entry below was written from a stale post-recovery snapshot — bot is actually online.)

**🔥 New blockers from audit (3) — complementary to LIVE-FEE-MODEL-AUDIT findings:**
- **WALLET-DRIFT-2026-04-29 🔥** — Trading wallet `4h4pstXd…` on-chain = **0.064 SOL** (Helius getBalance, 12:39 UTC). Last documented value in CLAUDE.md / `1b40df3` v4 forensics: ~1.6 SOL. Drop of ~1.5 SOL is unaccounted for in any STATUS / ZMN_ROADMAP / audit entry. Bot has been TEST_MODE=true since the 2026-04-25 21:52 EMERGENCY_STOP, so this is NOT bot-driven. Possible: undocumented manual transfer, additional unsupervised live window, or compromise. **Confirms LIVE-FEE-MODEL-AUDIT's "V5a BLOCKED until trading wallet ≥ 1.5 SOL" finding from a different angle.** Recommended next: Helius `getWalletTransfers(4h4pstXd…)` since 2026-04-19 to attribute the outflows.
- **TREASURY-TEST-MODE-002 🟡** — `treasury` service has `TEST_MODE=false`. All other services are `true`. Trigger=30.0 SOL, currently dormant (wallet=0.064), but a hidden risk if wallet ever crosses 30. Either flip to `true` for safety while supervised, or document the intent.
- **ML-THRESHOLD-DRIFT-2026-04-29 🟡** — `ML_THRESHOLD_SPEED_DEMON` drifts: signal_aggregator=65, bot_core=40, web=45. Last 100 closes contain 44 entries with `ml_score ∈ (0,40]` — confirms Jay's chat-side observation that "(0,40] band has 76 trades suggesting threshold ≠ 40". The (40,50] band turned negative (-0.42 SOL on n=27). `AGGRESSIVE_PAPER_TRADING=true` on SA + bot_core appears to bypass the SA gate for paper. Code-path investigation deferred.

**🟢 Audit confirmations (no action):**
- BUG-022 unchanged: 1080/1080 closed paper rows still NULL on `corrected_pnl_sol` (was 853 at `ca4812d`; +227 since). Fix execution still queued.
- userMem TPs (`STAGED_TAKE_PROFITS_JSON=[[2.0,0.2][5.0,0.375][10.0,1.0]]`) confirmed on bot_core. ✅
- userMem trail (no breakeven lock) confirmed on bot_core; actual schedule is 5-tier `[[0.10,0.30][0.50,0.25][1.00,0.20][2.00,0.15][5.00,0.12]]`.
- TUNE-005-ROLLBACK: `HOLDER_COUNT_MIN=1` confirmed live. ✅
- Speed Demon-only on last 100 closes (ANALYST-DISABLE-002 effective). ✅
- LIVE-FEE-MODEL-AUDIT verdict (live PnL omits fees, live rows have fees_sol=slippage_pct=0): independently observed in §4.3 — last 100 mix is 100% paper, so my sample doesn't reach those live rows; agree with their finding from a different angle (no contradictions).

**🟢 Side findings (deferred):**
- `signals:scored` LLEN=89 (recovery cleared 337→0 on 2026-04-28; regrew to 89 in ~24h — bot_core consumes slower than SA produces). Below 100 STOP threshold.
- `nansen:disabled` Redis TTL EXPIRED. Daily renewal lapsed. Combined with `NANSEN_DAILY_BUDGET=2000` on signal_aggregator/ml_engine/signal_listener, Nansen calls could be firing.
- `signals:raw` LLEN=2,908,957 — slow memory leak, no TTL/trim.
- `bot_core:health` Redis key absent (only signal_aggregator writes one).
- `governance:latest_decision.analyst_enabled = true` — Redis override clobbered (load-bearing now is the env-var via ANALYST-DISABLE-002 code fix; matches halflife caveat in 2026-04-28 entry).
- Two different Nansen API keys in production across services (SEC-001 split-key state).
- railway.toml has no `paths` filter → RAILWAY-REDEPLOY-DISCIPLINE-001 likely real (bot_core restart at 09:48 followed docs commit `5706d7e` at 09:34 with no other apparent trigger).
- Railway CLI v4.6.0 (need v4.10.0+ for `list-deployments`) — partial-block on Step 5.

**Stop-condition check:** 0 of 5 STOP conditions tripped. bot_core TEST_MODE=true, `signals:scored=89` (<100), all services reachable, DB OK, no EMERGENCY_STOP.

**Next prompt:** my recommendation: `SESSION_WALLET_DRIFT_INVESTIGATION` (15-30m read-only Helius forensics) BEFORE `SESSION_BUG_022_FIX_2026_04_29` and BEFORE LIVE-FEE-CAPTURE-001. The wallet drain is the most operationally surprising finding and unblocks (or escalates) any V5a discussion.

**Pending Claude-chat prompts not yet pasted:**
- `SESSION_BUG_022_FIX_2026_04_29` (carry — recommended after WALLET-DRIFT clears)
- `SESSION_LIVE_FEE_MODEL_AUDIT_2026_04_29` ✅ COMPLETED `a208aa5` (this morning)
- `SESSION_SD_MC_CEILING_DEPLOY_2026_04_29` (wait 24-48h after Apr 28 13:02 UTC recovery — earliest ~2026-04-30 13:00 UTC)

**Verdict:** Audit complete. Ground truth captured. **Three new blockers (1 🔥 + 2 🟡)**, three confirmations, several side findings. Audit doc: `docs/audits/ENV_AUDIT_2026_04_29.md`.

---

## 2026-04-29 — LIVE-FEE-MODEL-AUDIT-2026-04-29 (read-only)

**Committed (this session):** `<hash>` docs(audit): LIVE-FEE-MODEL-AUDIT-2026-04-29 paper/live divergence check. Files: `docs/audits/LIVE_FEE_MODEL_AUDIT_2026_04_29.md` (new) + STATUS.md + ZMN_ROADMAP.md. **Docs-only. No services/ touch. No env changes. No deploys.**

**State changes:** none.

**Bot state:** unchanged this session (EMERGENCY_STOPPED carry from 2026-04-25; SILENCE-RECOVERY still pending). TEST_MODE=true.

**Verdict:** **MAJOR DIVERGENCE between live and paper PnL/fee math.** Four load-bearing differences:
1. Live PnL formula at `bot_core.py:1232` is `(exit/entry-1)*amt` — no `- fees` term. Paper has `- fees`.
2. Live writes `slippage_pct=0.0` and `fees_sol=0.0` on every `paper_trades` row (entry INSERT and close UPDATE both omit these columns). Verified empirically on all 6 live rows.
3. Live entry/exit prices are queried RPC prices, not actual fill prices. `execute_trade` returns no fee/price data; bot_core calls `_get_token_price` after success.
4. Live `features_json` is NULL on all 6 historical live rows (live entry path doesn't UPDATE it).
TP/SL trigger logic = parity. Sizing function = parity (calls `risk_manager.calculate_position_size`).

**Spot-check (closed-form on 6 live rows):** all 4 rows with valid prices match `(exit/entry-1)*amt` (no fee subtraction) to ≤ 1e-5 SOL. STOP-condition (>1 row mismatched >1e-3 SOL) NOT tripped — divergence is consistent across all rows. id=6580 v4 yh3n441 trade: paper realised +0.0019 SOL stored, on-chain actual −0.094 SOL — 96× gap explained by fee+slippage omission.

**V5a wallet math (carry):**
- `_max_pos = min(MAX_POSITION_SOL=1.50, wallet * MAX_POSITION_SOL_FRACTION=0.10)`
- At wallet 0.064 SOL: `_max_pos_frac = 0.0064`. `_max_pos = 0.0064`.
- `size_sol = max(MIN_POSITION_SOL=0.15, min(any, 0.0064)) = 0.15`
- 0.15 SOL > 0.064 wallet → swap router rejects with insufficient balance.
- **V5a BLOCKED until trading wallet ≥ 1.5 SOL** (or MIN_POSITION_SOL lowered below FEE-MODEL-001 break-even — not recommended).

**Blockers cleared this session:** none (read-only).

**Blockers new/active (added by this audit):**
- 🔥 **LIVE-FEE-CAPTURE-001 (NEW, V5a-blocking)** — capture actual fee + slippage on live trades; write to `paper_trades.fees_sol` / `slippage_pct`. Path A (use `_simulate_*` from live close path, fast/low-fidelity) unblocks V5a numerical comparability. Path B (Helius `parseTransactions` for actual fill data, slow/high-fidelity) closes divergence completely. Recommended: Path A pre-V5a, Path B as follow-up.
- 🔥 **LIVE-PNL-FEE-FORMULA-001 (NEW, V5a-blocking)** — change `bot_core.py:1232` to subtract fees from live PnL. Pairs with LIVE-FEE-CAPTURE-001.
- **LIVE-ROW-BACKFILL-001 (NEW, high)** — backfill 6 historical live rows with FEE-MODEL-001 estimated fees + slippage; mark `correction_method='live_estimated_v1'`.
- **LIVE-FEATURES-JSON-001 (NEW, medium)** — add features_json UPDATE on live entry path (mirror paper).
- **SIZING-WALLET-FLOOR-001 (NEW, medium-preventative)** — make `bot_core.py:685-690` reject (not floor up) when wallet*fraction < MIN_POSITION_SOL.
- **TIME_PRIME-CONTRADICTION-001 (NEW, low — note for TUNE-006 implementation)** — `bot_core.py:695-696` upsizes 2.0× at AEDT 18-20, contradicting `SD_DEAD_ZONE_001` proposal (worst window).
- **ENV_AUDIT_2026_04_29 (NEW, low — process gap)** — referenced as prerequisite but never produced. Generate before next state-changing live session.
- All prior carry blockers unchanged (SILENCE-RECOVERY still pending; BUG-022 investigated; ANALYST-DISABLE-002 ✅; TUNE-006 stack waiting on recovery).

**Next prompt:** depends on Jay's V5a sequencing preference. Two reasonable orders:
- **(a)** SILENCE-RECOVERY → BUG-022 fix (Option A) → LIVE-FEE-CAPTURE-001 Path A → LIVE-PNL-FEE-FORMULA-001 → V5a wallet transfer → V5a.
- **(b)** Same but interleave LIVE-ROW-BACKFILL-001 with BUG-022 fix (single SQL UPDATE pass; both touch `paper_trades` corrected/fee columns).

**Pending Claude-chat prompts not yet pasted:** unknown — paste-status not visible from CC.

---

## 2026-04-29 09:34 UTC — TUNE-005-ROLLBACK (HOLDER_COUNT_MIN 15 → 1, testing WR-regression hypothesis)

**Committed (this session):** `<hash>` docs(tune): TUNE-005 ROLLED BACK — HOLDER_COUNT_MIN 15 → 1 pending 24h validation. ZMN_ROADMAP.md + STATUS.md only. No services/ changes.

**State changes:**
- Railway env var `HOLDER_COUNT_MIN` on signal_aggregator: **15 → 1** (set via Railway web UI by Jay; auto-redeploy triggered). Verified live via Railway MCP after Jay re-authed mid-session.
- No code changes, no Redis writes, no other env vars touched.

**Bot state:** RUNNING (recovered between sessions via the 2026-04-28 13:10 UTC silence-recovery work). Pre-rollback Redis snapshot: portfolio 24.73 SOL, daily PnL +2.29 SOL, 1 open Speed Demon position, market_mode=NORMAL, consecutive_losses=4, market:mode:override TTL ~4h, signals:scored=0. ANALYST-DISABLE-002 still in effect (no analyst entries observed).

**Rollback theory:** Jay's analysis showed Speed Demon WR dropped 52.9% → 34.9% over 3 days following TUNE-005 deploy (2026-04-23 → 2026-04-26 window). Hypothesis: HOLDER_COUNT_MIN=15 rejected legitimate winners with early holder counts <15, biasing the Speed-Demon-only paper sample toward losers. Roll back to 1 (HOLDER-LOWER baseline from 2026-04-22 session); observe 24h; validate or refute. If WR recovers to ~50% baseline → hypothesis confirmed, TUNE-005 stays rolled back; if WR stays depressed → hypothesis refuted, TUNE-005 reapplied and look elsewhere for the regression cause.

**Verification (post-deploy):**
- Railway MCP listed `HOLDER_COUNT_MIN=1` confirming variable change accepted
- Container swap landed at 2026-04-29 09:27:58 UTC (~12 min after Jay's UI change — Railway build slow, consistent with prior TUNE-005's 17-min build)
- New startup banner observed: `Signal Aggregator starting (TEST_MODE=True, ANALYST_DISABLED=True)` at 09:27:58
- Zero HOLDER reject lines in 5+ min post-swap (gate=1 is permissive — only zero-holder tokens would block; live tokens always have ≥1 holder)
- ML SCORE cadence ~5-7/min post-swap; no errors/exceptions/tracebacks; funnel categories distribute normally (TARGETS / ML / FILTER / RUGCHECK / SD / etc.)

**Side note (operational):** Railway CLI auth was non-interactively broken at session start, blocking both `railway` CLI and `mcp__railway__*` tools (MCP wraps the CLI). User restored access mid-session. Will need a persistent token solution to prevent this recurring (call-out below the formal entry).

**Blockers cleared:** none structurally.

**Blockers new/active:**
- 📋 **TUNE-005-ROLLBACK validation window** — observe 24h of paper trading post-revert (closes ~2026-04-30 09:34 UTC). Success criterion: Speed Demon WR returns toward 50%+ baseline. Outcome decides whether the rollback is codified (HOLDER gate=1 stays) or reverted (TUNE-005 reapplied, look elsewhere for the WR regression cause).
- 📋 **TUNE-005 status** — was ✅ COMPLETED 2026-04-24; now ⏪ ROLLED BACK 2026-04-29 pending validation. If hypothesis confirmed, status becomes ⏪ ROLLED BACK CONFIRMED (TUNE-005 permanently reversed). If refuted, status returns to ✅ COMPLETED with a footnote about the failed validation experiment.
- All other carry blockers unchanged (BUG-022 INVESTIGATED + fix execution queued; SILENCE-RECOVERY-2026-04-28 cleared per the recovery work; DOCS-004 Vybe URL; ANALYST-PAPER-AUDIT-001 legacy retire-vs-retune; HOLDER-DATA-PIPELINE verification window; BITFOOT-2026-BASELINE survivorship caveat; GOVERNANCE-RESILIENCE soft).

**Next prompt:** observation-only for the next 24h. After 09:34 UTC tomorrow, evaluate Speed Demon WR over the rollback window vs the TUNE-005-deployed window and decide outcome.

**Pending Claude-chat prompts not yet pasted:** carry — BUG-022 fix execution session and ANALYST-POST-GRAD-001 design session both still queued.

**Verdict:** TUNE-005 ⏪ ROLLED BACK 2026-04-29 — HOLDER_COUNT_MIN reverted to 1 to test the WR-regression hypothesis. 24h validation window opens. No other changes.

---

## 2026-04-28 13:25 UTC — BUG-022 INVESTIGATED (roadmap mark + verification)

**Committed (this session):** `<hash>` docs(roadmap+status): BUG-022 INVESTIGATED mark + STATUS append. ZMN_ROADMAP.md only (3 status edits) + STATUS.md prepend. **Note:** the audit doc itself (`docs/audits/CORRECTED_PNL_INVESTIGATION_2026_04_28.md`) was already committed in `ca4812d` ~15 min before this session started. This session verified those findings independently and updated the roadmap markers that the prior commit didn't touch.

**State changes:** none. No services/, no env vars, no Redis writes, no Railway deploys. Read-only DB inspection (DATABASE_PUBLIC_URL) for the verification.

**Bot state:** **EMERGENCY_STOPPED** (carried — pre-existing; 2026-04-25 21:52:50 UTC trigger; still 67h+ offline; SILENCE-RECOVERY-2026-04-28 still escalated, NOT cleared). TEST_MODE=true (carried; not re-read). Speed Demon sole active personality (carried; ANALYST-DISABLE-002 still in effect).

**Independent verification of `ca4812d` audit doc findings:**
- DB inspection: 853 of 853 closed paper_trades rows have `corrected_pnl_sol IS NULL` and `correction_method IS NULL`. ID range 6575 → 7484. `correction_applied_at` is NULL on every row. ✅ matches audit doc §2.1.
- Code search: zero `UPDATE…SET corrected_pnl_sol` or `INSERT…corrected_pnl_sol` writes in `services/`. Only `Scripts/rebaseline_paper_edge.py` references the column (read-only at L81). No APScheduler / cron / asyncio.create_task wiring for a correction job. ✅ matches audit doc §2.2.
- Spot-check on 3 simple-exit rows (id 7480, 7482, 7483): `realised_pnl_sol` matches the closed-form `(exit/entry - 1) * amount - fees_sol` formula to <5e-5 SOL. `corrected_pnl_sol` would be `pass_through` identity copy. ✅ matches audit doc §3.1.
- ml_engine.py training query (`services/ml_engine.py:407`) reads from `trades` table not `paper_trades`, and filters on `outcome IS NOT NULL` not `corrected_pnl_sol`. So audit doc §3.4 ML-training caveat ("if the training query filters") is conditional and does NOT apply to the current ml_engine.py — ML retraining is unaffected by the NULL state. (Minor note; doesn't change verdict or fix shape.)

**Roadmap edits (this session):**
- Line 28 "Blocking issues" — BUG-022 from 🔥 NEW MEDIUM to 🟡 INVESTIGATED `ca4812d` with verdict 2a + Option A summary.
- Line 81 critical-path #6 — from 🔥 #1 PRIORITY to 🟡 INVESTIGATED with framing downgrade ("every paper-PnL number is biased" was overstated; directional findings are already correct because all current rows are post-`e078b4c`).
- Line 151 Tier 1 row — full status column update with verdict + Option A recipe + nuance note + spot-check confirmation. Reference to audit + commit hash. Status: 🟡 INVESTIGATED 2026-04-28; fix execution 📋 QUEUED.

**Blockers cleared:**
- **BUG-022 (investigation phase)** ✅ — diagnostic complete, verdict + fix shape documented. **Fix execution remains queued.**

**Blockers new/active:**
- 📋 **BUG-022 fix execution (NEW carry)** — Option A: 5m SQL UPDATE backfill + ~10-line inline write at `services/paper_trader.py` close-time UPDATE (and the parallel sites in `services/bot_core.py:1268` + `1301`). ~30m total. No services/ logic changes; just adds 5 columns to existing close-time UPDATE statements. Recommended after silence recovery.
- 🔥 **SILENCE-RECOVERY-2026-04-28** (carry — bot still EMERGENCY_STOPPED 67h+).
- All other carry blockers unchanged (DOCS-004 Vybe URL; ANALYST-PAPER-AUDIT-001 legacy retire-vs-retune; HOLDER-DATA-PIPELINE verification window; BITFOOT-2026-BASELINE survivorship caveat; GOVERNANCE-RESILIENCE soft).

**Next prompt:** Silence recovery first (per `docs/audits/ANALYST_DISABLE_FIX_2026_04_28.md` §6.3). After that, BUG-022 fix execution session.

**Pending Claude-chat prompts not yet pasted:**
- `/mnt/user-data/outputs/SESSION_CORRECTED_PNL_INVESTIGATION.md` — investigation phase complete this session (`ca4812d` + `<hash>`). The execution-shape session is a new prompt yet to be drafted.
- `/mnt/user-data/outputs/SESSION_ANALYST_POST_GRAD_001_PLAN.md` (carry — design session, ready to paste).

**Verdict:** BUG-022 🟡 INVESTIGATED. Verdict 2a (writer never existed). Recommended fix Option A (~30m next session). Audit doc `ca4812d` is comprehensive; this session's role was independent verification + roadmap marker updates. No code/env/data changes.

---

## 2026-04-28 13:10 UTC — ANALYST-DISABLE-002 (code fix) + bot-silence diagnosis

**Committed (this session):** `9d6e95c` fix(signal_aggregator): ANALYST-DISABLE-002 — gate graduation sniper on env var (services/signal_aggregator.py +17/-2). Plus pending docs commit `<hash2>` for `docs/audits/ANALYST_DISABLE_FIX_2026_04_28.md` + STATUS.md + ZMN_ROADMAP.md.

**State changes:**
- Redis: `governance:latest_decision.analyst_enabled = False` (band-aid re-applied; TTL 86400s; `override_source=ANALYST-DISABLE-REAPPLY-2026-04-28`). Belt-and-suspenders alongside the code fix.
- Code: `services/signal_aggregator.py:_process_graduations` now gates on `ANALYST_DISABLED` env var (line 2443) AND logs `ANALYST_DISABLED=true|false` at startup (line 2436). Live and verified.
- No bot_core code changes. No env var changes. No other Redis writes.

**Bot state:** **EMERGENCY_STOPPED** (pre-existing; 2026-04-25 21:52:50 UTC trigger from analyst leak hitting `DAILY_LOSS_LIMIT_SOL=4.0`). 67h offline. NOT RECOVERED THIS SESSION — see "Blockers new" below. signal_aggregator is healthy and producing signals (~7-8 ML SCORE/min on the new container). TEST_MODE=true. Speed Demon is the only active personality on signal_aggregator.

**Bug findings (paper_trades export 2026-04-28, 835 rows id 6575→7466):**
- 301 analyst trades total (60 pre-disable + 241 post-disable) — `-15.034 SOL` realised
- Speed Demon over same window: 534 trades, +6.064 SOL, 44.6% WR
- **`corrected_pnl_sol` NULL on all 835 rows** (BUG-022 confirmed; out of scope this session)
- Last paper trade: id 7466 at 2026-04-25 21:47:03 UTC (5:47 before the EMERGENCY_STOP trigger)

**Verification (post-deploy):**
- Container swap landed at 2026-04-28 13:08:06 UTC (~17 min after push — Railway build was unusually slow due to fresh dependency download)
- New startup banner observed: `Graduation sniper processor started (ANALYST_DISABLED=True)` at 13:08:07,647
- Zero `GRAD_ACCEPT` / `GRAD_REJECT` / `GRAD_EVAL` events in 2+ min post-swap — function is silently draining the queue as designed
- No errors, no exceptions, no tracebacks

**Blockers cleared:**
- **ANALYST-DISABLE-002 ✅** — code-level gate now defends against governance halflife. Env-var pattern (durable) extended to the leak path that previously bypassed it. Audit: `docs/audits/ANALYST_DISABLE_FIX_2026_04_28.md`.
- **ANALYST-DISABLE-001 halflife concern** — superseded by 002. Band-aid Redis override re-applied as belt-and-suspenders but no longer load-bearing.

**Blockers new/active:**
- 🔥 **SILENCE-RECOVERY-2026-04-28 (NEW — escalated to Jay)** — bot has been EMERGENCY_STOPPED for 67h. Multi-step state cleanup needed (recipe in `docs/audits/ANALYST_DISABLE_FIX_2026_04_28.md` §6.3): reset `bot:consecutive_losses=0`; renew `market:mode:override=NORMAL EX 86400`; **drain stale `signals:scored` queue (337 entries piled up over 67h — replaying risks bot opening positions on stale prices)**; restart bot_core to clear in-memory `self.emergency_stopped`. NOT executed inline because it's three parallel state issues with non-trivial blast radius.
- 🔥 **BUG-022** (carry — `corrected_pnl_sol` NULL on all post-DASH-RESET rows; see prior STATUS entries; remains the recommended next session after silence recovery).
- **GOVERNANCE-RESILIENCE (NEW — soft, deferred)** — bot_core.py:612 fallback `gov.get("analyst_enabled", True)` defaults to True when governance is unavailable. Combined with Anthropic creds-out, this is the structural cause of the 4h halflife. Future hardening: per-personality env-var equivalents (SPEED_DEMON_DISABLED, WHALE_TRACKER_DISABLED) or a fail-closed default. Out of scope; not urgent now that ANALYST-DISABLE-002 closes the analyst-specific path.
- All prior carry blockers unchanged (DOCS-004 Vybe URL; ANALYST-PAPER-AUDIT-001 legacy retire-vs-retune; HOLDER-DATA-PIPELINE verification window; BITFOOT-2026-BASELINE survivorship caveat).

**Next prompt:** Silence-recovery recipe. Per audit doc §6.3 — should be 5–10 min if executed in order. After that, BUG-022.

**Pending Claude-chat prompts not yet pasted:**
- `/mnt/user-data/outputs/SESSION_CORRECTED_PNL_INVESTIGATION.md` (BUG-022 — recommended after silence recovery)
- `/mnt/user-data/outputs/SESSION_ANALYST_POST_GRAD_001_PLAN.md` (design session — Phase-1 summary ready in roadmap entry)

**Verdict:** ANALYST-DISABLE-002 ✅ — analyst leak permanently closed at code level. Bot still offline pending silence-recovery (escalated for explicit go-ahead before executing the 4-step state-cleanup recipe).

---

## 2026-04-24 00:39 AEDT (2026-04-23 14:39 UTC) — TUNE-005 (HOLDER_COUNT_MIN 1→15)

**Committed (this session):** `<hash>` docs(tune): TUNE-005 HOLDER_COUNT_MIN 1→15 rollback post pipeline fix. Touches ZMN_ROADMAP.md + STATUS.md only. No services/, no code.

**State changes:** Railway env var `HOLDER_COUNT_MIN` on signal_aggregator: **1 → 15** (via Railway MCP `set-variables`). Railway auto-redeployed on variable change; old container stopped 14:32:21 UTC, new container started 14:32:10 UTC (staggered rollover). No Redis writes, no Postgres changes, no other env vars touched.

**Bot state:** TEST_MODE=true (confirmed in new container boot log). Analyst disabled (ANALYST_DISABLED=true confirmed). Speed Demon sole active personality. Paper position count not re-read. Redis override for `governance.analyst_enabled: false` from 08:19 UTC entry — status unknown (~16h past, likely clobbered by governance re-run; should be re-applied before next Analyst-sensitive session if halflife matters).

**Blockers cleared:**
  - **TUNE-005** — `HOLDER_COUNT_MIN` gate restored to 15 per intended GATES-V5 design. Post-change verification confirmed zero `HOLDER reject: 0 < 15` pattern (pipeline fix is live) and ML SCORE cadence alive. No 5-min silence; no errors/tracebacks.

**Blockers new/active:**
  - **Cadence observation period opens (carry)** — post-change ML SCORE rate 5-8/min vs ~12/min baseline. May be natural variance (5-min window is small) or a real throughput reduction from the tightened gate. Worth a 24-48h observation before declaring steady-state rate.
  - All other carry blockers unchanged (BUG-022 🔥 `corrected_pnl_sol` NULL; ANALYST-PAPER-AUDIT-001 📋 legacy analyst retire-vs-retune diagnostic; DOCS-004 📋 CLAUDE.md Vybe URL; ANALYST-DISABLE-HALFLIFE re-apply; BITFOOT-2026-BASELINE survivorship caveat).

**Next prompt:** `/mnt/user-data/outputs/SESSION_CORRECTED_PNL_INVESTIGATION.md` — BUG-022 investigation (still the #1 recommended — every paper-PnL number is untrusted until fixed; with TUNE-005 landed, the paper-cadence observation window is now gated more tightly so PnL trust matters more, not less).

**Pending Claude-chat prompts not yet pasted:**
  - `/mnt/user-data/outputs/SESSION_CORRECTED_PNL_INVESTIGATION.md` (BUG-022 — recommended next)
  - `/mnt/user-data/outputs/SESSION_ANALYST_POST_GRAD_001_PLAN.md` (design session — Phase-1 summary ready in ANALYST-POST-GRAD-001 Tier 2 preamble)

**Verdict:** TUNE-005 ✅ — HOLDER gate restored to intended threshold of 15 post pipeline-fix verification. Pipeline remains alive, no breakage detected.

---

## 2026-04-23 13:17 UTC — ROADMAP-CONSOL-2026-04-23-LATE

**Committed (this session):** `<hash>` docs(roadmap): 2026-04-23 late-day consolidation. Touches ZMN_ROADMAP.md + STATUS.md only. Docs-only diff.

**State changes:** none (docs-only). No env vars, no Redis, no Railway deploys, no services/.

**Bot state:** TEST_MODE=true (carried; not re-read). Paper position count not re-read. Analyst disabled status unchanged from 08:19 UTC entry (Redis override may have expired by now, ~5h past the ≤4h halflife — flagged in 13:02 UTC entry).

**Blockers cleared:**
  - ANALYST-DISABLE-001 — tracked as ✅ COMPLETED 2026-04-23 in roadmap Tier 1 table (commit `cc8e5c9` Redis governance override addresses the graduation-sniper bypass).

**Blockers new/active:**
  - 🔥 **BUG-022 (NEW)** — `corrected_pnl_sol` NULL on all 215 post-DASH-RESET paper_trades rows. Correction job not running. Every paper-PnL number quoted in chat/dashboards today is falling back to `realised_pnl_sol`, which per FEE-MODEL-001 is systematically off. Prompt drafted at `/mnt/user-data/outputs/SESSION_CORRECTED_PNL_INVESTIGATION.md`. Recommended as the **next session**.
  - 📋 **ANALYST-PAPER-AUDIT-001 (NEW)** — 45m read-only diagnostic on the pre-existing `analyst` personality that leaked -2.48 SOL / 11.9% WR in 17h. Determine retire vs retune; identify what re-enabled it.
  - 📋 **DOCS-004 (NEW)** — CLAUDE.md Vybe URL fix (`.com` → `.xyz`), 5m.
  - 🟡 **STATUS-CONVENTION-001 (IN_PROGRESS)** — convention landed per 08:01 UTC entry + seeded entries; tracked formally in Tier 1 table.
  - **ANALYST-DISABLE-HALFLIFE (carry from 08:19 UTC)** — governance may have clobbered the Redis override by now. Re-apply before next Analyst-related session.
  - All other carry blockers unchanged (HOLDER-DATA-PIPELINE verification window, Raydium post-grad absent, CLAUDE.md Vybe URL wrong, BITFOOT-2026-BASELINE survivorship caveat).

**Next prompt:** `/mnt/user-data/outputs/SESSION_CORRECTED_PNL_INVESTIGATION.md` — BUG-022 investigation. Recommended #1 because every paper-PnL number right now is untrusted until this is resolved.

**Pending Claude-chat prompts not yet pasted:**
  - `/mnt/user-data/outputs/SESSION_CORRECTED_PNL_INVESTIGATION.md` (BUG-022 — recommended next)
  - `/mnt/user-data/outputs/SESSION_ANALYST_POST_GRAD_001_PLAN.md` (design session; can run after BUG-022 or in parallel if Jay prefers the Phase-1 distilled summary as the design input)

**Verdict:** Roadmap absorbs today's late-day findings. 5 new items + ANALYST-POST-GRAD-001 preamble distillation + critical-path re-sequencing (17 steps). Zero pre-existing items modified.

---

## 2026-04-23 13:02 UTC — BITFOOT-2026-BASELINE (verdict BASELINE-A, caveats)

**Committed (this session):** `<hash>` research(bitfoot): 2026 baseline vs 2025 edge — verdict BASELINE-A. Touches `docs/audits/BITFOOT_2026_BASELINE_2026_04_23.md` (new, committed) + STATUS.md + ZMN_ROADMAP.md. Also local-only under `.tmp_bitfoot2026/`: `sample_2026.py`, `bitfoot2026_sample.csv`, `run_stdout.log` (gitignored dir). No services/, no env vars, no Redis, no Railway deploys.

**State changes:** none (read-only external APIs — GT Demo tier `x-cg-demo-api-key` + Vybe free tier `X-API-KEY`). 0 credits spent. Analyst remains disabled via 08:19 UTC Redis override (will need re-apply before ~12:19 UTC expiration — now ~1h past, governance may have clobbered it; separate check recommended).

**Bot state:** TEST_MODE=true (carried; not re-read this session). Paper position count not re-read. Same as 09:12 UTC entry.

**Blockers cleared:** none strictly — this session is design-input for ANALYST-POST-GRAD-001, doesn't clear a named blocker. Provides concrete 2026 calibration guidance for that work item's upcoming design session.

**Blockers new/active:**
  - **BITFOOT-2026-BASELINE survivorship caveat (NEW)** — hit rates from this session's trending_pools sample (88.9% 2x+, 0% rug on n=18) are bias-inflated. Real-world forward hit rate lies between the dip-sample's 20.5% (biased low) and this session's 88.9% (biased high). Point estimate cannot be derived from either. Forward ROI must be calibrated via live paper observation (BITFOOT-MONITOR-001), not retrospective math.
  - **CLAUDE.md Vybe URL inverted (NEW)** — `CLAUDE.md` line under "Vybe Network MCP" says `API base: https://api.vybenetwork.com (NOT .xyz)`. This is **backwards** — every endpoint on `.com` returns 404; `.xyz` works. Verified on `/v4/tokens/{mint}/top-holders`. Needs a CLAUDE.md fix in a follow-up session.
  - **Raydium post-grad absent in 2026 trending (STRUCTURAL finding)** — 0 of 42 phase-1 candidates on Raydium; 2025 dataset had 39% Raydium. Pump.fun graduations now route pumpswap-first, meteora-second in 2026. Not a blocker, but ANALYST-POST-GRAD-001 execution planning must account for this (and for Meteora's larger winner share — 44% of 2-filter matches vs 10% of 2025 dataset).
  - **ANALYST-DISABLE-HALFLIFE (CARRY from 08:19 UTC)** — governance re-apply needed every ≤4h. Override was set at 08:19 UTC, now ~5h past; likely clobbered. Re-apply should run before next Analyst-related session. (No new action this session.)
  - All other carry blockers unchanged (HOLDER-DATA-PIPELINE verification window, corrected_pnl_sol NULL, SocialData outage auto-topup).

**Next prompt:** SESSION_ANALYST_POST_GRAD_001_PLAN.md (pending from Jay). Must incorporate BOTH DIP-D verdict (from 09:12 UTC session) AND this session's 2026 baseline findings — specifically: (a) drop `dex_paid` rule (untestable on current stack); (b) drop pre-grad `vol/MC < 1.5` gate (un-replicable without pre-grad visibility); (c) expect Meteora to be a meaningful fraction of entries; (d) ROI estimate is un-pinned and must come from paper window.

**Pending Claude-chat prompts not yet pasted:**
  - SESSION_ANALYST_POST_GRAD_001_PLAN.md — now blocked on Jay pasting; should be ready given both prerequisite sessions (dip-sample + 2026-baseline) are complete.

**Verdict:** **BASELINE-A (directionally)** — 2-filter Bitfoot still concentrates winners in 2026 trending post-grad data (16 of 18 hit 2x+). Absolute hit rates inflated by trending_pools survivorship. Design proceeds with revisions.

---

## 2026-04-23 09:12 UTC — BITFOOT-DIP-SAMPLE-001-RETRY (verdict DIP-D)

**Committed (this session):** docs-only — `session_outputs/bitfoot_analysis/BITFOOT_DIP_SAMPLE_DONE.md` + `fetch_dip_peaks.py` (auth header + 180d pre-filter + 401 escalation) + `analyze_dip_results.py` + `bitfoot_dip_results.csv` (99 rows, 39 with data) + `bitfoot_dip_progress.log` + STATUS.md + ZMN_ROADMAP.md. No services/, no env vars, no Redis writes, no Railway deploys.

**State changes:** none (read-only external API — authenticated GeckoTerminal Demo tier, zero credits). ANALYST-DISABLE Redis override from 08:19 UTC entry is still active (TTL expires ~12:19 UTC) — not touched this session.

**Bot state:** TEST_MODE=true (carried from 08:19 UTC; not re-read this session). Paper position count not re-read. Analyst remains disabled via Redis override.

**Blockers cleared:**
  - **BITFOOT-DIP-SAMPLE-001** — verdict **DIP-D**: 8 of 39 retrievable-data rows (20.5%) hit 2x+ post-ping, 4× above the 5% DIP-D threshold. Bitfoot's "unflagged" label is NOT reliable ground-truth for non-winners. Zero losses observed in 39 data rows is almost certainly survivorship bias in the retrievable subset, not signal — 55 of 100 sample rows were unreachable on Demo tier (180-day data retention cap), and GT's pool index curation filters out delisted pools before we see them. Full analysis at `session_outputs/bitfoot_analysis/BITFOOT_DIP_SAMPLE_DONE.md`.

**Blockers new/active:**
  - **ANALYST-POST-GRAD-001 REFRAME (NEW)** — strategy design cannot condition on Bitfoot label output (flagged/unflagged) as an entry filter. Three feature filters (top-10 ≥30% / vol-MC <1.5 / Dex Paid=🔴) remain candidate gates but must be validated prospectively via paper observation, not retroactively against Bitfoot flags. ROI estimate is currently un-pinned and must come from paper window, not historical Bitfoot math. Next design session prompt should incorporate this into §2 (design assumptions) + §6 (ROI framing).
  - **BITFOOT-DIP-SAMPLE-001 bias caveat (carry for future re-derivation)** — zero-losses finding is survivorship bias. If calibrated ROI is required before ANALYST-POST-GRAD-001 goes live, options are (a) CoinGecko Analyst tier subscription (~$150/mo) to recover the 55 unreachable rows, or (b) a second data source (Birdeye with credits; Helius on-chain reconstruction) to capture delisted pools. Neither fit this session's zero-credit scope.
  - **ANALYST-DISABLE-HALFLIFE (CARRY from 08:19 UTC)** — governance service will clobber the Redis override on next write; re-apply every ≤4 hours until proper fix lands.
  - **HOLDER-DATA-PIPELINE verification window (CARRY)** — still in progress (ends ~2026-04-23 23:00 UTC).
  - **corrected_pnl_sol NULL on post-reset rows (CARRY)** — CLEAN-004 correction job not re-wired.

**Next prompt:** SESSION_ANALYST_POST_GRAD_001_PLAN.md (Jay to paste when ready; must incorporate DIP-D verdict into design-assumptions + ROI framing).

**Pending Claude-chat prompts not yet pasted (in `/mnt/user-data/outputs/`; paste-status unknown to CC):**
  - SESSION_ANALYST_POST_GRAD_001_PLAN.md (drafting per prior session's forward pointer; must incorporate DIP-D)

**Verdict:** **DIP-D** — Bitfoot's unflagged label is not reliable ground-truth; 20.5% of unflagged retrievable pings actually hit 2x+.

---

## 2026-04-23 08:19 UTC — ANALYST-DISABLE (Redis-override stopgap)

**Committed (this session):** docs-only — STATUS.md entry + `session_outputs/ZMN_ANALYST_DISABLE_DONE.md`. No code, no Railway deploy.

**State changes:**
  - Redis `governance:latest_decision` — JSON field `analyst_enabled: true → false`, all other fields preserved; `override_source: ANALYST-DISABLE-2026-04-23` added. TTL 86400s.
  - No env vars touched. No service redeployed. `ANALYST_DISABLED=true` was already set on signal_aggregator (and effective for the normal signal path — the leak is the graduation sniper, which bypasses that gate).

**Bot state:** TEST_MODE=true, 1 paper open (`6aRVmWde98RZ`, analyst, pre-override entry — will exit via existing bot_core logic), 0 live open, consecutive_losses=0. Paper portfolio 21.054 SOL (pre-session).
  - Personalities active: **speed_demon** (analyst gated at bot_core:612 via governance override as of 08:11 UTC).

**Recent trade activity (window: last 10 min since override):**
  - analyst: 0 new entries (prior cadence ~2.5/hr from graduation sniper) — early but consistent with gate working.
  - speed_demon: 0 new entries (signal quality gates binding — unrelated to this session).

**Blockers cleared:**
  - **ANALYST-PNL-INVESTIGATION** — root cause identified and mitigated. The leak path was `_process_graduations` at `services/signal_aggregator.py:2418-2538`, which hardcodes `"personality": "analyst"` at line 2521 and pushes to `signals:scored` without checking `ANALYST_DISABLED`. bot_core's only gate for the graduation-sniper analyst was `gov.get("analyst_enabled", True)` at `services/bot_core.py:612`. Governance service is dead (Anthropic credits exhausted), so the Redis key `governance:latest_decision` had `analyst_enabled: true` by default. Redis override now forces False until governance's next write overwrites it.

**Blockers new/active:**
  - **ANALYST-DISABLE-HALFLIFE (NEW)** — governance service writes `governance:latest_decision` with `ex=28800` (8h) and re-runs every `next_review_hours=4`. When it next runs (even in its LLM-failed fallback branch at `services/governance.py:346`), it will SET the key to `GOVERNANCE_DEFAULTS` which has `analyst_enabled: True`, clobbering this override. **Re-apply the override every ≤4 hours until a proper fix lands.** Proper fix options: (a) add `if ANALYST_DISABLED: continue` at `services/signal_aggregator.py:2428` (after `brpop`); (b) flip `GOVERNANCE_DEFAULTS["analyst_enabled"] = False` in `services/governance.py`; (c) add a new Redis key `bot:personality:analyst:force_disable` and a bot_core check. Scope for follow-up session.
  - HOLDER-DATA-PIPELINE verification window still in progress (ends ~2026-04-23 23:00 UTC).
  - `corrected_pnl_sol` NULL on all post-reset rows (CLEAN-004 correction job not re-wired).
  - `market:mode:override` + `nansen:disabled` TTLs had dropped to <15 min at session start — also need daily renewal.

**Next prompt:** (Jay to decide) — candidates: ANALYST-POST-GRAD-001 design (Bitfoot-inspired rewrite) OR proper code-level fix for the halflife (~10-15m).

**Pending Claude-chat prompts not yet pasted (on Jay's machine in `/mnt/user-data/outputs/`; paste-status unknown to CC):**
  - `SESSION_BITFOOT_DIP_SAMPLE.md` (Bitfoot 71% unflagged question — still queued)
  - `SESSION_ANALYST_POST_GRAD_001_PLAN.md` (Bitfoot-inspired rewrite — being drafted per ANALYST-DISABLE prompt's forward pointer)

---

## 2026-04-23 08:01 UTC — STATUS-CONVENTION-001 (seed first entry)

**Committed (this session):** docs-only — CLAUDE.md "STATUS.md — single-file state tracker" section + STATUS.md + STATUS.md.template. Hash recorded in next session's opening state-read.

**State changes:** none. No env vars, no Redis writes, no deploys. State read-only via Railway / Redis / Postgres.

**Bot state:** TEST_MODE=true (paper), 0 paper open, 0 live open, consecutive_losses=0, emergency_stop=None, paper portfolio=21.054 SOL (Redis), SOL=$85.92.
  - Redis `market:mode:override=NORMAL` TTL 817s (⚠ ~13min — due for daily renewal)
  - Redis `nansen:disabled=true` TTL 817s (⚠ ~13min — due for daily renewal)
  - Railway: `HOLDER_COUNT_MIN=1`, `ML_THRESHOLD_SPEED_DEMON=65`, `PRE_FILTER_SCORE_MIN=1.15`, `BUY_SELL_RATIO_MIN=3.0` (signal_aggregator)

**Recent trade activity (last 24h, paper only; entry_time window):**
  - speed_demon: 150 trades closed, +2.517 SOL, 52.00% WR
  - analyst: 59 trades closed, **-2.478 SOL, 11.86% WR**
  - net: +0.039 SOL across 209 closes
  - Latest entry: ~18 min ago; latest exit: ~2026-04-23 07:53 UTC — pipeline alive.

**Blockers cleared:** none this session.

**Blockers new/active:**
  - **ANALYST-PNL-INVESTIGATION (NEW)** — Analyst personality is executing in paper despite CLAUDE.md / ZMN_ROADMAP.md stating `ANALYST_DISABLED=true` and "hard-disabled". 59 trades / -2.48 SOL / 11.86% WR over last 24h. Either the env flag isn't wired into the path that gates analyst entries, or the flag is unset on the actual running service. Decide: pause, tune, or observe-window.
  - **HOLDER-DATA-PIPELINE-001 (CARRY)** — ZMN_ROADMAP.md marks this ✅ FIXED in `fc87b03` + `4c5508b`, but prior session flag said Speed Demon `holder_count=0` on 100% of pipeline reads was still open as of 2026-04-22. Verify post-fix cadence in 24h observation window (ends ~2026-04-23 ~23:00 UTC).
  - **corrected_pnl_sol NULL on all 215 fresh rows (CARRY from CLEAN-004 reset)** — correction-method job appears not to have run since post-reset rows started landing. CLAUDE.md "Trade P/L Analysis Rule" says use `corrected_pnl_sol`; presently only `realised_pnl_sol` is populated on post-reset rows. Does not block trading; does dirty every downstream P/L query unless callers coalesce.

**Next prompt:** none queued (Jay decides based on chat discussion of the two active blockers).

**Pending Claude-chat prompts not yet pasted (on Jay's machine in `/mnt/user-data/outputs/` — CC cannot inspect that path; list reflects Jay's prior chat messaging; paste-status unknown, Jay to confirm):**
  - `SESSION_BITFOOT_DIP_SAMPLE.md` (resolves Bitfoot 71% unflagged-pings question)
  - `SESSION_ROADMAP_CONSOL_2026_04_22.md` (absorb 2026-04-22 findings into roadmap)
  - `SESSION_HOLDER_DISABLE.md` (paste-status unknown — Jay to confirm)
  - `SESSION_HOLDER_DATA_AUDIT.md` (paste-status unknown — Jay to confirm)

---
