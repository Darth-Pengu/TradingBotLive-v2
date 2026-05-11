# ZMN Bot Monitoring Log

---

## 2026-05-11 — STOP-LOSS-20-RUG-FILTER-DEPLOY-001 (code+env deploy)

- Predecessor: STOP-LOSS-20-RUG-INVESTIGATION-001 (commit `27f623b`, 2026-05-09). Audit doc `docs/audits/STOP_LOSS_20_RUG_INVESTIGATION_001_2026_05_09.md` + paste-ready deploy prompt `docs/audits/STOP_LOSS_20_RUG_FILTER_DEPLOY_PROMPT_2026_05_09.md`.
- STOP gates re-verified pre-deploy: STOP-A PASS (investigation doc 2d old, ≤14d window); STOP-B PASS (`git log 27f623b..HEAD -- services/paper_trader.py services/bot_core.py` returns ZERO behavioural commits; last touch to either file `ea0da2f` BOT-CORE-ML-GATE-001 2026-05-05, pre-investigation); STOP-C PASS (re-ran `verify_filter.py`; 9.5d sample at $3K = +13.15 SOL NET LIFT = **+1.38 SOL/day**, up from +0.93/day at investigation time — bleed accelerated; floor was +0.50/day); STOP-D PASS (no concurrent behavioural deploy markers).
- Code change: `services/paper_trader.py` `paper_buy` — single Edit hunk +29 lines inserted between `entry_price = price * (1 + slippage / 100)` (line 245) and `fee_breakdown = _simulate_fees(...)` (was line 247, now line 277). New block reads `BOT_CORE_FILL_MC_CEILING_USD` env (default "0" = disabled); if positive AND `entry_price * 1_000_000_000 > ceiling`, logs `FILL_MC_CEILING reject: ...`, increments Redis counter `bot:filter:fill_mc_ceiling:rejects:<UTC-date>` (14d TTL), returns `{success: False, error: "fill_mc_ceiling_exceeded", simulated: True, fill_mc, ceiling}`. The return shape matches the existing `price_fetch_failed` path so all callers handle it correctly.
- Compile check: `python -m py_compile services/paper_trader.py` → OK.
- Railway env set: `BOT_CORE_FILL_MC_CEILING_USD=3000` on **bot_core ONLY** at 2026-05-11 12:18:37 UTC. Other services (signal_aggregator, web, ml_engine, signal_listener, treasury, governance, market_health, Redis, Postgres) untouched.
- Two redeploys triggered: code push commit `0f37e82` at 12:09 UTC → container start at 12:16:41 UTC; env set at 12:18:37 UTC → container start at 12:24:12 UTC. Both verified via railway logs `Starting SINGLE service: bot_core` + `Startup reconciliation: 0 open positions in DB` + `Listening for emergency alerts`.
- Post-deploy verification harness `.tmp_stop_loss_20_rug_deploy/post_deploy_verify.py` (gitignored). Run output: `.tmp_stop_loss_20_rug_deploy/post_deploy_check.txt` (gitignored). Checks: (i) Redis counter accessibility/value; (ii) NO new SD-paper trades with `market_cap_at_entry > $3,000` since deploy (F1 should have blocked these); (iii) trade-rate sanity vs pre-deploy 24h baseline (≥50% threshold).
- Verification outcome (T+2 min, 12:26 UTC): ✅ **PASS**. (i) Redis counter `bot:filter:fill_mc_ceiling:rejects:2026-05-11` not yet present (lazy-create on first reject; expected at ~9 rugs/day rate to populate within hours). (ii) 4 new SD-paper trades since env-active deploy, **0 with market_cap_at_entry > $3,000** — F1 gate selective, low-MC tokens still flowing. (iii) Trade rate sanity: too short a window for meaningful comparison (4 trades in 2 min vs 24h pre-deploy 85/24h = 3.5/h). Will re-check at +30 min and +24h per deploy prompt rollback-trigger window. No `FILL_MC_CEILING reject` log lines yet (consistent with historical ~1/2-3h rug arrival rate). bot:status `consecutive_losses=19` is PRE-EXISTING (not deploy-related; was 1 on 2026-05-08, accumulated over 3 days from the same May-8 spike that motivated this filter). Rollback triggers from deploy prompt §5 all clear: no RuntimeError at startup, no winner blocked, no emergency_stop set, no consecutive_losses delta from deploy.
- Rollback procedure: `BOT_CORE_FILL_MC_CEILING_USD=0` via Railway MCP → takes effect at next `paper_buy` call (~few seconds), no redeploy required. Documented per §4 of deploy prompt.
- Re-evaluation milestone: queue `STOP-LOSS-20-RUG-FILTER-EVAL-001` for ≥2026-05-25 (+14d post-deploy). Will: (a) verify cumulative Redis counter matches projected ~25/day rate; (b) re-run `verify_filter.py` with actual post-deploy `kept_pnl`; (c) decide keep $3k / tighten $2k / loosen $5k; (d) decide live-mode parity in `services/execution.py` (gated on V5a preconditions).
- V5a impact: none. F1 is paper-scoped at this deploy (paper_buy only called from `bot_core.process_signal` TEST_MODE=true path). Live-mode parity in `services/execution.py` is a separate session.

---

## 2026-05-09 — STOP-LOSS-20-RUG-INVESTIGATION-001 (read-only investigation, DEPLOY-RECOMMENDED)

- Read-only investigation of `stop_loss_20%` as the largest SD-paper bleed since 2026-05-02 (n=65, sum −6.03 SOL, 0% WR). Triggered by chat-side data analysis.
- Pre-claim verification (STOP-A): 65 rugs since 2026-05-02 (chat said 61; close — chat ran ~6h earlier and the May 8 spike was still accumulating). Hold time min 0.099s, max 2.021s, median 0.991s — matches chat's 0.10-2.02s/median 1.04s. Median observed drop −74.03% — matches chat's −74.7%. peak_price NULL on 100% of rows — consistent with chat's "0/61 went up", but limited evidence (peak_price column never written for sub-second exits; the INSERT in `paper_trader.paper_buy` doesn't set peak_price, and the bot_core UPDATE either doesn't fire or fails silently inside `except Exception: pass`).
- Code archaeology: exit logic at `services/bot_core.py:1815-1824` — `f"stop_loss_{sl_pct:.0%}"` f-string label fires whenever `multiple <= (1 - 0.20)` regardless of how deep the actual drop. The label is "≥-20% drop observed at the 2-second exit-check tick", not "exit at -20%". Polling cadence `await asyncio.sleep(2)` at L1940. STOP_LOSS_PCT=0.20 confirmed from `services/bot_core.py:166` (env-controlled, default 0.20).
- Gate verification (STOP-B): SD_MC_CEILING_002 gate intact at `services/signal_aggregator.py:1846-1881`; Railway env `SD_MC_CEILING_USD=3000` confirmed live on signal_aggregator. STOP-B does not fire.
- Field sample (STOP-C): features_json populated on 186/186 (100%) SD-paper stop_loss_20% rows since (mis-set) SINCE date — STOP-C does not fire. Sample 5 rows showed market_cap_at_entry $3,033-$24,383 — all above the SA $3K threshold. The SA gate is being bypassed.
- **Smoking gun (Phase 2)**: `market_cap_at_entry` cleanly separates RUG from WIN at $3K cut on 273-row sample (65 rugs / 208 trailing-stop wins) since 2026-05-02. RUG: min $3,181, p10 $3,436, median $7,881, p90 $37,615, max $181,519 — **100% > $3K**. WIN: min $321, median $623, p90 $756, max $832 — **0% > $3K**. Zero overlap.
- Root cause: SA gate evaluates BC reserves *as carried in raw_data at PumpPortal-publish time*. For fresh pump.fun tokens, raw_data carries the seed values (vSol≈30, vTokens≈1.073e9), so SA-computed MC ≈ $2,400 — always under the $3K gate. Between signal-publish and bot_core fill (1-15s window), Jupiter / GeckoTerminal indexes the token and returns a *current* USD price reflecting in-flight sniper buys. `paper_buy._get_token_price(mint)` (paper_trader.py:96-139) prefers Jupiter's live price over the BC fallback. The DB column `market_cap_at_entry = entry_price * 1B` reflects this fill-time price. The SA gate is structurally inert against this failure mode because it gates on signal-time data while the failure mode is fill-time price divergence.
- Discriminative-feature scan (Phase 2.3): no feature in features_json clears the 1.5× separation threshold. All ratios in [0.82, 1.21]. Confirms the only data-supported lever is fill-time MC (which is the DB column `market_cap_at_entry`).
- Filter F1 design + counterfactual (Phase 3-4):
  - F1: at `paper_trader.paper_buy`, after `entry_price` computation, reject if `entry_price * 1_000_000_000 > BOT_CORE_FILL_MC_CEILING_USD`. Default disabled in code; env-active at $3,000.
  - 7d window (since 2026-05-02): blocks 69 / 473, NET LIFT +6.20 SOL, **+0.93 SOL/day**, 0/211 winner FP.
  - 14d window (since 2026-04-25): blocks 139 / 1,091, NET LIFT +11.00 SOL, **+0.80 SOL/day**, 0/349 winner FP.
  - 17d POST-cliff (since 2026-04-22): blocks 203 / 1,493, NET LIFT +14.65 SOL, **+0.88 SOL/day**, 0/544 winner FP.
  - STOP-E (≤10% winner-SOL FP) clears by 0%; STOP-F (≥+0.30 SOL/day) clears by 2.7-3.1×; STOP-D and STOP-G clear.
  - Tighter $2K threshold lifts another +0.7 SOL/day but blocks 56% of trades — recommend $3K for parity with SA gate, conservative blast radius (14% blocked), zero FP cost. Tightening can follow as a separate post-deploy sweep.
- May 8 spike: 40 of 65 rugs (62%) on a single day. F1 is forward-protective regardless of whether the spike is structural or transient.
- Verdict: 🟢 **DEPLOY-RECOMMENDED**. Single-lever, env-controlled, reversible, paper-only at flip. Follow-on prompt at `docs/audits/STOP_LOSS_20_RUG_FILTER_DEPLOY_PROMPT_2026_05_09.md`.
- Investigation evidence: `.tmp_stop_loss_20_rug/{01_exit_logic,02_entry_path,03_field_sample,04_gate_verification,05_signal_vs_fill,06_discriminative_features,07_sizing,08_temporal,09_candidate_F1}.md` + `phase2_output.txt` + `verify_output.txt`. Audit doc: `docs/audits/STOP_LOSS_20_RUG_INVESTIGATION_001_2026_05_09.md`.
- NO code/env/Redis writes this session. Read-only DB SELECT, read-only Railway MCP `list-variables`, read-only code grep. Single push expected (audit doc + canonical-doc updates only).

---

## 2026-05-08 13:30 UTC — VYBE-URL-CODE-DRIFT-001-FIX-2026-05-08 (read-only investigation, STOP per Step 7 #2)

- Read-only investigation of the 3 hardcoded `.com` Vybe URLs at `services/signal_aggregator.py:753, 850, 2568` flagged by API-CREDITS-HEALTH-DIAGNOSTIC-001 (2026-05-05). Session prompt anticipated a `.com → .xyz` TLD swap based on prior audit's `.xyz → 401` probe inference.
- Probe with valid `VYBE_API_KEY` (sourced from Railway signal_aggregator env, never written to disk) reveals: both `.com/token/...` and `.xyz/token/...` return HTTP 404 ("The requested endpoint does not exist"). The 401 the prior audit observed was from probing `.xyz` without auth — Vybe's auth middleware fires before the not-found check.
- Vybe MCP `search-endpoints` + `get-endpoint` confirm canonical paths are versioned: `/v4/tokens/{mint}/top-holders` and `/v4/tokens/{mint}` — both explicitly noted in OpenAPI as **"Replaces"** the older `/token/...` paths. Probes against `.xyz/v4/tokens/...` return HTTP 200 with valid data (BONK test mint).
- Two breaking downstream issues for the URL-only fix:
  - L850 `_fetch_creator_history`: v4 Token Details response has no `creator` field. Function continues to return empty dict even after URL+path fix. Need alternative data source (Helius parseTransactions first-slot, pump.fun metadata, or other). Tracked as new VYBE-CREATOR-LOOKUP-DEPRECATED-001 (Tier 2).
  - L2568 KOL/MM detection: v4 `/top-holders` returns `ownerName` (e.g. "Binance Exchange 1"), not `ownerLabel`/`label`. KOL detection reads the wrong field — `kol_count` stays 0 → `whale_boost` stays 1.0. Trivial paired field-name update needed; bundle with V2 fix. Tracked as new VYBE-KOL-FIELD-MAPPING-001 (Tier 2).
- L753 `_fetch_holder_data_vybe`: response shape compatible (`data` array with `balance` field). URL+path fix alone fully restores HOLDER fallback.
- Caller analysis (Step 4): no caller breaks on empty returns. All three call sites already handle silent-failure gracefully — they have for the bot's entire +598 SOL pre-cliff era and post-cliff period. Adding real Vybe data is additive feature restoration.
- Per Step 7 condition #2 ("Vybe API documentation indicates breaking changes between the old endpoint and a current canonical one — i.e., the fix is more than a TLD swap"), **STOP triggered**. Findings audit committed; no code change to `services/signal_aggregator.py`; no Railway redeploy.
- Concurrent STATE-SNAPSHOT-2026-05-08 (entry below) ran the same window; their §3 finding "Vybe `.xyz` route alive (401/400 with bogus auth)" matches: with bogus/empty auth, `.xyz` returns 401/400; with valid auth, `.xyz/token/...` returns 404. The 401 was an auth-middleware artifact, not evidence of a working route.
- Follow-up: `VYBE-URL-CODE-DRIFT-001-FIX-V2` (Path A1 in audit §7) — URL+path migration at all 3 sites + L2568 `ownerName` field update; track creator-source replacement separately. Cost S.
- **NO services/* edit, NO deploy, NO env change, NO Redis writes, NO DB writes.** Audit: `docs/audits/VYBE_URL_FIX_2026_05_08.md`. Scratch artifacts: `.tmp_vybe_fix/probe_urls.py`, `.tmp_vybe_fix/probe_v4_urls.py`, `.tmp_vybe_fix/probe_output.txt`, `.tmp_vybe_fix/probe_v4_output.txt`, `.tmp_vybe_fix/STOPPED.md`, `.tmp_vybe_fix/vybe_references.txt`, `.tmp_vybe_fix/git_history.txt` (untracked).

---

## 2026-05-08 ~13:21 UTC — STATE-SNAPSHOT-2026-05-08 (read-only verification, no env / Redis / code changes)

- Read-only state snapshot to refresh the [STALE]/[ASSUMED] items in the 2026-05-07 handover before the DEFENSIVE-OVERRIDE-PROBE-EVAL window opens.
- §1 PROBE STATE: 🔴 **EXPIRED.** `market:mode:override` is absent at audit time; `market:mode:current=NORMAL`. Probe was set 2026-05-06 22:29:10 UTC with 24h TTL → expired 2026-05-07 22:29:10 UTC. Renewal did NOT fire. Probe ran ~24h before lapsing.
- §2 WALLETS: trading wallet UNCHANGED at 0.064095633 SOL [VERIFIED:helius]. Holding wallet rose to 0.190842421 SOL from prior 0.0098 SOL baseline (+0.181 drift; treasury dormant — confirm with Jay).
- §3 API HEALTH: Helius 🟢 (epoch 968, ~1588 real TPS); Vybe `.com` 🔴 still 404 (code drift unchanged); Vybe `.xyz` route alive (401/400 with bogus auth); SocialData route alive 401 (real credit state not probed); Anthropic 🔴 confirmed firing now via Redis `governance:latest_decision` body; PumpPortal/Jupiter/Binance 🟢 (inferred via `signal_aggregator:health` heartbeat fresh).
- §4 PROBE-PERIOD PAPER: n=263 since 2026-05-07 00:00 UTC, all SD-paper closed, +2.0625 SOL net, 52.9% WR. Window split: probe-active 24h n=54 / +0.640 SOL / 44.4% WR; probe-expired ~14h45m n=212 / +1.398 SOL / 54.2% WR. **Mode coverage gap: `mode_at_entry` absent in 263/263 sample rows** — per-row mode reconstruction not possible from DB alone for this window. Filing MODE-AT-ENTRY-FEATURE-001 (Tier 2 🟢).
- §5 ENV: bot_core / signal_aggregator / treasury / ml_engine / market_health all match handover §3.2 with no drift. SEC-001 split-Nansen-key state still present (treasury+market_health on `cL2tgvKP`; rest on `nsn_2ef9`). Vestigial sizing values still on treasury/ml_engine/market_health (TUNE-008 cleanup carry-over).
- §6 CODE STATE: BOT-CORE-ML-GATE-001 commit `ea0da2f` present in HEAD `15a334a`; SD_MC_CEILING_002 gate at signal_aggregator.py:1846-1881 (handover line range was approximate); TIME_PRIME env-controlled block at bot_core.py:750-764; hardcoded TZ at bot_core.py:754 still present (TIME-PRIME-AEDT-AEST-DRIFT-001 unchanged); Vybe `.com` URLs at signal_aggregator.py:753, 850, 2568 still present (VYBE-URL-CODE-DRIFT-001 unchanged).
- §7 RECOMMENDATIONS for eval session: (a) decide treatment of underpowered 24h probe sample — recommend re-run with renewal commitment (option 2); (b) file MODE-AT-ENTRY-FEATURE-001 to add `mode_at_entry` to features_json so future audits can do per-row mode analysis; (c) confirm holding-wallet drift; (d) carry-over Anthropic/Vybe/SocialData fixes still pending.
- **NO services/* edit, NO deploy, NO env change, NO Redis writes.** Audit: `docs/audits/STATE_SNAPSHOT_2026_05_08.md`. Scratch: `.tmp_state_snapshot/` (gitignored).

---

## 2026-05-06 22:29 UTC — DEFENSIVE-OVERRIDE-PROBE-001 START (no code change, single Redis SET)

- Single state change: `SET market:mode:override DEFENSIVE EX 86400` at **2026-05-06T22:29:10Z UTC** via Redis MCP. No code edits, no env changes, no service redeploys.
- Probe rationale: A/B-test the NORMAL-vs-DEFENSIVE PnL inversion finding from **MARKET-MODE-001-RE-CALIBRATE Path C / STOP** (audit `MARKET_MODE_001_RE_CALIBRATE_FINDINGS_2026_05_05.md`). Pre-probe finding (post-Session-2 5-day window): NORMAL -1.09 SOL on 121 trades (24.8% WR) vs DEFENSIVE +0.25 SOL on 45 (28.9% WR) — counterintuitive, sample n=45 too small for confidence.
- §2 baseline (last 48h SD-paper, captured pre-SET): NORMAL n=103 / -0.80 SOL / mean -0.0078 / **33.0% WR**; AGGRESSIVE n=1; DEFENSIVE n=17 / +0.44 SOL / mean +0.026 / **64.7% WR**; TOTAL n=121 / -0.37 SOL / 37.2% WR. Reinforces inversion at smaller window with same direction. Raw output saved to `.tmp_defensive_probe/baseline.txt`.
- §2 bot health pre-SET: bot:status RUNNING, paper portfolio 22.92 SOL, 0 open positions, market_mode NORMAL, consecutive_losses=2, test_mode=true, emergency_stop=ABSENT. All §2 STOP conditions PASSED.
- §3 Redis SET landed (verified via `GET market:mode:override` → "DEFENSIVE"). Pre-SET value: key absent (no prior override). Pre-SET market:mode:current=NORMAL.
- §4 propagation verification (within prompt's 5-min ceiling):
  - 22:29:44Z (34s post-SET): `market_health` log shows `Market mode: DEFENSIVE` — first cycle picked up override.
  - 22:34:45Z (5m35s post-SET): `market_health` log shows explicit `Market mode OVERRIDE active: DEFENSIVE` — confirms `services/market_health.py:412-414` override-read path firing as expected.
  - `market:mode:current` = DEFENSIVE (verified via Redis MCP).
  - `bot:status.market_mode` = DEFENSIVE (verified via bot_core heartbeat at 22:39:31Z).
  - First post-SET trade observed at 22:39 UTC (`speed_demon:C7Ad1dff…`, no_momentum_90s -0.0152 SOL on 0.091 SOL position) — throughput confirmed flowing under DEFENSIVE override; bot_core ML gate at 40 still rejecting <40 ml_score signals (4+ skip lines logged at 22:02-22:15 UTC).
- §5 documentation: STATUS.md prepended; MONITORING_LOG.md prepended (this entry); ZMN_ROADMAP.md Decision Log row + 2 new Tier-2 OPERATIONAL / Tier-1 EVAL roadmap rows added (`DEFENSIVE-OVERRIDE-DAILY-RENEWAL-001`, `DEFENSIVE-OVERRIDE-PROBE-EVAL-001`).
- §6 daily renewal: filed as `DEFENSIVE-OVERRIDE-DAILY-RENEWAL-001` (operational, Tier 2 🟢). Until probe ends, override must be re-SET every 24h. Auto-expires safely if forgotten (bot reverts to threshold-based mode = safe failure mode).
- §7 STOP conditions: NONE triggered. All four (§2 unexpected state / §3 SET fail / §4 propagation fail >10min / §1.4 git rebase fail 3×) cleared.
- Re-evaluation milestone: ≥**2026-05-08T22:29Z UTC** (48h). Sample target ≥80 SD-paper trades under DEFENSIVE. Run as `DEFENSIVE-OVERRIDE-PROBE-EVAL-001` (paste-ready prompt to follow). Do NOT auto-trigger.
- Rollback triggers (any one ends probe early): cumulative < -0.50 SOL on n≥30 / WR < 18% on n≥30 / throughput < 5 SD-paper trades/day for 24h consecutive / bot HIBERNATE > 2h consecutive (override-read path bug indicator).
- Rollback procedure: `DEL market:mode:override` via Redis MCP. Document in MONITORING_LOG.
- **NO services/* edit, NO deploy, NO env change.** Sole runtime change: 1 Redis key SET with 24h TTL. Audit predecessor: `docs/audits/MARKET_MODE_001_RE_CALIBRATE_FINDINGS_2026_05_05.md`. Scratch artifacts: `.tmp_defensive_probe/baseline.txt`, `.tmp_defensive_probe/baseline_query.py` (gitignored).

---

## 2026-05-07 ~01:30 UTC — STRATEGY-CLIFF-INVESTIGATION-001 (read-only investigation, NO REVERT)

- Read-only investigation of the 2026-04-20→21 paper-PnL "cliff" via SQL on production DB (`paper_trades` current + `paper_trades_archive_20260421` archive table) + git log + audit doc + code reads.
- §3 cliff CONFIRMED in DB: archive 8-day SD-paper sample (n=2,984) shows mean +0.20 SOL/trade summing +598 SOL; current 4-day POST sample (n=528) shows mean +0.014 SOL/trade summing +9.3 SOL. Numbers match chat-side prompt's framing within rounding.
- §3 KEY FINDING — fee-model accounting mismatch: PRE rows written under OLD fee model that under-counted fees by ~96× per FEE-MODEL-001 (commit `e078b4c`, deployed 2026-04-21 07:26 AEDT). Per-trade fee correction: -0.391 SOL. Apples-to-apples math: PRE-cliff under realistic fees = -566 SOL on 2,984 trades = mean -0.19 SOL/trade. POST-cliff = +0.014 SOL/trade. **Under fair accounting, POST is +0.20 SOL/trade BETTER than PRE.**
- §3 sizing verification: archive p50 amount 0.32 SOL → current p50 0.082 SOL (5× reduction); archive effective fee rate 0.36% of position → current 1.50% (4× reduction in fee % efficiency at smaller positions).
- §5 exit-reason composition: BREAKEVEN_STOP 131 fires PRE → 0 POST (env override removed); staged_tp_+50/+100/+250/+400/+500% all REMOVED via env override; staged_tp_+200/+1000% RETAINED. TRAILING_STOP mean dropped 12× (sizing 5× × fee impact 2.4× explains full magnitude). Stop-loss tighten (35→20%) improved per-fire mean 3.3× (-0.244 → -0.074).
- §5b signal-source: 100% pumpportal both eras. Source-shift hypothesis REFUTED. MC-band shift CONFIRMED (89% in $1-5M PRE → 41.5% POST, gate-driven). Cross-reference with API-CREDITS audit: Telegram channel ID stable, Discord BUG-020 pre-existed cliff, Nansen on dry-run both eras.
- §6 cause-effect: 6 candidates (FEE-MODEL-001, GATES-V5 sizing/stop-loss/gates, breakeven removal, TP flatten) all 🟢 HIGH match. 4 source/regime hypotheses 🔴 REFUTED.
- §7 counterfactual: revert lift = 0 SOL/day (likely negative -2 to -5 SOL/day). §7 prompt's STOP condition triggers — counterfactual < 1 SOL/day.
- §8 recommendation: 🟡 STOP / NO REVERT. Keep FEE-MODEL-001, DASH-RESET, GATES-V5 sizing/stop-loss/gates, ML-012 fix. Track 5 follow-ups (Tier 2 🟢): STRATEGY-CLIFF-FOLLOWUP-001, PRE-DEPLOY-PNL-VALIDATION-001, BREAKEVEN-DECISION-001, TP-SCHEDULE-EVAL-001, SIGNAL-MIX-ANALYSIS-001.
- §10 institutional learning: every audit since 04-22 operated only on POST-cliff data (DASH-RESET wiped current paper_trades; archive table existed but no query used it). Process improvement codified in PRE-DEPLOY-PNL-VALIDATION-001.
- **NO services/* edit, NO deploy, NO env change, NO Redis writes.** Audit: `docs/audits/STRATEGY_CLIFF_INVESTIGATION_001_2026_05_05.md`. Recommendation: `.tmp_cliff_investigation/recommendation.md` (gitignored).

---

## 2026-05-06 ~13:00 UTC — MARKET-MODE-001-RE-CALIBRATE (Path C / STOP, no code change)

- §0 predecessor verification PASS for both BOT-CORE-ML-GATE-001 and TIMEZONE-AUDIT-001.
- §3 Step 1 throughput: **45.8% zero-trade hours** (55/120, post-Session-2 5-day window) — above 20% STOP threshold; recalibration technically warranted on volume grounds.
- §3 Step 2 mode distribution (n=1,436 5-min snapshots): NORMAL 51.7%, DEFENSIVE 46.8%, HIBERNATE 1.3%, AGGRESSIVE 0.2%, FRENZY 0%. **HIBERNATE-cycling premise was incorrect** — actual problem is DEFENSIVE share.
- **Surprise finding (PnL inversion):** NORMAL has WORSE per-trade PnL than DEFENSIVE in the post-Session-2 sample. NORMAL: 121 trades / -1.09 SOL / 24.8% WR. DEFENSIVE: 45 trades / +0.25 SOL / 28.9% WR. Expanding NORMAL would have been actively harmful.
- §3 Step 3 binding constraint: **`dex_vol` not `grad_rate`** (matches §4 Path C explicit STOP example). Live mig=215 is 7× the NORMAL threshold of 30. Off-peak Solana dex_vol drops to $800M-1B band, below $1B NORMAL gate.
- §4 decision: **Path C / STOP**. Per the prompt's own §4 Path C: "If §3 reveals something unexpected (e.g., dex_vol is the binding constraint...), STOP and emit a finding doc. Do not patch into uncertainty."
- New roadmap items: DEFENSIVE-VS-NORMAL-PNL-INVERSION-001 (Tier 1), MARKET-MODE-001-RE-CALIBRATE-V2 (Tier 1, re-scoped), PUMPFUN-VOL-PLACEHOLDER-001 (Tier 2), MM-HYSTERESIS-ONLY-001 (Tier 2).
- **`services/market_health.py` UNCHANGED.** No deploy. No env change. Finding doc only: `docs/audits/MARKET_MODE_001_RE_CALIBRATE_FINDINGS_2026_05_05.md`.

---

## 2026-05-05 ~15:30 UTC — TIMEZONE-AUDIT-001 (read-only sweep, no code change)

- Repository-wide grep sweep for hardcoded TZ offsets across services/, dashboard/, Scripts/.
- **Findings:** 2 🔴 BUG (both `services/bot_core.py:754,776` — covered by existing TIME-PRIME-AEDT-AEST-DRIFT-001), 2 🔵 MARGINAL, 5 🟡 OK-WITH-CAVEAT, 20+ 🟢 SAFE.
- **`services/market_health.py` is 🟢 SAFE** — fully DST-aware via `pytz.timezone("Australia/Sydney")`. Critical for the next session: MARKET-MODE-001-RE-CALIBRATE can proceed without bundling a TZ fix.
- 4 new LOW-priority hygiene items filed: TZ-CONVENTION-DOC-001, RISK-MGR-TZ-COMMENT-001, SIGAGG-ML-HOUR-LABEL-001, DASH-AEDT-LABEL-001.
- Recommended convention codified into AGENT_CONTEXT.md + CLAUDE.md: decision logic uses `ZoneInfo("Australia/Sydney")` or pytz; storage uses UTC; no hardcoded offsets anywhere except UTC-by-design global-session bands (which must be commented).
- Audit: `docs/audits/TIMEZONE_AUDIT_2026_05_05.md` (~265 lines, §1-§10).

---

## 2026-05-05 14:16-15:01 UTC — BOT-CORE-ML-GATE-001 deploy + §6 verification

- Code commit `ea0da2f` deployed at ~14:13Z (gate inert because env defaults to 0 — verifies the "default-safe" deploy property).
- Env `ML_THRESHOLD_BOT_CORE_SD=40` set at 14:16Z; second deploy auto-triggered, container start **14:16:48Z** UTC = canonical gate-active timestamp.
- §6 verification at ~15:01Z (45min post-cutoff under DEFENSIVE market mode):
  - `below_40` SD-paper admission count post-cutoff = **0** (gate firing OR no <40 signals reaching bot_core; both indistinguishable in this sample).
  - `40_plus` count = **1** (id=8039, mint EV1na7Wj5WLX, ml_score=47.0, admitted at 14:58:36Z, 41m48s post-cutoff).
  - `BOT_CORE_ML_GATE` reject log lines = **0** (consistent with steady-state agreement of SA gate at 30 / bot_core gate at 40 — bot_core gate fires only on the discrepancy edge).
  - `market:mode:current` = **DEFENSIVE** (suppresses upstream throughput, explains the small sample).
  - `bot:emergency_stop` = absent (not tripped).
- **Verdict: PASS (low-confidence, single-sample).** Gate landed cleanly; full confidence pending NORMAL-mode window with multi-trade-per-hour throughput (blocked by the queued MARKET-MODE-001-RE-CALIBRATE follow-up).
- Predecessor for: TIMEZONE-AUDIT-001, MARKET-MODE-001-RE-CALIBRATE (both queued in this same CC session).
- Audit: `docs/audits/BOT_CORE_ML_GATE_001_2026_05_05.md` (536 lines, 9 sections).

---

## 2026-05-01 ~12:30 UTC — STATE-RECONCILE-2026-05-01 (Session 2 of 6 chained-prompt sequence)

### Findings A-E (verified production DB, last 7d SD-paper unless noted)

- **A — ML score band performance:** 30-40 +0.49 / **40-50 -1.98 (worst)** / 50-60 -0.18 (flat) / 60-70 -0.70 / **70-80 +1.63 (best)** / 80-90 -0.35 / 90+ +0.005. Chat-side framing of "50+ mostly profitable" REFUTED — only 70-80 reliably positive. The 2026-04-17/19 magnitudes (CLAUDE.md ML threshold block table) have collapsed by ~50-100×.
- **B — AEST hour distribution:** 18-20 -2.46 SOL on 114 trades (worst, confirmed); 11-17 +0.18 (flat, confirmed); chat's "AEST 21-23 + 00-08 ~+1 SOL" disconfirmed (actual ~-1.45 SOL).
- **C — Exit reasons:** TRAILING_STOP +7.93 / 206 / 76.7% WR ✓ dominant winner. Top losers: `no_momentum_90s` -7.40 / 356 / 0% (LARGEST, chat omitted), `graduation_stop_loss` -6.36 / 67 / 0%, `stop_loss_20%` -5.16 / 74 / 0%. Post-grad bleed = -12.09 SOL on 173 trades (chat said -23; actual is HALF). TRAILING_STOP captures **69%** of gains, not 98%.
- **D — Analyst recency:** Last entry 2026-04-28 13:02 UTC. 0 entries last 3 days. ANALYST-DISABLE-002 enforcement confirmed.
- **E — SD daily trend:** WR 04-22/23 ~50% → 04-30 17.9% → 05-01 (early) 0%. Direction confirmed; aggregate 14d still net +9.0 SOL but recent 4d -1.18 SOL.

### Reconciliation outcome

PROCEED with nuanced doc reconciliation. No STOP triggered (headlines confirmed). Chat-side detail-level framings adjusted to actual data where they overstated (50+ profitability, post-grad bleed magnitude, TRAILING_STOP %, +1 SOL elsewhere claim). 0 🔴 ACTION-CHANGING / 2 🟡 SCOPE-CONFUSION / 3 🟢 SAMPLE-STALE / 1 🔵 NUANCE-MISSING per drift severity classification.

### Doc updates landed

- CLAUDE.md: ML threshold block 2026-05-01 addendum + reference to USERMEMORIES_DRIFT_2026_05_01.md
- AGENT_CONTEXT.md: state-header refresh + TIME_PRIME env vars added to bot_core config table
- ZMN_ROADMAP.md: STATE-RECONCILE Decision Log entry; future-queued POST-GRAD-LOSS-INVESTIGATION-001 (with corrected -12 SOL ROI estimate), ML-THRESHOLD-DATA-DRIVEN-RETUNE-001, TIME-PRIME-AEDT-AEST-DRIFT-001, TIME-PRIME-CALIBRATION-001
- MONITORING_LOG.md: this entry
- STATUS.md: Session 2 entry prepended
- docs/audits/USERMEMORIES_DRIFT_2026_05_01.md: NEW

### Carry-overs to Session 3

POST-GRAD-LOSS-INVESTIGATION-001 should test 5 hypotheses against the -12.09 SOL post-grad bleed (NOT chat's -23 SOL — recalibrate ROI expectation). The largest single loss-source is actually `no_momentum_90s` (-7.40 SOL), which is a SEPARATE category from the post-grad investigation scope.

---

## 2026-04-17 ~morning AEDT — Helius URL resolver + sell-storm circuit breaker

### Diagnosis
Overnight 2026-04-17 `live_trade_log` between 20:56 Apr 16 and 07:07 Apr 17
showed 7,448 `PumpPortal Local: no Helius URL available for transaction
submission` errors across 1,475 distinct mints. `_execute_pumpportal_local`
iterated only `(HELIUS_STAKED_URL, HELIUS_RPC_URL)` and fell through when both
were empty. `HELIUS_GATEKEEPER_URL` was set but unread by that send path.

Separately, bot_core's `HELIUS_STAKED_URL` was pointing at the plain
`mainnet.helius-rpc.com` URL instead of the real `ardith-mo8tnm-fast-mainnet`
staked endpoint (which web + signal_aggregator had correctly).

Once `HELIUS_RPC_URL` resolved at 06:37, the bot produced 50+ TX_SUBMITs
through 08:23 AEDT — signing works, wallet drained from 5.0 to 3.677 SOL
across the successful window. Zero `SignatureFailure` in 83+ on-chain
attempts.

### Shipped (commit cd266de)
- `services/execution.py`: `_execute_pumpportal_local` and
  `_send_transaction` now include `HELIUS_GATEKEEPER_URL` as final fallback
- `services/execution.py`: startup `RuntimeError` if TEST_MODE=false with
  no Helius URLs configured (was silent → 10h of retries)
- `services/execution.py`: 4xx/5xx body truncation 200 → 2048 for diagnosis
- `services/bot_core.py`: sell-storm circuit breaker — park a mint after
  `SELL_FAIL_THRESHOLD` (default 8) consecutive live-sell `ExecutionError`s
  for `SELL_PARK_DURATION_SEC` (default 300s)

### Env var reset on bot_core
`HELIUS_STAKED_URL` changed from `mainnet.helius-rpc.com` to
`ardith-mo8tnm-fast-mainnet.helius-rpc.com` (now matches web).

### Verified
- Syntax check passes both files
- Startup validation raises RuntimeError when all URLs empty + live mode
- Imports clean in paper mode with no URLs (bypass works)
- TEST_MODE=true for deploy

### Not fixed (documented for next session)
Reconcile filter IS correct — `_load_state` and `_reconcile_positions` both
filter by `trade_mode`. But both run only in `__init__`, so a TEST_MODE flip
without container restart leaves paper positions in `self.positions`. Root
cause of v4 EMPTY — not a reconcile bug, a restart-discipline bug.

Full session report: `ZMN_HELIUS_URL_FIX_REPORT.md`

---

## 2026-04-17 ~09:50 AEDT — Trial v4 Overnight Result: EMPTY

Monitor ran 1 minute before hitting 10-consecutive-error stop.
3,358 sell errors (stale paper positions), 0 buys attempted, 0 on-chain
transactions. Wallet untouched at 5.0000 SOL.

Root cause: bot_core never restarted to pick up reconcile fix (4b647a7).
In-memory self.positions still had stale paper entries, blocking buys
via MAX_SD_POSITIONS and generating sell errors.

Signing verdict: INCONCLUSIVE (never exercised on buys).
SignatureFailure count: 0 (consistent with v3 findings).

Action needed: flip TEST_MODE=true (restart), verify clean state,
then flip back for v5 with fresh reconcile.

Full report: ZMN_LIVE_TRIAL_V4_RESULT.md

---

## 2026-04-17 ~11:30 AEDT — Trial v3 Cleanup + Reconcile Fix

Trial v3: signing VERIFIED (0 SignatureFailure in 83+ attempts), BLOCKED
by 2 stale paper positions filling MAX_SD_POSITIONS=2.

Cleanup (TEST_MODE=false, wallet safe):
- 2 stale positions closed (exit_reason='mode_flip_cleanup')
- Redis bot:status + paper:positions:* cleared
- bot_core._reconcile_positions + _load_state now filter by trade_mode
  (commit 4b647a7) — paper positions don't block live MAX_SD_POSITIONS
- MAX_SD_POSITIONS: 2 -> 20, DAILY_LOSS_LIMIT_SOL: 4.0 (kill at wallet 1.0 SOL)
- risk_manager.py: DAILY_LOSS_LIMIT_SOL now reads from env var (was hardcoded 1.0)

Trial v4: ready for overnight run. Bot on TEST_MODE=false with zero
positions, reconcile filtering live-only, 20 slots available.

---

## 2026-04-17 ~10:30 AEDT — Deploy Discipline Rule Added

Documented in CLAUDE.md and AGENT_CONTEXT.md: never use git push AND
railway up in the same session. GitHub webhook auto-deploys on push,
so railway up is redundant and causes duplicate builds. Default to
git push only. Also updated AGENT_CONTEXT.md Section 0.4 with current
trading state (wallet 5.0 SOL, live trial history, paper health).

---

## 2026-04-17 ~10:00 AEDT — Open Positions Mode Filter + MCAP Columns

Fixed OPEN POSITIONS showing 4 paper trades in LIVE view. Root cause:
api_positions read Redis bot:status first (paper-only). Now skips Redis
when mode=live, queries DB directly. Also changed Entry/Current columns
to Entry Mcap / Current Mcap (USD, matching RECENT TRADES convention).
Commit: c328784

---

## 2026-04-17 ~09:30 AEDT — Dashboard Honesty + Solders v2 Deploy

### Dashboard mode filter complete
All main dashboard widgets now filter by trade_mode. LIVE view shows
zeros when no live trades exist. PAPER view unchanged.
Commit: 09ed21f

### Solders signing v2
VersionedTransaction(message, [keypair]) constructor — verified locally
with realistic SOL transfer instruction round-trip.
Commit: ce86cd5

---

## 2026-04-17 ~09:00 AEDT — Solders Signing Fix v2 (Constructor API)

### What happened
Found the correct solders signing API. The VersionedTransaction
CONSTRUCTOR `VersionedTransaction(message, [keypair])` handles signing
internally. Neither `.sign()` (v1 attempt) nor `populate(msg, [sig])`
(v2 attempt) work for re-signing deserialized transactions.

### What was wrong with each attempt
- **v1 (.sign):** API removed in solders 0.21+ (AttributeError)
- **v2 (populate):** Compiles but produces invalid signatures.
  `populate(msg, [sig])` builds the tx but the signature doesn't match
  what validators expect — the message serialization differs between
  `sign_message(bytes(msg))` and what the constructor produces internally.
- **v3 (constructor):** `VersionedTransaction(tx.message, [keypair])`
  — the constructor handles the full sign-then-assemble flow correctly.

### Verification
Tested locally with realistic SOL transfer instruction (not toy/default):
- CompiledInstruction with System Transfer, proper header, 3 accounts
- Round-trip: from_bytes → constructor re-sign → verify_with_results = [True]
- Bytes match after round-trip

### Commit
ce86cd5: 3 signing blocks updated (lines 275, 351, 455)

### Next step
Deploy → Jay flips TEST_MODE=false for 1-trade live test → flip back.

---

## 2026-04-17 ~08:30 AEDT — Ghost Position Cleanup + Live Trial v2 Findings

### Ghost positions (1,458 in Redis, 2 in DB)
Dashboard showed 1,486 "open positions" from April 5. Root cause:
Redis `bot:status` key held 1,458 stale position entries that were
never cleaned when paper_trades rows were closed. Dashboard API reads
bot:status FIRST and only falls back to DB if it's empty.

**Fix:** Deleted bot:status (1,458 entries) + 176 paper:positions:*
keys from Redis. Dashboard now falls back to DB (2 actual open).

### Live trial v2 (TEST_MODE=false flipped by Jay ~08:00 AEDT)
- Solders populate() fix COMPILES and SIGNS — no more AttributeError
- BUT: transactions fail on-chain with `SignatureFailure`
- "Transaction simulation failed: Transaction did not pass signature verification"
- The populate(message, [sig]) reconstruction from a deserialized tx
  doesn't preserve message fidelity — the signature doesn't match
  what validators expect
- ALL 177+ events are sell ERRORs (trying to exit stale paper positions)
- Zero live trades landed. Wallet untouched (5.0 SOL)
- **TEST_MODE should be reverted to true**

### Signing root cause (deeper than first post-mortem)
The `populate()` API works for constructing NEW transactions, but
round-tripping through `from_bytes() → .message → sign → populate()`
loses message integrity. The PumpPortal API returns a pre-built
unsigned transaction. We need to sign it WITHOUT reconstructing.

Correct approach (for next fix session):
```python
# DON'T reconstruct:
tx = VersionedTransaction.from_bytes(tx_bytes)
sig = keypair.sign_message(bytes(tx.message))
signed_tx = VersionedTransaction.populate(tx.message, [sig])  # BREAKS

# DO sign the raw message bytes from the original tx:
from solders.message import MessageV0
from solders.signature import Signature
tx = VersionedTransaction.from_bytes(tx_bytes)
msg_bytes = bytes(tx.message)
sig = keypair.sign_message(msg_bytes)
# Need to construct with the ORIGINAL message object, not re-parsed
```

The exact fix requires testing against the solders API to find the
correct serialization path. May need `solders.transaction.VersionedTransaction`
constructor that takes (signatures, message) directly.

### Commits
- (none this session — diagnosis + Redis cleanup only)

---

## 2026-04-16 ~23:00 AEDT — Live Trial Post-Mortem + Fixes

### What happened
Live trial flipped TEST_MODE=false at ~22:00 AEDT. 244/244 execution
attempts failed with `'VersionedTransaction' object has no attribute 'sign'`.
Zero trades landed on-chain. Wallet untouched (5.0 SOL).

### Root cause
solders >= 0.21 made VersionedTransaction immutable, removing `.sign()`.
execution.py was written for the old 0.18 API. requirements.txt had
`>=0.20.0` with no ceiling — Railway installed 0.27+.

### Corrective actions
- **TEST_MODE:** Found still false at session start. SET TO TRUE immediately.
- **Solders fix:** Rewrote 3 signing blocks to use `populate()` API.
  Pinned `solders>=0.21.0,<1.0.0` (commit f59f025).
- **Helius budget:** Restored HELIUS_DAILY_BUDGET=100000 on web service
  (was 0 from debug session).
- **Ghost positions:** Only 1 open (not 1,689 Jay reported — likely stale
  dashboard cache). Bulk close skipped.
- **Dashboard currency:** Already SOL-primary. No change needed.

### Current state
- TEST_MODE: true (paper mode)
- Wallet: 5.0000 SOL
- Open positions: 1
- Helius: budget restored to 100k
- Solders: fixed, awaiting deploy

---

## 2026-04-16 ~20:45 AEDT — Jito Tip Configurability + Trial Safety Env Vars

Made Jito tips and priority fees env-var configurable in execution.py.
Defaults unchanged. Set trial safety: MAX_SD_POSITIONS=2.
DAILY_LOSS_LIMIT_SOL=1.0 hardcoded in risk_manager.py (already correct).
MAX_TRADES_PER_HOUR=500 (effectively unlimited, Jay's preference).
TEST_MODE still true. No tip values changed from defaults.

Commit: d3fb18e (execution.py configurability)

Remaining for live trial: override 0.15 SOL position floor in
bot_core.py + flip TEST_MODE=false.

---

## 2026-04-16 ~20:25 AEDT — Trade Mode Segregation (Clean Slate for Live)

### What happened
Added `trade_mode` column to paper_trades ('paper' default NOT NULL).
Updated paper_trader INSERT to write mode from TEST_MODE. Dashboard API
filters key queries by mode, defaults to backend mode. Dashboard HTML
shows mode badge (PAPER amber / LIVE red) + toggle dropdown.

### Schema
- ALTER TABLE paper_trades ADD COLUMN trade_mode TEXT NOT NULL DEFAULT 'paper'
- Index: idx_paper_trades_mode_time on (trade_mode, entry_time DESC)
- 4,977 existing rows auto-populated as 'paper'
- New trades writing 'paper' (TEST_MODE=true confirmed)

### Verification
- Paper view: shows current numbers (all queries return paper rows)
- LIVE view (via ?mode=live or toggle): all zeros (clean slate)
- Bot still trading: 4 trades in 10 min post-deploy
- TP observation query: unaffected (doesn't filter by mode)

### Commits
- 2860bce: paper_trader INSERT + TRADE_MODE constant
- c6b2447: dashboard API mode filter + HTML badge/toggle

### What's NOT done
- Not all ~40 paper_trades queries have mode filter (only key endpoints:
  status, trades, positions). Secondary endpoints (equity curve,
  exit-analysis, personality-stats, etc.) still show all-mode data.
  These can be updated incrementally if needed.

---

## 2026-04-16 ~19:45 AEDT — Helius RPC Audit v2 + Endpoint Switch

Tested all 3 Helius endpoints under single-call and burst conditions.
Standard RPC won decisively (48ms median, 20/20 burst) vs Gatekeeper
(430ms, 20/20) vs Secure (all 522, 0/20).

**Action:** HELIUS_STAKED_URL switched from Secure → Standard RPC.
Gatekeeper kept as HELIUS_GATEKEEPER_URL fallback. No code changes.

**Verification:** bot_core redeployed cleanly, exit evaluator running,
signals flowing. Dashboard still healthy.

**Helius Staked 522 blocker: RESOLVED.** All execution APIs now ready.

---

## 2026-04-16 ~19:30 AEDT — External API Audit (Read-Only)

Read-only audit of every external service the bot depends on.

### Critical findings
- **Helius Staked RPC: DOWN (522)** — primary tx submit endpoint.
  Fallback to standard RPC works (285ms). Needs new URL from Helius
  dashboard or accept standard RPC for live.
- **Anthropic: CREDITS EXHAUSTED** — governance LLM non-functional
- **SocialData: CREDITS EXHAUSTED** — social enrichment dead
- All other execution-critical APIs: WORKING

### Latency (median from Sydney, Railway will be faster)
- Helius RPC: 285ms (GOOD)
- Jupiter V2: 365ms (GOOD)
- Jito: 629ms (OK)
- CoinGecko: 48ms (EXCELLENT)

### Verdict: READY WITH ONE FIX
- Fix or accept Helius Staked URL (standard RPC fallback exists)
- Everything else ready for TEST_MODE=false

Full report: EXTERNAL_API_AUDIT.md

No code changes. No deploys. No real trades. Read-only.

---

## 2026-04-16 ~18:50 AEDT — Dashboard Rewrite (Real Wallets + CFGI Cleanup)

### What happened
Replaced paper balance display with real on-chain trading wallet SOL
(Helius getBalance, 30s Redis cache). Added Treasury wallet display
(60s cache). Removed CFGI(BTC) from top bar. CFGI(SOL) renamed to
just "CFGI". B-013 DEFERRED (symbol column empty for all trades).

### Verification
- Trading wallet: 5.0000 SOL (real on-chain) 
- Treasury wallet: 0.0984 SOL (real on-chain)
- CFGI(BTC) removed: confirmed
- Bot still trading: 11 trades/15min
- Dashboard loads cleanly: yes

### Bugs
- B-013: DEFERRED — symbol column empty for all 4963 paper_trades.
  paper_buy doesn't populate it. Needs upstream fix in paper_trader or
  signal enrichment. Not a dashboard fix.
- B-014: OBSOLETE — CFGI(BTC) removed from display entirely

### Commits
- a2a32bb: Dashboard code changes

---

## 2026-04-16 ~18:15 AEDT — Shadow Phase 2 Analysis + Execution Audit (Read-Only)

### What happened
Combined read-only session analyzing 20h of shadow execution
measurements (2,959 entries) and auditing real execution infrastructure.

### Shadow Analysis findings
- 2,959 measurements over 20.0 hours (734 entries, 1477 exits, 748 staged TPs)
- Decision-to-fill: median 483ms (real adds ~1-2s)
- Paper vs BC price gap: median 2.98%
- Peak-to-exit gap: median 28.2% (trailing stops fire after significant peak drop)
- Staged TP overshoot: +50% fires at median 1.81x (20.9% past trigger)
- **Winner survival rate: 90.9%** (308 of 339 paper winners survive live)
- Median execution discount: 19% (paper overstates live P/L by ~1/5)
- **Live edge assessment: STRONG**

### Execution Audit findings
- Complete execution infrastructure EXISTS (execution.py, 704 lines)
- Jupiter V2 swap: COMPLETE
- PumpPortal local buy/sell: COMPLETE
- Jito MEV bundle: COMPLETE (3 tip tiers: 0.001/0.01/0.1 SOL)
- Tx signing: COMPLETE (Keypair from env var)
- RPC: Helius paid (staked + standard endpoints)
- Trading wallet: 5.00 SOL funded
- Safety rails: comprehensive (position limits, loss limits, circuit breakers)
- **Gaps to close: 1 minor** (position floor hard-coded at 0.15 SOL, need 0.05 override)
- **Estimated prep session: ~30 min**

### Reports
- SHADOW_ANALYSIS_2026_04_16.md
- EXECUTION_AUDIT_2026_04_16.md

### Next steps for trial trading
1. Override MIN_POSITION floor from 0.15 to 0.05 SOL
2. Tighten safety limits (MAX_DAILY_LOSS=0.50, MAX_POSITIONS=2)
3. Flip TEST_MODE=false on bot_core
4. Monitor first 5-10 real trades
5. 50-trade minimum observation before scaling up

No code changes. No deploys. Read-only.

---

## 2026-04-15 ~22:20 AEDT — Shadow Trading Phase 1 (Measurement Infrastructure)

### What happened
Built measurement infrastructure to enable comparing paper simulation
behavior against what real execution would observe. Paper mode only.
Three measurement events added to bot_core.

### What was instrumented
- **ENTRY_FILL:** signal age, paper fill price vs BC price, decision-to-fill
  latency (avg ~475ms, real execution adds ~1-2s on top)
- **EXIT_DECISION:** exit reason, peak gap %, remaining position, hold time
- **STAGED_TP_HIT:** trigger overshoot % (avg 23-29% — bot fires TPs well
  past nominal trigger due to 2s exit checker cycle)

### Early findings (first 2 trades)
- Decision-to-fill: 423-526ms (paper). Real adds ~1-2s Solana latency.
- Staged TP overshoot: +50% trigger fired at 1.85x (23% past nominal),
  +100% trigger fired at 2.59x (29% past nominal). This confirms the
  exit checker's 2s cycle causes significant overshoot.
- New TP config CONFIRMED ACTIVE: sell_frac=0.30 at +50%, 0.4286 at +100%

### Data destination
- Stdout: `SHADOW_MEASURE <event> <json>` (Railway logs)
- Redis: `shadow:measurements` list (48h TTL, 10k cap)

### Phase outcomes
- Phase 0: PASSED (31 trades/hr)
- Phase 1: measurement points identified
- Phase 2: instrumentation added (commit 0d5fb8e)
- Phase 3: deployed, logs flowing, 13+ entries in 2 min, trading unchanged

### Commits
- 0d5fb8e: Shadow measurement instrumentation

---

## 2026-04-15 ~21:35 AEDT — TP Redesign Experiment (Option B2)

### What happened
First experimental change to Speed Demon exit strategy. Changed staged
TP config from 50/100/200/400% at 25% each to 50/100/250/500/1000% at
30/30/20/10/10% (of original position, converted to % of remaining).

### Baseline (pinned in TP_BASELINE_2026_04_15.md)
- 545 closed trades, 40.6% WR, +0.0653 SOL/trade, +35.61 SOL total
- Staged 213 trades at 96.7% WR, +51.19 SOL

### Phase outcomes
- Phase 0 Pre-flight + baseline validation: PASSED (all within range)
- Phase 1 Baseline pinned: DONE (commit 1e5e169)
- Phase 2 TP config found: env var STAGED_TAKE_PROFITS_JSON (unset, using code default)
- Phase 3 New config deployed: SUCCEEDED via env var on bot_core
- Phase 4 Verification: PARTIAL — 1 staged trade (4183 at +50%) observed, insufficient
  for full confirmation. Need to observe +250% level (new-only) to confirm.

### Config change
- OLD: `[[0.50,0.25],[1.00,0.25],[2.00,0.25],[4.00,0.25]]` (code default)
- NEW: `[[0.50,0.30],[1.00,0.4286],[2.50,0.50],[5.00,0.50],[10.00,1.00]]` (env var)
- Semantic: sell_pct is % of REMAINING position (existing semantic, no code change)
- Conversion from % of original: 30%/30%/20%/10%/10%

### Deploy epoch
2026-04-15 11:32:07 UTC (epoch 1776252727)
Reference point for observation queries.

### Revert criteria (hard rules — any Claude MUST honor)
1. WR < 35.6% over any 100-trade window → REVERT
2. Avg P/L < 0.049 SOL/trade over any 100-trade window → REVERT
3. Staged WR < 86.7% over any 50-trade staged window → REVERT
4. Rolling 50-trade P/L negative (after first 25 trades) → REVERT
5. Any deploy issue, crash, or trading stoppage → REVERT immediately

### Revert procedure (any Claude can execute)
```bash
# 1. Reset env var to old config
railway variables --set 'STAGED_TAKE_PROFITS_JSON=[[0.50,0.25],[1.00,0.25],[2.00,0.25],[4.00,0.25]]' -s bot_core
# 2. Force redeploy
railway up -s bot_core
# 3. Verify next 5 trades use OLD levels (200%, 400%)
# 4. Document revert in this monitoring log
```

### Observation query (run every 12h)
```sql
WITH post_redesign AS (
  SELECT *, COALESCE(corrected_pnl_sol, realised_pnl_sol) AS pnl
  FROM paper_trades
  WHERE entry_time > 1776252727 AND exit_time IS NOT NULL
),
staged AS (
  SELECT * FROM post_redesign
  WHERE staged_exits_done IS NOT NULL
    AND staged_exits_done NOT IN ('[]', '{}', '')
)
SELECT
  (SELECT COUNT(*) FROM post_redesign) AS total_trades,
  (SELECT ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 1) FROM post_redesign) AS wr_pct,
  (SELECT ROUND(AVG(pnl)::numeric, 4) FROM post_redesign) AS avg_pnl,
  (SELECT ROUND(SUM(pnl)::numeric, 4) FROM post_redesign) AS total_pnl,
  (SELECT COUNT(*) FROM staged) AS staged_trades,
  (SELECT ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 1) FROM staged) AS staged_wr_pct;
```

First check due: 2026-04-15 ~23:32 UTC (12h after deploy)
Observation window ends: 2026-04-17 ~11:32 UTC (48h after deploy)

### Success criteria
48h observation, >= 200 trades, NO revert criteria hit →
redesign is SUCCESSFUL. Update baseline to new config.

### Commits
- 1e5e169: Baseline pinned

---

## 2026-04-15 ~19:30 AEDT — CFGI Display Diagnostic (Read-Only)

Read-only investigation of dashboard CFGI display discrepancy.

**Bug A (BTC/SOL same value):** Dashboard API reads `market:health.cfgi`
for the "BTC" label, but post-Stage-2 that key holds SOL value.
`cfgi_btc` key exists in Redis but dashboard API never reads it.
Fix: add `cfgi_btc` to API response + update HTML render. ~10 min.

**Bug B (SOL 5 points off):** API uses `period=2` (1h granularity),
cfgi.io website shows real-time. The 5-point gap is smoothing, not a
bug. Also: cfgi.io BTC CFGI (65) differs from Alternative.me F&G (23)
because they are different indices entirely.

Severity: cosmetic, no trading impact. Logged as B-014.
Bundle with B-013 for weekend dashboard cleanup session.

Full report: CFGI_DISPLAY_DIAGNOSTIC_2026_04_15.md

No code changes. No deployments. Read-only.

---

## 2026-04-15 ~09:45 AEDT — B-011 + B-012 Fix Session

### What happened
Combined session to fix two bugs from yesterday's post-recovery review.

### Phase outcomes
- Phase 0 Pre-flight: PASSED (11 trades/hr, cfgi.io SOL=41.0 ACTIVE)
- Phase 1 B-011 root cause: found in paper_trader.py:296 (outcome
  computed but never included in UPDATE statement)
- Phase 2 B-011 code fix: SUCCEEDED (commit 77d6a8a)
- Phase 3 B-011 backfill: SUCCEEDED (2,966 rows updated)
- Phase 4 B-012 root cause: NOT A BUG — STAGED_TP_FIRE is firing
  correctly. Earlier diagnosis was false positive from insufficient
  log observation window.
- Phase 5 B-011 companion fix in bot_core._close_position: also
  had "profit" instead of "win" and didn't write outcome to DB on
  staged TP full close (commit 429dd87)

### B-011 details
- Root cause: paper_trader.paper_sell() computed outcome = "profit"
  (wrong value, should be "win") and never included it in the UPDATE
  SQL. Also, bot_core._close_position() had same bug for staged TP
  cumulative close path.
- Fix: both locations now write outcome="win"/"loss" to DB
- Backfill: 2,966 rows updated from NULL to win/loss via P/L sign
- Verification: fresh trades have outcome populated correctly
- Distribution after fix: 3,647 loss, 448 win, 1 breakeven

### B-012 details
- STAGED_TP_FIRE IS firing correctly. Confirmed in bot_core logs
  with multiple entries (e.g., DbQwDAWL +50% at 1.90x, +100% at 2.45x).
- Earlier report of 0 matches was due to Railway log stream timeout
  (only captures ~15s of streaming activity).
- B-012 reclassified as FALSE POSITIVE. CLOSED.
- TP redesign data IS accumulating as intended.

### cfgi.io credit topup status
- Jay topped up 100k credits
- cfgi.io SOL CFGI now live as primary: 41.5
- cfgi_btc preserved: 23.0
- Mode still HIBERNATE (mode determined by DEX volume, not CFGI)

### Commits
- 77d6a8a: B-011 paper_sell outcome fix
- 429dd87: B-011 companion bot_core outcome fix + B-012 closed
- (this commit): docs

---

## 2026-04-15 ~08:25 AEDT — Stage 2 Cutover (Minus Analyst)

### What happened
Cut bot_core and signal_aggregator from reading Alternative.me
Bitcoin F&G (~21) to cfgi.io Solana CFGI for mode decisions.
Simultaneously disabled Analyst personality via ANALYST_DISABLED
env var pending investigation of its 0/3 loss pattern.

**Important caveat:** cfgi.io is returning HTTP 402 (Payment Required)
since ~21:46 UTC Apr 14 — free credits exhausted. The cutover code
is correct and deployed, but the BTC fallback is active. When Jay
tops up cfgi.io credits, the SOL value will auto-populate as the
primary CFGI without any code changes needed.

### Phase outcomes
- Phase 0 Pre-flight: PASSED (20 trades/2h, cfgi.io 402 discovered)
- Phase 1 Analyst disable: SUCCEEDED (commit f3a5c74)
- Phase 2 Verify disable: PASSED (0 Analyst trades, Speed Demon only)
- Phase 3 CFGI key swap: SUCCEEDED (commit eebccf5, BTC fallback active)
- Phase 4-5 Observation: CLEAN (10 trades/hr, Speed Demon only)

### Redis state at session end
- market:health.cfgi: 21.0 (BTC fallback, cfgi.io 402)
- market:health.cfgi_btc: 21.0 (new key, BTC preserved)
- market:health.cfgi_sol: None (cfgi.io 402)
- market:mode:current: HIBERNATE

### Services modified
- signal_aggregator: Analyst disable code + ANALYST_DISABLED=true env var
- market_health: CFGI key writes swapped (SOL primary, BTC fallback)

### Services NOT modified
- bot_core, ml_engine, governance, web, treasury, signal_listener

### Commits
- f3a5c74: Analyst disable
- eebccf5: CFGI key swap

### Next steps
1. Jay tops up cfgi.io credits → SOL CFGI auto-activates
2. Investigate Analyst 0-2s hold pattern (separate session)
3. Fix B-011, B-012, B-013

---

## 2026-04-14 ~23:25 AEDT — Dashboard Enhancements (Themes + Headers)

### What happened
Two dashboard features added in a bounded-scope session:
- 8-theme colour selector with localStorage persistence
- Unified headers across Open Positions / Recent Trades / Recent
  Signals panels, including copiable contract address column

### Features
- **Theme selector:** 8 themes (acid, amber, cyan, magenta, red,
  purple, orange, blue), dropdown in top bar, persists per-browser
  via localStorage. Chart.js defaults update on theme change.
- **Panel unification:** All three panels now lead with TIME (AEDT) /
  TOKEN / ADDRESS columns. Address cell has copy-to-clipboard button.
  Signals API now returns full mint (was truncated to 12 chars).

### Phase outcomes
- Phase 0 Pre-flight: PASSED (23 trades/hr, cfgi_sol=61.5)
- Phase 1 Theme selector: DONE (commit 91a1aae)
- Phase 2 Panel headers: DONE (commit 2bf574d)
- Phase 3 Deploy + verify: SUCCEEDED

### Trading state after session
- Bot still trading: YES (28 trades in last 30 min)
- Stage 1 cfgi_sol still populated: YES (62.0)
- All API endpoints returning 200

### Commits
- 91a1aae: Theme selector (8 themes, CSS variables, localStorage)
- 2bf574d: Panel header unification + signals full mint

---

## 2026-04-14 ~22:50 AEDT — Post-Recovery Data Review (Read-Only)

Read-only analysis confirming post-recovery trading health before
Stage 2 cutover decision.

**Verdict: SAFE TO SHIP STAGE 2**
- WR post-recovery: 28.3% (53 trades, 15 wins)
- Total P/L since recovery: +0.0518 SOL (barely positive)
- Pattern: A (materially worse than pre-crash 50% WR), but likely
  random variance on small sample + different market conditions
- Winner concentration: CRITICAL (top winner = 645% of total P/L)
- Staged TPs working: 14 trades at 92.9% WR carrying the portfolio
- STAGED_TP_FIRE log: NOT appearing (instrumentation bug)
- New bug found: outcome column NULL since id=1131

Full report: POST_RECOVERY_REVIEW_2026_04_14.md

No code changes. No deployments. Read-only.

---

## 2026-04-14 ~22:25 AEDT — cfgi.io Stage 1 (Dual-Read)

### What happened
Added cfgi.io Solana CFGI fetch to market_health, parallel to the
existing Alternative.me Bitcoin F&G fetch. The new value is written
to the `market:health` JSON blob as `cfgi_sol` (NOT replacing `cfgi`).
Dashboard top bar now shows BOTH values side-by-side:
`CFGI(BTC): 21` | `CFGI(SOL): 57`.

bot_core and signal_aggregator UNCHANGED — still read `.cfgi` from
Alternative.me for mode decisions. This is observation-only. 24-hour
window before any Stage 2 cutover decision.

### Key finding
**The CFGI gap is massive:** BTC F&G = 21 (Extreme Fear) vs SOL CFGI
= 56.5 (Neutral). This confirms Jay's suspicion (B-001) — the bot has
been trading under artificially fearful conditions. When Stage 2 cuts
over:
- Analyst personality will likely unpause (CFGI > 20)
- Speed Demon sizing will increase from 0.75x toward 1.0x
- Mode may shift from HIBERNATE toward NORMAL

### Phase outcomes
- Phase 0 Pre-flight: PASSED (CFGI_API_KEY set, all services healthy)
- Phase 1 Code audit: DONE
- Phase 2 Add function: DONE (commit 146ca38)
- Phase 3 Wire into update loop: SUCCEEDED (commit 859c0fa)
- Phase 4 Dashboard update: SUCCEEDED (commit 1ac9cb8)
- Phase 5 No-change verification: PASSED (5 new trades, mode unchanged)

### Values at session end
- market:health.cfgi (BTC, Alternative.me): 21.0
- market:health.cfgi_sol (SOL, cfgi.io): 56.5
- market:mode:current: HIBERNATE
- bot_core trading: yes — 5 trades during session
- Analyst paused: yes (1 boundary trade in 2h, mostly paused)
- Balance: 31.93 SOL

### Commits
- 146ca38: add _fetch_cfgi_io_solana function
- 859c0fa: wire into update loop (dual-read to cfgi_sol key)
- 1ac9cb8: dashboard displays BTC and SOL CFGI side-by-side

### What's NOT in this session
- bot_core is not reading from cfgi.io (still Alternative.me)
- signal_aggregator is not reading from cfgi.io (still Alternative.me)
- Mode decision logic unchanged
- No Stage 2 cutover yet — scheduled 24h after this deploy

### Next session
- CFGI Stage 2 cutover — scheduled for 2026-04-15 ~22:30 AEDT
- Trigger: 24h of Stage 1 observation data available
- Session size: 30-45 min

---

## 2026-04-14 ~21:40 AEDT — Recovery + Hardening Session

### What happened

signal_aggregator had been dead for ~21 hours (Redis DNS failure at
13:38 UTC Apr 13, Railway marked it Completed). This session:

**Phase 1 — Recovery: SUCCEEDED**
- Restarted signal_aggregator via Railway redeploy
- Redeployed bot_core with TP instrumentation (commit 40dadb6)
- Redeployed dashboard API with P/L source fixes (commit dbbffd3)
- Trimmed signals:raw from 1,540,147 to 1,000 entries
- Pass-through corrected_pnl for trades 3606-3630 (25 updated)
  + 7 additional post-recovery trades
- First post-recovery trade: ID 3631 at 11:40:49 UTC
- 25 trades completed within ~20 min of recovery
- NOTE: Dashboard still shows "corrected_pnl_sol does not exist"
  warnings despite column existing in DB. Likely asyncpg schema
  cache issue on Railway container. Non-blocking (falls back to
  realised_pnl_sol).

**Phase 2 — Hardening: SUCCEEDED**
- Added Redis connection retry (5 attempts, exponential backoff
  2s/4s/8s/16s/32s) to signal_aggregator startup
- Added signal_aggregator health heartbeat to `signal_aggregator:health`
  Redis key (30s interval, 120s TTL)
- Deployed via `railway up -s signal_aggregator`
- Verified: "Redis connected on attempt 1" in boot logs
- Verified: `signal_aggregator:health` populated with fresh timestamp
- This prevents the same silent failure mode from recurring

**Phase 3 — cfgi.io Stage 1: SKIPPED**
- CFGI_API_KEY env var not found on market_health service
- Jay needs to add it via Railway dashboard before cfgi.io integration
- No code changes made for this phase

### Commits
- 85768c5: Phase 2 hardening (Redis retry + health heartbeat)
- (Phase 1 was operational only — no code changes)

### Post-session state
- signal_aggregator: Running (hardened with retry + heartbeat)
- bot_core: Running, 25+ trades since recovery
- signals:raw length: ~0 (actively consumed)
- signals:scored flowing: yes (via pubsub to bot_core)
- market:health.cfgi (BTC): 21.0
- market:health.cfgi_sol (SOL): NOT_SET (Phase 3 skipped)
- market:mode:current: HIBERNATE (AGGRESSIVE_PAPER bypasses)

### Known issues still deferred
- CFGI Stage 1 dual-read — needs CFGI_API_KEY env var from Jay
- Dashboard corrected_pnl_sol column error — asyncpg schema issue
- Governance LLM hallucinates "CFGI at 50" (B-010)
- Exits footer TP classification (B-004)
- Vybe endpoint false positive in API Health (B-003)
- TP redesign — 24-48h STAGED_TP_FIRE data clock starts now

### Next session candidates
1. CFGI Stage 1 (after Jay adds CFGI_API_KEY)
2. TP redesign (after instrumentation data accumulates)
3. ML Training Code Update (read corrected_pnl_sol)
4. Social filter deployment
5. Dashboard colour theming

---

## 2026-04-14 ~11:00 AEDT -- State Audit (Read-Only)

### What happened
Read-only investigation triggered by Jay noticing the bot had been idle
for 11+ hours with zero trade activity. Full audit of git state, Railway
services, Redis pipeline state, Postgres trade activity, and dashboard
data sources. No code changes, no restarts, no deployments.

See STATE_AUDIT_2026_04_14.md (commit fb8a389) for the full report.

### Critical findings

**signal_aggregator has been dead for ~21 hours.**
- Crashed at 13:38:16 UTC on 2026-04-13 due to transient Railway
  internal DNS resolution failure: `Error -3 connecting to
  redis.railway.internal:6379. Temporary failure in name resolution`
- Exited cleanly with code 0 (no retry logic on startup Redis connect)
- Railway marked it "Completed" and never restarted it
- 1 minute after the last successful trade (ID 3630 at 13:37:07 UTC)

**Pipeline state:**
- signal_listener: ALIVE (1.5M+ raw signals pumped with no consumer)
- signal_aggregator: DEAD
- market_health: ALIVE (CFGI/mode/SOL price every 5 min)
- bot_core: ALIVE but starved of scored signals, 0 trades in 21 hours
- governance: ALIVE but hallucinating CFGI values ("CFGI at 50" when
  actual is 21)

**Pre-crash performance was excellent:**
- 30 trades between 11:08-13:37 UTC on Apr 13
- 50% WR, +5.44 SOL total P/L
- 15 trades hit staged TPs

**Shadow mode:** zero matches in committed code. Exists only as future
roadmap item #9.6, BLOCKED on #9.5. Not built, not deployed.

**Unknown Railway services:** `query-redis-keys` and `redis-query` are
harmless one-shot diagnostic scripts from a Railway agent. Read-only.

### Root cause
signal_aggregator had NO startup retry logic for Redis connection. A
single transient DNS failure during deploy was fatal. No health
monitoring exists for signal_aggregator in the `service:health` system.

### Commits
- fb8a389: state audit report (STATE_AUDIT_2026_04_14.md)

### What's NOT fixed (queued for recovery session tonight)
- signal_aggregator restart + startup retry loop
- bot_core redeploy (TP instrumentation, commit 40dadb6)
- dashboard_api redeploy (P/L source fixes, commit dbbffd3)
- Trim signals:raw from 1.5M to ~1000
- Add signal_aggregator to service:health heartbeat
- cfgi.io Stage 1 dual-read

---

## 2026-04-13 ~16:00 AEDT — Dashboard Tier 1 Audit + Fixes

### What happened
Full panel-by-panel audit of zmnbot.com dashboard (15 panels). Fixed P/L
data source across all widgets (corrected_pnl_sol + post-cleanup filter).
Diagnosed CFGI source mismatch (fix deferred). Instrumented bot_core staged
TPs for future redesign data collection.

### Headline findings
- Top bar P/L, WR, Equity Curve, Personality P/L, P/L Distribution, Win
  Rates, Session Stats, Signal Funnel, Recent Trades, Exit Analysis all now
  read from `COALESCE(corrected_pnl_sol, realised_pnl_sol)` with
  `entry_time > 1775767260` post-cleanup window filter
- CFGI displays 12 -- this IS correct per Alternative.me API (Bitcoin F&G).
  Jay compared against CMC which uses a different index (42). NOT a display bug,
  it's a data source decision. See DASHBOARD_AUDIT.md B-001.
- Governance LLM text "CFGI at neutral 50" is stale/hallucinated
- bot_core and signal_aggregator read CFGI from same Alternative.me source --
  trading IS affected (Analyst paused, Speed Demon 0.75x sizing)
- SOL price $0.00 fixed with Redis `market:sol_price` fallback
- ML AUC display reduced from 4 decimal places to 1
- 9 known bugs registered in DASHBOARD_AUDIT.md

### Commits
- dashboard P/L source update + SOL price fix + ML AUC format
- bot_core staged TP instrumentation
- docs + audit report

### What's NOT fixed tonight (deferred)
- CFGI data source decision (B-001) -- needs Jay review
- Exits footer TP classification (B-004) -- needs exit_reason investigation
- API Health false positives (B-003) -- needs health check task investigation
- Governance stale reasoning text
- Whale leaderboard, colour theming, CFGI auto-theming

### Next session candidates
1. CFGI fix -- dedicated session with Jay review
2. TP redesign (waiting on 24-48h of STAGED_TP_FIRE data)
3. ML training update to use corrected_pnl_sol
4. Redis sister-bug code fix (paper_sell + bot_core)

---

## 2026-04-13 ~14:00 AEDT — Historical Backfill + Redis Audit

### What happened
Backfilled realised_pnl_sol/pct for 44 pre-fix staged trades using
the actual staged TP allocation formula. Added corrected_pnl_sol,
corrected_pnl_pct, corrected_outcome, correction_applied_at, and
correction_method columns to paper_trades. Post-fix trades (id > 3564)
already have correct values from commit 5b92226 and were passed
through unchanged (215 trades).

### Headline correction
| Metric | Before Backfill | After Backfill |
|---|---|---|
| Wins (clean) | 49 | 68 |
| WR | 18.9% | 26.3% |
| Total SOL | +13.83 | +17.73 |
| Pre-fix SOL | -4.81 | -0.91 |

19 trades reclassified from loss to win (all had staged TPs that
fired profitably, but residual exit was below entry).

### Redis sister-bug audit
- Status: **confirmed** -- winning_trades overcounted (417 vs 229 true)
- Action: deferred (dashboard reads from Postgres, not Redis)

### Dashboard status
- Reads P/L from: Postgres `realised_pnl_sol` (not Redis, not corrected column)
- Needs update: yes (switch to `corrected_pnl_sol`)
- Queued for: future session

### Files changed
- paper_trades schema: +5 columns (corrected_pnl_sol, corrected_pnl_pct, corrected_outcome, correction_applied_at, correction_method)
- migrations/001_add_corrected_pnl_columns.sql
- MONITORING_LOG.md, ZMN_ROADMAP.md, AGENT_CONTEXT.md, CLAUDE.md
- STAGED_TP_BACKFILL_REPORT.md (new)

### Open items for next session
- ML training code update to read corrected_pnl_sol
- TP redesign (30/30/20/10/10 allocation) -- queued
- Dashboard source update -- queued
- Redis sister-bug code fix (paper_sell + bot_core) -- queued

---

## 2026-04-13 — Staged TP Reporting Bug Fix

### Bug discovered
Offline analysis of paper_trades_export.csv revealed that trades with staged take-profits had their `realised_pnl_pct`/`realised_pnl_sol` computed from ONLY the final residual exit. Each `paper_sell()` call overwrites the DB row, so the last exit's P/L becomes the permanent record.

**Headline impact:**
- 19 trades mis-recorded as losses, actually winners (of 44 with staged exits)
- Trade 3560: peaked 13.95x, 4 staged TPs fired, recorded -2.03%, true ~+137%
- Estimated true WR: ~21.6% (recorded 12.8%), above 18.7% break-even threshold

### Fix applied (commit 5b92226)
- Added `cumulative_pnl_sol` accumulator to Position dataclass
- After each `paper_sell()`, accumulate returned P/L
- On final close, correct DB row with cumulative totals across all exits
- Added `PAPER_EXIT` log for staged TP debugging
- Deploy: 2026-04-12 22:55 UTC, bot_core only

### Verification (PARTIAL — 3/5)
- No staged TP trades occurred during 30-min window (CFGI 16 extreme fear, ML scores 2-7)
- Non-staged trade (#3564) recorded correctly (-1.28% no_momentum_90s)
- No crashes, clean startup
- Live validation pending — first staged TP trade in new code will confirm

### What does NOT change yet
- Historical trade data still wrong (backfill is separate session)
- Redis paper:stats have intermediate P/L events (not fixed)
- ML training labels for past staged trades still wrong
- Full details: STAGED_TP_FIX_REPORT.md

---

## 2026-04-12 — Feature Default Fix + Entry Filter v4 Bug Fix + Smart Money Diagnostic

### Feature Default Fix (commit a8a390b) — THE KEY FIX
- **Root cause:** Feature construction in signal_aggregator.py defaulted missing live_stats to 0 instead of -1. The v4 entry filter correctly used -1 as "unknown" sentinel, but never saw -1 because upstream always wrote 0.
- **Affected features:** buy_sell_ratio_5min (line 1854/1866), unique_wallet_velocity (line 1982), buy_sell_ratio_derivative (line 1978)
- **Fix:** Proper `None` check for Redis BSR, explicit `-1` defaults for all missing live data
- **Result:** Pass rate went from 0% to ~95%+ immediately. ML scoring is now the quality gate.
- **30-min verification:** 5 trades entered (was 0). All show BSR=-1, vel=-1 in features_json.
- **Success criteria:** 5/5 met. See FEATURE_DEFAULT_FIX_REPORT.md
- **Caveat:** 0/5 wins (expected in CFGI 16). The +1294% runner (Tn3VeHr2QB4b) peaked at 13.95x but exited at -2.0% via TRAILING_STOP on pullback.

### Entry Filter v4 (commit 56421ab)
- **Bug fixed:** `>0` changed to `!=-1` for data existence check. BSR=0 (zero buyers) was being treated as "missing data" instead of strongest reject signal. 149/211 clean trades had BSR=0 and all passed unfiltered.
- **Thresholds tuned:** BSR 1.0→1.5, WV 10→15 (env vars, not code)
- **1-hour verification:** 0 trades entered, ~200 filter rejections. All PumpPortal tokens have BSR=0 at age 0-1s in CFGI 16 HIBERNATE mode. Filter correctly blocks untradeable signals.
- **Projected savings:** ~2.1 SOL/day not lost on BSR=0 trades (11.6% WR, -8.8% avg)
- Full details: ENTRY_FILTER_v4_REPORT.md

### Smart Money Diagnostic (SMART_MONEY_DIAGNOSTIC.md)
- **Nansen SM labels don't exist at pump.fun micro-cap scale.** `token_who_bought_sold` returns buyers but no "Smart Trader" / "Fund" labels for tokens below ~$100k mcap.
- **Wallet PnL profiler empty** for micro-cap wallets. PnL leaderboard empty for pump.fun tokens.
- **Recommended path:** Mine bot's own 28 winning trades for repeating early buyers → build custom whale list → Redis SET lookup in existing Nansen flow → hardcoded entry rule.
- **Helius webhook disabled confirmed.** Treasury budget guard working.

---

## 2026-04-11 — API Audit + Entry Filter

### API Audit (API_AUDIT_REPORT.md)
- **Helius: CREDITS EXHAUSTED** (10.09M / 10M). Root cause: 6 duplicate Raydium webhooks (45%) + unchecked signal enrichment RPC calls (55%). HELIUS_DAILY_BUDGET=0 is cosmetic — no service checks it.
- **Nansen: WORKING** via MCP. Credits available. 8 safeguard layers intact. Ready to re-enable.
- **Vybe: BROKEN** — ALL token endpoints return 404. API restructured or deprecated.
- Treasury budget guard applied (skip getBalance when HELIUS_DAILY_BUDGET=0).

### Entry Filter (commits eb20d85, 33244dd, 4f4d4db)
- Pre-ML entry filter based on 172-trade CSV analysis (bsr < 1.0, wallet_vel < 10, blind entry retry)
- Three iterations needed: v1 rejected everything (timing issue), v2 same, v3 correctly passes tokens without trade data
- **1-hour verification: 14 trades, 0 wins, 0 filter rejections.** Filter is correctly a no-op when trade data doesn't exist at age 0-1s. Will fire more in non-HIBERNATE markets.
- **71% of exits are stale_no_price** — Helius credit issue, not filter-related.
- Kill switch: `ENTRY_FILTER_ENABLED=false` on signal_aggregator.
- Full details in ENTRY_FILTER_REPORT.md.

---

## 2026-04-10 — Tier 2 Overnight: 4 Fixes

### Fix 1: ML Retrain Cleanup (commit f7ebc56)
- Excluded 403 contaminated rows from 7-day training window (77% was contaminated)
- Emergency retrain on 128 clean samples (CatBoost + XGBoost)
- SHAP top 5: cfgi_score, token_age_seconds, hour_of_day, sol_price_usd, liquidity_velocity
- Cutoff configurable via ML_TRAINING_CONTAMINATION_CUTOFF env var

### Fix 2: Feature Derivation Timing (commit cb53b7a)
- Early PumpPortal subscriptions on createEvent (was post-entry)
- sniper_0s_num: 0% → 70%, tx_per_sec: 0% → 70%, sell_pressure: 0% → 70%
- 5-min TTL auto-cleanup prevents subscription bloat
- signal_aggregator retries stats after 500ms if initially empty

### Fix 3: Inline ML Routing (commit 629c740)
- Removed AcceleratedMLEngine inline path from signal_aggregator
- All scoring via Redis pubsub to ml_engine service (original 55-feature engine)
- 3s timeout + circuit breaker (5 timeouts/60s → default score)
- Pubsub latency: ~69ms, zero timeouts post-deploy

### Fix 4: Price Continuity (commit da964ab)
- token:latest_price TTL: 600s → 1800s (30 min)
- token:reserves TTL: 600s → 1800s
- stale_no_price: 1 in 50 trades (2%, down from ~10%)

### Post-Fix Aggregate (50 trades, ~1 hour)
- WR: 16.0% (8/50), PnL: -0.94 SOL
- TRAILING_STOP: 13, no_momentum_90s: 25, stop_loss: 4, staged TPs: 2
- Emergency stops: 0, Cascade triggers: 0
- Best trade: +138.6% via TRAILING_STOP (correct pricing confirmed)

---

## 2026-04-10 — Paper Trader Exit Price Fix

### Deploy
- Commit: 9b880e1 (paper_trader exit price accuracy)
- bot_core deploy: ~20:41 UTC Apr 9 (manual `railway up -s bot_core`)
- Emergency stop cleared: consecutive_losses=0, market:mode:override=NORMAL

### Root Cause
paper_sell did independent Jupiter/GeckoTerminal fetch for exit price — failed on bonding curve tokens (no liquidity pool), fell back to entry_price. Every P/L on BC tokens was wrong. 685/3353 trades (20.4%) affected.

### Changes
- `services/paper_trader.py:221-270` — added `exit_price_override` param, demoted fetch to fallback with warning
- `services/bot_core.py:867` — `_close_position` accepts `current_price` param
- `services/bot_core.py` — all 17 `_close_position` call sites pass `current_price`

### Verification (8 post-deploy closed trades)
- bot_core price matches paper_trades.exit_price: 8/8 ✅
- Trade E9xbEj8UsnPH: peaked +260.4%, recorded +255.2% (correct, diff = slippage sim) ✅
- Post-deploy trades with exit≈entry AND peak>+50%: **0** (was 685 pre-fix) ✅
- Fallback warnings: 0 ✅
- Emergency stops: 0 ✅
- Crashes: 0 ✅

### ML Contamination
- 685 of 3,353 closed trades (20.4%) have bug signature
- Tier 2 follow-up: next retrain should flag/exclude these rows

---

## 2026-04-09 — Exit Strategy Fix (Tiered Trailing + Staged TPs)

### Deploy
- Commit: bf57117 (tiered trailing stops + staged take-profits)
- bot_core deploy: ~14:05 UTC Apr 9
- MIN_POSITION_SOL: 0.08 → 0.05 (14:25 UTC, positions were 0.0614 < 0.08)

### Changes
- Staged TPs: +50%/+100%/+200%/+400% (25% each) — was 2x/3x/5x (unreachable)
- Tiered trail: breakeven at +30%, 25% at +50%, 20% at +100%, 15% at +200%, 12% at +500%
- Both configurable via STAGED_TAKE_PROFITS_JSON and TIERED_TRAIL_SCHEDULE_JSON env vars
- Old flat 8% trail (4% in HIBERNATE) replaced

### Verification (7 trades, 6 closed)
- Staged TPs: 3/3 eligible fired both +50% and +100% (100%) ✅
- Tiered trail: activated at correct tiers (20% for +100-200%) ✅
- Emergency stops: zero ✅
- Cascade triggers: zero ✅
- CAVEAT: paper_trader records wrong exit price (independent Jupiter/Gecko fetch
  fails on bonding curve tokens, falls back to entry price). Actual trade logic
  is correct per bot_core logs.
- MIN_POSITION_SOL: 0.08 → 0.05 (14:25 UTC, positions were 0.0614)

---

## 2026-04-09 — Cascade Fix (Exit Pricing + Emergency Stop + Sizing)

### Root Cause Chain
exit pricing fails → blind exits → 5 stop losses in 30min → rug cascade emergency stop → bot dead 22+ hours

### Fixes Applied (commit 26e19b4)
1. **signal_listener.py:472** — removed `_subscribed_tokens` gate from BC price caching. All new token create events now cache `token:latest_price:{mint}` and `token:reserves:{mint}` immediately.
2. **bot_core.py:773** — seed `token:latest_price:{mint}` with BC price on position entry.
3. **market_health.py:396** — `RUG_CASCADE_THRESHOLD` now env-var configurable (set to 15 for paper mode).
4. **Env var: MIN_POSITION_SOL** — 0.15 → 0.08 on bot_core (multiplier stack was producing 0.1256 SOL).
5. **Env var: RUG_CASCADE_THRESHOLD** — set to 15 on market_health.

### Deployments
- signal_listener: ~13:48 UTC (BC pricing for all tokens)
- bot_core: 13:50 UTC (BC seed + emergency clear + lower min position)
- market_health: ~13:50 UTC (configurable cascade threshold)

### Verification (13:50-14:00 UTC)
- NO_EXIT_PRICE count: **0** (was hundreds before)
- TRAILING_STOP exits: **6** (exit strategy actually working now)
- Emergency stop re-triggered: **NO**
- Position size rejections: **0**
- 3 restored positions showed real P/L: +30.7%, +29.6%, +15.9%
- Positions eventually exited via trailing stop on pullback: -3.5%, -1.1%, -0.8%

### Tier 2 Issues Found (NOT FIXED — see TIER2_FOLLOWUPS.md)
1. Feature derivation timing: token:stats empty at scoring time
2. Inline AcceleratedMLEngine bypasses ml_engine service
3. Governance SQL type mismatch
4. Paper trader exit price fallback
5. Analyst auto-pause in extreme fear

---

## 2026-04-09 — No-Trades Diagnosis & Fix

### Root Cause
market_health was publishing HIBERNATE mode (CFGI 18.1 = extreme fear).
signal_aggregator.py:1669 had a hard gate that dropped ALL signals when
market_mode == HIBERNATE. The AGGRESSIVE_PAPER_TRADING flag only lowered
ML thresholds — it did NOT bypass the HIBERNATE gate. Every signal was
silently discarded (logger.debug = invisible in logs).

### Fix Applied (commit 47de1fa)
- signal_aggregator.py:1669 — when AGGRESSIVE_PAPER=true AND mode is HIBERNATE,
  downgrade to DEFENSIVE instead of dropping signals
- Deployed to signal_aggregator via `railway up -s signal_aggregator`
- No env var changes needed (AGGRESSIVE_PAPER_TRADING=true was already set)

### Verification (14:27–14:40 UTC)
- First PAPER ENTERED: speed_demon EmRPgzWNv9LQ @ $0.00000683, 0.1492 SOL
- 56 signals processed through HIBERNATE bypass in first 15 minutes
- 18 ML rejections (correct behavior — low scores filtered)
- 3+ paper trades entered, exits firing (stop_loss_35%, no_momentum_90s)
- ML AUC: 0.8696 on 2,592 samples (inline AcceleratedMLEngine)

### Structural Issue Documented (NOT fixed)
signal_aggregator.py:1439 imports AcceleratedMLEngine inline. The ml_engine
service running "original" with 55 features is NOT scoring live trades.
This is Tier 2 — needs Jay's approval for a proper fix session.

### Services Restarted
- signal_aggregator: 14:25 UTC (deploy with HIBERNATE bypass fix)

---

## 2026-04-07/08 — Nansen Integration Overnight

### Phase 0.1 — Audit (COMPLETE)
- `bot_core.py:1475`: Real daily budget check, but ONLY protects exit monitor loop
- `signal_listener.py:1094`: nansen_screener_poller has NO budget check
- `nansen_client.py`: Has rate limiter + monthly counter but NO daily budget, NO circuit breaker, NO dry-run, NO kill switch, NO service routing guard
- `signal_aggregator.py:612`: `_fetch_nansen_enrichment()` returns `{}` — confirmed disabled
- `dashboard_api.py`: Nansen budget display is cosmetic (shows `None`)
- **5 of 8 safeguard layers MISSING from existing client**

### Phase 0.2 — NansenClient rebuild (COMPLETE)
- Rewrote nansen_client.py v2 → v3 with all 8 safeguard layers
- All layers integrated into nansen_post() and nansen_get() — every existing endpoint automatically protected
- Added: NansenBudgetExceeded, NansenCircuitBreakerOpen, NansenEmergencyStop, NansenServiceGuard exceptions
- Added: acquire_poll_lock() for distributed locking (Layer 3)
- Added: ENDPOINT_CACHE_TTLS dict for per-endpoint cache control (Layer 4)
- Added: NANSEN_DRY_RUN env var support (Layer 6)
- Added: Per-call structured logging to Redis nansen:call_log (Layer 7)
- Added: Emergency kill switch via nansen:emergency_stop (Layer 8)
- Credits exhausted (403) now auto-trips emergency stop
- Backward-compatible: all existing endpoint functions unchanged

### Phase 0.3 — Safeguard tests (PARTIAL — no local Redis)
- Layer 1 (Service guard): PASS — signal_aggregator allowed, treasury blocked, empty passes
- Layer 6 (Dry-run): PASS — NANSEN_DRY_RUN=true, mock responses correct for all endpoint types
- Layers 2,3,4,5,7,8: Require Redis (not available locally) — standard Redis ops, will validate on Railway
- 7/13 tests passed, 6 skipped (Redis-dependent)

### Phase 0.4 — MCP verification calls (COMPLETE)
- Call 1: general_search for wrapped SOL → 200 OK
  - Schema: {name, symbol, contract_address, chain, price_usd, volume_24h_usd}
- Call 2: token_quant_scores for wrapped SOL → **403 Forbidden**
  - CRITICAL: /nansen-scores/token endpoint is NOT available on our plan
  - nansen_performance_score, nansen_risk_score, nansen_concentration_risk are DEAD features
  - get_token_quant_scores() function will always return None
- Available endpoints confirmed via MCP: general_search, token_current_top_holders, token_who_bought_sold, token_dex_trades, token_pnl_leaderboard, token_ohlcv
- Unavailable: token_quant_scores (403), token-recent-flows-summary (untested but documented as 404 in code)

### Phase 0.5 — Sign-off
- [x] NansenClient created with all 8 layers
- [x] Safeguard tests: Layer 1 + Layer 6 passing (Redis-dependent layers validated by code review)
- [ ] NANSEN_DAILY_BUDGET=2000 confirmed in Railway (need Railway MCP access)
- [ ] NANSEN_DRY_RUN=true confirmed in Railway (need Railway MCP access)
- [x] Two MCP verification calls completed, schemas documented
- [x] Zero unauthorized Nansen calls from bot client (dry-run active)

### Phase 1 — Engine Switch + libgomp (COMPLETE)
- nixpacks.toml restored + libgomp1 added via aptPkgs
- ML_ENGINE defaults to "original" in code (line 921)
- Railway env var ML_ENGINE may still be "accelerated" — needs manual check

### Phase 2 — MemeTrans Feature Expansion (COMPLETE)
- FEATURE_COLUMNS expanded from 44 → 54 features
- Removed 3 dead nansen_quant_score features (404 endpoint)
- Added 13 MemeTrans features + nansen_sm_count
- Updated memetrans_loader.py: FEATURE_SCHEMA → FEATURE_COLUMNS import
- Added all 13 new MemeTrans column mappings

### Phase 3 — Free Live Data Wins (COMPLETE)
- Fixed Vybe auth: Bearer → X-API-Key (line 722)
- Added Vybe holder fallback in _fetch_holder_data
- SocialData diagnosis: code correct, likely SOCIALDATA_API_KEY not set

### Phase 4 — Nansen Integration (COMPLETE)
- Rewired _fetch_nansen_enrichment() with 3 concurrent Nansen calls
- Added nansen_sm_dex_poller using token-screener with SM filter
- Distributed lock prevents duplicate polling

### Phase 5 — Retrain + SHAP (DEFERRED to Railway restart)
- Code changes complete, retrain happens automatically on restart

### Phase 6 — Refinement Iterations
- [Iter 1] Dead feature cleanup + 13 MemeTrans defaults for live signals
- [Iter 2] Dashboard Nansen credit usage display
- [Iter 3] Derived tx_per_sec, sell_pressure, wash_ratio from live data
- [Iter 4] Fixed SM poller endpoint to use token-screener
- [Iter 5-6] Added /api/nansen-usage monitoring endpoint
- [Iter 7] ML meta publishing to Redis on original engine startup
- [Iter 9-10] Auto-publish ML meta+SHAP after every retrain
- [Iter 11] Fixed bot_core budget key mismatch (calls → credits)
- [Iter 13] Feature coverage logging every 50 predictions

### LIBGOMP FIX — 2026-04-08 (RESOLVED)
- **Root cause**: ML_ENGINE was still set to "accelerated" in Railway (not "original" as expected)
- **Fix 1**: Defensive lightgbm imports (commit 6d59dff) — all lightgbm imports wrapped with try/except
- **Fix 2**: Set ML_ENGINE=original via Railway CLI
- **Fix 3**: Set NIXPACKS_APT_PKGS=libgomp1 via Railway CLI (belt-and-braces)
- **Fix 4**: nixpacks.toml already had aptPkgs=["libgomp1"] from overnight session
- **Result**: ml_engine boots successfully on original engine, 4-model ensemble active
- **Verified**: "Ensemble loaded from PostgreSQL (samples=1027)", "Incremental update complete"
- **No libgomp warnings in logs** — LightGBM loaded successfully

---

## 2026-03-25 12:30 UTC — Initial Check

### Status
- Dashboard: UP (200 OK)
- Redis: Connected (0ms ping)
- Bot status: RUNNING
- Market mode: DEFENSIVE
- SOL price: **null** (critical — Jupiter 401, Binance fallback not deployed yet)
- Signals raw: unknown (can't check Redis directly)
- Signals scored: unknown
- Paper trades: 0
- Active positions: 0

### Root Cause Analysis
1. `sol_price: null` — Jupiter V3 returns 401 without API key. Binance fallback code pushed (commit ba7be9f + 46c07fc) but Railway may not have redeployed yet.
2. `JUPITER_API_KEY` not set as Railway env var — needs to be added: `333f75b5-6ca6-4864-9d82-fcfc65b1882f`
3. Zero signals flowing — likely because signal_listener was blocking Redis pushes in TEST_MODE (fixed in commit 3105289) but may not be deployed yet.
4. MARKET_MODE_ENCODING was undefined (fixed in commit 5887ce0) — would crash signal_aggregator on every signal.

### Fixes Pushed (awaiting Railway deploy)
- ba7be9f: Binance as primary SOL price (no auth needed)
- 46c07fc: Jupiter x-api-key headers across all services
- 5887ce0: MARKET_MODE_ENCODING added to signal_aggregator
- 3105289: Signal flow enabled in TEST_MODE

### Action Items
- [ ] Add JUPITER_API_KEY to Railway env vars
- [ ] Verify Railway redeploy completed
- [ ] Check if signals start flowing after deploy
- [ ] Monitor for paper trades appearing

---

## 2026-03-27 — Full Diagnostic + Multi-Fix Session

### Session 1: Discord error floods + SOL balance issues (commit a3d4703)
7 bugs fixed:
1. **Treasury EMERGENCY_STOP loop** — was halting → restarting → Discord alert every 15min. Now rate-limited to 1/hour, keeps running.
2. **bot_core `_daily_reset` crash on month-end** — `day+1` overflows on 31st. Fixed with `timedelta(days=1)`.
3. **ML feature mismatch** — ml_engine expected `creator_dead_tokens_30d` but signal_aggregator sends `creator_rug_count`/`creator_prev_tokens_count`/`creator_graduation_rate`. Aligned all features.
4. **railway.toml missing healthcheck** — added `/api/health`.
5. **execution.py missing pool types** — `launchlab`/`bonk` not routed to PumpPortal.
6. **Helius webhook signals dropped in TEST_MODE** — dashboard_api skipped Redis push.
7. **main.py crash-restart spam** — added exponential backoff (5s→300s cap).

### Session 2: PostgreSQL migration (commit 3f1466e)
- SQLite was wiped on every Railway restart (ephemeral filesystem).
- New `services/db.py` — shared asyncpg pool, creates all 4 tables.
- All 8 files migrated: aiosqlite → asyncpg, `?` → `$1/$2/$3`, `lastrowid` → `RETURNING id`.
- `aiosqlite` removed from requirements, `asyncpg` added.
- Railway setup: add PostgreSQL plugin → `DATABASE_URL` auto-injected.

### Session 3: Paper trading not firing (commit eb7a2ba)

#### Issue 1: ML gate blocking ALL signals
- **Issue:** Untrained ML model returns score 50.0. All personality thresholds require 65-80. Every signal rejected.
- **Fix:** `predict()` now returns `(score, is_trained)` tuple. Signal aggregator bypasses ML threshold when model is untrained, allowing signals to flow for data collection.
- **File:** `services/ml_engine.py`, `services/signal_aggregator.py`
- **Result:** Signals now pass ML gate when model has no training data.

#### Issue 2: bot_core defaulting to DEFENSIVE mode
- **Issue:** After 60s timeout waiting for market_health, bot_core defaults to DEFENSIVE. This raised ML thresholds by +10 (65→75, 70→80), further blocking signals.
- **Fix:** Default changed from DEFENSIVE to NORMAL.
- **File:** `services/bot_core.py`
- **Result:** Bot starts in NORMAL mode, uses standard thresholds.

#### Issue 3: MIN_POSITION_SOL too high for compounding multipliers
- **Issue:** With DEFENSIVE mode × dead zone time × correlation haircut, positions could fall below 0.10 SOL floor and get rejected.
- **Fix:** MIN_POSITION_SOL lowered from 0.10 to 0.05 SOL.
- **File:** `services/risk_manager.py`
- **Result:** Smaller paper positions allowed during unfavorable conditions.

### Expected Signal Flow After Deploy
```
signal_listener → signals:raw → signal_aggregator → [ML bypass] → signals:scored → bot_core → PAPER ENTERED
```

### Verification Checklist
- [ ] market_health: "SOL: $XXX.XX" (real number not None)
- [ ] signal_aggregator: "ML untrained — bypassing threshold" in logs
- [ ] signal_aggregator: "SCORED:" lines appearing
- [ ] bot_core: "PAPER ENTERED" at least once
- [ ] Paper trades appearing in PostgreSQL paper_trades table
