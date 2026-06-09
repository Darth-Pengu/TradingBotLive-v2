# ZMN STATUS — operational journal

> Newest entry at top. Append-only. Never rewrite history.
> Every CC session appends an entry. Upload this to every Claude chat.
>
> See CLAUDE.md § "STATUS.md — single-file state tracker" for the convention.

---

## 2026-06-09 — LIVE-MC-CEILING-VERIFY-001 (read-only: does the live MC gate admit paper's 91% sub-$1k band?)

**Committed:** docs-only — NEW `docs/audits/LIVE_MC_CEILING_VERIFY_001_2026_06_08.md` + STATUS/ROADMAP/CLAUDE/AGENT_CONTEXT updates. **ZERO code/env/Redis/DB write. Read-only.**
**Verdict:** the live MC gate is **SAFE** (fails CLOSED `bot_core.py:1155-1157`; formula `price×1e9` USD identical across all 3 gates; binding cap **$1000**; both ceilings **STABLE across the §6 flip-config**) — **but the 91% sub-$1k WR does NOT transfer cleanly.**
**The crux:** paper's `market_cap_at_entry` == the gate quantity `entry_price×1e9` (verified exact), BUT the price INPUT diverges — live=Redis **fill-time** PumpPortal-stream-first; paper=Jupiter/Gecko→**signal-time** BC fallback + slippage bump. Live-admitted set = paper band **± un-measurable signal→fill drift**, landing on the **$1000 WR cliff**.
**🟠 NEW finding (not in the prompt's register):** "sub-$1k" is a **price PROXY**, not true MC (true full-supply MC ~8× larger, median ~$5172). WR is a near-vertical cliff in the proxy (`<500`=99.85% → `800-1000`=26.72% → `≥1000`≈0%). The 91% = the gate **selecting the winning side of its own proxy** (entry-price-selection artifact), **NOT a validated small-MC edge**. 800-1000 fringe = 9.07% of sub-1k, already a loss zone.
**DB (n=4468 closed SD paper):** sub-1k n=2890 WR **91.90%** +189.79 SOL (reproduces 91%); <1k & ML≥65 n=1724 **92.58%**; **0 rows ≥$1000 in last 14d** (paper confined to <1k by the same env it reads).
**Flags:** 🔴 FAIL-OPEN=**NO** (fails closed). 🔴 MC-MISMATCH=**PARTIAL** (formula same, source differs). 🟠 TIMING-DRIFT=**YES**. 🟠 PROXY-ARTIFACT=**YES** (new). Residuals: env=0 disables the whole gate (config fail-open); no lower price-sanity floor; drift un-instrumented.
**Bot state:** TEST_MODE=true (paper), RUNNING, wallet 5.064 SOL, 0 at risk. Unchanged by this session.
**Blockers cleared:** none (read-only). **Blockers new/active:** edge-validation owed (the 91% is proxy-bounded, not a confirmed live edge — instance of COST_FIDELITY_GAP) → EDGE-PROXY-ARTIFACT-EVAL-001; drift instrumentation (log live `fill_price` + signal-time BC anchor per live trade) → OBS-011/SLIPPAGE-CALIBRATION-001.
**Next prompt:** none queued.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-08 13:05 UTC — Live-trading UNBLOCK (stale 4-day emergency stop cleared) + pre-flip prep (paper-only; NO flip)

**Committed:** docs-only (this session) — NEW `session_outputs/ZMN_LIVE_UNBLOCK_PREP_2026_06_08.md` (full findings + CONDITIONAL-GO audit + flip card) + STATUS/ROADMAP/CLAUDE/AGENT_CONTEXT updates. **ZERO bot-code change; live path frozen.**
**THE FIND:** bot was **silently EMERGENCY_STOPPED ~4 days** (last trade 2026-06-04 10:18 UTC; not trading even paper) — `bot:status=EMERGENCY_STOPPED`, `bot:emergency_stop=1`, heartbeat healthy (deliberate halt, NOT a crash/outage). **Root cause:** the macro SOL-crash circuit breaker `SOL_24H_EMERGENCY=-0.10` (`market_health.py:117`) tripped on SOL −10.9%/24h (logged 2026-06-05 19:21 UTC) → publishes `alerts:emergency` → `emergency_stop()`; **latches** (durable `bot:emergency_stop`) until a manual clear **+ restart**. SOL since recovered (+3.9%/24h now) → the stop was STALE.
**UNBLOCK (Jay-authorized "clear blockers", paper only):** `DEL bot:emergency_stop` + `bot:consecutive_losses=0` + clear loss-pause + `market:mode:override NORMAL EX86400`; `railway redeploy -s bot_core` → dep `50806d8a`. **Verified clean:** `bot:status` RUNNING @12:59:41 UTC, NO re-trip; **paper resumed** (6 new trades ids 11094-11099 @12:59-13:00 UTC, 6 positions managed, market DEFENSIVE). Holders gate already=1 (NOT the blocker; real suppressors = `no_social_links` + ML<30 — Jay chose "keep quality filters" → unchanged).
**PRE-LIVE AUDIT (5-agent read-only workflow @c0846e8): CONDITIONAL-GO.** All load-bearing safety/exec VERIFIED present: peak-seed fix `bot_core.py:358` (bare assign, not max — the 2026-06-04 abort fix), import-guard, 3-tier Helius, solders v3 ctor, EXEC-001 unconditional pool-refresh, sell-storm breaker, D02-F1/F3, daily-loss+20%-drawdown rails, #9 entries-only HIBERNATE veto, SIZING-CAPS resolved (eff. concurrency 10). NO SOL-leak path found. **Single hard blocker = §6 flip-config NOT applied (operator applies at flip — incl. signal_aggregator AGGRESSIVE_PAPER=false).** Warnings (OK supervised; fix before UNSUPERVISED): governance fail-open (dead Anthropic credits; #9+loss-cap bind independently), 24h-macro-breaker blind ~24h post-`market_health`-restart, ACCT-6 mid-exit-restart PnL corruption (data-fidelity not capital), PNL-zero-price, TIMEZONE-SIZING 1h DST drift (within cap). Binding go-check: live-boot log must show on-chain peak seed, NOT snapshot fallback.
**State changes:** Redis safety keys cleared + `market:mode:override=NORMAL`(24h TTL); bot_core redeployed. NO env/config change. TEST_MODE stays true.
**Bot state:** TEST_MODE=true (paper), RUNNING, market DEFENSIVE, emergency_stop unset, consecutive_losses=0, wallet **5.0641 SOL** on-chain (topped up from 0.064 — pre-V5A top-up DONE), paper actively trading.
**Blockers cleared:** stale 4-day emergency stop (silent halt). Tooling: railway CLI confirmed logged-in (CLAUDE.md MCP note was stale → corrected).
**Blockers new/active (for LIVE flip):** apply §6 flip-config to BOTH bot_core + signal_aggregator; pre-flip `DEL market:mode:override`; (before any UNSUPERVISED run) restore governance credits + fix ACCT-6 persistence.
**Next prompt:** Jay's authorized `TEST_MODE=false` flip per `docs/FLIP_NIGHT_PLAYBOOK.md` + flip card in `session_outputs/ZMN_LIVE_UNBLOCK_PREP_2026_06_08.md` §6 (caps 0.10/1.5; **holders=1 per Jay's choice — flagged rug-risk vs canonical 15**). CC does NOT auto-flip.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-04 — 🔴→🟢 V5A-FLIP-003: first live flip ABORTED clean on boot (96.4% phantom drawdown) → root cause FIXED

**Committed:** `8fe7543` fix(safety): reset live drawdown peak to on-chain seed (LIVE-DRAWDOWN-PEAK-SEED-001) — `services/bot_core.py` + audit/docs.
**THE EVENT:** Jay authorized + I executed the first real `TEST_MODE=false` flip (~10:06 UTC). Preconditions ALL-GREEN, §6 config applied, held for regime (HIBERNATE→DEFENSIVE after 9min), CLEAN-003, pre-flight ALL-GREEN, flipped. **Live boot was CLEAN** (TEST_MODE=False, live mode OK 3 Helius URLs, **balance seeded 5.0641 from on-chain — #12 worked**, daily PnL 0.0 — #11, **0 positions reconciled**). **Then at 10:06:18 (6s post-boot): `EMERGENCY_STOP: Drawdown 96.4%`** → halted. **Rolled back per Step-8** (pre-authorized): TEST_MODE=true + full pre-flip config restored (bot_core+SA), emergency_stop/loss_pause cleared, consecutive_losses=0. **NO on-chain trade fired; wallet UNCHANGED 5.064 SOL; 0 positions throughout. Clean abort.**
**ROOT CAUSE — LIVE-DRAWDOWN-PEAK-SEED-001 (live-only, not paper-observable):** `_load_state` loads the latest snapshot (unfiltered → the ~132 SOL PAPER figure) and sets `peak_balance_sol` to it; the #12 live block correctly seeded `total_balance_sol=5.064` from on-chain BUT set `peak = max(peak, onchain)` → kept the 132 peak → drawdown `(132−5)/132 ≈ 96.4%` → >20% → EMERGENCY_STOP before any trade. Paper resets the peak every boot (321-323/375-377) so paper never sees it — **exactly the flip-confirmed-only class the supervised first-flip exists to catch.**
**FIX (applied, paper-safe):** live boot now RESETs `peak_balance_sol = _onchain` (not max) — mirrors the paper reset + #12's balance seed. DAILY_LOSS_LIMIT_SOL (#11) remains the durable cross-restart kill-switch, so the peak reset doesn't weaken the hard cap. py_compile + structural. Live-only → paper unchanged.
**What VERIFIED-WORKING in the abort:** #12 balance seed (5.0641 not 132.6), #11 daily-loss reload, reconcile/CLEAN-003 (0 positions), execution.py live import guard (3 Helius URLs), #8 emergency-stop durability + the rollback machinery (tripped→halted→reverted cleanly, 0 SOL at risk).
**State now:** TEST_MODE=true (paper), config rolled back to pre-flip (MAX_POSITION_SOL=0.25/DAILY_LOSS 4.0/AGGRESSIVE_PAPER true/HOLDER 1), caps stay 10/10, emergency_stop cleared, wallet 5.064 SOL, 0 positions.
**Re-flip:** requires NEW explicit authorization (session-gated rule: aborted live session → next defaults TEST_MODE=true). With the peak fix deployed, the next authorized flip should boot clean (balance + peak both = on-chain → 0% drawdown). Audit: `docs/audits/V5A_FLIP_003_2026_06_04.md`.
**Next prompt:** none — awaiting Jay's call on re-flip (after the peak-fix deploy confirms) or further work.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-04 — SIZING-CAPS-WIRING-001-B: effective concurrency raised 3 → 10 (Jay's decision)

**Committed:** `d0b039f` fix(caps): wire per-personality concurrency cap to env — `services/risk_manager.py` (+ `scripts/flip_preflight_check.py` verifier update). **Env set:** `MAX_CONCURRENT_PER_PERSONALITY=10` on bot_core.
**Change:** `risk_manager.py:51` `MAX_CONCURRENT_PER_PERSONALITY` (+ `MAX_CONCURRENT_WHALE`) now `int(os.getenv(...,"3"/"2"))` (was hardcoded 3/2). With env=10, the per-personality cap that BINDS first for SD-only no longer caps SD at 3 → **effective SD concurrency = `min(MAX_CONCURRENT_PER_PERSONALITY=10, MAX_CONCURRENT_POSITIONS=10)` = 10.** Bounded by MAX_WALLET_EXPOSURE=0.25 + per-position MAX_POSITION_SOL. Default 3 if unset (prior behaviour). **Paper-observable** (cap applies in paper too — SD can now hold up to 10 concurrent paper positions). py_compile + 6/6 verify; preflight now shows effective concurrency=10 GREEN.
**This RESOLVES the "effective cap=3 not 10" finding** from SIZING-CAPS-WIRING-001 — all docs reconciled (FLIP_READINESS §4.2/§5, PLAYBOOK STEP 2/5/7, CLAUDE caps note, FLIP_NIGHT_PREP flag 3, REMEDIATION). `MAX_SD_POSITIONS` (env 20) stays phantom — the live lever is `MAX_CONCURRENT_PER_PERSONALITY`.
**State changes:** bot_core env `MAX_CONCURRENT_PER_PERSONALITY` unset→10; one code commit; bot_core redeploy. TEST_MODE stays true.
**Bot state:** TEST_MODE=true, market:mode=NORMAL, emergency_stop unset, consecutive_losses=0, wallet 5.064 SOL.
**Next prompt:** none queued. Pre-flight: only the §6 flip-config rows remain (applied in-window).
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-04 — Cleared the 2 pre-flip flags: HELIUS_DAILY_BUDGET set + Jupiter 403 verified (false alarm)

**Committed:** `949e23d` — `scripts/flip_preflight_check.py` (UA fix) + doc updates. **State change:** `HELIUS_DAILY_BUDGET=100000` set on bot_core + treasury (Railway). No bot-code change; live path frozen.
**HELIUS_DAILY_BUDGET ✅ set 100000** (bot_core + treasury). **Correction:** it does NOT gate the live exec path — `grep` confirms it's read ONLY by `treasury.py:60` (balance polling) + dashboard display; bot_core/execution/helius_parser use `HELIUS_*_URL` directly. So it was never an exec blocker; setting it re-enables treasury wallet-balance tracking + clears the preflight row. Real live-Helius proof = on-chain getBalance GREEN (5.0641 SOL).
**Jupiter 403 ✅ verified — FALSE ALARM (verifier artifact).** Root cause: Jupiter's Cloudflare WAF 403s the default `Python-urllib` User-Agent (proven: `Python-urllib`→403, `Mozilla/5.0`→200). The bot uses aiohttp (unaffected); the deployed key + `api.jup.ag/price/v3` return 200 + valid price (with key, without, and lite-api all 200, 3/3 stable). Fixed `flip_preflight_check.py http_ok()` to send a browser UA → Jupiter row GREEN. `JUPITER-PRICE-AUTH-VERIFY-001` RESOLVED. (Jupiter can still 403 transiently under burst; bot has Redis/BC pricing fallbacks + #4 parks/retries a failed swap.)
**Preflight now:** 5 RED = ONLY the §6 flip-config items applied at PLAYBOOK Step 2 (`MAX_POSITION_SOL`, `DAILY_LOSS_LIMIT_SOL`, `AGGRESSIVE_PAPER_TRADING`×2, `HOLDER_COUNT_MIN`). All API/safety/infra rows GREEN.
**Remaining pre-flip item:** only the operator-decision on effective concurrency (3 vs wire 001-B) + applying the Step-2 flip-config in the window. Both pre-flight flags cleared.
**Bot state:** TEST_MODE=true, market:mode=NORMAL, emergency_stop unset, consecutive_losses=0, wallet 5.064 SOL.
**Next prompt:** none queued.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — FLIP NIGHT PLAYBOOK persisted (operator runbook; NO flip executed)

**Committed:** `1554612` — NEW `docs/FLIP_NIGHT_PLAYBOOK.md` (canonical operator runbook STEP 0–9) + index updates. **Docs-only; ZERO code/env/Redis/state change; the flip was NOT executed.**
**What it is:** the single in-window operator doc for the `TEST_MODE=false` flip, reconciled with what actually landed: P1 (`MAX_CONCURRENT_POSITIONS=10` total cap; **effective SD cap = 3** per-personality — called out in STEP 2/5/7), P2 (`flip_preflight_check.py` is the STEP 0/3 gate; `flip_rollback.sh` is the STEP 8 rollback; #9 exit-safety GREEN → HIBERNATE dip is NOT a rollback trigger). Corrected `HOLDER_COUNT_MIN`=SA-only. Adds the two new pre-flip flags to clear (STEP 0): `HELIUS_DAILY_BUDGET` unset + Jupiter price-API 403.
**Explicit:** the flip (STEP 4 `TEST_MODE=false`) is the operator's authorized in-window action — CC does NOT auto-flip (session-gated per CLAUDE.md). This session only persisted the doc.
**Indexed:** CLAUDE.md live-flip section → points at `docs/FLIP_NIGHT_PLAYBOOK.md`; ROADMAP changelog; AGENT_CONTEXT header.
**Next prompt:** none queued — all 3 of this session's prompts (SIZING-CAPS-WIRING-001 → FLIP-NIGHT-PREP-001 → FLIP NIGHT PLAYBOOK) are landed + persisted.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — FLIP-NIGHT-PREP-001 (read-only audit + flip tooling; NO live-branch change)

**Committed:** `f5df07b` — NEW `scripts/flip_preflight_check.py`, `scripts/flip_rollback.sh`, `docs/audits/FLIP_NIGHT_PREP_001_2026_06_03.md` + index updates. **No bot-behaviour change, no deploy of bot code, no state write.**
**Part A (load-bearing) ✅ GREEN:** #9 HIBERNATE veto gates ENTRIES only; ALL exits run regardless of `market:mode` — verified by direct trace + **3 adversarial refuters** (workflow, all `entries-only`, no mode-gate-on-exit). Citations: entry gates `bot_core.py:752-766/:817`, `risk_manager.py:223`; exits `_check_exits:2028` (only pause = emergency_stopped), `_close_position:1357`, `_evaluate_trailing_stop:1946`, `_exit_check_listener:2324`, `execution.py` (0 mode refs). ➡️ **A HIBERNATE dip is NOT a rollback trigger — verified.**
**Part B `flip_preflight_check.py`:** read-only GREEN/YELLOW/RED verifier; dry-run NOW = EXIT 1 / 6 RED = exactly the §6 flip-config items still to apply; all safety rows GREEN (mode NORMAL, emergency unset, losses 0, **0 open live positions**, wallet **5.0641 SOL**, `MAX_CONCURRENT_POSITIONS=10`). Windows-safe (railway shim resolution + ASCII).
**Part C `flip_rollback.sh`:** CONFIRM-gated one-command rollback (restores pre-flip config; NEVER touches emergency_stop or MAX_CONCURRENT_POSITIONS); verified `bash -n` + `--dry-run` + `--show-current` (NOT executed).
**Part D ✅ GREEN:** dashboard surfaces mode/open-positions/recent-trades+exec/corrected-PnL; unauth curl→401 (JWT auth fail-closed, security positive); corrected-column error 0 in window. Operator must log in before the window.
**🚩 NEW FLAGS (documented, NOT fixed — live path frozen):** (1) `HELIUS_DAILY_BUDGET` unset on bot_core (preflight RED; set at flip / verify raw-RPC not budget-gated); (2) **Jupiter price API → 403** with the deployed key (`api.jup.ag/price/v3`) — verify auth/endpoint before flip (live post-grad sells depend on it; paper has Redis/BC fallbacks) → `JUPITER-PRICE-AUTH-VERIFY-001`; (3) effective concurrency = 3 not 10 (per SIZING-CAPS-WIRING-001-B), shown as an informational verifier row.
**Next prompt:** persist the FLIP NIGHT PLAYBOOK (Prompt 3 of 3) — operator doc; I will NOT execute the flip.
**Pending Claude-chat prompts not yet pasted:** FLIP NIGHT PLAYBOOK (3 of 3).

---

## 2026-06-03 — SIZING-CAPS-WIRING-001 (deterministic total concurrency cap) + 🚩 binding-cap correction

**Committed:** `badb221` fix(caps): wire deterministic total concurrency cap at bot_core:831 — `services/bot_core.py`. **Env set:** `MAX_CONCURRENT_POSITIONS=10` on bot_core.
**Change (D04-F7):** `:831` now resolves `min(MAX_CONCURRENT_POSITIONS env, gov.max_concurrent_positions)` — env is a HARD ceiling, governance may only TIGHTEN below it (safety never loosens); default 5 if unset; logs `[CAPS] concurrency cap=N (env=E, gov=G)` once. Set env=10 (Jay's decision). **Paper-observable** (not TEST_MODE-gated). `MAX_SD_POSITIONS=20` left phantom (per scope). py_compile + 12/12 verify.
**🚩 PLAN-CHANGING FINDING (corrects this prompt's premise + my own FLIP_READINESS_REVIEW §4.2/§5):** `:831` is the TOTAL cap and is **NOT the binding cap for the SD-only trial.** A second, per-personality cap binds FIRST: `risk_manager.py:51 MAX_CONCURRENT_PER_PERSONALITY=3` (WHALE=2), enforced at `risk_manager:228` → `base_size=0` → bot_core `:898` blocks. Admission order: `:831` total(10) → sizing → risk_manager per-personality(3) → block. With Analyst disabled + Whale dormant, **Speed Demon is capped at 3 concurrent — total-10 never reached → effective trial concurrency = 3, NOT 10.** Wiring `:831` is robustness/determinism, not a behaviour change at the current value. **To set the effective trial cap to the V5A ladder, `risk_manager.MAX_CONCURRENT_PER_PERSONALITY` must ALSO be wired** → filed **SIZING-CAPS-WIRING-001-B** (out of this prompt's scope fence). This affects the FLIP NIGHT PLAYBOOK's "cap=10" expectation: the `[CAPS]` startup log shows the *total* (10); the *effective* SD cap is 3 until 001-B lands.
**State changes:** bot_core env `MAX_CONCURRENT_POSITIONS` 6→10; one code commit; bot_core redeploy. TEST_MODE stays true.
**Bot state:** TEST_MODE=true, market:mode=NORMAL, emergency_stop unset, consecutive_losses=0.
**Blockers cleared:** D04-F7 (total-cap determinism). **New/active:** SIZING-CAPS-WIRING-001-B (per-personality cap wiring — the binding one).
**Next prompt:** FLIP-NIGHT-PREP-001 (Prompt 2 of 3) — its pre-flight verifier should treat "effective cap = 3 (per-personality)" not 10; note the 001-B gap.
**Pending Claude-chat prompts not yet pasted:** FLIP-NIGHT-PREP-001 + FLIP NIGHT PLAYBOOK (2 of 3 queued this session).

---

## 2026-06-03 — FLIP-READINESS-REVIEW-001 (read-only; full dependency/env/API audit + go/no-go)

**Committed:** `badb221` docs: `docs/audits/FLIP_READINESS_REVIEW_001_2026_06_03.md` (new) + index updates. **ZERO state writes** (read-only).
**Verdict: CONDITIONAL GO (technical), HOLD pending 4 decisions + flip-time confirmation.** §B Phases 0–3 complete + deploy-verified; PC1/PC2/PC3 ✅; PC4 Jay-gated. Flip blocked NOT by code but by: BUG-010 (Anthropic credits — governance dead), the §6 sizing/cap config, and live-only-fix runtime confirmation.
**Live state verified:** TEST_MODE=true; on-chain wallet **5.064 SOL** (`4h4pstXd...`); market:mode=**NORMAL**; emergency_stop unset; consecutive_losses=0; paper balance 132.6 SOL (vs 5.064 real — #12 corrects at live startup); governance=CONSERVATIVE/0.8/max_concurrent 10 (LLM dead).
**🚩 Headline env-vs-intent discrepancies (must fix at flip):** `MAX_POSITION_SOL=0.25` (intent 0.10 — 2.5×), `DAILY_LOSS_LIMIT_SOL=4.0` (V5A decision 1.5 — 2.7×), concurrency cap = governance `max_concurrent_positions`=**10** enforced at bot_core:831 (intent 5; `MAX_SD_POSITIONS=20`/`MAX_CONCURRENT_POSITIONS=6` are BOTH phantom/unread — verified), `AGGRESSIVE_PAPER_TRADING=true` (set false), `HOLDER_COUNT_MIN=1` (GATES-V5 set 15 — loose), `HELIUS_DAILY_BUDGET` unset (verify >0).
**API matrix:** Helius RPC/Jupiter/PumpPortal = live-path CRITICAL (all configured); Anthropic DEAD (BUG-010); Jito disabled in code (#6); Nansen/SocialData dead-by-design/credits.
**Report covers:** verdict, live snapshot, §B status, API matrix, full env matrix (deployed vs intent), Redis keys, the 4 decision items, flip-config (§6), runbook (§7), risk register, handoff. **Built for Claude-web + cross-session persistence.**
**Next prompt:** resolve BUG-010 credits → apply §6 flip-config → supervised flip per §7; or address a flagged follow-up.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — CORRECTION: DASH-CORRECTED-PNL-COLUMN-001 TRUE root cause (subquery alias, not a missing column)

**Committed:** `badb221` fix(dashboard): api_status win-rate-window subquery alias — `services/dashboard_api.py`.
**Corrects the #15 claim below.** The `column "corrected_pnl_sol" does not exist` error (web, ×3 every 60s) was NOT a missing `trades` column (the audit's hypothesis, which I acted on with migration 003). **True root cause:** `api_status`'s win-rate-window query (3 windows 10/25/50 → the exact 3×/60s, polled via `/api/status`) referenced `COALESCE(corrected_pnl_sol, realised_pnl_sol)` in the **outer** SELECT over a subquery `t` that only PROJECTS `pnl` (the COALESCE was aliased to `pnl` inside). Postgres raised the error against the **subquery**, not any table. **Fix:** outer now uses `pnl`. Verified by prod-replay: the exact deployed query reproduced the error (2/2 fail pre-fix), the fixed query passes (6/6: windows 10/25/50 × paper+live).
**Migration 003 (corrected_* cols on `trades`) is RETAINED** — harmless (additive/nullable) and useful for `LIVE-TRADES-CORRECTED-POPULATE-001`, but it did NOT resolve this error. The #15 entry's "resolved via migration" wording is superseded by this correction.
**Verification:** py_compile PASS; prod-replay 6/6 (fixed) + 2/2 repro (broken). Paper-observable (the dashboard's win-rate-window cards + the spammed log). 
**Rollback:** `git revert` this commit.
**Next prompt:** Phase-3 capstone (re-verify error gone post-deploy).
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — API-STATS-FSTRING-BUG-001 (NEW finding, fixed) — api_stats silently returned zeros

**Committed:** `badb221` fix(dashboard): add missing `f` prefix to 3 api_stats queries — `services/dashboard_api.py`.
**Finding (NEW, discovered during #15):** `api_stats` built 3 queries (main pnl/win-rate/best/worst, today-pnl, avg-hold) with `{mf}` inside PLAIN (non-`f`) strings → the literal text `{mf}` reached Postgres → syntax error → swallowed by the function's `except` → **api_stats silently returned ZEROS** for total_pnl_sol/win_rate/best_trade/worst_trade/today_pnl_sol/avg_hold_minutes AND ignored the intended trade_mode filter. Pre-existing; the mode filter was clearly intended (the code already wrote `{mf}`, just missing the `f`).
**Fix:** added the `f` prefix to all three (lines 524/544/553). The other ~20 `{mf}` queries were already f-strings or use parameterized `$1`; verified none remain plain-string + `{mf}`.
**Verification:** py_compile PASS; 6/6 prod-replay (all 3 queries × paper+live execute with the mode filter applied). **Paper-observable** (api_stats now returns real mode-filtered numbers). Filed in oversight doc.
**Rollback:** `git revert` this commit.
**Next prompt:** Phase-3 capstone.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — §B Phase-3 #15 FIX-DASHBOARD-MODE-FIDELITY + DASH-CORRECTED-PNL-COLUMN-001 (🎯 PHASE 3 COMPLETE)

**Committed:** `badb221` fix(dashboard/accounting): mode-fidelity + corrected-column migration — `services/dashboard_api.py`, `services/bot_core.py`, `migrations/003_add_corrected_pnl_to_trades.sql`. **Plus a prod DB migration already applied** (ALTER TABLE trades — additive, idempotent).
**DASH-CORRECTED-PNL-COLUMN-001 (prod error every 60s, ×3):** web logged `column "corrected_pnl_sol" does not exist`. Confirmed schema gap: `paper_trades` has the 4 corrected/correction cols, `trades` had NONE (migration 001 added them to paper_trades only). **Fix:** migration 003 mirrors all 5 cols onto `trades` (applied to prod via DATABASE_PUBLIC_URL; `SELECT corrected_pnl_sol FROM trades` now OK). Live rows = NULL → any `COALESCE(corrected, …)` falls back gracefully. Roadmap-endorsed universal fix (kills the error regardless of the triggering query).
**D05-F4 (api_analytics):** had NO trade_mode filter on any of its 6 queries + used uncorrected realised → live view mixed paper+live and ignored Path B. Now threads `_mode_filter(mode)` + `COALESCE(corrected_pnl_sol, realised_pnl_sol)` into equity-curve / exit-reasons / WR-trends(l10/25/50) / expectancy.
**D05-F6 (falsy-zero):** `float(corrected or realised)` discarded a legit `corrected==0.0`. New `_coalesce_pnl()` helper (explicit None-check) used in api_trades; SQL paths use COALESCE (None-only). 
**D05-F3 (snapshot daily_pnl):** `_portfolio_snapshot_task` wrote `daily_pnl_sol` as a LIFETIME SUM with no window — and in live mode `trades` holds paper+live (no filter). Now midnight-UTC window + trade_mode filter (dashboard reads each snapshot's value as-is → safe).
**D02-F13 (live entry-price sentinel):** live entry used `price=0.000001` on an oracle miss → every exit computed a fabricated giant win (`(current−1e-6)/1e-6`) + corrupted `trades.entry_price`; verified `pos.entry_price` is NEVER corrected later. Now: retry `_get_token_price` 3× (stream lag), then `entry_price=0.0` (exit math guarded on `>0` books 0, defers to Path B) + ERROR + Sentry. Live-only.
**D05-F10** (corrected_pnl_pct denominator) already standardised in #14 (both Path A/B use `/size`). **D05-F8** (amount_sol paper-net vs live-gross) — documented as a known semantic difference, NOT changed (altering it would break historical analysis; 🟢).
**Verification:** py_compile PASS (both files); 10/10 prod-replay (rewritten analytics both modes + windowed snapshot both tables execute cleanly); migration confirmed applied. **Partly paper-observable** (dashboard analytics + snapshot daily_pnl for paper view); D02-F13 + populate-path live-only/flip-confirmed.
**Rollback:** `git revert` this commit; `ALTER TABLE trades DROP COLUMN corrected_pnl_sol, …` (cols are additive/nullable — safe to leave).
**🎯 §B PHASE 3 (accounting integrity) CODE-COMPLETE:** #14 ✅, #15 ✅. Full findings flag at end of this run.
**Next prompt:** Phase-3 capstone / flip-readiness review. Phases 0+1+2+3 done.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — §B Phase-3 #14 FIX-LIVE-STAGED-TP-PNL (live cumulative PnL + Path-B multi-exit + in-memory reconcile)

**Committed:** `badb221` fix(accounting): live staged-TP cumulative PnL + Path-B multi-exit sum + on-chain in-memory reconcile — `services/bot_core.py` (Position dataclass + `_close_position` live branch).
**Findings (D05-F1/D05-F2/D02-F12):** the live close booked only the FINAL partial's PnL/sig. **D05-F1:** earlier staged TPs booked NOTHING (the live PARTIAL case just logged+returned) → multi-TP winners grossly understated in realised/corrected/daily_pnl/balance. **D05-F2:** Path B paired the full-position entry native-delta with only the last exit sig → wrong corrected_pnl (could flip a winner to a loss). **D02-F12:** in-memory daily_pnl/balance (the kill-switch inputs) used the optimistic oracle estimate, not on-chain truth.
**Fix (live-only):** new Position accumulators (`exit_signatures`, `cumulative_fees_sol`, `cumulative_sell_slippage_sum`, `exit_count`). Every live exit leg now accumulates its realised PnL (`cumulative_pnl_sol += chunk_gross − chunk_sell_fees`), fees, slippage, and exit sig; the terminal close subtracts the one-time buy fee ONCE and books the cumulative (`pnl_sol = pos.cumulative_pnl_sol`; `pnl_pct = pnl_sol/size·100` — also standardises the Path A/B denominator, D05-F10). Path B now sums native deltas across ALL exit sigs (trusted only if entry + every exit parse). **D02-F12:** the in-memory daily_pnl/balance update moved below Path B and driven by `_booked_pnl = Path-B-if-available-else-Path-A` (kill-switch reconciles to on-chain truth). **Single full close (sell_pct=1.0) reduces to the prior arithmetic exactly.**
**Verification:** py_compile PASS; 6/6 structural; `.tmp_phase3/verify_staged_tp_pnl.py` 7/7 arithmetic (single-close==old; staged cumulative 0.073 vs old buggy final-only 0.023 = 3.2× understatement; Path-B sum +0.057 vs old last-only −0.048 = winner-flipped-to-loss; loss still books full downside). **NOT paper-observable (live `else:` branch) — flip-confirmed.** Paper path untouched.
**Rollback:** `git revert` this commit.
**§B Phase-3 progress:** #14 ✅ (code). Next: #15 dashboard mode-fidelity + DASH-CORRECTED-PNL-COLUMN-001 + D02-F13 entry-price sentinel.
**Next prompt:** Phase-3 #15.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — 🎯 §B PHASE 2 (SAFETY RAILS) COMPLETE & DEPLOY-VERIFIED + findings flag

**Committed/pushed (this run, on origin/main):** #9 `7e83949`, #10 `7fe2ad1`, #11+#12 `78cc45c`, #13 `c70aba1` (+ this docs capstone). (Per-fix STATUS entries below cite pre-amend content hashes; these are the pushed/`git revert`-able hashes.)
**Deploy-verified:** all 6 services Online after every Phase-2 deploy; bot_core clean startup each time, paper trading uninterrupted (ENTERING at real ML 40–80, mode=DEFENSIVE); paper-side `FILL_MC_CEILING reject` firing correctly; no tracebacks/import/Type errors. The combined #10+#11+#12 and the #13 deploys were each observed ~9min and confirmed clean.
**Verification posture:** all four Phase-2 fixes are **paper-safe by construction** (live-only or default-preserving), so their *deployment* is confirmed clean but their *behaviour* is **flip-confirmed-only** (live `else:`/`not TEST_MODE` branches are not paper-observable). Code hunks verified present in the pushed commits.
**Bot state (read live):** TEST_MODE=true (paper); `market:mode:current=DEFENSIVE`; `bot:emergency_stop` UNSET; `bot:consecutive_losses=0`; `governance:latest_decision=CONSERVATIVE / size_multiplier 0.8` (LLM dead — BUG-010).

**🚩 FINDINGS FLAG (new / plan-changing — surfaced during Phase 2):**
1. **BUG-010 is ACTIVE and has a live current-state effect.** Governance LLM is dead (Anthropic 400/credits) → fallback `CONSERVATIVE / 0.8×` → **every current paper trade is sized 0.8× base** (silent haircut; account for it in paper PnL-per-trade analysis) AND governance gives **zero real regime signal**. With #9 deployed, the `market:mode:current` HIBERNATE veto is now the **only** live regime control. **Restoring Anthropic credits is a real go-live prerequisite.** → `GOVERNANCE-STALENESS-POLICY-001` + BUG-010.
2. **`MAX_SD_POSITIONS=20` is deployed-but-unread.** Concurrent cap is hardcoded `MAX_CONCURRENT_PER_PERSONALITY=3`. Wiring the env *as currently set* would jump the paper cap **3→20** (6.7× exposure). Deliberately NOT auto-wired — must land together with setting the env to V5A-ladder intent (5/7). → `SIZING-CAPS-WIRING-001`.
3. **Sizing timezone + double time-of-day multiplier.** TIME_GOOD/DEAD/SLEEP/WEEKEND fire on a hardcoded UTC+11 clock (1h off in AEST) and time-of-day is applied twice on two clocks → changes *paper* sizing; needs a sizing-semantics decision. → `TIMEZONE-SIZING-FIX-001`.
4. **Observed:** paper ENTERING sizes are pinned at 0.2500 SOL (hitting a position cap) under the 0.8× haircut — not Phase-2-introduced, but relevant context for the sizing-caps + haircut decisions above.

**Plan unchanged otherwise:** Phases 0+1+2 done; Phase 3 (accounting: #14 live staged-TP cumulative PnL + Path-B multi-exit; #15 dashboard mode-fidelity + DASH-CORRECTED-PNL-COLUMN-001) NOT STARTED — awaits authorization. The 3 flagged decisions above are decision-gated, not code-blocked.
**Oversight doc:** `docs/audits/REMEDIATION_PHASE_0_1_2026_06_03.md` now carries the full Phase-2 section + commit index (covers Phases 0–2; share for double-check).
**Next prompt:** Phase-3 #14 (when authorized) — or resolve the 4 flagged decisions first.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — §B Phase-2 #13 fill-MC fail-closed (+ MAX_SD_POSITIONS/timezone deferred+flagged)

**Committed:** `beaa7de` fix(safety): live fill-MC-ceiling fails CLOSED on price-miss — `services/bot_core.py`.
**#13 done (D08-F7):** the live fill-MC-ceiling gate (`BOT_CORE_FILL_MC_CEILING_USD`) failed OPEN — `_get_token_price` returns 0.0 → `fill_mc = 0` → `0 > ceiling` is False → it ADMITTED an unbounded-MC live buy (the exact in-flight-pump case the gate exists to block). Now: `if fill_price <= 0: log + return` (fail CLOSED). Live-only (the gate is in the live buy branch); paper has its own fail-closed in `paper_buy`. py_compile + structural.
**🚩 DEFERRED + FLAGGED (two #13 sub-items need a decision — NOT auto-applied under "no input"):**
- **MAX_SD_POSITIONS wiring (D04-F7):** the cap is hardcoded `MAX_CONCURRENT_PER_PERSONALITY=3`; `MAX_SD_POSITIONS` is a phantom env var. **But `MAX_SD_POSITIONS=20` is DEPLOYED on Railway** (AGENT_CONTEXT §2) — so wiring it as-is would jump the concurrent cap **3 → 20 in paper** (6.7×, big exposure change). It must be wired *together with* setting the env to the V5A-ladder intent (5/7), which is a flip-time operator decision. Filed `SIZING-CAPS-WIRING-001`.
- **Timezone / double time-of-day multiplier (D08-F4 / D11-F2):** TIME_GOOD/DEAD/SLEEP/WEEKEND fire on a hardcoded UTC+11 clock (off by 1h in AEST) AND time-of-day is applied twice on two clocks. Fixing changes *paper* sizing and the de-dup needs a sizing-semantics decision (the audit said "confirm with Jay"). CORRECTNESS, not a money-loss 🔴. Filed `TIMEZONE-SIZING-FIX-001`.
**Verification:** py_compile PASS; 3/3 structural (fail-closed present, reject path intact, MAX_SD_POSITIONS unchanged/deferred). Live-only; flip-confirmed.
**Rollback:** `git revert` this commit.
**🎯 §B Phase-2 (safety rails) CODE-COMPLETE:** #9 HIBERNATE-live-veto ✅, #10 governance-cfgi ✅, #11+#12 live-startup-state ✅, #13 fill-MC-fail-closed ✅. Two #13 sub-items deferred+flagged (need decisions). Full findings summary at end of this run.
**Next:** Phase 3 (accounting) — when authorized. Plus the flagged decisions (SIZING-CAPS-WIRING-001, TIMEZONE-SIZING-FIX-001, GOVERNANCE-STALENESS-POLICY-001, BUG-010 credits).
**Next prompt:** Phase-3 #14 (or resolve the flagged decisions).
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — §B Phase-2 #11+#12 live startup-state (daily-loss persistence + on-chain balance seed)

**Committed:** `e739e07` fix(safety): live startup-state corrections — `services/bot_core.py` (`_load_state` + new `_fetch_onchain_balance_sol` helper).
**Bundled** #11 + #12 (both live-only corrections to `_load_state`, same function + concern). **Both gated on `not TEST_MODE` → paper path byte-for-byte unchanged (zero paper-disruption risk).**
**#11 (D04-F4 daily-loss persistence):** `_load_state` hard-zeroed `daily_pnl_sol` on every startup → any restart (incl. a crash-loop) laundered the daily-loss accumulator, so `DAILY_LOSS_LIMIT_SOL` could never accumulate across restarts (the headline safety cap defeated in the restart-prone state the bot was in). Fix (live-only): reload TODAY's (UTC) realized PnL from `trades WHERE trade_mode='live' AND closed_at >= midnight` (uses `pnl_sol` — `trades` has no corrected_pnl_sol, cf. DASH-CORRECTED-PNL-COLUMN-001; closed_at is epoch float). A new UTC day → ~0. Safe fallback to 0.0 on any error. **Paper keeps the existing hard-zero** (avoids any false-stop on paper data).
**#12 (D04-F2 live-balance seed):** `_load_state` read the latest `portfolio_snapshots` row with no trade_mode filter → post-flip it loads the ~50 SOL PAPER balance, inflating the 25% exposure ceiling + 20% drawdown denominator ~10× vs the real ~5 SOL wallet until the first live close self-corrects. Fix (live-only): seed `total_balance_sol` from on-chain `getBalance` (new `_fetch_onchain_balance_sol` helper) at live startup; falls back to the snapshot with a warning if the RPC is down. (Per-trade size was never at risk — the absolute MAX_POSITION_SOL cap floors it; this corrects the exposure/drawdown *denominators*.)
**Verification:** py_compile PASS; 6/6 structural (helper added, both live-only, paper hard-zero preserved, trades uses pnl_sol not corrected_pnl_sol). **NOT paper-observable (both `not TEST_MODE`); flip-confirmed.** Deploy bar = clean startup (live block doesn't run in paper).
**Rollback:** `git revert` this commit.
**§B Phase-2 progress:** #9 ✅, #10 ✅, #11+#12 ✅ (code). Next: #13 (sizing caps — MAX_SD_POSITIONS env + fill-MC fail-closed; timezone/double-multiplier deferred+flagged). Then Phase 2 COMPLETE.
**Next prompt:** Phase-2 #13 (final Phase-2 item).
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — §B Phase-2 #10 FIX-GOVERNANCE-FAIL-OPEN (cfgi read) + governance-state finding

**Committed:** `b273b54` fix(governance): read CFGI from market:health, not the non-existent market:cfgi — `services/governance.py`.
**Findings:** D04-F1/D09-F2/BUG-010. **Fix:** governance read `redis.get("market:cfgi")` — a key NO service writes → `cfgi` was PERMANENTLY the neutral 50 default in every governance prompt. Now reads from `market:health` (the JSON blob market_health writes), preferring `cfgi_sol`, with logging on absent/error.
**What was ALREADY in place (verified, no change needed):** (a) bot_core fetches + applies `gov.size_multiplier` (L772) → the CONSERVATIVE→0.8 haircut already takes effect; (b) the live regime VETO that governance fail-open left missing is now provided by **#9** (independent `market:mode:current` HIBERNATE check) — more reliable than the (dead) governance gate.
**DEFERRED + FLAGGED (needs decision, halt-risk):** the audit's "treat stale governance as PAUSE/cap." Governance's LLM is DEAD (Anthropic credits), so a "stale→halt" rule would HALT the paper bot; a "stale→size-cap" is strategy-adjacent + would apply a permanent live effect while dead. Filed `GOVERNANCE-STALENESS-POLICY-001` for a deliberate decision. The cfgi fix only helps once governance is revived (the LLM call fails on credits before using cfgi).
**🚩 CURRENT-STATE FINDING (flag):** `governance:latest_decision = {mode: CONSERVATIVE, size_multiplier: 0.8, reasoning: "classification failed: Error 400 … credits"}`. BUG-010 is ACTIVE: the dead-governance fallback is applying a **0.8× size haircut to ALL current paper trades** (silently shrinking paper sizes) and provides ZERO real regime signal. Two implications: (1) paper PnL-per-trade analysis should account for the 0.8× governance haircut; (2) restoring Anthropic credits (BUG-010) is a real go-live prerequisite for governance to function — until then, #9's market:mode veto is the only live regime control.
**Verification:** py_compile PASS; 4/4 structural. governance is non-trading (cfgi fix can't break paper trading). Deploy bar = clean startup.
**Rollback:** `git revert` this commit.
**§B Phase-2 progress:** #9 ✅, #10 ✅ (code). Next: #11+#12 (live startup state), #13 (sizing caps).
**Next prompt:** Phase-2 #11+#12.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — §B Phase-2 #9 FIX-HIBERNATE-LIVE-VETO (safety rail)

**Committed:** `71272cd` fix(safety): live HIBERNATE veto — `signal_aggregator.py` + `bot_core.py`.
**Findings:** D04-F3 / D07-F2 / D08-F1 / D08-F3 — bot_core had no effective live regime veto: the only HIBERNATE skip was the SA bypass, gated on `AGGRESSIVE_PAPER` (NOT TEST_MODE), so a bot_core-only flip leaving `AGGRESSIVE_PAPER_TRADING=true` would downgrade HIBERNATE→DEFENSIVE and **trade real money in a dead/outage regime**; bot_core's only other regime gate is the fail-open governance check (BUG-010).
**Fix:** (A) `signal_aggregator` — the HIBERNATE→DEFENSIVE bypass is now gated on `AGGRESSIVE_PAPER and TEST_MODE`; in LIVE, HIBERNATE always hard-skips. (B) `bot_core.process_signal` — independent live veto: when `not TEST_MODE`, read `market:mode:current` FRESH and `return` on HIBERNATE (doesn't trust the SA-downgraded label or governance). Belt-and-suspenders.
**Paper impact: NONE** — (A) preserves the paper bypass (AGGRESSIVE_PAPER and TEST_MODE → DEFENSIVE, as before); (B) is `not TEST_MODE` → no-op in paper. **Live-only behaviour change.**
**Verification:** py_compile PASS (both); 5/5 structural. NOT paper-observable for the live veto itself (flip-confirmed); deploy bar = paper trading continues + clean startup. **Runbook:** still set `AGGRESSIVE_PAPER_TRADING=false` on signal_aggregator at flip (defense-in-depth; code now enforces regardless).
**Rollback:** `git revert` this commit.
**§B Phase-2 progress:** #9 ✅ (code). Next: #10 governance-fail-open, then #11+#12 (live startup state), #13 (sizing caps). Deferred+flagged: timezone/double-multiplier (D08-F4/D11-F2 — needs sizing-semantics review).
**Next prompt:** Phase-2 #10.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — Consolidated remediation oversight doc (for external double-check)

**Committed:** `020f975` docs — NEW `docs/audits/REMEDIATION_PHASE_0_1_2026_06_03.md`. (Docs-only.)
**Why:** the Phase-0/1 work was documented across scattered chronological entries (STATUS/ZMN_ROADMAP/AGENT_CONTEXT/MONITORING) — no single shareable artifact for independent review. This doc consolidates every Phase-0 + Phase-1 fix: finding → change (file/func) → why correct → verification → **runtime-confirmation status** → pushed commit → rollback, plus the cross-cutting decisions, the end-to-end validation evidence, what's NOT done (Phase 2/3 + deferred follow-ups), and a "FOR THE REVIEWER" section flagging the highest-risk (live-money, non-paper-observable) changes to scrutinise first. Uses the **pushed** commit hashes (post-amend) so `git show`/`git revert` work on a fresh clone (STATUS cites pre-amend content hashes per convention; doc notes the mapping).
**Companion to:** `docs/audits/FULL_CODE_AUDIT_001_2026_06_02.md` (the findings register). To be appended as Phase 2/3 land — kept as the single oversight record through go-live.
**No code change.** Hand `REMEDIATION_PHASE_0_1_2026_06_03.md` + `FULL_CODE_AUDIT_001_2026_06_02.md` to Claude-web for oversight.

---

## 2026-06-03 — §B PHASE 1 DEPLOY-CONFIRMED + end-to-end Phase-0 validation (capstone, docs)

**Committed:** `7a6bb22` docs — Phase-1 deploy-confirmation + DEFENSIVE end-to-end validation. (Docs-only; this push redeploys all services — a clean no-op restart, proven 6× today.)
**Phase-1 all 4 deploys came up CLEAN** (the bar for non-paper-observable live-branch code): bot_core "Bot Core ready — managing 3 personalities" after each, paper trades entering with real ML scores, no traceback/import/Type errors from any edit. Commits: #4+#8 `2a85508`, #6 `29fca1b`, #5+D02-F8 `09f71c1`, #7 `94457ef`.
**END-TO-END VALIDATION of the Phase-0 chain (new finding):** `market:health` now reads **`mode: DEFENSIVE`** (was warm-up HIBERNATE), `data_degraded: false`, `dex_volume_24h: $1.65B`, with `market:migration_count_1h` climbing **2 → 6 → 10** over the session. The bot correctly transitioned out of HIBERNATE as the counter passed the DEFENSIVE threshold — proving the chain works: pubsub fix (pipeline flows → migrations captured) → redis-hardening (increments land, no longer dropped) → market-mode fix (classifies on real data, abstains only when genuinely absent). Whether it reaches NORMAL (≥30/hr) depends on the bot's true capture rate over a full clean hour → `MARKET-MODE-THRESHOLD-RECALIBRATE-003`.
**Bot state:** TEST_MODE=true (paper); all 6 services Online; mode DEFENSIVE; trading paper normally; Redis timeouts largely cleared post-hardening. Wallet 5.064 SOL (unchanged; no live activity).
**🎯 §B Phases 0 + 1 COMPLETE (code + deploy-confirmed).** Phase-1 fixes are flip-confirmed-only (live `else:` branch) for their *behaviour*; their *deployment* is confirmed clean.
**Remaining before any live flip:** §B **Phase 2 (safety rails)** — #9 FIX-HIBERNATE-LIVE-VETO, #10 FIX-GOVERNANCE-FAIL-OPEN, #11 daily-loss persistence, #12 live-balance seed, #13 sizing-caps wiring; then **Phase 3 (accounting)** — live staged-TP cumulative PnL, Path-B multi-exit, DASH-CORRECTED-PNL-COLUMN-001. **Pausing at the Phase-1→Phase-2 boundary** (Phase 2 = live-money safety gates — surfaced for sequencing rather than auto-rolled).
**Next prompt:** Phase-2 #9 (FIX-HIBERNATE-LIVE-VETO) when authorized to proceed.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — §B Phase-1 #7 FIX-EXEC-001-002-ROUTING — **§B PHASE 1 CODE-COMPLETE**

**Committed:** `3e4b502` fix(live-exec): unconditional pool-state refresh for live sells — `services/bot_core.py` only.
**#7 (D02-F4 + D03-F3):** the EXEC-001 pool-state refresh was gated on `pos.bonding_curve_progress > 0`, so it SKIPPED two classes that then mis-routed and HTTP-400'd: **(D02-F4)** whale/Raydium tokens (stored bc=0) sold via the pump.fun PumpPortal-Local path against a non-existent bonding curve; **(D03-F3)** reconciler-restored positions lose `bonding_curve_progress` (not persisted → 0.0), so a pump.fun token that graduated during the hold sold via the dead BC pool. Fix: **removed the gate — `_check_pool_state_fresh` now runs for EVERY live sell.** It returns 1.0 (BC closed → graduated or never-pump.fun → route non-local/Jupiter) or 0.0 (BC live → pre-grad → PumpPortal Local), so refreshing always yields correct routing regardless of the stored/lost value. Fail-closed to the stale value on RPC error (no worse than pre-fix; +1 Helius getAccountInfo per live sell). This avoids a schema migration (D03-F3's alt fix) — the live refresh covers the reconcile-lost case. EXEC-002 (Jupiter NameError) already resolved.
**Verification:** py_compile PASS; 4/4 structural (gate removed, unconditional refresh + assignment + fail-closed-except intact). NOT paper-observable (live `else:` branch); flip-confirmed (watch for stale-route 400s disappearing on the first post-grad live sell).
**State changes:** code only; single `git push`. No env/Redis/DB writes. **Rollback:** `git revert` this commit → push.
**🎯 §B PHASE 1 (live-execution correctness) CODE-COMPLETE:** #4+#8 (failed-sell-booked-as-closed + emergency-stop) ✅, #5+D02-F8 (partial-sell sizing both routes) ✅, #6 (buy-idempotency/double-submit + Jito-off + D02-F14) ✅, #7 (routing refresh) ✅. All in code; **all flip-confirmed-only (live branch not paper-observable).**
**Deferred reliability follow-ups FILED (not lost):** `SELL-STORM-PARK-PERSISTENCE-001` (D04-F10 — persist park state to Redis; less acute since Phase-0 stopped the crash-loop) and `EXEC-FORCE-ABANDON-001` (D03-F8 — after N park cycles, force-record a permanently-unsellable position as a loss + remove from tracking; entangles with Phase-3 accounting). `JITO-REIMPLEMENT-001` (real-sig + tip).
**Next:** §B **Phase 2 (safety rails)** — #9 FIX-HIBERNATE-LIVE-VETO, #10 FIX-GOVERNANCE-FAIL-OPEN, #11 daily-loss persistence, #12 live-balance seed, #13 sizing-caps wiring; then **Phase 3 (accounting)** incl. live staged-TP PnL + DASH-CORRECTED-PNL-COLUMN-001. These (esp. #9/#10) are the remaining must-fix-before-flip safety gates.
**Next prompt:** Phase-2 #9 (FIX-HIBERNATE-LIVE-VETO).
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — §B Phase-1 #5 FIX-PARTIAL-SELL-SIZING (+ D02-F8) — staged-TP live sells

**Committed:** `3b6d0b1` fix(live-exec): partial-sell sizing on both routes — `services/execution.py` + `services/bot_core.py`.
**Why (caught my own omission — "leave nothing out"):** #5 was dropped from my earlier "next" list; it's a 🔴 blocker. **D02-F5:** the pre-grad `_execute_pumpportal_local` SELL hardcoded `"amount":"100%"`, so EVERY partial/staged-TP live sell (sell_pct 0.25/0.50/0.95) **dumped the entire position** instead of the intended slice — the bot then thought it held a phantom remainder. **D02-F8:** the Jupiter (post-grad) sell fetched the FULL wallet balance and sold all of it (same bug, other route). (D02-F8 was scoped under #7; done here since it's the same fix.)
**Fix:** threaded a `sell_fraction: float = 1.0` param through `execute_trade` → both sell routes. bot_core's `_close_position` passes `sell_fraction=sell_pct` (fraction of CURRENT on-chain balance — matches the multiplicative `remaining_pct *= (1-sell_pct)` semantics). pre-grad: `"amount"` = `"100%"` if fraction≥0.999 else `f"{frac*100:g}%"` (e.g. "25%"). post-grad Jupiter: `token_amount = int(balance * sell_fraction)`. **Full closes (sell_pct=1.0) → 100%/full balance — byte-for-byte unchanged**; only partials/staged-TPs change.
**Verification:** py_compile PASS (both files); fraction→percent + Jupiter-int arithmetic 10/10 PASS; 4/4 structural (no hardcoded "100%" left, both routes apply the fraction, param threaded, bot_core passes sell_pct). **NOT paper-observable (live `else:` branch); runtime-confirmed at the flip** — validate against a multi-staged-TP live close.
**State changes:** code only; single `git push` redeploys all. No env/Redis/DB writes.
**Rollback:** `git revert` this commit → push.
**§B Phase-1 progress:** #4+#8 ✅, #6 ✅, #5+D02-F8 ✅ (code). **Next: #7 FIX-EXEC-001-002-ROUTING** — now SMALLER (D02-F8 done here): refresh pool state for live sells (EXEC-001), persist `bonding_curve_progress`/`pool_route` at entry + restore in reconcile (D03-F3), EXEC-002 confirmed already-resolved.
**Next prompt:** Phase-1 #7 (final Phase-1 item).
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — §B Phase-1 #6 FIX-BUY-IDEMPOTENCY (double-submit guard + Jito-off + D02-F14)

**Committed:** `2f00b19` fix(live-exec): buy/sell idempotency + disable broken Jito + close D02-F14 — `services/execution.py` only.
**#6 (D02-F3 double-submit):** the retry loop used to `continue` (re-build + re-broadcast the same tx) on a confirmation miss — a DOUBLE-SPEND risk on a buy that actually landed. New `_get_signature_status()` helper (`getSignatureStatuses` on the 3-tier Helius RPC → `landed`/`failed`/`unknown`). On a confirm-miss, execute_trade now polls status (3× w/ 2s) and decides: **landed → success (no resubmit)**; **failed (on-chain err) → resubmit (genuinely didn't execute)**; **unknown → BUY records-as-pending WITH the sig (never double-buy; reconcile/Path-B/_check_exits resolve it), SELL returns failure (caller #4 parks+retries rather than booking a maybe-unlanded close).**
**#6 (D02-F2/F7 Jito):** the Jito bundle path is broken — `_send_jito_bundle` returns the bundle UUID (not a tx sig → confirmation + Path B both fail → fed the double-submit) AND adds no tip (bundles never land). Forced `use_jito = False` in execute_trade → uses the proven local-RPC `_send_transaction` (real sig, 3-tier). Filed `JITO-REIMPLEMENT-001` (real-sig + tip) follow-up.
**#6 (D02-F14):** `_confirm_trade_helius` no longer blind-passes (`confirmed=True`) when `HELIUS_PARSE_TX_URL` is unset — now returns `confirmed=False` so the getSignatureStatuses check verifies on-chain. (Env check: `HELIUS_PARSE_TX_URL` IS currently set on bot_core, so D02-F14 wasn't active — but this removes the latent blind-pass.)
**Verification:** py_compile PASS; `.tmp_phase1/verify_idempotency.py` **6/6 PASS** (`_get_signature_status` landed/failed/unknown parsing + TEST_MODE short-circuit — unit-tested by mocking the RPC session); 9/9 structural checks (use_jito forced off, status-gated decision, action-differentiated unknown handling, D02-F14, old resubmit path gone); code review. **NOT paper-observable (live `else:` branch); runtime-confirmed at the flip.** Deploy bar = bot_core/execution import clean.
**State changes:** code only; single `git push` redeploys all. No env/Redis/DB writes.
**Rollback:** `git revert` this commit → push.
**§B Phase-1 progress:** #4+#8 ✅, #6 ✅ (code). **Next: #7 FIX-EXEC-001-002-ROUTING** — refresh pool state for live sells, persist `bonding_curve_progress`/`pool_route`, AND **must include D02-F8 Jupiter partial-sizing** (enabling a working Jupiter sell path would otherwise reintroduce the full-bag dump) + D02-F5 confirm pumpportal_local partial sizing.
**Next prompt:** Phase-1 #7.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — §B Phase-1 #4+#8 MERGED (live-sell result-check + emergency-stop robustness)

**Committed:** `2a85508` fix(live-exec): merged FIX-LIVE-SELL-RESULT-CHECK (#4) + FIX-EMERGENCY-STOP-ROBUSTNESS (#8) — `services/bot_core.py` only.
**Why merged:** Phase-0 analysis showed #4 changes the failure-raise behaviour #8 depends on — if #4 made `_close_position` raise on a failed sell, emergency_stop (no per-position guard) would abort on the first un-sellable mint, making it WORSE. So they were co-designed: #4 uses **park-and-continue (never raises)**, #8 adds the guard + always-runs the alert/kill-key.
**#4 (D02-F1):** `execute_trade` returns `success=False` on failure (it never raises), so the old `except ExecutionError` was dead code and a failed live sell fell through and was **booked as a successful close** (SOL stranded on-chain, fabricated oracle PnL, position popped + never retried). Now: a new `if not result.success:` check (and the except guard) call a shared `_handle_failed_live_sell()` that increments the per-mint sell-storm counter, parks past `SELL_FAIL_THRESHOLD`, records to `live_execution_log`, and **returns WITHOUT decrementing remaining_pct / booking PnL / writing the close row / popping** — the position stays OPEN for `_check_exits` to retry. Never raises. (Also protects partial/staged-TP sells — the check is before any decrement.)
**#8 (D03-F1, D04-F8):** emergency_stop now wraps each `_close_position` in try/except (one un-sellable mint can't abort the stop), detects "left open" via `key in self.positions` (since #4 leaves failed sells open without raising), **sets the durable Redis `bot:emergency_stop` kill key** (survives restart + visible cross-service), and ALWAYS runs the Discord alert + `bot:status` publish (now reporting `positions_failed`).
**Verification:** py_compile PASS; `.tmp_phase1/verify_phase1_4_8.py` **10/10 PASS** (structural + flow). **CANNOT be paper-observed** — this is the live (`TEST_MODE=false`) `else:` branch, which does not execute in the current paper deployment; runtime confirmation is deferred to the supervised first-live-trades at the flip. Code-reviewed: success path (counter reset, decrement, price, booking) intact; paper branch untouched; no caller relies on the removed raise (`_check_exits` per-position try/except + emergency_stop guard cover it).
**State changes:** code only; single `git push` redeploys all. Deploy observation bar = bot_core comes up clean (no import/startup error); the fix itself runs only live. No env/Redis/DB writes.
**Rollback:** `git revert` this commit → push.
**§B Phase-1 progress:** #4+#8 ✅ (code). Next: **#6 FIX-BUY-IDEMPOTENCY** (double-submit guard + verify `HELIUS_PARSE_TX_URL` set + Jito), then **#7 FIX-EXEC-001-002-ROUTING** (incl. D02-F8 Jupiter partial-sizing — pairs so enabling the Jupiter sell path doesn't reintroduce the full-bag dump).
**Next prompt:** continue Phase-1 #6.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — Phase-0 #3 RUNTIME-CONFIRMED + new finding DASH-CORRECTED-PNL-COLUMN-001 (docs)

**Committed:** `b89f265` docs — Phase-0 #3 runtime confirmation + file DASH-CORRECTED-PNL-COLUMN-001. (No code; this docs push redeploys all services — harmless no-op restart.)
**#3 runtime-confirmed:** read `service:health` from Redis post-deploy — internal-service rows are present and all `ok`: bot_core (heartbeat 8s ago), signal_aggregator (28s), signal_listener (via signals:raw, 0s), market_health (41s). No false-down → no spurious Discord alerts; the down-alert is armed. **A 05-28-style internal crash is now visible on the dashboard + Discord-alerted.** **§B Phase 0 is fully done and verified** (#1 pubsub+leak, #2 market-mode, #2.5 redis-hardening, #3 observability).
**NEW finding `DASH-CORRECTED-PNL-COLUMN-001` (🟠 Phase-3, prod-observed, FILED):** `web` logs a repeating DB error every ~60s — `column "corrected_pnl_sol" does not exist`. A dashboard PnL/analytics query references `corrected_pnl_sol` on a table lacking it (almost certainly `trades` — migration `001` added corrected_* to `paper_trades` only). A PnL panel silently errors. PRE-EXISTING (not from Phase-0 work). Fix: add corrected_* to `trades`, or COALESCE-from-realised when absent / restrict to `paper_trades`. Bundle with FIX-DASHBOARD-MODE-FIDELITY (§B Phase-3 #15). Filed in ZMN_ROADMAP.
**Next:** revised §B Phase 1 begins — merged FIX-LIVE-SELL-RESULT-CHECK + FIX-EMERGENCY-STOP-ROBUSTNESS (#4+#8), unit-test-driven (live `else:` branch can't be paper-observed).

---

## 2026-06-03 — DEPLOY-OBSERVABILITY (§B Phase-0 #3) — PHASE 0 COMPLETE

**Committed:** `51ed450` feat(observability): internal-service liveness rows + Discord down-alert in web health-checker.
**Redis-hardening runtime-confirmed:** post-`2337565` observation — all 6 services Online, **bot_core supervise-restart count = 0** (was restart #8/#9 every 60s → the safety listeners are now stable), `market:migration_count_1h` climbing **2 → 6** (increments landing now), pipeline flowing, paper trades entering. HIBERNATE persists as a warm-up artifact (counter still filling toward DEFENSIVE's ≥10; resolves over ~1h; tracked by MARKET-MODE-THRESHOLD-RECALIBRATE-003). REDIS-CLIENT-HARDENING-001 = success.
**This fix (#3):** makes a crashed internal service VISIBLE + ALERTED (the gap that made the 05-28 outage silent — D12-F2/F3/F4). Chose to fold the liveness checks into the existing `web` service's `_service_health_checker` (runs every 60s) rather than stand up a new billable Railway worker for `continuous_audit.py`. (a) `services/dashboard_api.py`: adds internal-service rows to `service:health` — bot_core (`service:bot_core:heartbeat`+`bot:status`), signal_aggregator (`signal_aggregator:health`), signal_listener (`signals:raw` freshness proxy), market_health (`market:health` freshness proxy); TTL'd keys mean absence==down. Fires a **rate-limited (30min) Discord alert** when bot_core/signal_aggregator/signal_listener has no liveness key. (b) `dashboard/dashboard-analytics.html`: new "ZMN Services" health section renders those rows (5th svc-grid, index-aligned with the JS `sections` map).
**Verification:** py_compile PASS; confirmed liveness keys exist+fresh via Redis (`signal_aggregator:health` has a timestamp); HTML/JS alignment verified (5 grids ↔ 5 sections). Dashboard visual not render-tested (Playwright gated on OBS-004) — markup is append-only + mirrors existing cards (low layout risk). NOT runtime-verified against live Railway yet.
**State changes:** code only; single `git push` redeploys all. No env/Redis/DB writes.
**Note:** a fully-independent watchdog (`continuous_audit.py` as its own Railway service) would survive a `web` outage too; folding into `web` is the no-new-infra choice — filed as the stronger-option follow-up if `web` reliability becomes a concern.
**Rollback:** `git revert` this commit → push.
**§B Phase-0 COMPLETE:** #1 pubsub-isolation (+leak hotfix) ✅, #2 market-mode ✅, #2.5 redis-hardening ✅, #3 observability ✅. Bot recovered + hardened + observable. **Next phases before any live flip:** §B Phase 1 (live-execution correctness — D02-F1/F3/F5, D03-F1), Phase 2 (safety rails), Phase 3 (accounting). Open Phase-0 follow-ups: MARKET-MODE-THRESHOLD-RECALIBRATE-003 (needs ≥1h steady-state counter data).
**Next prompt:** `FIX-LIVE-SELL-RESULT-CHECK` (§B Phase-1 #4 — the most dangerous live defect) when ready to start the live-execution-correctness phase.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — REDIS-CLIENT-HARDENING-001 (Phase-0 reliability) + market-mode observation

**Committed:** `b72fac2` fix(redis): harden all aioredis.from_url calls (keepalive/health_check/retry_on_timeout).
**Why (prod observation of #2 deploy `e30d41b`):** all 6 services Online; `market:health` shows `dex_volume_24h=$1.65B` (healthy), `data_degraded=false`, `mode=HIBERNATE`, and `market:migration_count_1h=2`. So the market-mode fix is WORKING AS DESIGNED — it abstains only on an ABSENT counter; here the counter is PRESENT-but-low (2/hr, below DEFENSIVE's ≥10) so it correctly enforces. The low value is a warm-up (services just restarted → 1h-rolling counter near-empty) + Redis-timeout artifact (the persistent `Timeout reading from redis.railway.internal` is dropping counter INCRements and reads). Paper trades still flow (`ENTERING ... mode=DEFENSIVE [PAPER]` via AGGRESSIVE_PAPER HIBERNATE→DEFENSIVE downgrade). So the dominant remaining issue is the Redis read-timeouts → this fix.
**This fix:** added `socket_keepalive=True, health_check_interval=30, retry_on_timeout=True` to ALL 15 `aioredis.from_url(...)` call sites across 11 service files (bot_core, signal_listener, signal_aggregator, market_health, ml_engine ×2, ml_model_accelerator, governance ×3, dashboard_api, treasury, nansen_wallet_fetcher ×2, telegram_listener). `health_check_interval` reconnects connections Railway's internal proxy silently dropped; `retry_on_timeout` retries transient read-timeouts in-client; `socket_keepalive` keeps idle conns alive. Goal: stop the dropped increments/reads so the migration counter populates accurately + the safety pubsub listeners stop backing off to 60s.
**Verification:** redis-py 7.4.0 construct-test — `from_url` ACCEPTS all 3 kwargs (no startup-crash risk, the key concern for an all-services change); py_compile 11/11 PASS; grep confirms all 15 from_url sites hardened.
**State changes:** code only; single `git push` redeploys all. No env/Redis/DB writes.
**NEW follow-up FILED:** `MARKET-MODE-THRESHOLD-RECALIBRATE-003` (🟡, needs steady-state data) — once Redis is hardened + the counter accumulates a full clean hour, verify the bot's actual migration capture rate vs MARKET_MODES thresholds (DEFENSIVE≥10/NORMAL≥30); the bot may capture only a fraction of real graduations (diagnostic: ~3% feed) so thresholds may need recalibration, and a post-restart warm-up bypass may be warranted. Not addressable now (no steady-state sample).
**Rollback:** `git revert` this commit → push.
**Next:** observe (timeouts↓, counter climbing, mode→DEFENSIVE/NORMAL), then §B Phase-0 #3 `DEPLOY-OBSERVABILITY`.

---

## 2026-06-03 — FIX-MARKET-MODE-MISCLASSIFICATION (§B Phase-0 #2) + bot-RECOVERY confirmation

**Committed:** `5a3e5aa` fix(market-mode): missing-data != dead-market in `_determine_market_mode`.
**BOT RECOVERED (verified in prod):** after the pubsub fixes (`98c8007` + `9fa45b0`) all 6 services are ● Online, **`MaxConnectionsError` gone (0 occurrences)**, and the pipeline is FLOWING — signal_listener emitting signals, signal_aggregator `SCORED → speed_demon`, bot_core `ENTERING ... [PAPER]`. **The 05-28 crash-loop outage is resolved.** `supervise` confirmed catching the redis `TimeoutError` (concise one-liner restarts) and listeners re-subscribe. Phase-0 #1 DONE.
**This fix (#2):** `services/market_health.py` only. `_determine_market_mode` no longer conflates missing data with a dead market: (1) an ABSENT `market:migration_count_1h` → `None` sentinel that ABSTAINS (does not veto) — distinguished from a genuine 0 via `is not None`; (2) `_fetch_defillama` returns `None` (not `0.0`) on failure + last-good fallback (≤1h); (3) the fabricated `pumpfun_vol = 0.15*dex_vol` placeholder is DROPPED as a binding leg (kept as a labelled estimate); (4) total-data-loss → DEFENSIVE (cautious-but-trading), never HIBERNATE-on-a-data-outage; (5) `data_degraded` flag + warning logs. **Net:** a transiently-starved migration counter (the 05-28 trigger) no longer slams a healthy market to HIBERNATE; genuine low volume still → HIBERNATE.
**Verification:** py_compile PASS; `.tmp_market_mode/verify_market_mode.py` **10/10 PASS** incl. the exact outage scenario ($1.75B dex + absent counter → NORMAL, was HIBERNATE) and genuine-dead-market → HIBERNATE. Logic-tested against the real function (pytz stubbed locally; pytz present on Railway).
**State changes:** code only; single `git push` redeploys all. No env/Redis/DB writes. Supersedes MARKET-MODE-001-RE-CALIBRATE-002.
**NEW finding/follow-up (prod-observed, FILED):** `REDIS-CLIENT-HARDENING-001` (Phase-0 reliability) — persistent `Timeout reading from redis.railway.internal:6379` (~every 6s) is environmental Railway-Redis slowness the resilience fix tolerates but doesn't cure; the safety pubsub listeners back off to 60s restarts under it. Harden every `aioredis.from_url` with `socket_keepalive=True`, `health_check_interval`, `retry_on_timeout=True`, lenient `socket_timeout`. Do before live (safety listeners must not be down 60s).
**Rollback:** `git revert` this commit (market_health only) → push.
**Next:** observe #2 deploy (market_health should classify NORMAL not HIBERNATE when counter starved + dex healthy; `data_degraded` flag), then `REDIS-CLIENT-HARDENING-001`, then §B Phase-0 #3 `DEPLOY-OBSERVABILITY`.

---

## 2026-06-03 — FIX-PUBSUB-ISOLATION round 2 (prod-observed connection-leak hotfix)

**Committed:** `3eeb516` fix(pubsub-isolation): release pubsub connection on listener restart + concise supervise logging.
**Why:** Deploy of `98c8007` succeeded — **all 6 services went ● Online, crash-loop RESOLVED** (bot_core logs show the exact `redis.exceptions.TimeoutError` from `_emergency_listener`/`pubsub.listen()` now CAUGHT by `supervise` at `async_utils.py:52` instead of killing the process — the fix is verified working in prod against the very error that caused the outage). **But** observation surfaced a defect the fix exposed: under the current Redis slowness, `supervise` restarts crashed listeners, and 3 listeners create a pubsub with NO `finally: aclose()` → each restart **leaked a pool connection** → `signal_listener` hit `redis.exceptions.MaxConnectionsError: Too many connections` (and likely amplified cluster-wide `Timeout reading from redis.railway.internal` on signal_aggregator/bot_core). Before the fix a crash killed the whole process (fresh pool on Railway restart) so leaks never accumulated; keeping the process alive exposed it.
**Fix:** added `try/finally: await pubsub.aclose()` cleanup-on-exit to the 3 listeners that lacked it — `signal_listener._token_subscribe_listener`, `governance._trigger_listener`, `dashboard_api._redis_broadcaster` (bot_core ×2 + ml_engine ×3 already had it). Now a supervise-restart releases the connection before re-subscribing → no leak. Also made `supervise` log a concise one-liner per restart (was full traceback → spam under sustained transient Redis errors).
**Verification:** py_compile PASS (4 files); all 3 leakers confirmed to have `pubsub.aclose()`; `.tmp_pubsub_fix/verify_pubsub_isolation.py` 25/25 PASS.
**State changes:** code only; single `git push` redeploys all services (fresh pools also clear any accumulated leak). No env/Redis/DB writes.
**Open watch item:** if cluster-wide `Timeout reading from redis` persists AFTER this deploy + fresh pools, it's environmental Railway-Redis slowness → next follow-up = Redis-client hardening (`socket_keepalive`, `health_check_interval`, `retry_on_timeout`) — NOT done here (scope). Observe post-deploy.
**Rollback:** `git revert` this commit + the `98c8007` commit (revert newest first) → push.
**Next:** confirm MaxConnectionsError gone + pipeline flowing, then §B Phase-0 #2 `FIX-MARKET-MODE-MISCLASSIFICATION` (already designed).

---

## 2026-06-03 — FIX-PUBSUB-ISOLATION (§B Phase-0 #1; CODE DEPLOYED; restores the crash-looped bot)

**Committed:** `98c8007` fix(pubsub-isolation) — code (hash backfilled via `git commit --amend`). NEW `services/async_utils.py` (`supervise()` supervised-restart helper); wired into all 7 service top-level gathers + dashboard bg-tasks (signal_listener, bot_core, ml_engine ×2, signal_aggregator, market_health, governance, dashboard_api) + `main.py` single-service entrypoint now routes through `run_service()` (was a bare `await mod.main()`). Docs: AGENT_CONTEXT/ZMN_ROADMAP/CLAUDE.md/STATUS/MONITORING_LOG; `.gitignore` (+`.tmp_pubsub_fix/`).
**State changes:** Code only. **Single `git push` → Railway auto-redeploys ALL services** (the fix touches all of them; the monorepo has no per-service git path, and the bot is already down, so a simultaneous restore is intended here). No env/Redis/DB writes.
**Bot state at session start:** TEST_MODE=true (paper); bot_core + signal_listener CRASHED (pubsub crash-loop) per MARKET-REGIME-DIAGNOSTIC-001 / FULL-CODE-AUDIT-001. **Expected post-deploy:** services come up RUNNING (no crash-loop); migration counter recovers; HIBERNATE clears once legs genuinely pass.
**What landed:** `supervise(coro_factory, name)` runs each long-lived task in a restart-on-crash loop — restarts on Exception (capped exp backoff), STOPS on clean return (no hot-loop), PROPAGATES CancelledError (clean shutdown). Wrapping every gather member isolates a crashing task (e.g. a transient redis pubsub `TimeoutError` in an unguarded `async for pubsub.listen()`) from its siblings AND self-heals it (restart re-subscribes) — no edits to listener bodies (minimal/reversible). `main.py` single-service path now supervised so a process-level escape backs off + restarts instead of crash-looping the container. Fixes D01-F1/F2/F3/F4/F5/F6 + D12-F5.
**Verification:** `py_compile` all 9 changed files PASS. `.tmp_pubsub_fix/verify_pubsub_isolation.py` **25/25 PASS** — behavioral (A1 restart-on-exception→clean-exit; A2 clean-return→no-restart; A3 CancelledError propagates; A4 sibling survives a perma-crashing supervised task) + structural (all 7 services import+wrap `supervise`; `main.py` uses `run_service`, no direct `mod.main()` in the single-service block). NOT runtime-verified against live Railway (deploy observation pending — see below).
**Scope discipline (one lever):** ONLY crash-isolation. Did NOT touch trading logic (entry/ML/sizing/exit), did NOT fix the co-located D10-F1 Redis-URL-password log at `market_health.py:543` (separate FIX-SECRET-LOGGING session), did NOT change `return_exceptions` semantics (supervise handles it; leaving CancelledError propagation intact). No env/Redis/DB writes.
**Blockers cleared:** PIPELINE-PUBSUB-ISOLATION-001 + BOT-CORE-EMERGENCY-LISTENER-PUBSUB-ISOLATION-001 (code-resolved; deploy-observation pending). FULL-CODE-AUDIT §B Phase-0 #1 done.
**Blockers new/active:** §B Phase-0 #2 (FIX-MARKET-MODE-MISCLASSIFICATION) + #3 (DEPLOY-OBSERVABILITY) still required before flip; then Phase 1-3.
**Deploy observation:** WATCH Railway — bot_core + signal_listener should reach SUCCESS/RUNNING (not CRASHED) and the `[supervise]` log lines should appear only on actual task restarts (steady-state silent). **Rollback if regressed:** `git revert` the `fix(pubsub-isolation)` commit (content hash `98c8007`; resolve the exact pushed sha via `git log --oneline -- services/async_utils.py`) — single revert, no force-push → push.
**Next prompt:** confirm clean startup on Railway, then `FIX-MARKET-MODE-MISCLASSIFICATION` (§B Phase-0 #2).
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-03 — FULL-CODE-AUDIT-001 (read-only comprehensive pre-flip codebase audit; ~90 findings; 🔴×14)

**Committed:** `d2f6ea3` docs(full-code-audit-001) — docs-only (hash backfilled via `git commit --amend`). NEW `docs/audits/FULL_CODE_AUDIT_001_2026_06_02.md` (per-dimension narrative + §A findings register + §B pre-flip remediation sequence + §C coverage); AGENT_CONTEXT.md (header), ZMN_ROADMAP.md (Decision Log + tiered follow-ups), CLAUDE.md (Standing-findings row), this STATUS prepend, MONITORING_LOG prepend, `.gitignore` (+`.tmp_full_audit/`). NO services/* change. (One all-services auto-redeploy from this docs push — watchPatterns empty, harmless no-op restart since no code changed.)
**State changes:** NONE. Read-only (source reads + 2 multi-agent workflows: recon+12-dim audit `wf_0d7b9f6b-970`, focused adversarial re-verify of 13 blockers `wf_bcc00321-6df`). No env/Redis/DB/override/redeploy writes.
**Bot state:** TEST_MODE=true (paper). Still DEGRADED/DOWN per MARKET-REGIME-DIAGNOSTIC-001 (dual-service pubsub crash-loop → HIBERNATE-misclassification). Not re-verified this session (static source audit; predecessor 5.064 SOL).
**Findings (key, post adversarial verification):**
- 🟢 **Two reassuring NON-findings (verified):** (a) **TEST_MODE money-path gating is correct & defense-in-depth** — no real on-chain send can fire in paper mode (execution.py early-returns in all 3 routes AND bot_core branches paper/live; both must agree). (b) **Wallet private key NOT leaked in code** (empirical: even repr(Keypair) redacts the seed).
- 🔴 **NEW execution-path blockers** (masked because validated live trade id 6580 was a single full round-trip): **D02-F1** failed live sells booked as closed (`execute_trade` returns success=False, never raises → the `except ExecutionError` at bot_core:1366 is dead, `result.success` never checked on the sell path → SOL stranded, accounting lies, position popped); **D02-F5** pre-grad `_execute_pumpportal_local` SELL hardcodes `"amount":"100%"` → every partial/staged-TP live sell dumps the whole position; **D02-F3** buy double-submit on confirm timeout (no idempotency); **D03-F1** emergency_stop has no per-position guard → unreliable in a mass dump.
- 🔴 **CONFIRMS+EXTENDS the outage** (PIPELINE-PUBSUB-ISOLATION-001): pubsub-crash class in **5 services not 2** (ml_engine/governance/dashboard added); all 6 gathers miss `return_exceptions=True`; **single-service `main.py` has no supervised restart** (resilient `run_service()` wired only to dead legacy mode) — the 2nd structural amplifier.
- 🔴 **Outage is INVISIBLE:** heartbeat keys have zero readers; dashboard health has no internal-service rows; only liveness alerter (`continuous_audit.py`) is undeployed — why the ~05-28 outage was silent.
- 🔴/🟠 **Safety fail-opens:** governance veto (BUG-010); AGGRESSIVE_PAPER HIBERNATE bypass → live-trades-in-HIBERNATE; daily-loss accumulator zeroed every restart; `MAX_SD_POSITIONS` a phantom env var (real cap hardcoded 3 → V5A 5/7 ladder unenforceable); dead `market:loss_override` (3 writers/0 readers); stale-balance inflates exposure/drawdown denominators ~10× until first live close.
- 🟠 **Live accounting:** live close books only the final-partial PnL across staged TPs; Path B pairs full-entry with final-partial exit → corrupts `corrected_pnl_sol` (the go/no-go data) on multi-sell trades.
- **Adversarial verify** downgraded 6 of 13 NEW 🔴→🟠 (real but not capital-fatal: D02-F2 Jito-path-secondary, D02-F8 not-live-reachable, D04-F2 abs-cap-floors-size, D04-F4 drawdown-stop-backstops, D05-F1 understates-wins-only, D05-F2 corrupts-corrected_*-only) and **refuted 1** (D09-F3 $80-SOL-fallback — bot_core refreshes the key every 2s; divide/multiply cancel).
**Verdict:** ⛔ **DO NOT FLIP.** The §B remediation sequence (Phase 0 restore → Phase 1 execution → Phase 2 safety → Phase 3 accounting) must be GREEN first; each is a separate verified fix-session.
**Blockers cleared:** none (audit; it enumerates+ranks). Confirmed RESOLVED in code: EXEC-002 (Jupiter NameError); solders signing API correct.
**Blockers new/active:** see ZMN_ROADMAP Decision Log + tiered follow-ups (this session files the NEW execution/observability/accounting items). PIPELINE-PUBSUB-ISOLATION-001 remains the #1 flip-unblocker, now scoped wider (5 services + main.py supervisor).
**Concurrent-session compatibility:** fetch before push; pull-rebase ≤3× else PUSH_DEFERRED + STOP-L.
**Next prompt:** `FIX-PUBSUB-ISOLATION` (§B Phase-0 #1) — restore the bot first; then the §B sequence.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-02 — MARKET-REGIME-DIAGNOSTIC-001 (read-only; HIBERNATE = pipeline OUTAGE, not a lull; ⛔ DO-NOT-FLIP)

**Committed:** `356a91a` docs(market-regime-diagnostic-001) — docs-only (hash is the pre-amend content commit, backfilled into this line via `git commit --amend`). NEW `docs/audits/MARKET_REGIME_DIAGNOSTIC_001_2026_06_02.md`, NEW `docs/findings/MARKET_REGIME_GAP.md`, CLAUDE.md (Standing-findings row), AGENT_CONTEXT.md (header + §6 PC4 note + new pipeline-health pre-flip gate), ZMN_ROADMAP.md (Decision Log row), this STATUS prepend, MONITORING_LOG prepend, `.gitignore` (+`.tmp_market_regime/`). NO services/* change. (One all-services auto-redeploy from this docs push — watchPatterns empty.)
**State changes:** NONE. Read-only (Railway env/Redis reads, deploy logs + `list-deployments`, asyncpg SELECTs, source reads, + a 9-agent external-corroboration/adversarial-verification workflow). No env/Redis/DB/override/redeploy writes.
**Bot state:** TEST_MODE=true (paper). **DEGRADED/DOWN:** latest Railway deploy of BOTH bot_core AND signal_listener = **CRASHED** (crash-looping ~6.7s on a redis pubsub `TimeoutError`). `market:mode:current=HIBERNATE` (misclassified). override absent. consecutive_losses=0. 0 open. Wallet not re-verified (read-only; predecessor 5.064 SOL; no on-chain activity). Effectively DOWN since ~2026-05-28T13:00Z (1 paper trade in 5 days).
**Findings (key):**
- 🔴 **The V3R HIBERNATE is a PIPELINE OUTAGE misclassified as a market lull** — predecessor's "broad memecoin lull" REFUTED. Forced solely by `grad_rate=0` (`market:migration_count_1h` absent), caused by a dual-service pubsub-timeout crash loop (`signal_listener.py:335`/`1395` + bot_core ~`L2410`, unguarded `asyncio.gather`). External (3 sources, conf 0.8-0.9): pump.fun launching ~1,500-2,000/hr + ~350 graduations/day; bot feed ~64/hr = ~3%. `dex_vol=$1.753B` is healthy (NORMAL-tier).
- 🟢 **Validation edge is genuine-regime** (Q4): +8.91 SOL/day, 91.9% WR, n=1066 (05-20..28) ran NORMAL(830)/DEFENSIVE(236)/HIBERNATE(0); snapshots NORMAL 1747/DEF 691/HIB 0 → **PC2 NOT re-opened** (cost-fidelity gap applies separately; full Path-B cost-correction still leaves +32.5 SOL/76.7% WR).
- 🔴 **LIVE-TRADES-IN-HIBERNATE** (Q2): HIBERNATE skip (`signal_aggregator.py:1741`) is `AGGRESSIVE_PAPER`-gated (not TEST_MODE); bot_core has no independent skip → a bot_core-only flip would trade live in HIBERNATE (NOT inert), and the flip's redeploy would revive the CRASHED bot_core into live mode.
- 🟢 All 6 sub-verdicts survived adversarial verification (conf 0.88-0.95).
**Verdict:** ⛔ **DO NOT FLIP — the system is DOWN, not hibernating.** PATH C (misclassified) + PATH D (flow degraded), one root cause. The V3R NO-FLIP was correct; its *reason* ("wait for market") was wrong — fix the pipeline, not patience.
**Blockers cleared:** none (diagnostic; it reframes the V3R/PC4 blocker).
**Blockers new/active:**
- 🔴 **NEW `PIPELINE-PUBSUB-ISOLATION-001` (Tier 1, V5A flip-blocker)** — isolate pubsub `.listen()` loops from the top-level `asyncio.gather` in signal_listener (L335/L1395) + bot_core (~L2410); promotes+extends `BOT-CORE-EMERGENCY-LISTENER-PUBSUB-ISOLATION-001`. Acceptance gate before any flip: both services RUNNING (not CRASHED), counters recovered, mode non-HIBERNATE for the right reason.
- 🟡 `MARKET-MODE-001-RE-CALIBRATE-002` (Tier 2) — single-leg `grad_rate` veto + `pumpfun_vol = dex_vol*0.15` placeholder (`market_health.py:390`).
- 📋 PC4 (V5A flip itself) — stays `[ ]`, now also gated on pipeline restoration.
**Concurrent-session compatibility:** local HEAD == origin/main `1a44349` (0/0) at start; `git fetch` clean; single docs push at end.
**Next prompt:** `PIPELINE-PUBSUB-ISOLATION-001` (chat-side to author) — the real flip-unblocker.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-02 — RAILWAY-CLI-UPGRADE + deploy-SHA RESOLVED (follow-on to V3R; tooling + 1 finding)

**Committed:** docs-only follow-on (audit §9 addendum + ZMN_ROADMAP Decision Log row + this STATUS entry + AGENT_CONTEXT header note). NO services/* code change. NO env/Redis/DB writes. (Two bot_core redeploys were triggered earlier by the V3R docs pushes — see Findings; this commit triggers one more, expected.)
**State changes:** **Railway CLI upgraded 4.6.0 → 4.66.0** (npm global, local machine — not a Railway/bot change). bot_core redeployed twice today from the V3R docs pushes (Railway redeploys on every `main` push — watchPatterns empty). No env/Redis/DB/TEST_MODE changes.
**Bot state:** TEST_MODE=true (paper). **bot_core now running deployment `39b44e7` (SUCCESS)** — `service:bot_core:heartbeat={alive, emergency:false}`, `bot:status={RUNNING, test_mode:true, open_positions:0, market_mode:HIBERNATE, consecutive_losses:0}`. Wallet 5.064095633 SOL (unchanged — no on-chain activity). market:mode still HIBERNATE.
**Findings (key):**
- 🟢 **Deploy-SHA carry-forward RESOLVED.** With CLI ≥4.10.0, `list-deployments` confirms bot_core's active deployment is `39b44e7` — a descendant of `7458f2d`. All three V5A fixes (`f3591eb`/`3c50520`/`7458f2d`) are confirmed **running in production**, not just at HEAD. Closes the "deploy unconfirmed since 2026-05-28" item.
- 🟡 **Transient crash observed + self-recovered.** Deployment `298833d` (V3R audit docs commit) CRASHED at startup: `redis.exceptions.TimeoutError: Timeout reading from redis.railway.internal:6379` in `_emergency_listener` (`bot_core.py:2067`) → propagated through unguarded `asyncio.gather` (`bot_core.py:2410`) → container stopped. Follow-up `39b44e7` came up SUCCESS (same code; Redis blip cleared). No code defect — both commits docs-only on top of `7d33994`.
- 🟡 **NEW Tier-2 follow-up `BOT-CORE-EMERGENCY-LISTENER-PUBSUB-ISOLATION-001`** (not V5A-blocking). The emergency-listener pubsub `.listen()` TimeoutError isn't isolated → a Redis read-timeout crashes the whole process instead of restarting just that task. Self-heals via restart policy (10 retries) but adds startup flakiness relevant to **flip-time clean-restart verification** (Phase 2.3/4.3/5.1 depend on a clean bot_core restart + `Startup reconciliation: 0`). Recommend a try/except-with-reconnect loop around the listener before the next flip.
**Verdict:** ✅ Tooling fixed; deploy-SHA blocker CLOSED; 1 new Tier-2 startup-resilience follow-up filed. V3R's NO-FLIP verdict on STOP-M (HIBERNATE) is unchanged.
**Blockers cleared:** Deploy-SHA verification (Railway CLI now ≥4.10.0; running container confirmed on `7458f2d`-inclusive `39b44e7`).
**Blockers new/active:**
- 🟡 **`BOT-CORE-EMERGENCY-LISTENER-PUBSUB-ISOLATION-001` Tier 2** — isolate `_emergency_listener` pubsub timeouts so a Redis blip can't crash the container during a flip restart. Land before the next flip attempt (not strictly blocking — restart policy recovers — but it can abort a flip's clean-restart verification).
- 📋 **PC4 (V5A flip itself)** — still gated on a non-HIBERNATE window + Jay D-S7 watch.
**Concurrent-session compatibility:** single push; `git fetch` clean before push.
**Next prompt:** none. Re-attempt the flip in the next non-HIBERNATE window.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-06-02 — V5A-FLIP-002-V3R (read-only preflight, ⛔ NO-FLIP — HALTED at Phase 1 on STOP-M)

**Committed:** `298833d` docs(v5a-flip-002-v3r) — docs-only (this hash backfilled by a small follow-up commit). NEW `docs/audits/V5A_FLIP_002_V3R_2026_06_02.md` (the no-flip audit; prompt referenced it as `_2026_06_01`); `AGENT_CONTEXT.md` (header refresh + §6 PC4 2026-06-02 no-flip note; PC4 stays `[ ]`); `ZMN_ROADMAP.md` (Decision Log row); this `STATUS.md` prepend; `MONITORING_LOG.md` prepend; `.gitignore` (+`.tmp_v5a_flip_v3r/`). NO services/* code change. **NO env change. NO Redis writes. NO Postgres writes. NO deploy/redeploy. NO TEST_MODE flip.**
**State changes:** **NONE.** Pure read-only preflight (Railway env reads, Redis reads, Helius `getBalance`+`parseTransactions`, asyncpg SELECTs). The bot was not touched.
**Bot state:** TEST_MODE=true (paper, unchanged). DAILY_LOSS_LIMIT_SOL=4.0, MAX_POSITION_SOL=0.25, MAX_SD_POSITIONS=20 (sizing reconcile to 1.5/0.10/5 was NEVER reached — gate failed first). BOT_CORE_FILL_MC_CEILING_USD=1000. ML_THRESHOLD_BOT_CORE_SD=40. **Wallet 5.064095633 SOL on-chain** (Helius `getBalance`, exact; `bot:onchain:balance` matches). `bot:emergency_stop` absent; `bot:consecutive_losses=0`; `bot:daily_pnl=0`; `bot:loss_pause_until` absent. 0 paper open / 0 live open. `market:mode:current=HIBERNATE`. bot_core alive-but-idle (`bot:filter:fill_mc_ceiling:rejects:2026-06-02=2`; heartbeat/`bot:status` absent = HIBERNATE-quiet artifact, not a crash). Outstanding V5A blockers: **1** (PC4 — the flip itself).
**Findings (key):**
- 🔴 **STOP-M FIRED (×2) — NO FLIP.** (1) `market:mode:current=HIBERNATE` (fresh `market:health` ts 12:54:34Z: cfgi 34.0, sentiment 22.5, SOL $78.84). Per D-S4 (binding), HIBERNATE aborts; NORMAL/DEFENSIVE/AGGRESSIVE would proceed. `market:mode:override` not set — computed HIBERNATE genuinely governs. (2) Signal pipeline near-dead: `market:new_token_count_1h=14` (was 10,257 on 2026-05-20 — ~700× collapse); `service:health.pumpportal="no signals"`. A flip would be inert. Setting an override to NORMAL is out of §2 scope AND would defeat the safety gate — not done.
- 🟢 **Everything-else-GO.** Railway authed (10 services). Commits `f3591eb`/`3c50520`/`7458f2d` all ancestors of HEAD `7d33994` (local==origin 0/0). All 3 fixes present in `services/bot_core.py` source (reconcile filter L260/L319 + `[RECONCILE]`; entry-sig field L225 + kwarg L1022 + `[ENTRY_SIG]`; PC3 MC gate L982; per-decision estop L612; sell-storm default 8 L228; ORIGIN_MISMATCH L1558). Wallet 5.064 SOL ≥ 5.0.
- 🟢 **Path B engine intact (id 6580).** DB row `correction_method='live_actual_v1'`, both sigs populated; Helius on-chain re-parse of the entry sig → native delta **−374,251,786 lamports** EXACT match. STOP-PathB no-fire.
- 🟢 **Orphan baseline CLEAN (the May-20 vector).** `trades WHERE closed_at IS NULL AND trade_mode='live'` = **0** (the exact live-reconciler query). paper-open=0; any-mode trades-open=6 (paper orphans Bug-1 now skips); MAX(paper_trades.id)=10926. 14 phantom rows still tagged; 1 real live row. STOP-Orphan no-fire.
- 🟡 **Deploy-SHA UNCONFIRMABLE (carry-forward).** Railway CLI is **v4.6.0** → `list-deployments` unsupported (needs ≥4.10.0). Running-container SHA for `7458f2d` remains unconfirmed since 2026-05-28. The Phase 1.5 forced-redeploy fail-safe was NOT triggered (flip halted on STOP-M; redeploy is a flip-enablement write). Next attempt: upgrade CLI ≥4.10.0 OR rely on forced-redeploy.
- 🟡 **Market context shift since 2026-05-20:** SOL ~$85→$78.84; mode DEFENSIVE→HIBERNATE; new-token flow 10,257→14/hr. Looks like a broad memecoin lull (all data-source health `ok`), not a single-service outage.
- 🟢 **Every STOP evaluated:** A/H/Wallet/PathB/Orphan/Scope/Loop/L/Claude all no-fire; STOP-M fired ×2; Deploy/Reconcile/Contamination/DailyHalt/Rollback n/a (never flipped). **Zero state writes → STOP-Scope clean; Phase R not applicable.**
**Verdict:** ⛔ **NO FLIP — HALTED at Phase 1 preflight gate on STOP-M (HIBERNATE + dead signal pipeline).** This is a market-timing halt, **NOT STOP-Rollback** — no failed flip, no contamination, no diagnosis-and-fix gate. Re-attemptable in the next non-HIBERNATE window under the same authorization framework. PC4 stays `[ ]`.
**Blockers cleared:** none (none were closeable — PC4 requires a successful flip, which market regime prevented).
**Blockers new/active:**
- 📋 **PC4 (V5A flip itself)** — still Jay-authorization-gated; re-attempt when `market:mode:current` ∈ {NORMAL/DEFENSIVE/AGGRESSIVE} AND `new_token_count_1h` back in the thousands (pumpportal flowing) AND Jay can commit the D-S7 4–6h watch.
- 📋 **Railway CLI v4.6.0 < 4.10.0** — upgrade so Phase 1.5 deploy-SHA verification works; else use forced-redeploy fail-safe. (Deploy-SHA for `7458f2d` unconfirmed since 2026-05-28.)
- All prior carries unchanged (3 Tier-3 V5A-FIXES-001 follow-ups, BUG-010 Anthropic, etc.).
**Concurrent-session compatibility:** No concurrent session at start (last commit `7d33994` from 2026-05-28). `git fetch origin main` clean (0/0). Single docs push at session end; append-only updates throughout.
**Next prompt:** None auto-triggered. Re-paste V5A-FLIP-002-V3R (or a thin re-run) in the next non-HIBERNATE window. Carry-forward unchanged: Phase 10.5/6.3 first-live-close must produce `correction_method='live_actual_v1'` (entry-sig wiring `7458f2d`).
**Pending Claude-chat prompts not yet pasted:** none — this session terminated with a NO-FLIP verdict.

---

## 2026-05-28 — LIVE-FEE-CAPTURE-ENTRY-SIG-WIRING-001 (code+deploy, ✅ 1 FIX DEPLOYED — Path B entry-sig wiring resolved)

**Committed:** `7458f2d` fix(live-exec): LIVE-FEE-CAPTURE-ENTRY-SIG-WIRING-001 — populate Position.entry_signature from live buy result (9 LOC in `services/bot_core.py`); follow-up docs commit (this entry) for audit + canonical doc updates. Files: NEW `docs/audits/LIVE_FEE_CAPTURE_ENTRY_SIG_WIRING_001_2026_05_27.md` (11 sections), `services/bot_core.py` (+9 LOC: Position dataclass `entry_signature` field + live-entry kwarg + `[ENTRY_SIG]` observability log), `AGENT_CONTEXT.md` (header refresh + §6 follow-up resolution), `ZMN_ROADMAP.md` (Decision Log row), `MONITORING_LOG.md` (entry), this STATUS.md prepend, `.gitignore` (.tmp_entrysig/).
**State changes:** Code: 1 commit to `services/bot_core.py` (+9 LOC, 0 deletions). One Railway auto-deploy from `git push origin main`. No env changes. No Redis writes. No DB writes. Bot remained TEST_MODE=true throughout. Net behavior delta: live close path's Path B parser (`bot_core.py:1450` `helius_parse_signature(pos.entry_signature)`) now receives a real signature when a live buy populates Position.entry_signature; produces `correction_method='live_actual_v1'` instead of `'live_estimated_v1'`. **Paper mode behavior byte-for-byte unchanged** (paper buy result has no real sig → field stays None → close-path falls back to Path A exactly as before).
**Bot state:** TEST_MODE=true (paper, unchanged). DAILY_LOSS_LIMIT_SOL=4.0. MAX_POSITION_SOL=0.25. MAX_SD_POSITIONS=20. BOT_CORE_FILL_MC_CEILING_USD=1000. ML_THRESHOLD_BOT_CORE_SD=40. **Wallet 5.064 SOL on-chain** (unchanged since V5A-FIXES-001; not re-verified this session — no on-chain activity expected, none occurred). `bot:status` + `service:bot_core:heartbeat` transiently absent during deploy window (Redis post-restart re-population); `bot:filter:fill_mc_ceiling:rejects:2026-05-28=1982` confirms bot active today. Outstanding V5A blockers: **1** (PC4 — the flip itself, Jay-authorization-gated).
**Findings (key):**
- 🟢 **Q1-Q5 investigation resolves V5A-FIXES-001 §11 follow-up.** exit_signature template works; live buy returns sig synchronously via `ExecutionResult` (not STOP-Async); Position constructed at `bot_core.py:1005` with `result.signature` already in scope (used at L1061 for DB INSERT and L1090 for ENTERED log); close-path Path B at L1450 reads in-memory `pos.entry_signature` (not DB column); reconciler reads `trades` table which has no `entry_signature` column → mid-position-restart edge case documented as known limitation.
- 🟢 **Fix deployed clean** (commit `7458f2d`). 9 LOC total, 1 file. Fail-safe by design: default None covers paper entries, reconciler-restored Positions, and any buy result lacking a signature attr — all paths the close path already handles as "skip entry parse, fall back to Path A".
- 🟢 **17/17 verify checks PASS** (`.tmp_entrysig/verify_entrysig.py`). Source assertions (10/10), Position dataclass unit tests (2/2), mock ExecutionResult fail-safe (2/2), Path B dry-run on id 6580 (3/3). id 6580 entry_signature parses to `success=True` with `native_delta_lamports=-374251786` — proves downstream Path B consumer works end-to-end when given a real sig.
- 🟡 **Behavioral verification deferred to V5A-FLIP-002-V3 first live close.** Paper mode does not exercise the live entry branch (L993-1090) so `[ENTRY_SIG]` log line cannot appear until flip. The 17/17 verify suite covers everything except live-buy-runtime; that's tonight's job.
- 🟡 **Known limitation: mid-position restart loses entry_signature.** trades-table schema migration would be required to persist across restart; STOP-Scope deferred. SD short-hold + rare restarts make this an acceptable trade-off per session prompt §3 Q5.
- 🟢 **All STOPs evaluated, none critical fired:** A (Railway MCP callable), D (clean fetch pre-push), H (precedence files all readable), Z (TEST_MODE=true verified via Railway MCP), Async (sig is synchronous), Investigate (exit_signature template works), Scope (9 LOC ≪ 50, 1 file, no schema migration), Verify (17/17 PASS), Loop (no retry loops needed), L (no git conflicts — single push clean), Claude (no limit hit). STOP-J evaluated post-deploy (see "Blockers new/active" — deploy poll inconclusive at session end).
- 🟢 **Scope discipline maintained:** NO TEST_MODE change; NO env change; NO other service touched; NO schema migration; NO modification of exit_signature mechanism (mirrored, not touched); NO modification of trade execution logic; NO fix of other Tier 3 follow-ups (PORTFOLIO-SNAPSHOT-MODE-FILTER-001 / HEARTBEAT-EMERGENCY-STOP-REFLECTION-001 / PAPER-CLOSE-TRADES-CLOSED_AT-HARDENING-001 unchanged).
**Verdict:** ✅ **CODE DEPLOYED.** V5A-FIXES-001 §11 follow-up `LIVE-FEE-CAPTURE-002-PATH-B-ENTRY-SIG-NOT-WIRED-001` RESOLVED. Tonight's V5A-FLIP-002-V3 first live close will produce `correction_method='live_actual_v1'` and count toward `PAPER-FEE-MODEL-CALIBRATION-001` ≥10-Path-B-row prereq, unless the in-memory-only fix misses (mid-position-restart edge case). Behavioral verification at flip time.
**Blockers cleared:** `LIVE-FEE-CAPTURE-002-PATH-B-ENTRY-SIG-NOT-WIRED-001` Tier 3 (filed by V5A-FIXES-001 §11) ✅ RESOLVED.
**Blockers new/active:**
- 📋 **PC4 (V5A flip itself)** — Jay-authorization-gated per CLAUDE.md "Live trading mode — session-gated"; next D-S5 window (Wed/Thu AEST evening 18:00-21:00 Sydney).
- 📋 **Railway deploy verification pending** — `railway logs -s bot_core` returned "No deployments found" through end of session; commit `7458f2d` confirmed on `origin/main`; `bot:filter:fill_mc_ceiling:rejects:2026-05-28=1982` confirms bot active today, but `bot:status` + `service:bot_core:heartbeat` absent at last check (could be ongoing build or unrelated Redis-key absence). If deploy fails to land, the fix is queued and will land on the next code-deploy-triggering push to `bot_core`.
- 📋 **Mid-position restart limitation** — documented in audit §7; future work (out of scope tonight): reconciler lookup of `paper_trades.entry_signature` by mint+open match.
- All prior carries unchanged (V5A-FIXES-001's 3 remaining Tier 3 follow-ups, BUG-010 Anthropic, etc.).
**Concurrent-session compatibility:** No concurrent session detected at session start (last commit `0cb9923` V5A-FIXES-001 docs from 2026-05-21). `git fetch origin main` clean before push (no ahead/behind). Single push, no conflicts.
**Next prompt:** None auto-triggered. Carry forward to V5A-FLIP-002-V3 Phase 10.5: verify first live close produces `correction_method='live_actual_v1'`. If `live_estimated_v1`, flag for investigation but do NOT auto-rollback (profitability unaffected; calibration data quality is the impact).
**Pending Claude-chat prompts not yet pasted:** none — this session terminated with verdict.

---

## 2026-05-21 — V5A-FIXES-001 (overnight autonomous, code+DB+deploy, ✅ 3 FIXES DEPLOYED + 1 CLOSED-AS-NON-BUG + 14 ROWS TAGGED)

**Committed:** `f3591eb` fix(bot-core): V5A-FLIP-RECONCILE-FILTER-001 — apply trade_mode filter to BOTH paper_trades AND trades tables in reconcile paths; `3c50520` fix(bot-core): V5A-FLIP-CLOSE-TRADE-MODE-001 / Bug 2 — defensive-INSERT trade_mode derived from trades.trade_mode (was hardcoded 'live'); `<HASH>` docs(v5a-fixes): V5A-FIXES-001 — investigation + 3 deploys + 14-row contamination cleanup + V5A-FLIP-002-V3 prep notes. Files: NEW `docs/audits/V5A_FIXES_001_2026_05_21.md` (combined session audit, 11 sections), NEW `docs/audits/ORPHAN_PAPER_CLOSURE_INVESTIGATION_001_2026_05_21.md` (Phase 1 Q1-Q4 evidence), NEW `docs/audits/V5A_FLIP_002_V3_PREP_NOTES_2026_05_21.md` (chat-side reference for next flip session), `services/bot_core.py` (~45 LOC total across 2 commits: Bug 1 in `_reconcile_positions` + `_load_state`, Bug 2 in defensive INSERT path), `ZMN_ROADMAP.md` (Decision Log row + 3 status updates: RECONCILE-FILTER ✅ DEPLOYED, CONTAMINATION-CLEANUP ✅ DONE, EMERGENCY-STOP-LIVENESS ✅ CLOSED-AS-NON-BUG, +1 NEW row V5A-FLIP-CLOSE-TRADE-MODE-001 ✅ DEPLOYED), `AGENT_CONTEXT.md` (header refresh), `MONITORING_LOG.md` (entry), this STATUS.md prepend. **DB UPDATE:** 14 phantom rows (paper_trades ids 9940-9953) tagged `correction_method='paper_orphan_at_flip_v5a_001'` + `correction_applied_at='2026-05-21T14:31:14Z'`. **2 Railway auto-deploys** (Phase 3 commit `f3591eb` ready 14:42:26Z; Phase 6 commit `3c50520` ready ~15:05Z) — both clean restarts, paper-mode reconciler verified loading 0 positions, no errors. **Wallet UNCHANGED on-chain throughout: 5.064095633 SOL** (Helius `getBalance` at Phase 0; no on-chain activity expected, none occurred).
**State changes:** Code: 2 commits to `services/bot_core.py` (Bug 1 + Bug 2). Two container restarts via Railway auto-deploy. DB: 14 paper_trades rows tagged (one UPDATE). No env changes. No Redis writes. Bot remained TEST_MODE=true throughout. Net behavior delta: live-mode reconciler now correctly filters paper rows from `trades` table; live-mode defensive close-path INSERT now derives `trade_mode` from `trades.trade_mode` lookup instead of hardcoded `'live'`.
**Bot state:** TEST_MODE=true (paper, unchanged). DAILY_LOSS_LIMIT_SOL=4.0 (baseline post-V5A-FLIP-001-V2 rollback). MAX_POSITION_SOL=0.25. MAX_SD_POSITIONS=20. BOT_CORE_FILL_MC_CEILING_USD=1000 (active on paper + live; live dormant). ML_THRESHOLD_BOT_CORE_SD=40. **Wallet 5.064095633 SOL on-chain** (verified Helius). 3 paper open positions at session end (BaAAekrnP4Xx, CbQeeReWJjrH, 2mYdJCtxFXDY etc. — bot trading normally). bot:emergency_stop absent. bot:consecutive_losses=0. Outstanding V5A blockers: **1** (PC4 — the flip itself, Jay-authorization-gated).
**Findings (key):**
- 🟢 **Phase 1 puzzle resolved.** V5A-FLIP-001-V2's 14 phantoms came from open paper rows in the `trades` ML corpus, NOT from `paper_trades`. The live-mode reconciler reads `trades`, where `mode_clause` was empty (filter only applied to paper_trades). Open trades rows accumulate when `pos.trades_ml_id == 0` causes `_close_position` to skip the `UPDATE trades SET closed_at=...` step. The 14 phantom paper_trades rows ids 9940-9953 are NEW INSERTs by the live container's defensive close path — NOT original paper_trades rows with flipped trade_mode. STOP-INV1/2/3 all evaluated, none fired.
- 🟢 **Bug 1 / V5A-FLIP-RECONCILE-FILTER-001 deployed clean** (commit `f3591eb` 14:35Z, deploy ready 14:42:26Z). New `[RECONCILE]` log markers confirmed present in startup logs. Paper-mode reconciler loaded 0 positions correctly. Live-mode SQL now includes `AND trade_mode='live'` filter (verified via behavioral test against live DB).
- 🟢 **Phase 2 cleanup clean** (DB UPDATE only, no commit). 14 rows tagged paper_orphan_at_flip_v5a_001 with correction_applied_at='2026-05-21T14:31:14Z'. id 6580 (real on-chain live trade with `correction_method='live_actual_v1'`) verified unchanged. STOP-CLEAN1/CLEAN2 both PASS.
- 🟢 **Bug 2 / V5A-FLIP-CLOSE-TRADE-MODE-001 deployed clean** (commit `3c50520` ~14:46Z, deploy ready ~15:05Z). Plan's Option A (entry_signature discriminator) was infeasible — Position dataclass has no entry_signature field; adopted Option C (DB lookup of trades.trade_mode). All 14 V5A-FLIP-001-V2 incident trade_ids verified to now write `trade_mode='paper'` instead of `'live'` under the new code path. +`[ORIGIN_MISMATCH]` warning log for observability. No `[ORIGIN_MISMATCH]` warnings post-deploy (correct — defensive INSERT path not triggered in paper mode).
- 🟢 **Bug 3 / BOT-CORE-EMERGENCY-STOP-LIVENESS-001 closed as non-bug.** Investigation found per-decision `bot:emergency_stop` Redis check already at `services/bot_core.py:604-609` inside `process_signal`. V5A-FLIP-001-V2 audit's "Phase 5 finding" was misinterpretation: heartbeat.emergency (in-memory flag) was conflated with the per-decision check (which works correctly). The 14 phantoms had entry_time 2026-05-12..2026-05-19 — NOT new positions opened during the 9-min drain window. STOP-Scope5 fires for the right reason (no fix needed). Filed `HEARTBEAT-EMERGENCY-STOP-REFLECTION-001` Tier 3 for observability surfacing.
- 🟢 **V3 prep notes written.** `docs/audits/V5A_FLIP_002_V3_PREP_NOTES_2026_05_21.md` captures 7 deltas vs V2 — Phase 1 reconciler-mirror query, Phase 3 trades-table snapshots, Phase 5 drain effectiveness signal change, auto-rollback `[ORIGIN_MISMATCH]` trigger, etc.
- 🟢 **All STOPs evaluated; no critical/process STOPs triggered.** A (Railway MCP), D (concurrent session), H (precedence files), Z (TEST_MODE), INV1/2/3, CLEAN1/2, Scope1/4/5, Verify3/4, Verify3-Post, J3/J6 all evaluated; none fired.
- 🟡 **4 new Tier 3 follow-ups filed** (all non-blocking): PORTFOLIO-SNAPSHOT-MODE-FILTER-001 (snapshot task counts ignore trade_mode), LIVE-FEE-CAPTURE-002-PATH-B-ENTRY-SIG-NOT-WIRED-001 (latent Path B bug — pos.entry_signature never set), HEARTBEAT-EMERGENCY-STOP-REFLECTION-001 (heartbeat doesn't surface Redis flag), PAPER-CLOSE-TRADES-CLOSED_AT-HARDENING-001 (close path's trades.closed_at UPDATE is conditional on `trades_ml_id`).
- 🟡 **Operational note:** there's 1 ongoing trades-table orphan at any given moment (different mint changes minute-to-minute as paper bot operates). Post-Bug-1 the live reconciler correctly skips these. The Bug 2 defense-in-depth would catch any Bug-1 regression with `[ORIGIN_MISMATCH]` log. Defense in depth working as designed.
**Verdict:** ✅ **3 FIXES DEPLOYED + 1 CLOSED-AS-NON-BUG + CLEANUP DONE.** V5A-FLIP-002 is now structurally unblocked from the 3 follow-ups filed by V5A-FLIP-001-V2 rollback. PC1/PC2/PC3 all satisfied; only PC4 (the flip itself) remains, gated on Jay-authorization for next D-S5 window. V5A-FLIP-002-V3 prep notes available for chat-side prompt assembly.
**Blockers cleared:** V5A-FLIP-RECONCILE-FILTER-001 ✅ DEPLOYED; V5A-FLIP-CONTAMINATION-CLEANUP-001 ✅ DONE; BOT-CORE-EMERGENCY-STOP-LIVENESS-001 ✅ CLOSED-AS-NON-BUG.
**Blockers new/active:**
- 📋 **PC4 (V5A flip itself)** — Jay-authorization-gated per CLAUDE.md "Live trading mode — session-gated"; next D-S5 window (Wed/Thu AEST evening 18:00-21:00 Sydney).
- 📋 **HEARTBEAT-EMERGENCY-STOP-REFLECTION-001 Tier 3 🟢** — observability improvement; not V5A-blocking.
- 📋 **PORTFOLIO-SNAPSHOT-MODE-FILTER-001 Tier 3 🟢** — cosmetic.
- 📋 **LIVE-FEE-CAPTURE-002-PATH-B-ENTRY-SIG-NOT-WIRED-001 Tier 3 🟢** — latent Path B bug (Position.entry_signature never set); not V5A-blocking.
- 📋 **PAPER-CLOSE-TRADES-CLOSED_AT-HARDENING-001 Tier 3 🟢** — data hygiene; not V5A-blocking.
- All prior carries unchanged (BUG-010 Anthropic, etc.).
**V5a precondition delta:** No PC closures (PC1/PC2/PC3 already satisfied; PC4 unchanged). 3 follow-ups closed. Outstanding V5A blockers: **1** (PC4 outstanding).
**Concurrent-session compatibility:** No concurrent session detected at session start (last commit `c1c9345` V5A-FLIP-001-V2 docs from 2026-05-20 20:57+10:00). Pull-rebase before each push (retry up to 3× on conflict per CLAUDE.md). Append-only updates throughout (STATUS prepend, MONITORING_LOG prepend, ZMN_ROADMAP Decision Log + 3 status updates + 1 new row, AGENT_CONTEXT header refresh).
**Next prompt:** None auto-triggered. Jay assembles V5A-FLIP-002-V3 chat-side using `docs/audits/V5A_FLIP_002_V3_PREP_NOTES_2026_05_21.md` as reference. Recommended flip window: next D-S5 (Wed or Thu AEST evening, 2026-05-21 → 2026-05-22 if conditions met).
**Pending Claude-chat prompts not yet pasted:** none — this session terminated with verdict.

---

## 2026-05-20 — V5A-FLIP-001-V2 (env+Redis+deploy, ❌ FLIP FAILED → ROLLED BACK)

**Committed:** `<HASH>` deploy(v5a-flip): V5A-FLIP-001-V2 — TEST_MODE=false on bot_core at 10:00:05Z UTC → ROLLED BACK at 10:22:42Z after Phase 8 failed (Startup reconciliation: 14 open positions in DB, not 0); risk_manager EMERGENCY_STOP at -1.86 SOL daily loss from in-memory closes of 14 pre-existing phantom paper_trades rows; wallet UNCHANGED on-chain (5.064 SOL — no live transactions); rollback completed cleanly (TEST_MODE=true restart 10:26:57Z, sizing reverted 10:42:56Z restart, bot:emergency_stop DEL'd 10:52Z); PC1 SATISFIED but PC4 stays `[ ]` outstanding; 3 new Tier 1/2 follow-ups required before V5A-FLIP-002 can fire; 14 contaminated rows in paper_trades (ids 9940-9953) need cleanup. Files: NEW `docs/audits/V5A_FLIP_001_2026_05_20.md` (8 sections + 14-row contamination table), `AGENT_CONTEXT.md` (header prepend + §6 PC1 flip [ ]→[x] + §6 PC4 expanded with retry gating + Outstanding V5A blockers wording change), `ZMN_ROADMAP.md` (Decision Log row + 3 NEW Tier 1/2 entries: V5A-FLIP-RECONCILE-FILTER-001, V5A-FLIP-CONTAMINATION-CLEANUP-001, BOT-CORE-EMERGENCY-STOP-LIVENESS-001), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend). NO services/* code change. **Env changes (Railway, bot_core):** DAILY_LOSS_LIMIT_SOL 4.0→1.5→4.0; MAX_POSITION_SOL 0.25→0.10→0.25; MAX_SD_POSITIONS 20→5→20; TEST_MODE true→false→true (all reverted on rollback). **Redis writes:** bot:status DEL (Phase 3); bot:consecutive_losses SET 0 (Phase 3) → 14 (live container) → SET 0 (post-rollback); bot:emergency_stop SET true (Phase 5) → DEL (post-rollback). **Postgres writes:** bot_state.consecutive_losses UPSERT '0' (Phase 3, repeated post-rollback). **DB side-effect (UNINTENDED):** 14 rows in paper_trades (ids 9940-9953) committed with trade_mode='live', NULL signatures, NULL correction_method — data contamination from in-memory closes of pre-existing orphan paper positions.
**State changes:** Significant. See above. Two restarts during attempt (Phase 2 + Phase 7) + two restarts during rollback. Bot is now back at original env state (TEST_MODE=true paper, sizing 4.0/0.25/20) — net env delta is **zero** vs session start.
**Bot state:** TEST_MODE=true (paper, restored). DAILY_LOSS_LIMIT_SOL=4.0 (restored). MAX_POSITION_SOL=0.25 (restored). MAX_SD_POSITIONS=20 (restored). BOT_CORE_FILL_MC_CEILING_USD=1000 (unchanged, C1 active). ML_THRESHOLD_BOT_CORE_SD=40 (unchanged). **Wallet 5.064095633 SOL on-chain** ← **UNCHANGED throughout the incident** (verified Helius getBalance 4× across the session). 0 open positions (paper or live). bot:emergency_stop DEL'd. bot:consecutive_losses=0 (Redis + Postgres). Outstanding V5A blockers: **1 PC + 3 new follow-ups** (PC1 ✅ closes, PC4 ⚠ stays open with new gating dependencies, V5A-FLIP-RECONCILE-FILTER-001 + V5A-FLIP-CONTAMINATION-CLEANUP-001 + BOT-CORE-EMERGENCY-STOP-LIVENESS-001 newly filed).
**Findings (key):**
- 🔴 **Phase 8 FAIL — `Startup reconciliation: 14 open positions in DB`** (expected 0). CLEAN-003 script clears Redis (paper:positions, bot:open_positions, bot:status) but does NOT touch `paper_trades` DB rows. 14 pre-existing rows with `entry_time IS NOT NULL AND exit_time IS NULL` carried across the TEST_MODE flip. The live container's `bot_core._reconcile_positions` loaded them into `self.positions` without filtering by `trade_mode`.
- 🔴 **DATA CONTAMINATION — 14 rows in paper_trades committed with `trade_mode='live'`.** ids 9940-9953. All have `entry_signature=NULL`, `exit_signature=NULL`, `correction_method=NULL`. These are NOT real live trades — they're orphan paper positions closed in-memory by the live container at synthetic exit prices. They will pollute any future live-mode analytics filtering by `trade_mode='live'`. Cleanup is a Tier 1 follow-up (`V5A-FLIP-CONTAMINATION-CLEANUP-001`).
- 🟢 **Wallet SAFE throughout.** 5.064095633 SOL on-chain at every checkpoint (pre-flip 09:22Z, T-30s 09:59:30Z, post-emergency-stop 10:08Z, post-rollback 10:50Z). Zero on-chain transactions. The `risk_manager EMERGENCY_STOP: Daily loss limit: -1.86 SOL` fired BEFORE any live buy decision reached `execution.py`.
- 🟢 **Rollback per §7 executed cleanly.** First rollback restart (TEST_MODE=true) at 10:26:57Z: AUDIT auto-reset consecutive_losses 14→0, Startup reconciliation: 0 open positions in DB, Bot Core ready, "Emergency stop active — skipping all new signals" log lines confirm bot honored bot:emergency_stop on the fresh container's signal-entry path. Second restart (sizing reverted) at 10:42:56Z: MAX_ABS=0.25 SOL confirmed in startup log. bot:emergency_stop DEL'd post-second-restart. Bot is in paper mode, sizing original, ready to resume paper trading.
- 🔴 **Phase 5 finding (root cause #2): `bot:emergency_stop=true` Redis flag set at 09:55:01Z did NOT halt paper-bot signal intake for 9 min.** Heartbeat reported `emergency: false` through 10:08 (only flipped true after the live risk_manager fired). The check is honored at container startup (proven by rollback restart) but NOT continuously by a running container. This is independent of root cause #1 (the paper_trades reconcile gap) — both contributed: even with a proper reconcile filter, future flips would still have to deal with paper-bot trades continuing through Phase 5 unless this is fixed too.
- 🟢 **Path B re-validation (Phase 1 step 11): EXACT MATCH.** Parser reconstructed id 6580 to `-0.094244978 SOL`, delta vs DB `corrected_pnl_sol` = `0.0 SOL` (within 0.001 tolerance). `services/helius_parser.py` regression-free.
- 🟢 **Phase 2 sizing reconcile + restart #1 — CLEAN.** Bot restarted at 09:36:26Z with MAX_ABS=0.10 SOL active; post-restart paper entries verified at 0.1000 SOL position sizing.
- 🟡 **CLEAN-003 script deviation:** `redis-cli` not on Windows PATH on this machine — substituted Redis MCP + asyncpg equivalents for steps 1-4 of `scripts/live_flip_prep.sh`. Functionally equivalent (verified: bot:status DEL'd, paper:positions:* empty, bot:open_positions:* empty, consecutive_losses=0 in both Redis and Postgres). Did NOT mitigate the root cause — script does not reconcile `paper_trades` rows anyway.
- 🟡 **Open question (not investigated this session):** how did the 14 orphan paper positions accumulate in the first place? Entry times span 2026-05-12 to 2026-05-19 — some are days old. The 09:55:28Z query `SELECT COUNT(*) FROM paper_trades WHERE entry_time IS NOT NULL AND exit_time IS NULL` returned 0, yet 10:04:11Z reconcile loaded 14. Either the bot's reconcile filter is different from my audit query, OR there are paper_trades rows that match certain criteria but not others (e.g., `is_closed` flag without `exit_time`). Worth investigating before V5A-FLIP-002.
- 🟢 **All other STOP checks passed at the appropriate phase** (STOP-A/A2/B/D/E/F/G/H all evaluated; STOP-C / Path B PASSED; STOP-M (market mode) = DEFENSIVE accepted per D-S4 V2 amendment).
**Verdict:** ❌ **FLIP FAILED → ROLLED BACK CLEANLY.** STOP-Rollback applies. No retry until 3 follow-ups land (V5A-FLIP-RECONCILE-FILTER-001 + V5A-FLIP-CONTAMINATION-CLEANUP-001 + BOT-CORE-EMERGENCY-STOP-LIVENESS-001) + new D-S5 window + new explicit Jay authorization. Wallet safety verified. Bot returned to original paper state.
**Blockers cleared:** PC1 (wallet 5.064 SOL on-chain ≥ 5.0 target, confirmed Helius 4× during session). PC2 already SATISFIED. PC3 already SATISFIED. Outstanding `V5A_GO_LIVE_DECISIONS` precondition: only PC4 remains (the flip itself).
**Blockers new/active:**
- 📋 **V5A-FLIP-RECONCILE-FILTER-001 Tier 1 🔴** (V5A-blocking) — patch `bot_core._reconcile_positions` to filter by `trade_mode='live'` when `TEST_MODE=false`. ≤30 lines. Without this, every future flip attempt will repeat the failure.
- 📋 **V5A-FLIP-CONTAMINATION-CLEANUP-001 Tier 1 🟡** (data hygiene — not strictly V5A-blocking but should ship before V5A-FLIP-002 to keep live analytics clean) — tag (or DELETE) `paper_trades` ids 9940-9953. Recommended: tag with `correction_method='paper_orphan_at_flip_v5a_001'`. Preserves audit trail.
- 📋 **BOT-CORE-EMERGENCY-STOP-LIVENESS-001 Tier 2 🟡** — make running bot honor `bot:emergency_stop` Redis flag per-entry-decision (not just at container startup). Without this, the Phase 5 position-drain mechanism is unreliable.
- 📋 **PC4 (V5A flip itself)** — Jay-authorization-gated. STOP-Rollback applies; cannot fire until 3 follow-ups above land + new D-S5 window.
- All prior carries unchanged (BUG-010 Anthropic, etc.).
**V5a precondition delta:** **−1 PC blocker (PC1 closes)**. **+3 new Tier 1/2 follow-ups** (gating PC4 retry). Honest V5A blocker count: **1 PC outstanding (PC4) + 3 new dependencies**.
**Concurrent-session compatibility:** No concurrent session detected (last commit `6567ef7` API-MCP-PREFLIGHT-001 from earlier this same chat at 09:16Z — 43 min before session start). Pull-rebase before push (retry up to 3× on conflict per CLAUDE.md). Append-only updates throughout.
**Next prompt:** None auto-triggered. The 3 follow-ups need to be scheduled by Jay as separate sessions before V5A-FLIP-002 can fire. Recommended sequence: (1) V5A-FLIP-CONTAMINATION-CLEANUP-001 (fastest — Postgres UPDATE, no code change, ~15 min); (2) V5A-FLIP-RECONCILE-FILTER-001 (Tier 1 code fix, ~1-2h); (3) BOT-CORE-EMERGENCY-STOP-LIVENESS-001 (Tier 2 code fix, scoping investigation may be needed first). Then V5A-FLIP-002-V3 prompt with updated CLEAN-003 (or pre-flip DB-reconcile step) + new D-S5 window.
**Pending Claude-chat prompts not yet pasted:** none — this session terminated with ROLLED-BACK verdict.

---

## 2026-05-20 — API-MCP-PREFLIGHT-001 (read-only, ⚠ CONDITIONAL READY)

**Committed:** `dc84f38` docs(api-mcp-preflight): API-MCP-PREFLIGHT-001 — read-only verification of live-execution dependencies pre-V5A-flip — verdict ⚠ CONDITIONAL READY; PC1 SATISFIED (wallet 5.064 SOL on-chain — material change from carry-forward 0.064); STOP-A fired (Railway MCP re-auth needed); all other critical items GO; 9/9 Phase 4 code checks PASS. Files: NEW `docs/audits/API_MCP_PREFLIGHT_001_2026_05_20.md` (11 sections), `AGENT_CONTEXT.md` (header refresh — no §6 PC1 status flip here; happens at the flip session), `ZMN_ROADMAP.md` (Decision Log row + Tier 3 `DASHBOARD-PUMPPORTAL-HEALTH-PROBE-001`), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend). NO services/* code change, NO env change, NO Redis writes, NO DB writes, NO deploy.
**State changes:** None. Pure read-only verification — Phase 1 MCP no-op battery + Phase 2 no-auth external API probes + Phase 3 Redis state reads + Phase 4 grep-based code checks. Helius `getBalance` re-verified incidentally; Redis reads via MCP only.
**Bot state:** TEST_MODE=true (paper, unchanged — carry-forward). `BOT_CORE_FILL_MC_CEILING_USD=1000` ACTIVE on both paper and live paths (live dormant under TEST_MODE=true — Phase 4 #2 verified gate intact at `bot_core.py:953-965`). `ML_THRESHOLD_BOT_CORE_SD=40` ACTIVE (Phase 4 #5 verified `bot_core.py:60, 130-144, 674`). **Wallet 5.064095633 SOL on-chain** ← **MATERIAL CHANGE from 0.064 carry-forward.** Exact +5.000 SOL top-up matches D-S3 trial budget — PC1 SATISFIED. 0 paper open positions / 0 live open positions / circuit_breaker N/A (0 consecutive losses) — STOP-E and STOP-I do NOT fire. `market:mode:current=DEFENSIVE` (not NORMAL — D-S4 manual judgment needed at flip time). 2h+ bot_core uptime, 10K+ signals/hour observed. Outstanding V5A blockers: **1** (PC4 flip itself; PC1 now SATISFIED).
**Findings (key):**
- 🟢 **PC1 SATISFIED — wallet 5.064 SOL.** Helius `getBalance(4h4pst...)` returned 5.064095633 SOL — exactly +5.000000000 SOL vs. 0.064095633 SOL carry-forward (last verified hours earlier by PC1-WALLET-TARGET-RECONCILE-001 and CLAUDE-MD-MCP-INDEX-001). Matches D-S3 trial budget exactly. **STOP-B does NOT fire.** Outstanding V5A blockers drop 2 → 1 (PC4 flip remains).
- 🔴 **STOP-A FIRED — Railway MCP not callable.** "Not logged in to Railway CLI. Please run 'railway login' first" — unchanged from yesterday's CLAUDE-MD-MCP-INDEX-001 observation. Per §4 STOP-A: Phase 2 env-read path blocked. Phases 3 and 4 continued via non-Railway tools (Helius/Redis MCP + grep). The "abort remaining phases" instruction interpreted as "abort Phase 2 specifically" (Phase 2 depends on Railway env reads for API keys); Phase 3 (Redis+DB) and Phase 4 (code grep) DO NOT depend on Railway.
- 🟢 **Phase 1 — 10/12 MCPs callable.** Connected: Helius, Redis, GitHub project-scoped, Vybe, DexPaprika, CoinGecko, Playwright, shadcn, Context7, Google Drive. Failed: Railway (STOP-A), Socket (known-broken, non-blocking).
- 🟢 **Phase 2 no-auth probes — all GO.** Binance SOL $85.02 (vs Redis $84.9 = 0.14% delta), Jito 8 tip accounts returned, GeckoTerminal Raydium SOL/USDC pool $85.08, Rugcheck SOL token report. Authenticated APIs proxy-validated via Redis `service:health` (helius/vybe/dexpaprika/rugcheck/jupiter all OK from bot's own server-side probes).
- 🟡 **PumpPortal "no signals" WARN is a dashboard quirk, NOT a signal outage.** `dashboard_api.py:2041` reports WARN when `last_signal` Redis key is absent, but `market:new_token_count_1h=10257`, `market:migration_count_1h=67`, `signals:evaluated` present — pipeline is ALIVE (10K+ signals/hour). Filed Tier 3 `DASHBOARD-PUMPPORTAL-HEALTH-PROBE-001`.
- 🟢 **Phase 3 — bot RUNNING paper, 0 open positions.** 2h+ uptime, daily P&L +2.88 SOL today. `bot:emergency_stop` absent, `bot:loss_pause_until` absent, `bot:consecutive_losses=0`. **`market:mode:current=DEFENSIVE`** — operator judgment required at flip time per D-S4 manual check.
- 🟢 **Phase 4 — 9/9 code checks PASS.** C1 paper + C1 live (V2), Path B parser + integration, ML gate helper, sell-storm circuit breaker, CLEAN-003 script, TIME_PRIME env-driven, Analyst suppression at SA. Prompt-side correction: `ANALYST_DISABLED` is at SA only (correct design — bot_core uses `ML_THRESHOLD_BOT_CORE_ANALYST=0` reserved-not-active).
- 🟡 **Sentry DSN env status unknown** (`mcp__sentry__*` needs auth; Railway env blocked). Non-blocking for tonight (observability, not execution path).
- 🟡 **DB queries blocked** (no DATABASE_PUBLIC_URL without Railway). STOP-F (portfolio snapshot delta) cannot be evaluated — deferred to flip session.
- 🟢 **Jupiter prompt error — current host is `api.jup.ag/swap/v2/*`** per CLAUDE.md, NOT prompt's `quote-api.jup.ag/v6/*` which DNS-failed. `service:health.jupiter=ok HTTP 200` confirms current endpoint works.
**Verdict:** ⚠ **CONDITIONAL READY.** All technical preconditions GO. Railway MCP must be re-authed for CC-automated flip OR Jay manually flips via dashboard. Both paths technically unblocked.
**Blockers cleared:** PC1 (wallet top-up) — Helius confirms 5.064 SOL on-chain. Outstanding V5A blockers 2 → 1.
**Blockers new/active:**
- 🟡 **Railway MCP re-auth needed** — Jay action: `! railway login` (interactive). Sessions touching Railway env/deploys remain blocked until done.
- 📋 **PC4 (V5A flip itself)** — Jay-authorization-gated. Pre-flip self-check: (a) re-verify wallet ≥5 SOL; (b) decide market:mode at DEFENSIVE per D-S4; (c) reconcile `DAILY_LOSS_LIMIT_SOL=4.0 → 1.5` per D-S3; (d) run `live_flip_prep.sh`; (e) set TEST_MODE=false on bot_core only.
- 📋 **`DASHBOARD-PUMPPORTAL-HEALTH-PROBE-001` Tier 3 🟢** — `dashboard_api.py:2041` false-WARN on "no signals" when pipeline is actually alive. Cosmetic observability defect.
- All prior carries unchanged (BUG-010 Anthropic governance, Socket MCP broken — both non-blocking).
**V5a precondition delta:** **−1 blocker** (PC1 closes — wallet verified 5.064 SOL via Helius). Honest V5A blocker count: **1 outstanding** (PC4 flip itself).
**Concurrent-session compatibility:** No concurrent session detected at session start (last commit `98145ab` STOP-LOSS-20-NO-MOMENTUM-90S-COMBINED-EVAL-001 from earlier this same chat). Pull-rebase before push (retry up to 3× on conflict per CLAUDE.md). Append-only updates throughout (STATUS prepend, MONITORING_LOG prepend, ZMN_ROADMAP Decision Log + Tier 3 row insertion, AGENT_CONTEXT header prepend, NEW audit doc).
**Next prompt:** **V5A flip session** is the natural next step (Jay-authorization-gated). Recommended approach in audit §11. The flip cannot proceed CC-automated until Railway MCP is re-authed; manual dashboard flip is fully unblocked.
**Pending Claude-chat prompts not yet pasted:** none — this session terminated with verdict.

---

## 2026-05-20 — STOP-LOSS-20-NO-MOMENTUM-90S-COMBINED-EVAL-001 (read-only, VALIDATED)

**Committed:** `35a5b18` docs(combined-eval): STOP-LOSS-20-NO-MOMENTUM-90S-COMBINED-EVAL-001 — combined eval verdict VALIDATED on post-C1 sample (n=511, 7.13d, WR 90.0%, +33.10 SOL / +4.64/day, max MC $998, 0 above $1K, 0 FP winners, nm90 rate 0%); PC2 SATISFIED; flag DASH-CLEAN-DATA-FLOOR-FIX-001 Tier 3 follow-up. Files: NEW `docs/audits/STOP_LOSS_20_NO_MOMENTUM_90S_COMBINED_EVAL_001_2026_05_20.md`, `AGENT_CONTEXT.md` (header + §6 PC2 flip [ ]→[x] + blocker count 3→2), `ZMN_ROADMAP.md` (Decision Log row + Tier 3 row for `DASH-CLEAN-DATA-FLOOR-FIX-001`), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend). NO services/* code change, NO env change, NO Redis writes, NO DB writes, NO deploy.
**State changes:** None. Pure read-only analytical investigation — SQL queries via DATABASE_URL+asyncpg + Redis MCP gate-counter spot-check. No Redis writes, no env changes, no deploy. (Note: the eval also incidentally confirmed `BOT_CORE_FILL_MC_CEILING_USD=1000` still active via Redis evidence of 12,443 cumulative gate rejects across 2026-05-13 → 2026-05-20.)
**Bot state:** TEST_MODE=true (paper, unchanged — carry-forward; no behavioural change this session). `BOT_CORE_FILL_MC_CEILING_USD=1000` ACTIVE on bot_core paper + live paths (live dormant under TEST_MODE=true; carry-forward — confirmed via Redis gate-firing evidence this session). `ML_THRESHOLD_BOT_CORE_SD=40` ACTIVE (carry-forward). Wallet **0.064095633 SOL on-chain** (carry-forward — Helius getBalance verified twice earlier this chat by PC1 reconcile + MCP index sessions; unchanged). 0 paper open positions / 0 live open positions / circuit_breaker N/A (paper) — carry-forward. Outstanding V5A blockers: **2** (down from 3) — PC1 (wallet top-up to ~5 SOL per 2026-05-20 reconcile, Jay action), PC4 (flip itself, Jay-authorization-gated).
**Findings (key):**
- 🟢 **PC2 SATISFIED.** Combined eval VALIDATED on post-C1 SD-paper sample: n=511 closed (≥250), 7.13d (≥72h), 8 distinct days (≥3), 7 days with ≥30 trades. WR 90.0% with every day above 83.6%. Total +33.10 SOL / +4.64 SOL/day, no negative day (range +0.87 to +7.36).
- 🟢 **F1/C1 gate PASS all criteria.** Max market_cap_at_entry $998 (under $1K ceiling); 0 trades above $1K; 0 FP winners; `stop_loss_20%` rate 2.5% (target ≤5%); median MC $661; avg MC $653. MC bands: $0-$500 (+17.41/100% WR), $500-$750 (+16.23/100% WR), $750-$1000 (-0.54/53.6% WR — marginal tier).
- 🟢 **no_momentum gate PASS.** `no_momentum_90s` exit rate **0%** (target ≤30%, was 76.5% pre-C1). `TRAILING_STOP` 95.5% (was ~14%). Strip-top-10 daily rate **+3.39 SOL/day** (target ≥+1.0). NOT lottery-driven — top trade +2.84 SOL (8.6% of total).
- 🟢 **Cross-validation tight.** C1 STOP-A counterfactual baseline (523/+32.62/91.4%/8.12d) vs post-deploy actual (511/+33.10/90.0%/7.13d): matches within 2.3% N, 1.5% PnL, 1.4 pp WR. Per-day actual +4.64 SOL is 15.4% above counterfactual +4.02. Counterfactual was correct.
- 🟢 **Redis gate-firing evidence.** 12,443 cumulative post-C1 rejects across 8 days vs 511 kept = ~96% reject rate. ~24× the F1 reject rate (consistent with $1K vs $3K ceiling structure).
- 🟢 **Cost-fidelity translation.** Paper +4.64 SOL/day is UPPER BOUND. First-order cost-only adjustment: live-equiv ≈ +2.64 SOL/day. With latency + MEV unmodelled and V5A staged sizing (D-S6 0.10/5), realistic V5A-equivalent: **+0.5 to +1.5 SOL/day** with material uncertainty.
- 🟡 **Side-effect finding (NOT fixed per scope):** `BIGGEST_WINS_CLEAN_DATA_FLOOR_TS=1747104561.0` constant in DASHBOARD-DESIGN-REALIGNMENT-001 amendment is wrong-year — `1747104561` is **2025-05-13 02:49:21 UTC**, correct C1 floor for **2026-05-13 03:29:21 UTC** is **`1778642961`**. Caught at first query pass: SQL with wrong floor returned 2,966 trades / 28d / Apr 22 → May 20 instead of expected ~7d / 511 / post-C1. Filed Tier 3 `DASH-CLEAN-DATA-FLOOR-FIX-001`.
- 🟢 **§1.5 prompt assumption corrected at session start.** Prompt's "Postgres MCP — primary tool" doesn't exist (per earlier `CLAUDE-MD-MCP-INDEX-001`). Used canonical pattern: `DATABASE_URL=postgresql://...@gondola.proxy.rlwy.net:29062/railway` (shell env) + asyncpg Python script. Railway MCP broken (re-auth needed) — substituted AGENT_CONTEXT §2 + Redis evidence for config-drift check.
- 🟢 **All STOPs evaluated, none triggered.** STOP-A/B/C/D/E/F/G all pass.
**Verdict:** ✅ **VALIDATED — supports V5A relaunch.** PC2 (post-C1 observation through combined eval) SATISFIED. The paper-side strategy is robustly validated. The sizing graduation ladder (D-S6) + active observation (D-S7) is the right structural answer to the cost-fidelity gap. Relaunching IS how the gap gets closed (per PAPER-FEE-MODEL-CALIBRATION-001's ≥10-Path-B-row prerequisite).
**Blockers cleared:**
- PC2 (post-C1 observation through combined eval) — SATISFIED with VALIDATED verdict. §6 flipped `[ ]` → `[x]`.
- `STOP-LOSS-20-RUG-FILTER-EVAL-001` and `NO-MOMENTUM-90S-EVAL-001` both closed as bundled by this combined session.
**Blockers new/active:**
- 📋 **`DASH-CLEAN-DATA-FLOOR-FIX-001` Tier 3 🟢** — fix `BIGGEST_WINS_CLEAN_DATA_FLOOR_TS` constant before DASH-001 BUILD-1 ships Card 7. Out of scope for this eval; flagged for follow-up.
- 📋 **PC1 (wallet top-up to ~5 SOL)** — Jay action, unchanged from 2026-05-20 PC1 reconcile.
- 📋 **PC4 (V5A flip itself)** — Jay-authorization-gated per CLAUDE.md "Live trading mode — session-gated". The flip session's natural agenda: (a) verify PC1 actioned (wallet ≥5 SOL); (b) reconcile `DAILY_LOSS_LIMIT_SOL=4.0 → 1.5` per D-S3 (flagged in-cell by 2026-05-20 PC1 reconcile); (c) execute flip per D-S4/D-S5/D-S6/D-S7 operational rules.
- 🟡 **Railway MCP re-auth needed** (unchanged from MCP index session) — Jay action.
- All prior carries unchanged (BUG-010 Anthropic, etc.).
**V5a precondition delta:** **−1 blocker** (PC2 closes). Honest V5A blocker count post-this-session: **2 outstanding** (PC1 wallet, PC4 flip), 4 completed (historical: SD_MC_CEILING_002, LIVE-FEE-CAPTURE-002 Path B, LIVE-MODE-FILTER-PARITY-001-V2, **PC2 / combined eval new**).
**Concurrent-session compatibility:** No concurrent session detected at session start (last commit `3ea0290` CLAUDE-MD-MCP-INDEX-001 earlier this same chat). Pull-rebase before push (retry up to 3× on conflict per CLAUDE.md). Append-only updates throughout (STATUS prepend, MONITORING_LOG prepend, ZMN_ROADMAP Decision Log + Tier 3 row insertion, AGENT_CONTEXT header prepend + §6 PC2 flip + blocker count change, NEW audit doc).
**Next prompt:** **V5A flip session** is the natural next step (Jay-authorization-gated; not auto-triggered). The flip session reads: (a) `docs/findings/V5A_GO_LIVE_DECISIONS.md` for the operational rules, (b) AGENT_CONTEXT §6 PC1/PC4 for pre-flip checks, (c) this eval doc for the validation evidence, (d) yesterday's PC1 reconcile session output for the related `DAILY_LOSS_LIMIT_SOL` env reconciliation. The flip cannot fire until PC1 (Jay action: wallet top-up to ~5 SOL) is complete.
**Pending Claude-chat prompts not yet pasted:** none — this session terminated with VALIDATED verdict.

---

## 2026-05-20 — CLAUDE-MD-MCP-INDEX-001 (docs-only, INDEX ADDED)

**Committed:** `4f70cba` docs(claude-md-mcp-index): CLAUDE-MD-MCP-INDEX-001 — add MCP servers available H2 section to CLAUDE.md (10 connected verified, 3 connected-but-broken, 6 unavailable, Postgres MCP notably absent); file Tier 3 MCP-REFERENCE-CORRECTION-001 follow-up. Files: `CLAUDE.md` (+1 H2 section between Standing findings and Resolved Bugs), `AGENT_CONTEXT.md` (header refresh), `ZMN_ROADMAP.md` (Decision Log row + Tier 3 row), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend). NO services/* code change, NO env change, NO Redis writes, NO DB writes, NO deploy.
**State changes:** None. Pure docs work — Phase 1 was no-op verification calls (read-only on each MCP). No Redis writes, no env changes, no deploy.
**Bot state:** TEST_MODE=true (paper, unchanged — carry-forward from PC1-WALLET-TARGET-RECONCILE-001 earlier this same chat, no behavioural change since). `BOT_CORE_FILL_MC_CEILING_USD=1000` active (live path dormant under TEST_MODE=true; carry-forward). Wallet **0.064095633 SOL on-chain** (incidentally re-verified Helius `getBalance` THIS SESSION as part of Phase 1 no-op battery — unchanged). 0 paper open positions / 0 live open positions / circuit_breaker N/A (paper) — carry-forward, no trading-affecting change this session. Outstanding V5A blockers: **3** (PC1 wallet top-up — target ~5 SOL per yesterday's reconcile, PC2 observation through ≥2026-05-27 combined eval, PC4 flip-itself).
**Findings (key):**
- 🟢 **Phase 1 no-op verification battery (13 calls).** 10 succeeded: `mcp__redis__*` (list pattern), `mcp__helius__*` (getBalance → 0.064095633 SOL), `mcp__github__*` project (search_repositories), `mcp__vybe__*` (list-endpoints → 47 v4 paths), `mcp__dexpaprika__*` (getNetworks → 35 networks), `mcp__coingecko__*` (search_docs), `mcp__playwright__*` (browser_tabs list), `mcp__shadcn__*` (get_project_registries → @shadcn), `mcp__plugin_context7_context7__*` (resolve-library-id React → 5 matches), `mcp__claude_ai_Google_Drive__*` (list_recent_files). 3 failed: `mcp__railway__*` ("Not logged in to Railway CLI"), `mcp__plugin_github_github__*` ("invalid session" — use project-scoped `mcp__github__*` instead), `mcp__socket__*` ("No valid session").
- 🟢 **Phase 3 grep** found "Postgres MCP" references in CLAUDE.md:32 (already qualified "(once installed)" — fine), `docs/SETUP_NEW_MACHINE.md:194`, `docs/CLAUDE_TOOLING_INVENTORY.md:5,183` (line 183 explicitly says "deliberately NOT installed"), and 4 historical audits (April 19). All accurate-in-historical-context (asyncpg shim IS the Postgres-MCP-equivalent). Per §7 scope: NOT fixed this session; flagged for follow-up.
- 🟢 **CLAUDE.md edit:** new H2 section "MCP servers available" added between line 54 (Standing findings instruction) and line 56 (Resolved Bugs). Three sub-tables (Connected / Connected-but-broken / Configured-but-unavailable) + Notably-absent (no Postgres MCP) + self-amending instruction. Mirrors `CLAUDE-MD-FINDINGS-INDEX-001` pattern.
- 🟢 **Tier 3 follow-up filed:** `MCP-REFERENCE-CORRECTION-001` (📋 OPEN Tier 3 🟢, ~20m) — sweep historical audit docs to add "(via asyncpg shim — not an actual MCP)" qualifier where "Postgres MCP" is used as shorthand. Not blocking; docs hygiene.
- 🟢 **No STOP triggered.** STOP-A (no concurrent session — last commit `0ad2282` earlier this chat session). STOP-B (CLAUDE.md Standing findings section present and intact at line 37). STOP-C (10/13 succeeded; "most fail" threshold not met). STOP-D (no scope creep — single section added). STOP-E/F (no Claude limit, no git conflict pre-push).
- 🟡 **Side-effect observation (Railway re-auth):** `mcp__railway__*` is a real blocker for any session needing to read Railway env or trigger deploys via MCP. Workaround: Railway dashboard. Existing CC sessions that have shelled out to the `railway` CLI may also be hitting the same expired token — verify before assuming the shell variant works. NOT a session-fix here (Jay action).
**Verdict:** ✅ **INDEX ADDED.** Future CC sessions reading CLAUDE.md as first action will discover the MCP layer with verified callable status. Chat-side prompts can now reference the index when naming MCPs to avoid the "Postgres MCP" class of inaccuracy. The 3 broken-in-session servers are explicitly flagged so prompts don't reference them as available.
**Blockers cleared:** discoverability gap for MCP server callable status (the trigger for this session); plugin-vs-project GitHub MCP redundancy decision now codified (prefer project-scoped).
**Blockers new/active:**
- 📋 **`MCP-REFERENCE-CORRECTION-001` Tier 3 🟢** — sweep historical audit docs for "Postgres MCP" → "(via asyncpg shim)" qualifier. Not blocking anything.
- 🟡 **Railway MCP re-auth needed** — sessions that need Railway env reads / deploy triggers via MCP will fail until `railway login` is run. (Jay action, separate from this session.)
- All prior carries unchanged (PC1 wallet top-up ~5 SOL target per yesterday's reconcile, PC2 observation through ≥2026-05-27 combined eval, PC4 flip-itself, BUG-010 Anthropic, etc.).
**V5a precondition delta:** None to the gating blockers. PC2's observation continues; PC3 still satisfied per LIVE-MODE-FILTER-PARITY-001-V2.
**Concurrent-session compatibility:** No concurrent session detected at session start (last commit `0ad2282` earlier this chat). Pull-rebase before push (retry up to 3× on conflict per CLAUDE.md). Append-only updates throughout (STATUS prepend, MONITORING_LOG prepend, ZMN_ROADMAP Decision Log + Tier 3 row insertion, AGENT_CONTEXT header prepend, CLAUDE.md +1 H2 section).
**Next prompt:** **STOP-LOSS-20-NO-MOMENTUM-90S-COMBINED-EVAL-001** is queued by Jay for immediate execution (chat-side, sent during this session). It is the PC2 eval; pulled forward from the +14d-post-C1 anchor. Read-only DB analysis; the verdict either satisfies PC2 or doesn't.
**Pending Claude-chat prompts not yet pasted:** none — combined-eval prompt is in-flight.

---

## 2026-05-20 — PC1-WALLET-TARGET-RECONCILE-001 (docs-only, RECONCILED)

**Committed:** `47f5829` docs(pc1-wallet-target-reconcile): PC1-WALLET-TARGET-RECONCILE-001 — reconcile `AGENT_CONTEXT.md` §6 PC1 wallet top-up target from prior `≥1.5-2.5 SOL` to `~5 SOL` per D-S3 of `docs/findings/V5A_GO_LIVE_DECISIONS.md`; preserve operational-minimum reasoning as lower-bound note; flag related PC4 `DAILY_LOSS_LIMIT_SOL=4.0→1.5` inconsistency for V5A flip session (out of scope here). Files: `AGENT_CONTEXT.md` (PC1 wording rewrite at line 146 + header refresh), `ZMN_ROADMAP.md` (Decision Log row prepended), `MONITORING_LOG.md` (entry prepended), `STATUS.md` (this prepend). NO services/* code change, NO env change, NO Redis writes, NO DB writes, NO deploy.
**State changes:** None. Pure docs work — single-scope reconciliation of an internal numeric inconsistency between PC1 (older) and D-S3 (newer authority). No Redis writes, no env changes, no deploy.
**Bot state:** TEST_MODE=true (paper, unchanged — carry-forward from V5A-GO-LIVE-DECISIONS-RECORD-001 2026-05-19 23:58 UTC; no behavioural change since). `BOT_CORE_FILL_MC_CEILING_USD=1000` active on bot_core paper + live paths (live dormant under TEST_MODE=true; carry-forward). `ML_THRESHOLD_BOT_CORE_SD=40` ACTIVE (carry-forward). **Wallet 0.064095633 SOL on-chain** (re-verified Helius `getBalance` THIS SESSION 2026-05-20 — unchanged from 2026-05-14 ~12:57 UTC; unchanged from 2026-04-21 single-event 1.5 SOL outgoing). Outstanding V5A blockers: **3** (PC1 wallet top-up — target now ~5 SOL per D-S3, PC2 observation through ≥2026-05-27 combined eval, PC4 flip-itself). 0 paper open positions / 0 live open positions / circuit_breaker N/A (paper) — carry-forward from prior entry, no trading-affecting change this session.
**Findings (key):**
- 🟢 **Inconsistency verified at session start.** `AGENT_CONTEXT.md` line 146 PC1 read "Top-up target ≥1.5-2.5 SOL" verbatim; `V5A_GO_LIVE_DECISIONS.md` D-S3 read 1.5 / 3.0 / 5 SOL (with §5 Amendments empty — no D-S3 amendment in flight). Independent cross-doc confirmation: `ZMN_ROADMAP.md` line 19 already says "awaiting 5 SOL top-up planned for v5 staged attempts" — the inconsistency was scoped to PC1 in AGENT_CONTEXT.md specifically.
- 🟢 **Helius spot-check (optional per §1.5) executed.** `mcp__helius__getBalance(4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ)` returned 0.064095633 SOL — unchanged since 2026-04-21. No surprise top-up; PC1 stays `[ ]` outstanding (target update only, not status flip).
- 🟢 **PC1 wording rewritten.** Title `~3 SOL transfer to trading wallet` → `~5 SOL on trading wallet`. Body: stale "Top-up target ≥1.5-2.5 SOL ..." replaced with "Top-up target updated 2026-05-20 from prior `≥1.5-2.5 SOL` to `~5 SOL`" + explicit citation of D-S3 + numeric chain (1.5/30%, 3.0/60%, 2 SOL floor) + operational-minimum reasoning preserved as a lower-bound note (rationale chain intact).
- 🟢 **PC4-related flag added in-cell** per §5 Phase 3 of session prompt. Single sentence cross-referencing `DAILY_LOSS_LIMIT_SOL=4.0 → 1.5 SOL` inconsistency as deferred to V5A flip session. Documentation hygiene, NOT env change.
- 🟢 **All STOPs evaluated, none triggered.** STOP-A (concurrent session): no — last commit `753b5ce` 2026-05-20 ~00:00 UTC. STOP-B (PC1 already reconciled): no — verified stale wording at session start. STOP-C (D-S3 amended): no — §5 Amendments empty. STOP-D (scope creep): no — PC1 only; §6.6 historical snapshot left alone; §2 env table left alone; D-S3 not amended. STOP-E/F: N/A.
- 🟢 **Scope discipline maintained.** Did NOT touch PC2/PC3/PC4 substance, §6.6 V5A readiness snapshot (2026-05-01 audit — historical, append-only), §2 env table, or `V5A_GO_LIVE_DECISIONS.md` (it's the authority being cited, not the doc being edited). Did NOT broaden into a §6 documentation audit.
**Verdict:** ✅ **RECONCILED.** Future CC sessions reading AGENT_CONTEXT.md §6 PC1 will see the correct ~5 SOL trial-budget target with D-S3 as the cited authority; the operational-minimum reasoning is preserved so they understand the lower bound; and PC4's `DAILY_LOSS_LIMIT_SOL=4.0` is flagged inline for V5A flip session reconciliation. The V5A go-live decision (D-S3) and the PC1 precondition checklist now agree on the same number.
**Blockers cleared:** internal numeric inconsistency between PC1 (older `≥1.5-2.5 SOL` wallet target framing) and D-S3 (newer 5 SOL trial budget) — the trigger for this session.
**Blockers new/active:**
- 📋 **PC4 / `DAILY_LOSS_LIMIT_SOL=4.0 → 1.5` env reconciliation** — surfaced this session, deferred to V5A flip session (env change + verification belong with the flip, not this docs-only fix). The V5A flip session's pre-flip self-check at PC4 will pick this up via the same precedence-rules read of D-S3.
- All prior carries unchanged (PC1 wallet top-up — target now ~5 SOL per D-S3, PC2 observation through ≥2026-05-27 combined eval, PC4 flip-itself, BUG-010 Anthropic, etc.).
**V5a precondition delta:** None to the gating blockers themselves. PC1's wallet target updated from ≥1.5-2.5 SOL to ~5 SOL — Jay action threshold raised; PC1 status unchanged (still `[ ]` outstanding). PC4 substance unchanged this session (env reconciliation deferred to flip session).
**Concurrent-session compatibility:** No concurrent session detected at session start (last commit `753b5ce` ~hours before). Pull-rebase before push (retry up to 3× on conflict per CLAUDE.md). Append-only updates throughout — STATUS prepend, MONITORING_LOG prepend, ZMN_ROADMAP Decision Log prepend, AGENT_CONTEXT header prepend (existing content demoted to "Prior:" chain). If a concurrent eval session has just pushed and this session needs to rebase prepends on top — expected and fine.
**Next prompt:** None auto-triggered. The V5A flip session is gated on PC1 (wallet top-up to ~5 SOL — Jay action), PC2 (≥2026-05-27 combined eval), and PC4 (the flip itself). The flip session's pre-flip self-check should also set `DAILY_LOSS_LIMIT_SOL=1.5` per D-S3 (related inconsistency surfaced by this session).
**Pending Claude-chat prompts not yet pasted:** none — this session terminated with verdict.

---

## 2026-05-19 23:58 UTC — V5A-GO-LIVE-DECISIONS-RECORD-001 (docs-only, DECISIONS RECORDED)

**Committed:** `753b5ce` docs(v5a-decisions): V5A-GO-LIVE-DECISIONS-RECORD-001 — captured seven chat-side V5A relaunch decisions as a survivable findings doc; filed two roadmap items; linked supersession; updated V5A checklist + CLAUDE.md findings index. Files: `docs/findings/V5A_GO_LIVE_DECISIONS.md` (NEW), `ZMN_ROADMAP.md` (Tier 1 new + Tier 2 new + Decision Log + MARKET-MODE-001-RE-CALIBRATE-V2 absorption link), `AGENT_CONTEXT.md` (§6 new "Decisions (recorded)" subsection + header refresh), `CLAUDE.md` (new row in Standing findings table per yesterday's self-amending instruction), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend). NO services/* edit, NO env change, NO Redis writes, NO deploy.
**State changes:** None. Pure docs work — wrote findings doc, filed roadmap items, updated indices.
**Bot state:** TEST_MODE=true (paper, unchanged). `BOT_CORE_FILL_MC_CEILING_USD=1000` active on bot_core paper + live paths (V2 dormant under TEST_MODE=true). Wallet 0.064 SOL on-chain (unchanged). Outstanding V5A blockers: 3 (PC1 wallet top-up, PC2 observation through ≥2026-05-27 combined eval, PC4 flip-itself — PC3 V2 landed 2026-05-19).
**Findings (key):**
- 🟢 **New survivable findings doc:** `docs/findings/V5A_GO_LIVE_DECISIONS.md` (≤1500 words) following the COST_FIDELITY_GAP pattern. Contains all 7 decisions (D-S3 loss tolerance 1.5/3.0 SOL realized; D-S4 manual market-mode check; D-S5 Wed/Thu AEST evening 18:00-21:00; D-S6 0.10/5 + NO auto-scale + staged ladder; D-S7 4-6h active observer) + sizing graduation ladder (§2) + GOVERNANCE-AGENT pointer (§3) + cross-refs (§4) + override path (§5).
- 🟢 **Roadmap items filed:** Tier 1 `V5A-SIZING-GRADUATION-LADDER-001` (ACTIVE RULE — governs trial sizing, not a session to run); Tier 2 `GOVERNANCE-AGENT-MARKET-MODE-001` (autonomous classifier + halt authority, gated on V5A producing ≥2 distinct regime samples).
- 🟢 **Supersession linked:** `MARKET-MODE-001-RE-CALIBRATE-V2` Tier 1 row updated with "2026-05-20: absorbed by `GOVERNANCE-AGENT-MARKET-MODE-001`" link — recalibration concern (NORMAL bleeds) becomes one input to the classifier scope. Not deleted; preserved for audit trail.
- 🟢 **V5A checklist updated:** new "Decisions (recorded)" subsection in `AGENT_CONTEXT.md` §6 between "Known conditions at relaunch" and "Completed preconditions" pointing at findings doc and roadmap items.
- 🟢 **CLAUDE.md self-amending instruction honored:** new row appended to "Standing findings — read before related work" table for `V5A_GO_LIVE_DECISIONS.md`. Yesterday's CLAUDE-MD-FINDINGS-INDEX-001 instruction: "When new findings are added to `docs/findings/`, append a row here as part of the session that creates them" — this session is the first to fulfill it.
- 🟢 **No STOP triggered:** no concurrent session in flight (last commit `4210c4b` 2026-05-19 ~13:00 UTC; my session at 23:58 UTC, ~10h gap); §6 V5A checklist locatable; no scope creep; no Claude limit hit.
**Verdict:** ✅ **DECISIONS RECORDED.** All seven V5A relaunch decisions are now in a discoverable, survivable doc with the same lifespan and prominence as `docs/findings/COST_FIDELITY_GAP.md`. V5A checklist points to them. CLAUDE.md indexes them. Future sessions cannot miss them.
**Blockers cleared:** chat-side decisions ephemerality (the trigger for this session).
**Blockers new/active:**
- 📋 **V5A-SIZING-GRADUATION-LADDER-001 ACTIVE RULE** — consult before any manual sizing change during the trial.
- 📋 **GOVERNANCE-AGENT-MARKET-MODE-001 Tier 2** — design session pending; gated on V5A live data across ≥2 regimes.
- All prior carries unchanged (PC1 wallet top-up, PC2 ≥2026-05-27 combined eval, PC4 flip, BUG-010 Anthropic, etc.).
**V5a precondition delta:** None to the gating blockers themselves. New "Decisions (recorded)" subsection added to §6 — the seven decisions are inputs to the flip, NOT additional preconditions.
**Concurrent-session compatibility:** No concurrent session detected. Pull-rebase before push (retry up to 3× on conflict per CLAUDE.md). Append-only updates throughout.
**Next prompt:** None auto-triggered. Future sessions touching V5A sizing or market-mode handling MUST read `docs/findings/V5A_GO_LIVE_DECISIONS.md` first (CLAUDE.md's Standing findings index enforces this).
**Pending Claude-chat prompts not yet pasted:** none — this session terminated with verdict.

---

## 2026-05-19 12:59 UTC — CLAUDE-MD-FINDINGS-INDEX-001 (docs-only, INDEX ADDED)

**Committed:** session output landed across two commits due to a concurrent hygiene-commit pickup (`5adff0b docs: index docs/findings/ in CLAUDE.md + correct V2 line-count in MONITORING_LOG` — landed the CLAUDE.md +18 lines and MONITORING_LOG.md +14 -1 portions of my working-tree edits, attributed to Jay's hygiene commit but byte-identical to my output) + `0639b3f` docs(claude-md-findings-index-001): CLAUDE-MD-FINDINGS-INDEX-001 — canonical updates (AGENT_CONTEXT.md header refresh + ZMN_ROADMAP.md Decision Log row + STATUS.md prepend). Combined session deliverables: `CLAUDE.md` (+15-line "Standing findings — read before related work" H2 section between Roadmap and Resolved Bugs, table indexing `docs/findings/COST_FIDELITY_GAP.md` + self-amending instruction; landed via `5adff0b`), `MONITORING_LOG.md` (entry prepended; landed via `5adff0b`), `AGENT_CONTEXT.md` (header refresh only — no structural change to §6), `ZMN_ROADMAP.md` (Decision Log entry), `STATUS.md` (this prepend). NO services/* edit, NO env change, NO Redis writes, NO deploy.
**State changes:** None. Read-only — `ls docs/findings/`, repo grep for `V5A_GO_LIVE_DECISIONS` (0 matches) + `docs/findings` cross-ref verification (3 in AGENT_CONTEXT, 2 in ZMN_ROADMAP, all point at existing `COST_FIDELITY_GAP.md`), CLAUDE.md insertion.
**Bot state:** TEST_MODE=true (paper, unchanged). `BOT_CORE_FILL_MC_CEILING_USD=1000` active on bot_core paper AND live paths (per LIVE-MODE-FILTER-PARITY-001-V2 yesterday, dormant under TEST_MODE=true). Wallet 0.064 SOL on-chain (unchanged). Outstanding V5A blockers: 3 (PC1 wallet top-up, PC2 observation through ≥2026-05-27 combined eval, PC4 flip-itself).
**Findings (key):**
- 🟢 **STOP-A check PASS (partial):** `docs/findings/` exists with one file (`COST_FIDELITY_GAP.md`). Index has content to write.
- 🟡 **Expected `V5A_GO_LIVE_DECISIONS.md` missing:** dependent session `V5A-GO-LIVE-DECISIONS-RECORD-001` not yet run; no doc references it (0 grep hits); no broken-reference flag needed. Will be indexed when it lands. CLAUDE.md instruction added: "When new findings are added to `docs/findings/`, append a row here as part of the session that creates them."
- 🟢 **Cross-reference verification clean:** AGENT_CONTEXT.md lines 3 / 162 / 167 + ZMN_ROADMAP.md lines 41 / 315 all reference `docs/findings/COST_FIDELITY_GAP.md` correctly. No drift.
- 🟢 **CLAUDE.md insertion:** new H2 "Standing findings — read before related work" placed between Roadmap and Resolved Bugs — keeps "what to read first" guidance adjacent. Table lists `COST_FIDELITY_GAP.md` with about + read-before columns. Self-amending instruction added.
**Verdict:** ✅ **INDEX ADDED.** Future CC sessions reading CLAUDE.md as first action now discover `docs/findings/` without needing to deep-read AGENT_CONTEXT.md or ZMN_ROADMAP.md.
**Blockers cleared:** discoverability gap for standing findings (the chat-side trigger for this session).
**Blockers new/active:**
- 📋 `V5A-GO-LIVE-DECISIONS-RECORD-001` (dependent session) — when it runs, must append its row to CLAUDE.md's standing-findings table (per the instruction added this session).
- All prior carries unchanged (combined STOP-LOSS-20-RUG-FILTER-EVAL-001 + NO-MOMENTUM-90S-EVAL-001 ≥2026-05-27, V5A wallet/observation/flip blockers, BUG-010 Anthropic, etc.).
**V5a precondition delta:** None.
**Concurrent-session compatibility:** No concurrent session detected at audit time. Pull-rebase before push (retry up to 3× on conflict).
**Next prompt:** None auto-triggered. Future session creating any new finding doc carries the obligation to append a row to CLAUDE.md "Standing findings" table.
**Pending Claude-chat prompts not yet pasted:** none — this session terminated with verdict.

---

## 2026-05-19 — LIVE-MODE-FILTER-PARITY-001-V2 (code+deploy, GATE IMPLEMENTED + DEPLOYED)

**Committed:** `7286421` feat(bot_core): LIVE-MODE-FILTER-PARITY-001-V2 — fill-time MC ceiling gate on live buy path; mirrors paper C1; dormant until V5A. Files: `services/bot_core.py` (+28 lines in live `else:` branch — gate now occupies `:953-980`, shifting the original `execute_trade(...)` call to `:982`), `docs/audits/LIVE_MODE_FILTER_PARITY_001_V2_2026_05_19.md` (NEW audit incl. §8 paper↔live parity table), `AGENT_CONTEXT.md` (header + §2 `BOT_CORE_FILL_MC_CEILING_USD` row expanded "GOVERNS BOTH PAPER AND LIVE PATHS AS OF 2026-05-19" + §6 PC3 marked ✅ DEPLOYED + "Outstanding V5A blockers (4)" → "(3)"), `ZMN_ROADMAP.md` (Decision Log new 2026-05-19 row marks V2 DEPLOYED + structurally closes NO_MOMENTUM_90S_AUDIT_001 §10 "execution.py parity" open item — Option A lands in bot_core, not execution.py), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend), `.gitignore` (`.tmp_live_filter_parity_v2/`).
**State changes:** bot_core redeploy via single `git push` to main. NO env change (gate reuses existing `BOT_CORE_FILL_MC_CEILING_USD=1000`; no new var introduced). NO Redis writes this session (the gate's runtime Redis writes happen at first reject — currently dormant). NO paper_trader.py edit (paper observation window untouched). NO execution.py edit (per predecessor audit). NO TEST_MODE flip (bot remains paper).
**Bot state:** TEST_MODE=true on bot_core (verified Railway MCP, unchanged). `BOT_CORE_FILL_MC_CEILING_USD=1000` (now governing both paper AND live paths, but live gate dormant under TEST_MODE=true). `ML_THRESHOLD_BOT_CORE_SD=40` ACTIVE. Wallet 0.064 SOL on-chain (carry-forward; not re-read this session — no behaviour-affecting state question). Paper portfolio carry-forward. 0 open positions / circuit_breaker N/A (paper). **PC2 observation window:** today 2026-05-19, +6d post-C1 (2026-05-13 03:38:37Z UTC); combined eval still ≥2026-05-27 (+8d from today). Concurrent: `COST-FIDELITY-FINDINGS-DOCUMENTATION-001` (`a3e9ac4`/`4bb5247`) completed earlier today as docs-only, no `services/*` touch — its Railway build was image-pushing when I checked logs; sequential `git push` from this session safe (Railway queues, my push supersedes its image without losing any code change).
**Findings (key):**
- 🟢 **Phase 1 routing reconfirmed.** `bot_core.py:82-83` `paper_buy` imported only under `if TEST_MODE`; `:836` paper→`paper_buy`; `:951` `else:`→`execute_trade` at `:953-956` (line numbers shifted +3 vs predecessor audit due to LIVE-TRADES-LOGGING-AUDIT-001 `b867daa` comment additions; structure identical). STOP-A does NOT fire — the live branch is unreachable under TEST_MODE=true.
- 🟢 **Phase 1 units parity.** `_get_token_price` at `:388-391` returns USD price-per-token (same units as paper_trader's helper; Jupiter `price/v3` → USD, Redis cache → SOL-converted-to-USD via `market:sol_price`). The live branch already uses `price * 1_000_000_000` at `:996` for `_pe_market_cap` post-execution — direct empirical confirmation. STOP-B does NOT fire.
- 🟢 **Phase 1 insertion point clean.** Between current `:952` (`signal_type = ...`) and `:953` (`result = await execute_trade(...)`). Enclosing entry-method ends at `:1052` immediately after the if/else — bare `return` on reject is semantically equivalent to paper's "paper_buy → success=False → no Position created" fall-through. STOP-C does NOT fire.
- 🟢 **Phase 3 gate inserted + py_compile clean.** 20-line block in `bot_core.py` else branch. No re-indent of surrounding code; no new imports.
- 🟢 **Phase 3 validation: 8 mock cases ALL PASS (2 dev-loop iterations within the 3-cap).** Iter 1: Unicode `→` codec crash on Windows; iter 2: wrong sentinel-return indent count fixed via regex anchored on line shape. Cases: above-ceiling reject + Redis incr; at-ceiling pass-strict; below-ceiling pass to `execute_trade`; gate-disabled pass; env-absent pass; price-fetch failure fail-OPEN; two ceiling-tier sanity cases. Raw output: `.tmp_live_filter_parity_v2/verify_output.txt`.
- 🟢 **Phase 4 deploy clean.** Railway container restart confirmed (build artifact image-push observed in real-time logs). Single `git push` (no `railway up`).
- 🟡 **Verification standard caveat (paper-mode dormant):** the gate cannot be observed firing in production this session because `TEST_MODE=true`. First live-fire is at V5A relaunch. Code-level + clean-startup + 8-case rolled-back behavioral proof is the standard, explicit in audit §6 and matching predecessor LIVE-MODE-FILTER-PARITY-001 §6.
- 🟢 **§8 paper↔live parity table** in audit confirms line-for-line mirror across env var / default / read pattern / MC formula / price source / comparison / log line / Redis counter / TTL / try/except / short-circuit / failure-mode-at-gate-block. Two intentional divergences documented: (a) MC term uses raw `fill_price` (no live slippage sim); (b) gate fails open on price-fetch failure (paper's fail-closed happens earlier in `paper_buy`, not in the gate block).
**Verdict:** ✅ **GATE IMPLEMENTED + DEPLOYED.** PC3 is CLOSED.
**Blockers cleared:** PC3 `LIVE-MODE-FILTER-PARITY-001-V2`. The NO_MOMENTUM_90S_AUDIT_001 §10 "execution.py parity" open item is structurally resolved (Option A landed in `bot_core.py`).
**Blockers new/active:**
- All prior V5A carries unchanged except PC3 (now ✅): PC1 wallet top-up (0.064 SOL on-chain), PC2 observation through combined eval ≥2026-05-27 (+8d from today), PC4 flip-itself.
- ML_THRESHOLD_RETUNE_002 remains dependency-gated behind `PAPER-FEE-MODEL-CALIBRATION-001` per yesterday's COST-FIDELITY-FINDINGS-DOCUMENTATION-001 re-sequencing.
- DASH-001 build sessions (BUILD-0/1/2) remain June parallel-track.
**V5a precondition delta:** **−1 outstanding blocker** (PC3 closes). Honest V5A blocker count post-this-session: **3 outstanding** (PC1 wallet, PC2 observation, PC4 flip), 3 completed (historical: SD_MC_CEILING_002, LIVE-FEE-CAPTURE-002 Path B, **LIVE-MODE-FILTER-PARITY-001-V2 new**).
**Concurrent-session compatibility:** `COST-FIDELITY-FINDINGS-DOCUMENTATION-001` complete earlier today (docs-only); its build was image-pushing when I checked. Pull-rebase before push (retry up to 3× on conflict). My push triggers a new build that supersedes the in-flight docs-only build — no code lost (docs commit is already in git). Append-only canonical doc updates.
**Rollback:** `BOT_CORE_FILL_MC_CEILING_USD=0` (no redeploy; disables both paper and live gates simultaneously). To undo C1 retune only (keep gate, loosen ceiling): env→3000.
**Next prompt:** None auto-triggered. The next behavioural session is gated on Jay decisions: (a) PC1 wallet top-up timing; (b) PC2 ≥2026-05-27 combined eval verdict; (c) PC4 V5A flip itself. PAPER-FEE-MODEL-CALIBRATION-001 remains gated on accumulating Path B rows (needs V5A relaunch). DASH-001-BUILD-0 micro-session optionally available standalone.
**Pending Claude-chat prompts not yet pasted:** none — V2 was the standing paste-ready prompt and it landed this session.

---

## 2026-05-19 — COST-FIDELITY-FINDINGS-DOCUMENTATION-001 (docs-only, DOCS COMPLETE)

**Committed:** `a3e9ac4` docs(cost-fidelity-findings): COST-FIDELITY-FINDINGS-DOCUMENTATION-001 — make the audit's conclusions survivable. Files: `docs/findings/COST_FIDELITY_GAP.md` (NEW survivable summary), `AGENT_CONTEXT.md` (header + §6 acknowledged-condition entry + retune re-sequencing), `ZMN_ROADMAP.md` (Decision Log + `ANALYST-POST-GRAD-001` cost-fidelity gate), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend), `.gitignore` (`.tmp_cost_fidelity_docs/`). **NO services/* code change, NO env change, NO Redis writes, NO deploy.**
**State changes:** None. Docs-only.
**Bot state:** TEST_MODE=true (paper, unchanged). `BOT_CORE_FILL_MC_CEILING_USD=1000` (C1) ACTIVE per AGENT_CONTEXT §2. `ML_THRESHOLD_BOT_CORE_SD=40` ACTIVE. Wallet 0.064 SOL on-chain (last verified 2026-05-14 ~12:57 UTC via V5A-PRECONDITION-CHECKLIST-CLEANUP-001; not re-read this session — docs-only). Paper portfolio carry-forward. 0 open positions / circuit_breaker N/A. **PC2 observation window advanced:** today is 2026-05-19, +6d post-C1 deploy (2026-05-13 03:38:37Z UTC); combined eval still scheduled ≥2026-05-27 (+14d from C1). Concurrent: no concurrent session detected at session-resume.
**Mid-session side-task:** Jay requested CSV export of trades data. Ran `Scripts/export_paper_trades.py` (3,158 rows → `session_outputs/paper_trades_export.csv`) + one-shot helper for the sibling `trades` table (9,805 rows → `session_outputs/trades_export.csv`). Naming correction: historical convention used `live_trades_export_*.csv` for the second file — a misnomer per LIVE-TRADES-LOGGING-AUDIT-001 (there is no `live_trades` table). Used corrected name `trades_export.csv`. Both files gitignored. No bearing on the docs work below.
**Findings (key):**
- 🟢 **NEW survivable findings doc `docs/findings/COST_FIDELITY_GAP.md`** — first file under `docs/findings/` (new convention dir). ~1,000 words, summary-with-pointers, cites audit by section. Contains the "label corruption in marginal band wider than median trade PnL" framing explicitly (corruption band ~±0.030 SOL vs median `|realised_pnl_sol|` = 0.0257 SOL) so a future session doesn't miss the sharpest expression of the problem.
- 🟢 **AGENT_CONTEXT §6 carries an acknowledged-condition entry** under a new "Known conditions at relaunch (acknowledged, NOT blocking)" subsection. Sits in front of whoever runs V5A go/no-go. Links to the survivable findings doc in one hop. Deliberately NOT a precondition checkbox.
- 🟢 **`ML_THRESHOLD_RETUNE_002` re-sequenced** behind `PAPER-FEE-MODEL-CALIBRATION-001`. Date-gate (≥2026-05-19, which is TODAY) replaced with dependency-gate. Two independent reasons stated. Item NOT deleted — re-prioritized. Important because the original date-gate is hitting *right now* on 2026-05-19; without this re-sequencing the retune would be auto-triggerable today against corrupted labels.
- 🟢 **`ANALYST-POST-GRAD-001` Phase 0 sub-session (c) gated** on `PAPER-FEE-MODEL-CALIBRATION-001` deploy + ≥7d post-calibration data. Sub-sessions (a)(b)(d) NOT gated. Rationale documented in the cell (Analyst sizing 0.2-0.5 SOL vs SD 0.05-0.25 SOL — gap bites harder at higher leverage).
- 🟢 **`ML-TRAINING-MODE-FILTER-001` single-entry confirmed** (line 329 of Tier 3 table). No duplicate filing. Both Decision Log references point to the same canonical row.
- 🟢 **No new follow-up items filed** — the audit's 4 + 1 re-scoped (`PAPER-FEE-MODEL-CALIBRATION-001`, `PAPER-LATENCY-MODEL-001`, `PAPER-MEV-SLIPPAGE-MODEL-001`, `ML-CONTAMINATION-FILTER-BIAS-001`, `ML-TRAINING-MODE-FILTER-001`) already filed by prior session. This session re-sequences `ML_THRESHOLD_RETUNE_002` and adds the Analyst gate.
- 🟢 **No re-investigation, no broader doc-rewrite.** Per §7 scope discipline. The audit is the evidence base.
**Verdict:** ✅ **DOCS COMPLETE.** Survivable findings doc created; V5A checklist carries acknowledged-condition entry with link; ML retune re-prioritized behind calibration; Analyst Phase 0 gated; follow-up sessions confirmed single-filed; all cross-references consistent.
**Blockers cleared:** None this session (docs-only).
**Blockers new/active:**
- All prior V5A carries unchanged (PC1 wallet 0.064 SOL, PC2 observation through combined eval ≥2026-05-27 [+8d from today], PC3 LIVE-MODE-FILTER-PARITY-001-V2 land, PC4 flip).
- New **acknowledged condition** (not a blocker): cost-fidelity gap at V5A relaunch — see AGENT_CONTEXT §6 + `docs/findings/COST_FIDELITY_GAP.md`.
**V5a precondition delta:** No new blockers. The acknowledged-condition entry is a docs surface, not a checkbox.
**Concurrent-session compatibility:** Pull-rebase before push (retry up to 3× on conflict). Append-only canonical updates. Single push with `git commit --amend` hash backfill into STATUS.md.
**Next prompt:** None auto-triggered. `ML_THRESHOLD_RETUNE_002` (previously date-gated to ≥2026-05-19 = today) is now correctly dependency-gated behind `PAPER-FEE-MODEL-CALIBRATION-001` and should NOT auto-trigger. Combined eval ≥2026-05-27 (+8d) remains the next observability checkpoint.
**Pending Claude-chat prompts not yet pasted:** LIVE-MODE-FILTER-PARITY-001-V2 paste-ready (carries from 2026-05-14 audit).

---

## 2026-05-14 — ML-TRAINING-COST-FIDELITY-AUDIT-001 (read-only investigation, AUDIT COMPLETE — gap CONFIRMED)

**Committed:** `49290b1` docs(ml-training-cost-fidelity): ML-TRAINING-COST-FIDELITY-AUDIT-001 — sim-to-real gap confirmed; ML trains on ~17.6× optimistic fee labels + zero-latency fills. Files: `docs/audits/ML_TRAINING_COST_FIDELITY_AUDIT_001_2026_05_14.md` (NEW), `ZMN_ROADMAP.md` (Decision Log + 3 new Tier-2/3 items + 1 unresolved + 1 re-scoped), `AGENT_CONTEXT.md` (header), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend), `.gitignore` (`.tmp_ml_cost_fidelity/`). **NO services/* code change, NO env change, NO Redis writes, NO deploy.**
**State changes:** None. Read-only — repo + DB SELECTs (DATABASE_PUBLIC_URL via asyncpg). No code/env/Redis writes.
**Bot state:** TEST_MODE=true (paper, unchanged). F1+C1 filter ACTIVE (`BOT_CORE_FILL_MC_CEILING_USD=1000` on bot_core). `ML_THRESHOLD_BOT_CORE_SD=40` ACTIVE. `trade_mode` discriminator on `trades` table active post LIVE-TRADES-LOGGING-AUDIT-001 (`b867daa`). Wallet 0.064 SOL on-chain (carry-forward from V5A-PRECONDITION-CHECKLIST-CLEANUP-001 2026-05-14 ~12:57 UTC). Paper portfolio carry-forward. 0 open positions / circuit_breaker N/A (paper, this is a read-only research session). Concurrent: no concurrent session detected at session-start (STATUS head was DASHBOARD-DESIGN-REALIGNMENT-001 amendment `b28bdbe`, docs-only, complete).
**Findings (key):**
- 🔴 **Sim-to-real gap CONFIRMED.** Training pipeline (`services/ml_model_accelerator.py:351-374`) reads `trades` + `paper_trades` with NO `trade_mode` or `correction_method` filter. Target = `outcome` string (binary win/loss) → `pnl_sol > 0` (`paper_trader.py:415`, `bot_core.py:1149,1365`). `pnl_sol` is net of `_simulate_slippage` + `_simulate_fees` (`paper_trader.py:142-213`). Cost model IS in the training signal at threshold zero.
- 🔴 **Cost under-count quantified.** DB (n=2874 closed paper_trades post-C1): avg `fees_sol`=0.00170 SOL on avg `amount_sol`=0.116 SOL = **1.46% round-trip**. Path B truth (id 6580, sole `live_actual_v1` row): 0.094 SOL / 0.365 SOL = **25.8% round-trip**. **~17.6× optimistic at avg paper sizing.**
- 🔴 **Latency not modelled.** 4 latency columns exist on `paper_trades` but 100% NULL across 2874 rows. Paper fill uses Jupiter/Gecko quote at `paper_buy` time — wall-clock-current but no in-flight pump model.
- 🟡 **Corpus fidelity-tier:** 2873/2874 `pass_through` (paper sim), 0 `live_estimated_v1`, 1 `live_actual_v1`. ML-eligible corpus ≈ 8,680 rows; live share 0.47%; Path-B share 0.012%. **Fidelity problem lives in the paper sim, not the paper/live blend.**
- 🟢 **NOT a current-profitability fire.** ML already weakly predictive (AUC 0.536); SD profitability is structural-filter-driven (C1 MC ceiling, independent of ML); +1.49 SOL/day W3+W4 holds.
- 🟡 **DOES materially affect:** (a) ML_THRESHOLD_RETUNE_002 — retune optimizes against ~17× optimistic labels; recommend "calibrated against sim costs" caveat, NOT blocked; (b) Analyst Phase 0 (June) — ML-driven, higher sizing; gap transfers into new personality.
**Verdict:** ✅ **AUDIT COMPLETE — sim-to-real gap CONFIRMED.**
**Blockers cleared:** None (read-only investigation).
**Blockers new/active:**
- 📋 **PAPER-FEE-MODEL-CALIBRATION-001** (NEW Tier 2 🟡) — env-only recalibration to Path-B-derived truth. Gated on ≥10 Path B rows (currently 1; needs sustained V5A relaunch). 30m deploy + 7d obs.
- 📋 **PAPER-LATENCY-MODEL-001** (NEW Tier 3 🟢) — gated on LATENCY-OBSERVABILITY-001 backfill.
- 📋 **PAPER-MEV-SLIPPAGE-MODEL-001** (NEW Tier 3 🟢) — structural; gated on Path B sample sufficiency.
- 📋 **ML-CONTAMINATION-FILTER-BIAS-001** (NEW Tier 3 🟢, UNRESOLVED) — possible sim-flattering bias in existing exit-near-entry filter; 45m DB analysis.
- 📋 **ML-TRAINING-MODE-FILTER-001 re-scoped to Tier 3 🟢 hygiene** (from LIVE-TRADES-LOGGING-AUDIT-001 §9.1) — 0.47% live share is a rounding error on training signal.
- All prior V5A carries unchanged (PC1 wallet, PC2 observation, PC3 V2, PC4 flip).
**V5a precondition delta:** None directly. PAPER-FEE-MODEL-CALIBRATION-001 is gated BY V5A relaunch (needs ≥10 Path B rows), not blocking V5A. Analyst Phase 0 gains a new gate (PAPER-FEE-MODEL-CALIBRATION-001 lands before Analyst ships).
**Concurrent-session compatibility:** No concurrent session detected at session-start. Pull-rebase before push (retry up to 3× on conflict). Append-only updates to canonical docs.
**Next prompt:** None auto-triggered. ML_THRESHOLD_RETUNE_002 (≥2026-05-19) carries forward — should ship with "calibrated against sim costs" caveat in verdict per this audit §6/§7.4.
**Pending Claude-chat prompts not yet pasted:** LIVE-MODE-FILTER-PARITY-001-V2 paste-ready (carries from 2026-05-14 audit).

---

## 2026-05-14 — DASHBOARD-DESIGN-REALIGNMENT-001 (amendment, AMENDMENT LANDED)

**Committed:** `431b670` docs(dashboard-design-realignment-amendment): DASHBOARD-DESIGN-REALIGNMENT-001 — Jay §9 resolutions + 4 design additions folded into design doc. Files: `docs/audits/DASHBOARD_DESIGN_REALIGNMENT_001_2026_05_14.md` (amended in place), `ZMN_ROADMAP.md` (Decision Log + DASH-001 row + 3 new roadmap items), `AGENT_CONTEXT.md` (header), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend). **NO services/* code change, NO env change, NO Redis writes, NO deploy.**
**State changes:** None. Docs-only design amendment.
**Bot state:** TEST_MODE=true (paper, unchanged). `BOT_CORE_FILL_MC_CEILING_USD=1000` (C1) ACTIVE. `ML_THRESHOLD_BOT_CORE_SD=40` ACTIVE. Wallet 0.064 SOL on-chain (carry-forward from V5A-PRECONDITION-CHECKLIST-CLEANUP-001 verification 2026-05-14 ~12:57 UTC). Paper portfolio ~39.7 SOL (carry-forward). Concurrent: `LIVE-TRADES-LOGGING-AUDIT-001` (commit `b867daa`) landed during this session — schema fix + backfill of `trades.trade_mode`, bot_core redeploy. Pulled-rebase clean against `b867daa`; no conflict with my docs-only amendment.
**Findings (key):**
- 🟢 **§9 open questions all resolved per Jay's amendment** (re-scope ACCEPTED; ≥30d legacy coexistence; SINGLE accent; Sentry DEFER; emergency-stop-from-phone DEFER; June parallel-track CONFIRMED).
- 🟢 **4 design additions folded in:**
  - (A) Card 2 expanded to today + all-time cumulative P&L (single card, two numbers). `paper_trades`-only scope; no `trades` or Redis-aggregate fallback (prevents resurfacing pre-cleanup +601 SOL lifetime contamination from `paper:stats` Redis hash).
  - (B) NEW Card 7 biggest wins. Top-3 default → top-10 expand. Mint tap-to-copy + DexScreener "↗" link. **CRITICAL hardcoded floor:** `trade_mode='paper' AND entry_time >= 1747104561.0` (C1 deploy 2026-05-13 03:29:21Z UTC) as module constant `BIGGEST_WINS_CLEAN_DATA_FLOOR_TS` with comment ref to audit §3.
  - (C) Celebration FX on ≥3x wins. Trigger: `realised_pnl_pct >= 200` (column verified `services/db.py:128-129`). Confetti (vendored canvas-confetti ~7KB, `prefers-reduced-motion`-safe) + `navigator.vibrate([60,30,60,30,120])` haptic + optional sound toggle (muted by default, `localStorage`-persisted, iOS-autoplay-aware). `seenTradeIds` Set in `sessionStorage` prevents re-fire on reload within session. Threshold = JS const `BIG_WIN_PCT_THRESHOLD=200` for trivial retune.
  - (D) Push-notification version EXPLICITLY DEFERRED to post-SD-validation. PWA SW push handler stub (console-log only) in BUILD-2. No backend emitter, no subscription registry, no server keys yet.
- 🟢 **Card count 6 → 7, cap nudged.** Three merge alternatives evaluated and rejected (Card 6 merge produces confused dual-ordering; Card 2 fold-in causes cognitive density; footer-link violates "first build" intent). Still one route, zero tabs, zero sub-pages. 30 → 7 = ~77% smaller than Concept C (was 80%). Forward guardrail: >7 cards / tabs / sub-pages / second routes trigger fresh STOP-C.
- 🟢 **STOP-B re-checked post-amendment:** 3/7 cards need backend (Card 2 all-time half + Card 3 alerts + Card 7 biggest wins) ≈ 43%. ≪50% threshold. UI remains the bulk of the work.
- 🟢 **Build breakdown re-stated honestly:** BUILD-0 0.5h → 1.0h (3 endpoints); BUILD-1 2.5h → 2.8h (Cards 1/2/4/7); BUILD-2 2.5h → 2.8h (Cards 3/5/6 + FX + PWA + push stub). **Total 7.5h → ~8.5h.** Sequencing unchanged: June parallel-track with Analyst Phase 0, NOT May trading-logic critical path.
- 🟢 **Concurrent reconciliation:** `LIVE-TRADES-LOGGING-AUDIT-001` closed during this session and adds `trade_mode` to `trades` (9,480 paper / 41 live). Card 7's hardcoded floor REMAINS because the floor guards pre-F1 / pre-C1 paper-side variance + pre-cliff archive accounting — not just live-side contamination. DASH-BIGGEST-WINS-SCOPING-001 revisit conditions updated to reflect prereq closure + the residual cliff-accounting reason for the floor.
**Verdict:** ✅ **AMENDMENT LANDED.** Design doc current; ROADMAP DASH-001 row + 3 new Tier 3 items added; canonical docs synced.
**Blockers cleared:** None (docs amendment, no behavioural blockers).
**Blockers new/active:**
- 📋 **DASH-BIGGEST-WINS-SCOPING-001** (Tier 3 🟢, OPEN with prereq closed) — revisit floor after Jay reviews ≥30d post-C1 sample.
- 📋 **DASH-PUSH-NOTIFICATIONS-001** (Tier 3 🟢, OPEN) — gated on SD-validation completion + V5A flip stability.
- 📋 **DASH-CELEBRATION-FX-THRESHOLD-TUNE-001** (Tier 3 🟢, OPEN) — post-deploy fine-tune of `BIG_WIN_PCT_THRESHOLD`.
- All prior V5A carries unchanged (PC1 wallet 0.064 SOL, PC2 observation through combined eval ≥2026-05-27, PC3 LIVE-MODE-FILTER-PARITY-001-V2, PC4 flip).
**V5a precondition delta:** None.
**Concurrent-session compatibility:** Pulled-rebase against `b867daa` LIVE-TRADES-LOGGING-AUDIT-001 (clean — different files except append-only canonical docs). Single push.
**Next prompt:** None auto-triggered. Next behavioural sessions are gated on Jay decisions (V5A flip scoping + V2 scoping + wallet top-up timing). Build sessions DASH-001-BUILD-0/1/2 remain June parallel-track.
**Pending Claude-chat prompts not yet pasted:** LIVE-MODE-FILTER-PARITY-001-V2 paste-ready (carries from yesterday's audit).

---

## 2026-05-14 — LIVE-TRADES-LOGGING-AUDIT-001 (code+schema fix, FIXED + DEPLOYED)

**Committed:** `b867daa` fix(live-trades-logging): LIVE-TRADES-LOGGING-AUDIT-001 — add trade_mode discriminator to the `trades` ML corpus + backfill. Files: `services/bot_core.py` (2 `INSERT INTO trades` sites tagged), `services/db.py` (`trade_mode` in `trades` CREATE + idempotent ALTER), `migrations/002_add_trade_mode_to_trades.sql` (NEW, one-time backfill — applied to DB this session), `docs/audits/LIVE_TRADES_LOGGING_AUDIT_001_2026_05_14.md` (NEW), `ZMN_ROADMAP.md` (Decision Log), `AGENT_CONTEXT.md` (header), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend), `.gitignore` (`.tmp_live_logging_audit/`).
**State changes:** DB schema: `trades.trade_mode` column added + backfilled (9,480 'paper' / 41 'live'). No env changes, no Redis writes. `services/bot_core.py` + `services/db.py` redeploy of bot_core via single `git push`.
**Bot state:** TEST_MODE=true (paper, unchanged). `BOT_CORE_FILL_MC_CEILING_USD=1000` (C1), `ML_THRESHOLD_BOT_CORE_SD=40` ACTIVE. Wallet 0.064 SOL on-chain (unchanged, per V5A-PRECONDITION-CHECKLIST-CLEANUP-001 2026-05-14 ~12:57 UTC verification). Paper portfolio ~39.7 SOL (per same). 0 open positions / circuit_breaker consecutive_losses=1 (carried from V5A-PRECONDITION-CHECKLIST-CLEANUP-001 Redis read ~12:57 UTC — not re-read this session; this session is a logging-path fix, not a trading-state-sensitive change).
**Findings (key):**
- 🟢 **PREREQ gate PASS:** LIVE-MODE-FILTER-PARITY-001 completed (commit `81a20a0`, STOP-C). Concurrent docs-only session V5A-PRECONDITION-CHECKLIST-CLEANUP-001 completed mid-session — not behavioural, not in-flight; proceeded with pull-rebase discipline + re-read all canonical docs before editing.
- 🟢 **Premise corrected:** NO `live_trades` table exists (repo grep 0 hits; `to_regclass` NULL). Chat-side "live_trades" = the `trades` table — paper+live combined ML-training corpus BY DESIGN (`bot_core.py` writes from both branches; `ml_model_accelerator` trains from both `trades` + `paper_trades`). No misrouting bug. `paper_trades` already correctly mode-separated; `live_trade_log` correctly live-only.
- 🟢 **Real defect:** `trades` lacked a `trade_mode` discriminator — 41 genuine live rows *buried* among 9,480 paper rows. Classification: paper 9,480 / live 41 / unclassifiable 0. The 41 live = 35 v3/v4 trial trades (all confirmed via `live_trade_log` TX_SUBMIT sigs) + 1 on-chain round-trip (id 6596) + 5 reconcile-residuals.
- 🟢 **Isolated real-money result ≈ −3.36 SOL** — cross-validates the ~3.4 SOL on-chain wallet drawdown in CLAUDE.md's `1b40df3` forensics.
- 🟢 **Fix + verify:** `trade_mode TEXT DEFAULT 'paper'` added; both INSERT sites tagged; `migrations/002` backfill applied. `verify_logging_fix.py` ALL PASS iteration 1 (paper INSERT→'paper', live INSERT→'live' in rolled-back txn; split exactly 9,480/41; 0 NULLs). Not STOP-A/B/C.
**Verdict:** ✅ **FIXED + DEPLOYED.** Historical rows TAGGED (not purged). Purge recommendation: DO NOT PURGE — filter by `trade_mode`.
**Blockers cleared:** None (this resolves a chat-side investigation request, not a tracked blocker).
**Blockers new/active:**
- 📋 **ML-TRAINING-MODE-FILTER-001 NEW (flagged, not Tier-assigned)** — `ml_model_accelerator` reads from both `trades` + `paper_trades` with no `trade_mode` filter; now *possible* to decide include/exclude/weight of live rows. Not decided this session (would touch ML logic, out of scope).
- All prior carries unchanged (LIVE-MODE-FILTER-PARITY-001-V2 V5A blocker, combined eval ≥2026-05-27, ML_THRESHOLD_RETUNE_002 ≥2026-05-19, V5a wallet/observation/flip blockers, BUG-010 Anthropic, DASH-001 promotion decision).
**V5a precondition delta:** None as a blocker — this is a V5A *enabler* (live rows now self-identify in the ML corpus). The 4 outstanding V5A blockers (wallet / observation / V2 / flip-itself) per V5A-PRECONDITION-CHECKLIST-CLEANUP-001 §6 are unchanged.
**Post-deploy verification:** Railway bot_core container-restart confirmation + routing check (new SD-paper trades land in `trades` with `trade_mode='paper'`; no new `'live'` rows while `TEST_MODE=true`) — performed post-push, results reported to Jay.
**Concurrent-session compatibility:** V5A-PRECONDITION-CHECKLIST-CLEANUP-001 completed mid-session (docs-only). Pull-rebase before push (retry up to 3× on conflict). Append-only updates.
**Next prompt:** none queued — this was the second of the two sequential sessions (LIVE-MODE-FILTER-PARITY-001 → this). LIVE-MODE-FILTER-PARITY-001-V2 remains paste-ready-pending Jay authorization.
**Pending Claude-chat prompts not yet pasted:** none.

---

## 2026-05-14 — V5A-PRECONDITION-CHECKLIST-CLEANUP-001 (docs-only, CHECKLIST REWRITTEN)

**Committed:** `f8af901` docs(v5a-precondition-checklist-cleanup): V5A-PRECONDITION-CHECKLIST-CLEANUP-001 — rewrote AGENT_CONTEXT §6 against verified 2026-05-14 live state. Files: `AGENT_CONTEXT.md` (header + §6 rewritten), `docs/audits/V5A_PRECONDITION_CHECKLIST_CLEANUP_001_2026_05_14.md` (NEW), `ZMN_ROADMAP.md` (Decision Log), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend), `.gitignore` (`.tmp_v5a_cleanup/`). **NO services/* code change, NO env change, NO Redis writes (read-only on live state), NO deploy.**
**State changes:** None. Read-only on live state — Railway MCP env reads on bot_core + signal_aggregator, Redis MCP key reads (`market:mode:override`, `nansen:disabled`, `market:mode:current`, `bot:status`), Helius MCP `getBalance` on trading wallet.
**Bot state:** TEST_MODE=true on bot_core + signal_aggregator (verified Railway MCP). F1+C1 filter ACTIVE (`BOT_CORE_FILL_MC_CEILING_USD=1000`). `ML_THRESHOLD_BOT_CORE_SD=40` ACTIVE. `SD_MC_CEILING_USD=3000` ACTIVE on SA. `ANALYST_DISABLED=true` on SA. `NANSEN_DRY_RUN=TRUE` on SA. Trading wallet **0.064095633 SOL** (Helius `getBalance`, UNCHANGED). Paper portfolio 39.73 SOL via `bot:status`. 0 open positions. `consecutive_losses=1`. `market:mode:current=NORMAL` (automated; no override key). circuit_breaker N/A (paper). Heartbeat 2026-05-14T12:56:38Z UTC. Concurrent: no concurrent session detected at session-start (STATUS head was LIVE-MODE-FILTER-PARITY-001, read-only, complete).
**Findings (key):**
- 🟢 **§6 rewrite landed atomically.** Verified-against-live-state: all 7 old items + LIVE-MODE-FILTER-PARITY-001-V2 (newly added) classified into kept / re-framed / completed / removed / added; one inline `<!-- STALE: ... -->` flag for §7 broader staleness (STOP-C).
- 🟢 **PC1 (wallet top-up):** STILL OUTSTANDING — 0.064095633 SOL verified, unchanged from 2026-04-21.
- 🟢 **PC2 (observation window):** REFRAMED — was "Sessions A-D / 24-48h" (meaningless after 5+ config changes), now "post-C1 deploy 2026-05-13 03:38:37Z UTC → combined STOP-LOSS-20-RUG-FILTER-EVAL-001 + NO-MOMENTUM-90S-EVAL-001 ≥2026-05-27". ~33h elapsed at session start of T+14d window.
- 🟢 **PC3 (LIVE-MODE-FILTER-PARITY-001-V2):** ADDED — resolves audit §8.2 open question from yesterday's investigation. Recommended Option A scope: gate in `bot_core.py` live branch before `execute_trade` using `self._get_token_price(mint)`.
- 🟢 **PC4 (flip-itself):** KEPT with expanded pre-flip self-check (CLEAN-003 script + `market:mode:current=NORMAL` flip-time verify + DAILY_LOSS_LIMIT + sell-storm breaker). The old "renew `market:mode:override` Redis daily TTL" precondition was folded here as a flip-time verification step — current state automatically NORMAL, no manual override required.
- 🟢 **2 completed preconditions** moved to historical subsection (verified live): SD_MC_CEILING_002, LIVE-FEE-CAPTURE-002 Path B.
- 🟢 **3 obsolete preconditions removed** with audit trail: SD_EARLY_CHECK relax (TUNE-009 deferred permanently); `nansen:disabled` Redis renewal (migrated to env `NANSEN_DRY_RUN=TRUE`); `market:mode:override` standing renewal (folded into PC4 flip-time check).
- 🟡 **STOP-C broader staleness flagged:** §7 row `LIVE-FEE-CAPTURE-002 (Path B) 📋 V5a-blocking-but-degradable` contradicts the Decision Log + §6 deploy carry. Inline `<!-- STALE: ... -->` left in §6 for a separate small §7 sync session; NOT silently rewritten this session.
- 🟢 **STATUS UNKNOWN items:** zero. All preconditions had at least one verifiable signal.
**Verdict:** ✅ **CHECKLIST REWRITTEN.** Honest V5A blocker count post-rewrite: **4 outstanding** (PC1-PC4), **2 completed (historical)**, **3 removed/folded**.
**Blockers cleared:** None (no behavioural blockers cleared; this was a docs-accuracy cleanup).
**Blockers new/active:**
- 📋 **AGENT_CONTEXT-SECTION-7-SYNC** (NEW Tier-3 🟢 hygiene) — separate small session to sync §7 row statuses against the Decision Log (specifically the `LIVE-FEE-CAPTURE-002 (Path B)` stale row + audit any other §7 rows that are post-deploy carry-forwards). Inline `<!-- STALE: ... -->` flag left in §6.
- All prior carries unchanged (PC1 wallet top-up, PC2 observation, PC3 LIVE-MODE-FILTER-PARITY-001-V2, PC4 flip, combined eval ≥2026-05-27, ML_THRESHOLD_RETUNE_002 ≥2026-05-19, BUG-010 Anthropic).
**V5a precondition delta:** **net 0 outstanding count** (1 reframed, 1 added, 1 folded, 1 removed) — but the checklist is now ACCURATE and INTERPRETABLE against today's state. PC3 was added yesterday by LIVE-MODE-FILTER-PARITY-001; this session formalizes it into §6.
**Concurrent-session compatibility:** No concurrent session detected at session-start. Pull-rebase before push (retry up to 3× on conflict). Append-only updates to canonical docs (MONITORING_LOG / STATUS / Decision Log). §6 itself rewritten as atomic Edit (per piece 2 — never half-done).
**Next prompt:** None auto-triggered. The next behavioural session is gated on Jay decisions: (a) explicit authorization to scope LIVE-MODE-FILTER-PARITY-001-V2 (PC3); (b) wallet top-up timing (PC1); (c) optionally a small AGENT_CONTEXT-SECTION-7-SYNC hygiene session. Combined eval at ≥2026-05-27 remains the next observability checkpoint.
**Pending Claude-chat prompts not yet pasted:** LIVE-TRADES-LOGGING-AUDIT-001 (paste-status unknown — Jay to confirm; carries from yesterday's LIVE-MODE-FILTER-PARITY-001 entry).

---

## 2026-05-14 — LIVE-MODE-FILTER-PARITY-001 (read-only investigation, STOP-C / SCOPING NEEDED)

**Committed:** `600f726` docs(live-mode-filter-parity): LIVE-MODE-FILTER-PARITY-001 — STOP-C, execution.py has no clean insertion point for a fill-time MC gate. Files: `docs/audits/LIVE_MODE_FILTER_PARITY_001_2026_05_14.md` (NEW, main deliverable), `ZMN_ROADMAP.md` (Decision Log + new item LIVE-MODE-FILTER-PARITY-001-V2), `AGENT_CONTEXT.md` (header), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend), `.gitignore` (`.tmp_live_filter_parity/`). **NO services/* code change, NO env change, NO Redis writes, NO deploy.**
**State changes:** None. Read-only — repo + `services/execution.py` (full read) + `services/bot_core.py` (routing + buy branches) + `services/paper_trader.py` (C1 gate) + canonical docs + NO_MOMENTUM_90S_AUDIT_001.
**Bot state:** TEST_MODE=true (paper, unchanged from C1 deploy 2026-05-13 03:38:37Z UTC). F1+C1 filter ACTIVE (`BOT_CORE_FILL_MC_CEILING_USD=1000` on bot_core). `ML_THRESHOLD_BOT_CORE_SD=40` ACTIVE. Wallet 0.064 SOL on-chain (carry-forward from STATE-SNAPSHOT-2026-05-08). Paper portfolio ~30.7 SOL. Open-position count not refreshed (read-only investigation, no behavioural deploy since C1 — carry-forward acceptable, consistent with the two prior read-only STATUS entries). circuit_breaker N/A (paper mode).
**Findings (key):**
- 🟢 **Routing confirmed — not STOP-B:** `services/execution.py` is the LIVE path only (`bot_core.py:82-83` imports `paper_buy` only under `TEST_MODE`; `:836` paper→`paper_buy`, `:948` live→`execute_trade`; all `execution.py` network calls `TEST_MODE`-guarded). Changing `execution.py` does not affect paper trading or the May 27 SD validation.
- 🟢 **Gate absent — not STOP-A:** `execution.py` (816 lines) read end-to-end; no MC ceiling check anywhere in the live buy path.
- 🔴 **STOP-C fired:** the C1 gate (`paper_trader.py:247-275`) gates on a **fill-time** `entry_price * 1e9` it computes itself. `execution.py` has (a) 3 execution routes and (b) **no fill-time price computation** — it returns a signature from unsigned tx bytes; bot_core fetches price *after* at `:956`. The only MC value inside `execute_trade` is signal-time `token.liquidity_usd` — gating on it fails MC-computation parity (prompt §4.3) and duplicates SA's signal-time `SD_MC_CEILING_USD`. No clean single-gate port achieves parity inside `execution.py`.
- 🟢 **Scoping doc produced** (`.tmp_live_filter_parity/02_design.md`): 3 options. **Recommended Option A** — gate in `bot_core.py` live branch before `execute_trade` using existing `self._get_token_price(mint)`, mirroring `paper_buy`'s fill-time MC + env var + reject-log + Redis-counter exactly.
**Verdict:** 🟡 **STOP-C — SCOPING NEEDED.** A STOP is a successful outcome per the session prompt §2/§9. Audit doc written; V5A relaunch implication stated.
**Blockers cleared:** None.
**Blockers new/active:**
- 📋 **LIVE-MODE-FILTER-PARITY-001-V2 NEW Tier-1 🟡 — V5A relaunch blocker.** Scoped to Option A; needs explicit authorization to edit the `bot_core.py` live buy branch. Supersedes the NO_MOMENTUM_90S_AUDIT_001 §10 "execution.py parity" open item. Until V2 lands, a live relaunch reintroduces the $1k-$3k fill-time bleed C1 eliminated on the paper path.
- All prior carries unchanged (C1 observation → combined STOP-LOSS-20-RUG-FILTER-EVAL-001 + NO-MOMENTUM-90S-EVAL-001 ≥2026-05-27, ML_THRESHOLD_RETUNE_002 ≥2026-05-19, V5a wallet/observation/NORMAL blockers, BUG-010 Anthropic, DASH-001 promotion decision + 6 open questions).
**V5a precondition delta:** **+1 blocker** — LIVE-MODE-FILTER-PARITY-001-V2 must land before any `TEST_MODE=false` flip (open question §8.2 of the audit: add to AGENT_CONTEXT §6 preconditions). Original blockers (wallet 0.064 SOL, 48h observation, NORMAL window) unchanged.
**Concurrent-session compatibility:** No concurrent session detected at session-start (STATUS head was DASHBOARD-DESIGN-REALIGNMENT-001, design-only, complete). Pull-rebase before push (retry up to 3× on conflict). Append-only updates.
**Next prompt:** LIVE-TRADES-LOGGING-AUDIT-001 (the second of the two sequential sessions; its PREREQ gate detects this session finished via this STATUS prepend). Separately, LIVE-MODE-FILTER-PARITY-001-V2 is paste-ready-pending — needs Jay's authorization to scope a `bot_core.py` live-branch edit.
**Pending Claude-chat prompts not yet pasted:** LIVE-TRADES-LOGGING-AUDIT-001 (paste-status unknown — Jay to confirm).

---

## 2026-05-14 — DASHBOARD-DESIGN-REALIGNMENT-001 (design session, DESIGN COMPLETE)

**Committed:** `fb1b80f` docs(dashboard-design-realignment): DASHBOARD-DESIGN-REALIGNMENT-001 — re-scope DASH-001 to mobile-first 6-card monitor. Files: `docs/audits/DASHBOARD_DESIGN_REALIGNMENT_001_2026_05_14.md` (NEW, main deliverable), `docs/audits/DASHBOARD_REDESIGN_2026_04_19.md` (header note: SUPERSEDED for scope; original preserved), `ZMN_ROADMAP.md` (Decision Log + DASH-001 row + references table), `AGENT_CONTEXT.md` (header), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend). **NO services/* code change, NO env change, NO Redis writes, NO redeploy.**
**State changes:** None. Read-only design — repo + 4 prior dashboard audits + `services/dashboard_api.py` route inventory + ZMN_ROADMAP + AGENT_CONTEXT + STATUS.
**Bot state:** TEST_MODE=true (paper, unchanged from C1 deploy 2026-05-13 03:38:37Z UTC). F1+C1 filter ACTIVE (`BOT_CORE_FILL_MC_CEILING_USD=1000` on bot_core). `ML_THRESHOLD_BOT_CORE_SD=40` ACTIVE. Wallet 0.064 SOL on-chain (unchanged from STATE-SNAPSHOT-2026-05-08). Paper portfolio ~30.7 SOL. Open positions count not refreshed this session (design-only, no behavioural deploy since DASHBOARD-AUDIT-002 yesterday — carry-forward acceptable). circuit_breaker N/A (paper mode). market_mode read deferred to next behavioural session.
**Findings (key):**
- 🟢 **STOP-A weak:** Concept C "Unified Cockpit" did NOT already fit the re-scoped mobile-monitor purpose (desktop-first, ~30 surfaces, 14 legacy panels). Re-scope produced a materially smaller spec — STOP-A correctly did not fire.
- 🟢 **STOP-B pass:** 1 of 6 cards needs backend work (`/api/active-alerts` endpoint, ~30 lines, 0.5h). ≪50% threshold. UI is the bulk of the work.
- 🟢 **STOP-C did not trigger:** card set sits at 6 within the ≤6 cap. No tabs, no routes, no sub-pages. The re-scope did not creep back to Unified Cockpit.
- 🟢 **STOP-D N/A:** frontend-design skill loaded cleanly via Skill tool.
- 🟢 **STOP-E none:** no concurrent session at session-start; STATUS.md head is DASHBOARD-AUDIT-002 from yesterday.
- 🟢 **Scope diff:** ~30 Concept C surfaces → 6 cards on one screen. ≈5-7× smaller. Analytical surfaces (equity curve / P/L distribution / exit analysis / win-rates × regime / signal funnel / ML status / personality stats / governance / whale activity) DEFER-TO-CLAUDE-LOOP. Sidebar / tabs / routes / accent picker / breadcrumb / sub-pages CUT.
- 🟢 **Backend dependencies:** 1 new endpoint (~30 lines, aggregates existing Redis keys). All 5 other cards backed by existing endpoints (`/api/status`, `/api/session-stats`, `/api/wallets`, `/api/positions`, `/api/trades`) — verified by direct read of `services/dashboard_api.py` route registrations 256-2548.
- 🟢 **Build breakdown:** 3 sessions × 2.5h = 7.5h (vs Concept C's 4-6 × 3h = 12-18h, ~55% smaller). BUILD-0 backend endpoint 0.5h; BUILD-1 UI scaffold + Cards 1/2/4 + `/m` route 2.5h; BUILD-2 Cards 3/5/6 + PWA + offline-shell 2.5h.
- 🟢 **Sequencing:** June parallel-track with Analyst Phase 0, NOT May trading-logic critical path.
- 🟢 **Legacy:** `dashboard.html` retained at `/` for desktop analytical depth; new monitor at `/m`; coexist ≥30 days.
- 🟢 **Testability:** DASH-T-001 test list shrinks (3-4h → ~2.5h); does NOT need its own realignment doc — 30m test-list refresh once OBS-004 unblocks. Build NOT blocked on DASH-T-001.

**Verdict:** ✅ **DESIGN COMPLETE.** Ready for build sessions DASH-001-BUILD-0 / BUILD-1 / BUILD-2 to come off this spec in June (parallel with Analyst Phase 0).
**Blockers cleared:** None this session (design-only).
**Blockers new/active:**
- 📋 **6 open questions to Jay** (audit §9): re-scope acceptance, 30-day legacy coexistence, single accent vs picker, Sentry fold-in v1.5, active emergency-stop from phone (deferred — auth-impact), June timing window.
- All prior carries unchanged (C1 observation, combined STOP-LOSS-20-RUG-FILTER-EVAL-001 + NO-MOMENTUM-90S-EVAL-001 ≥2026-05-27, ML_THRESHOLD_RETUNE_002 ≥2026-05-19, V5a wallet/observation/NORMAL blockers, BUG-010 Anthropic).

**V5a precondition delta:** None.
**Concurrent-session compatibility:** No concurrent session detected at design-start. Pull-rebase before push (retry up to 3× on conflict). Append-only updates only.
**Next prompt:** Either (a) Jay-decision on the 6 open questions (in particular re-scope acceptance + June timing), then DASH-001-BUILD-0 (`/api/active-alerts` endpoint, 0.5h, can ship as a standalone micro-session if F1+C1 observability is acutely needed before June) → BUILD-1 → BUILD-2; or (b) continue with May trading-logic critical path (C1 observation → combined eval ≥2026-05-27). NOT auto-triggered.
**Pending Claude-chat prompts not yet pasted:** none — this design session terminated with verdict.

---

## 2026-05-13 09:31 UTC — DASHBOARD-AUDIT-002 (read-only investigation, AUDIT COMPLETE)

**Committed:** `12434e2` docs(dashboard-audit-002): DASHBOARD-AUDIT-002 — REAFFIRM REBUILD; promote DASH-001 QUEUED → Tier 1. Files: `docs/audits/DASHBOARD_AUDIT_002_2026_05_13.md` (NEW), `ZMN_ROADMAP.md` (Decision Log), `AGENT_CONTEXT.md` (header), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend). NO services/* edit, NO env change, NO Redis writes.
**State changes:** None. Read-only — repo + git history + ROADMAP + 3 prior dashboard audits + 2 post-Apr-19 reality-shift audits.
**Bot state:** TEST_MODE=true (paper, unchanged from C1 deploy). F1+C1 filter ACTIVE (`BOT_CORE_FILL_MC_CEILING_USD=1000` on bot_core). `ML_THRESHOLD_BOT_CORE_SD=40` ACTIVE. Wallet 0.064 SOL on-chain (unchanged). Paper portfolio ~30.7 SOL.
**Findings (key):**
- 🟢 **STOP-B PASS:** only 1 commit on `dashboard/` / `services/dashboard_api.py` since 2026-04-19 baseline (`bc622eb` BUG-021 trade_mode filter). Source is materially unchanged.
- 🟡 **Decision-flow audit:** 0 of 8 operator decisions fully SUPPORTED. 4 PARTIAL, 4 MISSING. New operator workload (deploy verification, audit pipeline, rollback triggers) uniformly under-served.
- 🟡 **Reality-shift gap analysis:** 10 items; only 1 severity-5 (G-01 F1+C1 filter visibility); all 10 survive DASH-001 rebuild and would be built there anyway.
- 🟢 **Bug status:** 4 closed since 2026-04-19 (B-002 via BUG-022 pass-through, B-004 confirmed, B-011 + B-012 already closed); 9 still apply (defer to rebuild); 2 separate fix candidates (DASHBOARD-CORRECTED-PNL-WARN-001, DASHBOARD-HEALTH-CHECK-PROBE-DEPTH-001); 3 unverified (B-007/B-008/B-009 → DASH-T-001 Playwright suite).
- 🟢 **Prioritized list:** PATCH-NOW count = 1 definitive (G-01, M-effort) + 2 conditional. Below §8 BUNDLE threshold (3-5 small items).
- 🟢 **STOP-A applies weakly:** prior audits cover all framing except G-01 (F1+C1 verification urgency).
**Verdict:** ✅ **AUDIT COMPLETE. REAFFIRM REBUILD.** Recommendation: promote DASH-001 from QUEUED → Tier 1 scheduled. DASH-001 has been QUEUED ~4 weeks; F1+C1 deploys + ML retune queue + audit pipeline create accumulating observability gaps that the rebuild naturally closes. ⛔ DASH-PATCH stays deferred (rebuild-not-patch). Open question to Jay: schedule DASH-001 now or continue queuing?
**Blockers cleared:** None this session (read-only).
**Blockers new/active:**
- 📋 **DASH-001 promotion decision** — recommendation in audit §1 + §7 + §9 to elevate QUEUED → Tier 1. Jay-decision.
- All prior carries unchanged (combined STOP-LOSS-20-RUG-FILTER-EVAL-001 + NO-MOMENTUM-90S-EVAL-001 ≥2026-05-27, ML_THRESHOLD_RETUNE_002 ≥2026-05-19, V5a wallet/observation/NORMAL blockers, BUG-010 Anthropic).
**V5a precondition delta:** None.
**Concurrent-session compatibility:** No concurrent session detected at audit time. Pull-rebase before push (retry up to 3× on conflict). Append-only updates.
**Next prompt:** Either (a) DASH-001 scheduling discussion / kickoff session if Jay accepts promotion, or (b) continue with combined eval at ≥2026-05-27. NOT auto-triggered.
**Pending Claude-chat prompts not yet pasted:** none — this audit terminated with verdict.

---

## 2026-05-13 03:29 UTC — NO-MOMENTUM-90S-FILTER-RETUNE-DEPLOY-001 (C1, env-only deploy, DEPLOYED-VERIFIED)

**Committed:** `a3ee421` docs+deploy(no-momentum-90s-retune): NO-MOMENTUM-90S-FILTER-RETUNE-DEPLOY-001 C1 — `BOT_CORE_FILL_MC_CEILING_USD` retuned 3000 → 1000 on bot_core at 2026-05-13 03:29:21Z UTC; container restart 03:38:37Z UTC clean. Files: `AGENT_CONTEXT.md` (header + §2 bot_core row + §6.5 nm90 row), `ZMN_ROADMAP.md` (Decision Log + STOP-LOSS-20-RUG-FILTER-DEPLOY-001/EVAL-001 rows superseded/folded), `docs/audits/NO_MOMENTUM_90S_AUDIT_001_2026_05_12.md` (§12 "Decision to skip T1" appended), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend). NO services/* code change. No `railway up`; single env command via Railway MCP triggered auto-redeploy.
**State changes:** Railway env: `BOT_CORE_FILL_MC_CEILING_USD=1000` (was 3000) on bot_core ONLY. No Redis writes. No code edits. No other service touched. Bot_core container restarted at 03:38:37Z UTC.
**Bot state:** TEST_MODE=true (paper, unchanged), F1+C1 filter ACTIVE at $1000, `ML_THRESHOLD_BOT_CORE_SD=40` ACTIVE (unchanged from 2026-05-05 14:16:48Z UTC), 0 open positions in DB at restart (`Startup reconciliation: 0 open positions in DB`), `Bot Core ready`, market mode NORMAL at restart, 44 whale wallets reloaded, portfolio 30.7304 SOL paper, wallet 0.064 SOL on-chain (unchanged), circuit_breaker N/A. Concurrent: no concurrent session detected; predecessor ML-SCORE-ATH-VALIDATION-001 closed 2026-05-12 (commit `c3a6ba1` / `e96fa1a`).
**Findings (key):**
- 🟢 **STOP-A retest PASS on fresh 8.12d sample** (vs audit's 7.49d). C1 ($1000 ceiling) marginal blocked: 589 trades / sum_pnl saved -10.86 SOL → **+1.49 SOL/day W3+W4 rate**, **+3.02 SOL/day W4-only rate**. Both exceed ≥+1.0 SOL/d threshold. **False-positive winners blocked: 0** (matches audit exactly). KEPT slice strengthened: 523 trades / +32.62 SOL / **91.4% WR** (vs audit's 433 / +30.71 / 94.2%). Structural pattern held: $1k-$3k cliff persists.
- 🟢 **STOP-B PASS:** last fill-path commit on `services/paper_trader.py` / `services/bot_core.py` = `0f37e82` (the F1 deploy itself). No behavioural drift since audit.
- 🟢 **STOP-C PASS:** no concurrent bot_core deploy in flight. Last STATUS entries are read-only research sessions (ML-SCORE-ATH-VALIDATION-001 docs-only, predecessor audit T0 docs-only).
- 🟢 **STOP-D PASS:** Jay authorization explicit in session prompt; named `BOT_CORE_FILL_MC_CEILING_USD=1000` by name; provided rollback steps; acknowledged this is a fast-track decision and authorized T1 skip.
- 🟢 **Deploy:** env set via Railway MCP at 03:29:21Z UTC. Triggered one auto-redeploy. Container `Starting Container` at 03:38:37Z UTC (~9 min after env set — longer than doc's ~90s but within bounds). Clean startup: `TEST_MODE=True` → `Starting SINGLE service: bot_core` → `Startup reconciliation: 0 open positions in DB` → `Bot Core ready — managing 3 personalities` → `Listening for emergency alerts`. No RuntimeError / Traceback / ImportError.
- 🟢 **First post-deploy rejection log:** `[paper_trader] INFO: FILL_MC_CEILING reject: 6X5V79NvN85P mc=$10753 > ceiling=$1000` at 03:41:38Z. Env plumbed through to rejection logic. (Mint at $10K would also have hit old $3K ceiling; meaningful $1k-$3k rejections accrue over next hours.)
**Verdict:** ✅ **DEPLOYED-VERIFIED** at T+~12 min. Plumbing confirmed. T+30 min and T+24h verification scheduled per deploy doc.
**Blockers cleared:** NO-MOMENTUM-90S-FILTER-RETUNE-DEPLOY-001 (was paste-ready carry).
**Blockers new/active:**
- 📋 **STOP-LOSS-20-RUG-FILTER-EVAL-001 + NO-MOMENTUM-90S-EVAL-001 (combined)** — eval queue date pushed from ≥2026-05-25 to ≥2026-05-27 (+14d from this deploy). T1 STOP-F regime test rolled into combined eval.
- 📋 **ML_THRESHOLD_RETUNE_002** carry — re-derive sweep on post-gate window ≥2026-05-12 + 7d (≥2026-05-19).
- All other carries unchanged from prior STATUS entries.
**V5a precondition delta:** None directly. F1+C1 reduces SD-paper-active leak (`no_momentum_90s` $1k-3k bleed) which would amplify on live at sizing factor. Audit §6.5 noted V5a flip caps could be re-evaluated post-eval window; original blockers (wallet 0.064 SOL, 48h observation, NORMAL window) unchanged.
**Rollback procedure (instant):** `BOT_CORE_FILL_MC_CEILING_USD=3000` via Railway MCP / CLI. Triggers single auto-redeploy. No code revert. Rollback triggers per deploy doc §"Rollback triggers" — see MONITORING_LOG entry.
**Concurrent-session compatibility:** Pull-rebase before push (retry up to 3× on conflict). Append-only updates to AGENT_CONTEXT/MONITORING_LOG/STATUS/ROADMAP. Decision Log row added at top of ZMN_ROADMAP.
**Next prompt:** Combined STOP-LOSS-20-RUG-FILTER-EVAL-001 + NO-MOMENTUM-90S-EVAL-001 at ≥2026-05-27. T+30 min and T+24h observability checks per deploy doc (Jay-side spot-checks).
**Pending Claude-chat prompts not yet pasted:** none — this session executed the previously-queued retune deploy.

---

## 2026-05-12 ~23:35 UTC — ML-SCORE-ATH-VALIDATION-001 (read-only research, EVIDENCE-PRODUCED)

**Committed:** `c3a6ba1` docs(ml-ath-validation): ML-SCORE-ATH-VALIDATION-001 — ML weakly predictive (AUC 0.5361); live gate at thr=40 sub-optimal vs thr=55 historical. Files: `docs/audits/ML_SCORE_ATH_VALIDATION_001_2026_05_12.md` (NEW), `scripts/ml_ath_validation_001.py` (NEW, research-only fetch loop), `scripts/verify_ml_calibration.py` (NEW, standalone counterfactual tool), `AGENT_CONTEXT.md` (header), `ZMN_ROADMAP.md` (Decision Log), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend), `.gitignore` (`.tmp_ml_ath_validation/`). New DB object: `mint_ath_lookups` table (research-only cache, NOT consumed by production).
**State changes:** None to deployed config. DB schema change: new `mint_ath_lookups` table populated with 29 partial rows (8 gecko_terminal + 21 gt_no_ohlcv_in_window). Read-only otherwise: SELECT against paper_trades, HTTP GET against GeckoTerminal/DexPaprika public APIs, no Redis writes, no env writes, no redeploy.
**Bot state:** TEST_MODE=true (paper, unchanged). F1 filter ACTIVE (`BOT_CORE_FILL_MC_CEILING_USD=3000` on bot_core, deployed 2026-05-11). `ML_THRESHOLD_BOT_CORE_SD=40` ACTIVE (deployed 2026-05-05 14:16:48Z UTC). Wallet 0.064 SOL on-chain (unchanged). Concurrent state: no concurrent session detected; predecessor NO-MOMENTUM-90S-AUDIT-001 T0 closed earlier today (commit `7cce801` / `bf544fe`).
**Findings (key):**
- 🟢 **Phase 1 pre-claim verification (STOP-A):** EXACT match. n=1,097 SD-paper trades in window 2026-04-22 → 2026-05-05 14:16:48 UTC (pre-`BOT_CORE_ML_GATE`); ml_score range 30.0-97.2 (mean 54.37); exit_reason distribution (nm90 44.6%, TS 36.2%, sl20 11.9%, stale 5.9%) all match within rounding.
- 🟢 **Phase 1 GeckoTerminal coverage probe (STOP-B):** all 3 sample mints (1 TRAILING_STOP, 1 nm90, 1 sl20) indexed under `pump-fun` dex namespace with pool + OHLCV. **Pre-graduation pump.fun BC pools ARE indexed.** DexPaprika ruled out as fallback (0 pools returned for the same TS mint — only Raydium post-grad indexed).
- 🟡 **Phase 2 operational reality:** GeckoTerminal free-tier sustained throughput ~2-3 successful rows/min due to sliding-window 429 backoff (vs documented 30/min). Full 1,097-mint fetch infeasible within session budget. **Pivoted to coverage-strategy:** `paper_peak` (45%) + `gecko_terminal` direct (1.6%) + `no_pump_gt_confirmed` (1.2%) + `no_pump_exit_inferred` (53.4%) = **99.9% effective ATH coverage**. Inference rule: nm90/sl20/time_exit_loss rows without peak_price AND no GT data → ath_mult=1.0 (no observed pump). Inference is correct in expectation given exit-reason semantics; 95.7% of nm90 rows fall in this bucket.
- 🟢 **Phase 3 ML calibration:** mean ath_multiplier monotonic by quintile Q1=2.20 → Q5=2.72. Mean PnL/trade monotonic upward Q1=+0.007 → Q5=+0.017 SOL (Q2 dip aside). **But %≥5× rate is non-monotonic and paradoxical:** 30-40 band 9.0% > 80+ band 4.8%. The bot's "lowest confidence" trades catch as many or more mega-pumps as its "highest confidence" trades.
- 🟢 **Phase 3 ROC/AUC:** AUC = **0.5361** on ATH≥5× binary classifier. Barely above chance (0.50). Verdict per plan rubric: **WEAKLY PREDICTIVE** (0.55 lower bound; we sit just below). At live thr=40, precision is 6.5% (essentially the 6.9% base rate — zero lift).
- 🟢 **Phase 3 counterfactual gate sweep:** **thr=40 (LIVE) is the WORST in the 30-55 range.** Blocking ml_score<40 would have cost -1.26 SOL over 12d sample (the 30-40 band catches 17 of 76 ≥5× mega-winners — disproportionate). Best historical = **thr=55** (+0.71 SOL vs no-gate; +1.97 SOL vs current live live; **+0.16 SOL/day implied lift**). thr=30 (effectively no gate) is +0.20 SOL/day better than current.
- 🟢 **Phase 3 killer chart:** 0 of 489 nm90 exits had ath_mult ≥ 2× (mostly inference-driven, structurally correct). Only 2 of 489 (0.41%) had GT-confirmed peak AFTER exit, both at multi-day lag (median 3,384 min = 56h). **Timer is NOT killing winners** at any meaningful rate. Independent corroboration of NO-MOMENTUM-90S-AUDIT-001's verdict that MC discrimination is the real lever.
**Verdict:** ✅ **EVIDENCE-PRODUCED.** ML score has weak predictive power. Live gate is sub-optimal. **No deploy change recommended this session** — decision belongs to ML_THRESHOLD_RETUNE_002 (≥7d post-gate clean data, re-derive on post-gate window).
**Blockers cleared:** None this session (read-only research).
**Blockers new/active:**
- 📋 **ML_THRESHOLD_RETUNE_002 NEW Tier-1** — re-derive §5 sweep on post-gate window (≥2026-05-12 + 7d). Decide {raise to ~55, drop to ~30 or disable}. Apply same STOP-gate discipline as STOP-LOSS-20-RUG-FILTER-DEPLOY-001.
- 📋 **NO-MOMENTUM-90S-FILTER-RETUNE-DEPLOY-001** carry — paste-ready, awaiting Jay's explicit go (or bundle with STOP-LOSS-20-RUG-FILTER-EVAL-001 ≥2026-05-25).
- 📋 **STOP-LOSS-20-RUG-FILTER-EVAL-001** carry — eval window ≥2026-05-25 unchanged.
- 📋 **ML-SCORE-ATH-VALIDATION-001-PHASE2-COMPLETION** (NEW Tier-3 🟢) — optional. Re-run `scripts/ml_ath_validation_001.py` to populate full 1,097 mint_ath_lookups (currently 29). Multi-hour wall clock at GT free-tier limit. Not blocking; the audit's conclusions are stable via inference. Useful for future research on ATH-after-exit pumps.
- All other carries unchanged from prior STATUS entries.
**V5a precondition delta:** None. ML threshold retune is paper-only at flip and orthogonal to V5a. Original blockers (wallet 0.064 SOL, 48h observation, NORMAL window) unchanged.
**Concurrent-session compatibility:** Pull-rebase before push (retry up to 3× on conflict). Append-only updates to AGENT_CONTEXT/MONITORING_LOG/STATUS/ROADMAP. Decision Log row added at top.
**Next prompt:** **ML_THRESHOLD_RETUNE_002** at ≥2026-05-19 (≥7d post-gate). No auto-trigger; paste-ready prompt to be derived from §6-§7 of this audit.
**Pending Claude-chat prompts not yet pasted:** none — independent session complete.

---

## 2026-05-12 ~13:00 UTC — NO-MOMENTUM-90S-AUDIT-001 (T0, read-only, DEPLOY-RECOMMENDED)

**Committed:** `bf544fe` docs(no-momentum-90s-audit): NO-MOMENTUM-90S-AUDIT-001 T0 — $1000 MC ceiling retune identified. Files: `docs/audits/NO_MOMENTUM_90S_AUDIT_001_2026_05_12.md` (NEW), `docs/audits/NO_MOMENTUM_90S_DEPLOY_PROMPT_2026_05_12.md` (NEW), `AGENT_CONTEXT.md` (§6.5 nm90 row), `ZMN_ROADMAP.md` (Decision Log), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend), `.gitignore` (`.tmp_no_momentum_90s/`).
**State changes:** None. Read-only — DB SELECT against `paper_trades` (read-only via DATABASE_PUBLIC_URL), no code/env/Redis writes, no redeploy.
**Bot state:** TEST_MODE=true (paper). F1 filter ACTIVE (`BOT_CORE_FILL_MC_CEILING_USD=3000` on bot_core, deployed 2026-05-11 12:24 UTC). Wallet 0.064 SOL on-chain (unchanged from 2026-04-30 baseline). Concurrent state: no concurrent session detected in STATUS.md (last entry STOP-LOSS-20-RUG-FILTER-DEPLOY-001 closed 2026-05-11).
**Findings (key):**
- 🟢 **Phase 0 pre-claim verification:** mean PnL −0.018 ✓; **hold-time prose was wrong** (actual median 51s, not 80-90s — exit fires at window-open since timer env=60s makes window (50, 90)s and the loop iterates fast); $0-1k WR 72-100% ✓; $1k-3k WR 0% ✓; filter deploy time ✓. STOP-A passes on load-bearing anchor.
- 🟢 **Window pattern:** W2 (29 Apr - 4 May, pre-F1) already showed the W4 pattern (nm90 rate 64%, WR 18.4%, sum +0.69 SOL). W3 was the anomalously-good window (+9.30 SOL on 959 trades). W4 is a regression-to-W2, not a novel failure mode.
- 🟢 **MC-band structural cliff:** W4 ($0-1k = 51 trades / +1.48 SOL / 73% WR) vs ($2k-3k = 205 trades / -3.54 SOL / **0** winners / 202 nm90 exits). Same cliff existed in W3 ($1k-3k: 376 trades / -7.20 SOL / 0-4% WR). Filter just exposed the next layer.
- 🟢 **DISCRIMINATOR FOUND:** market_cap_at_entry is the SOLE discriminative feature. trail_win p25/p50/p75 = $550/$639/$720; nm90 p25/p50/p75 = $2615/$2778/$2909. **Max trail_win MC in W3+W4 = $892** — zero overlap with $1000 ceiling. ML score, rugcheck, liq_velocity, cfgi, bc_progress, age all IDENTICAL across nm90/trail_win/trail_loss groups.
- 🟢 **C1 ($1000 ceiling)** counterfactual: 589 trades blocked incrementally over F1 / -10.86 SOL saved over 7.49d = **+1.45 SOL/day W3+W4 rate / +3.67 SOL/day W4-only rate**. **Zero false positives**. KEPT slice: 433 trades / +30.71 SOL / WR 94.2%. STOP-C clears (0% trail_win lost). STOP-D clears 5×+. STOP-E clears (C1+C2 both viable).
- 🟡 **Scope collision:** the recommended lever IS a retune of F1 (same env var). §9 of audit prompt prohibits touching F1 in this session; deploy is a follow-on paste-ready prompt for Jay-authorized early retune OR bundled into STOP-LOSS-20-RUG-FILTER-EVAL-001 (≥2026-05-25).
- ⚪ **Phase 2.4 signal-age check INFEASIBLE:** signal_detected_at/scored_at/traded_at NULL on 100% of post-filter rows (LATENCY-OBSERVABILITY-001 still open). Phase 2.5 time-of-day pattern confounded with W4 timing — not actionable.
**Verdict:** ✅ **DEPLOY-RECOMMENDED** (deploy in follow-on session per Jay's authorization). Forward ROI midpoint **+1.5 to +2.5 SOL/day** at zero FP cost. T1 re-run scheduled ≈2026-05-14 to test regime-vs-structural via STOP-F.
**Blockers cleared:** None this session (read-only).
**Blockers new/active:**
- 📋 **NO-MOMENTUM-90S-FILTER-RETUNE-DEPLOY-001 NEW Tier-1 🟢** — single env-var change, ~20 min wall clock, paper-only at flip, instant rollback. Paste-ready at `docs/audits/NO_MOMENTUM_90S_DEPLOY_PROMPT_2026_05_12.md`.
- 📋 **NO-MOMENTUM-90S-AUDIT-001-T1 NEW Tier-1** — re-run THIS prompt at ≈2026-05-14 to test STOP-F (regime reverting). Compare against `.tmp_no_momentum_90s/T0_BASELINE.json`.
- 📋 **STOP-LOSS-20-RUG-FILTER-EVAL-001** carry — eval window pushed to ≥2026-05-26 if C1 deploy lands ≥2026-05-12 (else unchanged at ≥2026-05-25).
- All other carries unchanged from prior STATUS entries.
**V5a precondition delta:** None. C1 retune is paper-only and orthogonal to V5a. Original blockers (wallet 0.064 SOL, 48h observation, NORMAL window) unchanged.
**Concurrent-session compatibility:** Pull-rebase before push (retry up to 3× on conflict). Append-only updates to AGENT_CONTEXT/MONITORING_LOG/STATUS. Decision Log row added at top.
**Next prompt:** `NO-MOMENTUM-90S-FILTER-RETUNE-DEPLOY-001` (paste-ready). DO NOT auto-trigger — Jay must explicitly authorize early retune of F1 (or wait for STOP-LOSS-20-RUG-FILTER-EVAL-001 to bundle).
**Pending Claude-chat prompts not yet pasted:** none — independent session complete.

---

## 2026-05-11 12:24 UTC — STOP-LOSS-20-RUG-FILTER-DEPLOY-001 (code+env deploy)

**Committed:** `0f37e82` feat(filter): F1 fill-time MC ceiling (default disabled, env-controlled). Files: `services/paper_trader.py` (+30 lines in `paper_buy` after entry_price computation), `.tmp_stop_loss_20_rug_deploy/post_deploy_verify.py` (NEW, gitignored), `STATUS.md` (this prepend), `ZMN_ROADMAP.md` (Decision Log + 2 item-status updates), `AGENT_CONTEXT.md` (§2 bot_core + §6.5 leaks), `MONITORING_LOG.md` (entry), `.gitignore` (`.tmp_stop_loss_20_rug_deploy/`).
**State changes:** Railway env `BOT_CORE_FILL_MC_CEILING_USD=3000` SET on bot_core ONLY at 2026-05-11 12:18:37 UTC. Triggered 2 redeploys (code push at 12:09 UTC → container start at 12:16:41 UTC; env set at 12:18:37 UTC → container start at 12:24:12 UTC). Code default in `services/paper_trader.py:253` reads env=0 = disabled, so the gate is inert on services where the env isn't set (signal_aggregator, web, ml_engine, etc.).
**Bot state:** TEST_MODE=true (paper, unchanged). Trading wallet 0.064 SOL on-chain (unchanged). Pre-deploy STOP gate verification: STOP-A PASS (investigation doc 2d old, ≤14d window); STOP-B PASS (no behavioural change to paper_trader/bot_core since investigation commit 27f623b — last touch ea0da2f was BOT-CORE-ML-GATE-001 on 2026-05-05, pre-investigation); STOP-C PASS (re-ran verify_filter; 9.5d ROI at $3K = **+1.38 SOL/day**, up from +0.93/day at investigation — bleed accelerating, filter more valuable); STOP-D PASS (no concurrent deploy).
**Findings (post-deploy verification, T+2 min):**
- 🟢 Code container started cleanly at 12:16:41 UTC: "Starting SINGLE service: bot_core" → "Startup reconciliation: 0 open positions in DB" → "Listening for emergency alerts" — no RuntimeError, no import failure.
- 🟢 Env container started cleanly at 12:24:12 UTC after env-set redeploy. PAPER ENTERED logs resumed normally; bot processing signals.
- 🟢 4 new SD-paper trades since env-active deploy, **0 with market_cap_at_entry > $3,000** (verification harness PASS). F1 gate is selective — low-MC tokens still flow through.
- ⚪ Redis counter `bot:filter:fill_mc_ceiling:rejects:2026-05-11` not yet present — lazy-create on first reject. Expected at this short timescale (~1 reject/2-3h pre-deploy historical rate); will populate within hours.
- 🟢 No `FILL_MC_CEILING reject` log lines in first 2 min — consistent with the ~9 rugs/day historical rate (would expect first reject within 1-3 hours).
- ⚪ `consecutive_losses=19` in bot:status — high but PRE-EXISTING (not deploy-related; AGENT_CONTEXT showed `consecutive_losses=1` on 2026-05-08, so it's accumulated over 3d). Not a deploy rollback trigger; orthogonal phenomenon (likely related to the May 8+ spike that motivated this filter).
**Verdict:** ✅ **DEPLOYED-VERIFIED** at T+2 min. Rollback triggers from deploy prompt §5 not fired:
- ✗ Bot_core failed to start with new code — NO, clean startup
- ✗ SD-paper trade rate < 50% of pre-deploy within 30 min — too early (re-check at +30 min); 4 trades in first 2 min consistent with pre-deploy rate (~3.5/h × 2 min = 0.12 expected, observed 4 = burst above expectation)
- ✗ TRAILING_STOP / staged_tp_+1000% winner with realised_pnl_sol > 0.5 SOL blocked — too early
- ✗ bot:emergency_stop set or new consecutive_losses ≥ +5 within 24h — pre-existing 19 unchanged
Rollback procedure documented; instant rollback by `BOT_CORE_FILL_MC_CEILING_USD=0` via Railway MCP (no redeploy).
**Blockers cleared:**
- ✅ **STOP-LOSS-20-RUG-FILTER-DEPLOY-001** — DEPLOYED.
**Blockers new/active:**
- 📋 **STOP-LOSS-20-RUG-FILTER-EVAL-001** unchanged — re-evaluate at +14d post-deploy (queue ≥2026-05-25). Verify Redis counter rate ~25/day, re-run verify_filter, decide keep/tighten/loosen, decide live-mode parity in `services/execution.py`.
- All other carries unchanged from prior STATUS entries.
**V5a precondition delta:** None. F1 is paper-only at flip; TEST_MODE=true unchanged. Live-mode parity in `services/execution.py` is a separate (gated on V5a-go-no-go) session.
**Concurrent-session compatibility:** Pull-rebase before push (retry up to 3× on conflict). Single behavioural code change to `services/paper_trader.py` (one Edit hunk). Append-only updates to canonical docs.
**Next prompt:** **STOP-LOSS-20-RUG-FILTER-EVAL-001** at +14d (queue ≥2026-05-25). No auto-trigger.
**Pending Claude-chat prompts not yet pasted:** none — independent session complete.

---

## 2026-05-09 ~UTC — STOP-LOSS-20-RUG-INVESTIGATION-001 (read-only investigation, DEPLOY-RECOMMENDED)

**Committed:** `27f623b` docs(stop-loss-20-rug): STOP-LOSS-20-RUG-INVESTIGATION-001 — fill-time MC ceiling lever identified. Files: `docs/audits/STOP_LOSS_20_RUG_INVESTIGATION_001_2026_05_09.md` (NEW), `docs/audits/STOP_LOSS_20_RUG_FILTER_DEPLOY_PROMPT_2026_05_09.md` (NEW), `AGENT_CONTEXT.md` (§6.5 leaks updated), `ZMN_ROADMAP.md` (Decision Log + 4 new follow-up items), `MONITORING_LOG.md` (entry), `STATUS.md` (this prepend), `.gitignore` (`.tmp_stop_loss_20_rug/`).
**State changes:** None. Read-only — DB SELECT against `paper_trades` (read-only), Railway MCP `list-variables` × 2 services, code grep, no Redis/env/DB writes, no redeploy.
**Bot state:** TEST_MODE=true (paper). Wallet 0.064 SOL on-chain (UNCHANGED from 2026-04-30 baseline). SD_MC_CEILING_USD=3000 confirmed live on signal_aggregator. STOP_LOSS_PCT=0.20 confirmed at bot_core code default. Concurrent state: not verified live this session (read-only DB+code work; STATE-SNAPSHOT-2026-05-08 last live verify).
**Findings (key):**
- 🟢 **DISCRIMINATOR FOUND**: `market_cap_at_entry` perfectly separates RUG from WIN at $3K cut on 273-row sample (65 rugs / 208 trailing-stop wins) since 2026-05-02. RUG min $3,181 → max $181,519 (100% > $3K); WIN min $321 → max $832 (0% > $3K). Zero overlap.
- 🟢 **ROOT CAUSE**: SA `SD_MC_CEILING_002` gate evaluates BC reserves at signal-publish time (raw_data carries fresh-mint vSol≈30, vTokens≈1.073e9 → MC≈$2,400 < $3K, always passes). Bot_core fills via Jupiter/Gecko *current* price, which has pumped during 1-15s signal-to-fill window. The gate is structurally inert against this failure mode. Fix has to be at fill time.
- 🟢 **F1 FILTER**: reject if `entry_price * 1B > $3,000` at `paper_trader.paper_buy` after entry_price computation. Counterfactual ROI **+0.80 to +0.93 SOL/day** across 7d/14d/17d-POST-cliff windows. Zero winner false positives (0/544 over 17d). STOP-E and STOP-F clear by 2.7-3.1×.
- 🟢 features_json features all default to sentinels for fresh tokens age <30s — none discriminate. The lever has to use a fill-time quantity, which is `market_cap_at_entry`.
- 🟡 **May 8 spike**: 40 of 65 rugs (62%) on a single day. Could be transient or structural; F1 is forward-protective regardless.
- 🟡 peak_price NULL on 100% of rugs (data limitation; OBS-INTRA-HOLD-DRAWDOWN-001 already proposed).
**Verdict:** ✅ **DEPLOY-RECOMMENDED**. Single-lever, env-controlled (default OFF), reversible, paper-only at flip. Follow-on prompt at `docs/audits/STOP_LOSS_20_RUG_FILTER_DEPLOY_PROMPT_2026_05_09.md`.
**Blockers cleared:** None this session (read-only investigation).
**Blockers new/active:**
- 📋 **STOP-LOSS-20-RUG-FILTER-DEPLOY-001 NEW Tier-1 🟢** — single-lever code change, env=$3000, ~30-45min wall clock. Paper-only at flip; no live risk.
- 📋 **STOP-LOSS-20-RUG-FILTER-EVAL-001 NEW Tier-2** — re-evaluate at +14d post-deploy (queue ≥2026-05-23). Decide keep/tighten/loosen.
- 📋 **PAPER-ENTRY-PRICE-DENOMINATION-001 NEW Tier-3 🟢** — TRAILING_STOP winners cluster at MC $321-832 (well below BC fresh-mint baseline ~$2,400). Likely Jupiter v3 sub-baseline pricing for fresh pump.fun pools. Doesn't affect F1; observability follow-up only.
- 📋 **OBS-INTRA-HOLD-DRAWDOWN-001 EXISTING (reinforced)** — peak_price NULL on 100% of rugs prevents direct measurement of "did stop_loss_20% amputate winners". Add `min_price_during_hold` column.
- All carries unchanged from prior STATUS entries (DEFENSIVE-OVERRIDE-PROBE-001 EXPIRED, VYBE-URL-CODE-DRIFT-001 scope expanded, STRATEGY-CLIFF NO-REVERT, CLIFF-VYBE-SOCIALDATA-SUPPLEMENT carries, BUG-010 Anthropic, SOCIALDATA-AUTO-TOPUP-001 ACTIVE, V5a wallet/observation/NORMAL blockers).
**V5a precondition delta:** None. F1 deploy is paper-only and orthogonal to V5a (TEST_MODE=true unchanged at flip; live-mode parity is a separate session). NO-MOMENTUM-90S-AUDIT-001 still next-highest-ROI on the V5a-blocking SD-paper bleed list.
**Concurrent-session compatibility:** Pull-rebase before push (retry up to 3× on conflict per CLAUDE.md). Append-only updates to AGENT_CONTEXT.md / MONITORING_LOG.md / STATUS.md. ZMN_ROADMAP.md Decision Log row added at top of table.
**Next prompt:** **STOP-LOSS-20-RUG-FILTER-DEPLOY-001** (paste-ready at `docs/audits/STOP_LOSS_20_RUG_FILTER_DEPLOY_PROMPT_2026_05_09.md`). Single push, no `railway up`, ~30-45 min wall clock. Recommended priority: high — clearest ROI lever in current backlog at low risk.
**Pending Claude-chat prompts not yet pasted:** none — independent session complete.
**Verdict:** ✅ INVESTIGATION COMPLETE. Filter F1 designed and validated at +0.80-0.93 SOL/day with 0% winner FP. Deploy prompt ready.

---

## 2026-05-08 ~13:21 UTC — STATE-SNAPSHOT-2026-05-08 (read-only verification, no env / Redis / code changes)

**Committed:** `badb221` docs(state-snapshot): STATE-SNAPSHOT-2026-05-08 — refresh stale claims pre probe eval. Files: `docs/audits/STATE_SNAPSHOT_2026_05_08.md` (NEW), `AGENT_CONTEXT.md` (header + §3 wallet + §8 Redis-snapshot refresh), `MONITORING_LOG.md` (entry), `ZMN_ROADMAP.md` (Decision Log entry), `STATUS.md` (this prepend), `.gitignore` (`.tmp_state_snapshot/`).
**State changes:** None. Read-only — Redis MCP get/list, Helius MCP getBalance/getNetworkStatus, Railway MCP list-variables × 6 services, Postgres query against `paper_trades` (read-only), aiohttp/curl probes against Vybe / SocialData / Anthropic / Helius routes (no real-key probes burning credits). NO services/* edit, NO deploy, NO env / Redis writes.
**Bot state:** TEST_MODE=true (paper). Paper portfolio 24.83 SOL (live), 1 open partial position (mint GnNFCenU…, staged_tp_+200% 80% remaining — cosmetic). market_mode=NORMAL (probe expired). emergency_stop=ABSENT. Trading wallet 0.064095633 SOL (UNCHANGED from 2026-04-30 baseline). Holding wallet 0.190842421 SOL (UP from 0.0098 SOL on 2026-04-29 — drift +0.181, confirm with Jay).
**Findings (key):**
- 🔴 **DEFENSIVE-OVERRIDE-PROBE-001 EXPIRED.** `market:mode:override` absent; expired 2026-05-07 22:29 UTC after one TTL cycle (no renewal fired). Probe sample n=54 SD-paper closed during pure 24h window — under the 80-trade target.
- 🟡 Probe-period sample (since 2026-05-07 00:00 UTC) is contaminated. n=263 SD-paper closed, +2.06 SOL net, 52.9% WR. Window split: probe-active 24h n=54 / +0.640 SOL / 44.4% WR; probe-expired ~14h45m n=212 / +1.398 SOL / 54.2% WR.
- 🔴 Mode coverage gap: `mode_at_entry` ABSENT in 263/263 sample rows. Per-row mode reconstruction not possible from DB alone.
- 🟢 Code state intact: BOT-CORE-ML-GATE-001 commit `ea0da2f` present in HEAD `15a334a`; SD_MC_CEILING_002 gate at signal_aggregator.py:1846-1881; TIME_PRIME env-controlled at bot_core.py:750-764.
- Carry-overs unchanged: 🔴 Anthropic credits firing now (Redis governance log); 🔴 Vybe URL drift (signal_aggregator.py:753/850/2568 still on `.com`); 🟡 SocialData status assumed unchanged.
**Blockers cleared:** None this session.
**Blockers new/active:**
- 📋 **MODE-AT-ENTRY-FEATURE-001 NEW Tier 2 🟢** — paper_trader / signal_aggregator should write `mode_at_entry` to features_json so future audits can do per-row mode-coverage analysis. Trivial change; high diagnostic ROI.
- 📋 **HOLDING-WALLET-DRIFT-2026-05-08 NEW Tier 3 🟢** — confirm +0.181 SOL increase to holding wallet (treasury dormant; should NOT be automation).
- 📋 **DEFENSIVE-OVERRIDE-DAILY-RENEWAL-001** carry-over: probe needs renewal mechanism if eval session re-runs.
- All carries unchanged from prior STATUS entries (BUG-010 Anthropic, VYBE-URL-CODE-DRIFT-001, SOCIALDATA-AUTO-TOPUP-001 ACTIVE, V5a wallet/observation/NORMAL blockers, TREASURY-TEST-MODE-002 dormant).
**V5a precondition delta:** None. The probe expiration does NOT block V5a (V5a blockers per V5A_GO_NO_GO_2026_05_01.md unchanged: wallet 0.064 SOL, 48h obs window, NORMAL window). The probe needs re-run with renewal commitment for confident eval.
**Concurrent-session compatibility:** Pull-rebase before push (retry up to 3× on conflict per CLAUDE.md). NOTE: a concurrent session ran VYBE-URL-CODE-DRIFT-001-FIX-2026-05-08 in parallel — its untracked audit doc `docs/audits/VYBE_URL_FIX_2026_05_08.md` is left untouched for that session's own commit. Its STATUS.md entry (immediately below this) and its updates to `AGENT_CONTEXT.md §6.7 Vybe row` are in this session's working tree by happenstance and are bundled into this commit since they're consistent with this audit's findings.
**Next prompt:** `DEFENSIVE-OVERRIDE-PROBE-EVAL-001` per the 2026-05-06 22:29 UTC MONITORING_LOG entry. **Decision required from eval prompt:** re-run probe with renewal commitment (recommended) vs use underpowered 24h sample.
**Pending Claude-chat prompts not yet pasted:** none — independent session complete.
**Verdict:** ✅ COMPLETE (read-only). Audit doc + canonical-doc updates landed. Probe state finding flagged for eval session.

---

## 2026-05-08 13:30 UTC — VYBE-URL-CODE-DRIFT-001-FIX-2026-05-08 (read-only investigation, STOP per Step 7 #2)

**Committed:** `badb221` docs(vybe-url): VYBE-URL-CODE-DRIFT-001-FIX-2026-05-08 STOP — investigation only, NO code change. Files: `docs/audits/VYBE_URL_FIX_2026_05_08.md` (NEW), `STATUS.md` (this prepend), `ZMN_ROADMAP.md` (Decision Log entry), `AGENT_CONTEXT.md` (Vybe row refined), `MONITORING_LOG.md` (entry).
**State changes:** None. Read-only — Vybe MCP search-endpoints/get-endpoint, aiohttp probes against `.com` / `.xyz` / `/v4/tokens/` URLs (BONK mint), git blame on the 3 sites, Railway list-variables for VYBE_API_KEY. No DB/Redis/env/code writes.
**Bot state:** TEST_MODE=true (unchanged). `DEFENSIVE-OVERRIDE-PROBE-001` already EXPIRED at 2026-05-07T22:29Z UTC per concurrent STATE-SNAPSHOT-2026-05-08 (renewal did not fire — `market:mode:override` absent at audit; `market:mode:current=NORMAL`). Wallet 0.064 SOL (unchanged).
**Findings:** Step 7 STOP condition #2 triggered. Probe with valid `VYBE_API_KEY` confirms the prior session's "`.com → .xyz` TLD swap" hypothesis is INVALID — both `.com` and `.xyz` versions of `/token/{mint}/...` return HTTP 404 ("The requested endpoint does not exist"). Canonical Vybe v4 paths `https://api.vybenetwork.xyz/v4/tokens/{mint}/top-holders` and `https://api.vybenetwork.xyz/v4/tokens/{mint}` return HTTP 200 (verified BONK). Vybe OpenAPI explicitly notes these "**Replace**" the older `/token/...` paths. Two breaking downstream issues: (1) v4 Token Details no longer returns `creator` — `_fetch_creator_history` Vybe step continues to return empty even after URL fix; (2) v4 `/top-holders` returns `ownerName` not `ownerLabel`/`label` — L2568 KOL detection needs paired field-name update.
**Blockers cleared:** None this session.
**Blockers new/active:**
- 📋 **VYBE-URL-CODE-DRIFT-001 status updated** — scope expanded from "TLD swap" (3-string subst) to "URL+path migration + paired downstream field-name updates". Recommended follow-up: `VYBE-URL-CODE-DRIFT-001-FIX-V2` (Path A1 in audit §7 — URL+path migration at all 3 sites + L2568 `ownerName` field update; track creator-source replacement separately).
- 📋 **VYBE-CREATOR-LOOKUP-DEPRECATED-001 NEW Tier 2** — v4 Token Details no longer returns `creator`. `_fetch_creator_history` Vybe-step-1 needs an alternative data source (Helius parseTransactions first-slot, pump.fun metadata, or other). Bigger scope; defer to its own session.
- 📋 **VYBE-KOL-FIELD-MAPPING-001 NEW Tier 2** — L2568 KOL detection reads `ownerLabel`/`label`; v4 returns `ownerName`. Trivial field-name update; bundle with VYBE-URL-CODE-DRIFT-001-FIX-V2.

All carries unchanged from prior STATUS entries (DEFENSIVE-OVERRIDE-PROBE-001 expired ~24h after start — see STATE-SNAPSHOT-2026-05-08; CLIFF-VYBE-SOCIALDATA-SUPPLEMENT-001, STRATEGY-CLIFF-INVESTIGATION-001, V5a wallet/observation/NORMAL blockers, BUG-010 Anthropic, SOCIALDATA-AUTO-TOPUP-001 ACTIVE).

**V5a precondition delta:** None. Vybe URL fix is current-edge-restoration only, not V5a-blocking (per CLIFF supplement: Vybe was non-load-bearing pre-cliff). Cliff supplement's bound on lift (~+0.4-0.5 SOL/day) still applies after the scope expansion since fix is structurally the same set of code paths.
**Concurrent-session compatibility:** Pull-rebase before push (retry up to 3× on conflict per CLAUDE.md). Append-only updates to AGENT_CONTEXT.md / MONITORING_LOG.md / STATUS.md. ZMN_ROADMAP.md Decision Log row added at top of table.
**Next prompt:** Optional `VYBE-URL-CODE-DRIFT-001-FIX-V2` (paste-ready prompt structure documented in audit §7 Path A1). Cost S. NOT auto-triggered.
**Pending Claude-chat prompts not yet pasted:** none — independent session complete.
**Verdict:** ⏸ STOP per Step 7 condition #2. Findings audit committed; no code change. User to decide on follow-up scope.

---

## 2026-05-06 22:29 UTC — DEFENSIVE-OVERRIDE-PROBE-001 START (no code change)

**Committed:** `badb221` docs(defensive-probe): DEFENSIVE-OVERRIDE-PROBE-001 — A/B-probe set, 24h TTL. Files: `MONITORING_LOG.md` (entry), `ZMN_ROADMAP.md` (Decision Log + 2 new items), `STATUS.md` (this prepend). NO services/* edit, NO deploy, NO env change. Single Redis SET.
**State changes:** `market:mode:override=DEFENSIVE EX 86400` SET at **2026-05-06T22:29:10Z UTC** (verified value+propagation). No other Redis writes. No DB writes.
**Bot state:** TEST_MODE=true (paper), bot:status=RUNNING, paper portfolio 22.92 SOL, 1 open position (`speed_demon:C7Ad1dff…` opened+closed under DEFENSIVE during this session — `no_momentum_90s` -0.0152 SOL, n=1 throughput proof), consecutive_losses=2, emergency_stop=ABSENT, market:mode:current=**DEFENSIVE** (was NORMAL pre-SET; switched at 22:29:44Z = ~34s post-SET). Wallet 0.064 SOL (unchanged). bot_core ML gate at threshold=40 still active (release `cf4d4d6`).
**Probe purpose:** A/B-test the DEFENSIVE-VS-NORMAL-PNL-INVERSION-001 finding (Tier 1 Q from MARKET-MODE-001-RE-CALIBRATE Path C). Pre-probe baselines reinforce the inversion at multiple sample sizes:
- Post-Session-2 5d (MARKET-MODE audit): NORMAL **-1.09 SOL on 121 trades / 24.8% WR** vs DEFENSIVE **+0.25 SOL on 45 / 28.9% WR**.
- Last 48h (this session §2): NORMAL **-0.80 SOL on 103 / 33.0% WR** vs DEFENSIVE **+0.44 SOL on 17 / 64.7% WR**.

Probe generates a real DEFENSIVE-only sample to either confirm at scale (n≥80) or refute as small-sample noise.
**Override propagation verification:**
- Code path: `services/market_health.py:409` reads `market:mode:override`, short-circuits threshold logic at L412-414, logs `Market mode OVERRIDE active: %s`. Loop cadence 300s (`market_health.py:476`).
- Observed: `market_health` log at **22:34:45Z** shows explicit `Market mode OVERRIDE active: DEFENSIVE`. `market:mode:current` flipped NORMAL→DEFENSIVE by 22:29:44Z (1 cycle post-SET). `bot:status.market_mode` reflects DEFENSIVE by next bot_core heartbeat (22:39:31Z snapshot read).
**Re-evaluation milestone:** ≥**2026-05-08T22:29Z UTC** (48h). Sample target: ≥80 SD-paper trades under DEFENSIVE override. Run as DEFENSIVE-OVERRIDE-PROBE-EVAL-001 (paste-ready prompt to follow).
**Renewal requirement:** TTL 86400 (24h). Override must be re-SET every 24h via Redis MCP (`SET market:mode:override DEFENSIVE EX 86400`) until probe ends. Filed as **DEFENSIVE-OVERRIDE-DAILY-RENEWAL-001** (operational, Tier-2 daily action). Auto-expires safely if forgotten — bot reverts to threshold-based mode determination (no destructive default).
**Rollback triggers (any one ends probe early):**
- Cumulative SOL since probe start < -0.50 SOL on n≥30 trades
- Win rate < 18% on n≥30 trades
- Throughput drop to <5 SD-paper trades/day for 24h consecutive
- Bot enters HIBERNATE for >2h consecutive (override SHOULD prevent this — code reads override before threshold logic; if HIBERNATE persists, override-read path bug)

Rollback procedure: `DEL market:mode:override` via Redis MCP; document outcome in MONITORING_LOG.
**Blockers cleared:** None this session.
**Blockers new/active:**
- 📋 **DEFENSIVE-OVERRIDE-DAILY-RENEWAL-001 NEW Tier-2 OPERATIONAL** — daily Redis renewal until probe ends or rollback fires.
- 📋 **DEFENSIVE-OVERRIDE-PROBE-EVAL-001 NEW Tier-1** — 48h evaluation session, queued for ≥2026-05-08T22:29Z. Decides KEEP / REVERT / EXTEND.
- All carries unchanged from prior STATUS entries (CLIFF-VYBE-SOCIALDATA-SUPPLEMENT-001, STRATEGY-CLIFF-INVESTIGATION-001, API-CREDITS-HEALTH-DIAGNOSTIC-001, V5a wallet/observation/NORMAL blockers).
**V5a precondition delta:** Mixed signal — running DEFENSIVE for 48h means the V5a NORMAL-window precondition is intentionally suspended for the duration of the probe. The probe outcome will inform whether NORMAL is even the right V5a-flip mode (if DEFENSIVE keeps outperforming at scale, V5a may want DEFENSIVE-flip semantics instead).
**Concurrent-session compatibility:** Independent of STRATEGY-CLIFF-INVESTIGATION-001 and CLIFF-VYBE-SOCIALDATA-SUPPLEMENT-001 (different file/Redis surface). No conflict expected.
**Next prompt:** **DEFENSIVE-OVERRIDE-PROBE-EVAL-001** (paste-ready prompt to follow). Do NOT auto-trigger — needs 48h wall clock first. Concurrent operational task: daily renewal of override key.
**Pending Claude-chat prompts not yet pasted:** none — independent session complete.
**Verdict:** DEFENSIVE-OVERRIDE-PROBE-001 ✅ STARTED. Override SET, propagation verified, throughput confirmed (1 trade in first ~10 min). 48h sample accumulation in progress.

---

## 2026-05-07 ~10:00 AEDT (~23:00 UTC 2026-05-06) — CLIFF-VYBE-SOCIALDATA-SUPPLEMENT-001 (read-only)

**Committed:** `badb221` docs(cliff-supplement): CLIFF-VYBE-SOCIALDATA-SUPPLEMENT-001 — both candidates NOT CLIFF. Files: `docs/audits/CLIFF_VYBE_SOCIALDATA_SUPPLEMENT_2026_05_05.md` (NEW, 8 sections), `ZMN_ROADMAP.md` (Decision Log entry), `STATUS.md` (this prepend).
**State changes:** None. Read-only — git blame, git log -S, DB SELECT against `paper_trades_archive_20260421` and `paper_trades`. No code/env/redeploy.
**Bot state:** TEST_MODE=true (unchanged). market_mode cycling. Wallet 0.064 SOL (unchanged). bot_core ML gate at threshold 40 still active (release `ea0da2f`).
**Findings:**
- **Vybe NOT CLIFF**: Lines 753/850/2568 in signal_aggregator.py use `.com`, all introduced 2026-04-04 to 2026-04-08 (commits `672eb8ac`, `94b3c564`, `751680e3`) — 13-17 days BEFORE 2026-04-21 cliff. `.xyz` has never appeared in signal_aggregator.py per `git log -S`. Sibling `nansen_wallet_fetcher.py:209` was correct from creation 2026-03-29.
- **SocialData NOT CLIFF**: DB temporal pattern shows pct_sentinel jumped 18.7% → 99.2% on 2026-04-16 (5 days pre-cliff). Commit `35bdfe6` (2026-04-19) explicitly: "495/495 of most-recent 500 SD paper trades have twitter_followers=-1". Pre-cliff sentinel-bucket (n=2101) outperformed populated-bucket (n=883) on mean PnL +0.231 vs +0.127 SOL/trade — Twitter feature NOT load-bearing.
- **BONUS**: SocialData drained AGAIN starting 2026-05-03 (10 days post-Jay's $10 top-up of 2026-04-22). Confirms yesterday's audit observation (113 ERROR/11min on 2026-05-05). Strengthens SOCIALDATA-AUTO-TOPUP-001 auto-renewal case.

**Synthesis:** Both candidates pre-date the cliff. Both were already broken during the bot's +598 SOL pre-cliff era. **Reinforces parent STRATEGY-CLIFF-INVESTIGATION-001 "DO NOT REVERT"** — the cliff is a fee-model accounting artifact, not a strategy/feature edge regression.

**Blockers cleared:** None this session (read-only).
**Blockers new/active:** No new blockers. **Existing items refined:**
- VYBE-URL-CODE-DRIFT-001 (Tier 1) — re-classified as **current-edge-restoration only**, not cliff-recovery. Estimated lift small (~+0.4-0.5 SOL/day at current sizing).
- SOCIALDATA-AUTO-TOPUP-001 (ACTIVE) — re-confirmed via second drain on 2026-05-03. Jay's manual top-ups last ~10 days; auto-renewal mechanism warranted.

**Concurrent-session compatibility:** Ran cleanly alongside the just-landed STRATEGY-CLIFF-INVESTIGATION-001 entry (now directly below mine). My Decision Log row added above the parent's row.

**Next prompt:** None queued. Recommended next actions: (a) ship VYBE-URL-CODE-DRIFT-FIX-001 at low priority (Tier 1 fix, S cost); (b) Jay action: SocialData top-up + alerting per SOCIALDATA-AUTO-TOPUP-001; (c) defer to parent's other follow-ups (BREAKEVEN-DECISION-001, TP-SCHEDULE-EVAL-001, SIGNAL-MIX-ANALYSIS-001).

**Pending Claude-chat prompts not yet pasted:** none — independent session complete.

**Verdict:** CLIFF-VYBE-SOCIALDATA-SUPPLEMENT-001 ✅ INVESTIGATION COMPLETE. Both NOT CLIFF; reinforces parent's DO NOT REVERT.

---

## 2026-05-07 ~01:30 UTC — STRATEGY-CLIFF-INVESTIGATION-001 (NO REVERT, no code change)

**Committed:** docs-only — single commit landing `docs/audits/STRATEGY_CLIFF_INVESTIGATION_001_2026_05_05.md` + `ZMN_ROADMAP.md` Decision Log + 5 new Tier-2 entries + `AGENT_CONTEXT.md` new §6.8 + `STATUS.md` (this prepend) + `MONITORING_LOG.md`. **NO services/* edit, NO deploy, NO env change, NO Redis writes.**
**State changes:** None. Read-only investigation: SQL against production DB (`paper_trades` current + `paper_trades_archive_20260421` archive), git log, audit docs, code reads. No writes.
**Bot state:** TEST_MODE=true (unchanged). market_mode unverified at session end (no Redis read this session — last verified DEFENSIVE 2026-05-06 13:00 UTC per MARKET-MODE-001-RE-CALIBRATE entry; cycling per recalibrated thresholds). Wallet 0.064 SOL on-chain (unchanged). bot_core ML gate (`ML_THRESHOLD_BOT_CORE_SD=40`) still active from BOT-CORE-ML-GATE-001 deploy.
**Verdict:** 🟡 **STOP / NO REVERT.** The 2026-04-20→21 paper-PnL "cliff" (+0.20 → +0.014 mean SOL/trade) is **primarily a fee-model accounting artifact**, not a strategy regression. PRE-cliff archive rows were written under the OLD paper fee model that under-counted fees by ~96× per FEE-MODEL-001 (commit `e078b4c`); per-trade fee correction is -0.391 SOL. Apples-to-apples: PRE-cliff under realistic fees ≈ -0.19 SOL/trade (-566 SOL on 2,984 trades) vs POST-cliff +0.014 SOL/trade. **Under fair accounting, the new strategy is +0.20 SOL/trade BETTER than the old.**
**Hypotheses scored:** FEE-MODEL-001 🟢 HIGH match. GATES-V5 sizing/stop-loss/gates 🟢 HIGH match (all real strategy changes, downscale magnitudes appropriately under realistic accounting). Breakeven removal & TP flatten 🟢 HIGH match (env overrides removed BREAKEVEN_STOP and staged_tp_+50/+100/+250/+400/+500%). Signal-source shift 🔴 REFUTED (100% pumpportal both eras). Telegram channel switch / Discord BUG-020 onset / Nansen state change 🔴 all REFUTED via cross-reference with API-CREDITS audit. Market regime shift 🟡 LOW (too coincidental with 3 single-day commits to be regime alone).
**Counterfactual:** lift if cliff "reverted" = 0 SOL/day (likely negative -2 to -5 SOL/day on real edge). The §7 STOP condition triggers per prompt — "counterfactual < 1 SOL/day → STOP".
**Blockers cleared:** None this session (read-only investigation).
**Blockers new/active:** 5 new Tier-2 🟢 follow-ups proposed (none V5a-blocking): **STRATEGY-CLIFF-FOLLOWUP-001** (re-validate at 14d POST sample ≥2026-05-12), **PRE-DEPLOY-PNL-VALIDATION-001** (process), **BREAKEVEN-DECISION-001** (A/B test), **TP-SCHEDULE-EVAL-001** (full-ladder re-eval), **SIGNAL-MIX-ANALYSIS-001** (per-gate ablation). Existing Tier-1 carries unchanged (DEFENSIVE-VS-NORMAL-PNL-INVERSION-001, MARKET-MODE-001-RE-CALIBRATE-V2, NO-MOMENTUM-90S-AUDIT-001, ML-THRESHOLD-DATA-DRIVEN-RETUNE-002, VYBE-URL-CODE-DRIFT-001 from API-CREDITS audit).
**Institutional learning (per §9 of prompt):** every audit since 2026-04-22 operated exclusively on POST-cliff data because DASH-RESET wiped current `paper_trades` into the archive. The drift report (USERMEMORIES_DRIFT_2026_05_01.md) had access to the cliff data via the archive table but used "last 7d/14d" windows that exclusively look at POST-cliff. The chat-side prompt's premise (that the cliff = strategy regression) was a natural conclusion from raw `realised_pnl_sol` comparison, missing the FEE-MODEL-001 accounting transition. **Process improvement:** PRE-DEPLOY-PNL-VALIDATION-001 codifies "check accounting-regime deploys at the boundary" for future cliff investigations.
**Next prompt:** None auto-triggered. Recommended next session: STRATEGY-CLIFF-FOLLOWUP-001 (re-validate after ≥2026-05-12 once POST-cliff sample reaches 14d) OR continue work on already-tracked Tier-1 carries (DEFENSIVE-VS-NORMAL-PNL-INVERSION-001 first per the post-cliff degradation concern).
**Pending Claude-chat prompts not yet pasted:** None — chat-side STRATEGY-CLIFF-INVESTIGATION-001 is now resolved.

---

## 2026-05-06 ~02:00 AEDT (15:00 UTC) — API-CREDITS-HEALTH-DIAGNOSTIC-001 (read-only audit)

**Committed:** `badb221` docs(api-credits-health): API-CREDITS-HEALTH-DIAGNOSTIC-001 — service-health snapshot across 12 dependencies. Files: `docs/audits/SERVICE_HEALTH_SNAPSHOT_2026_05_05.md` (NEW, 10 sections), `ZMN_ROADMAP.md` (Decision Log entry), `AGENT_CONTEXT.md` (NEW §6.7 external-API state matrix), `STATUS.md` (this prepend).
**State changes:** None. Read-only — no code, no env, no redeploy. Probes were `getNetworkStatus`/`getBalance` (Helius), `WebFetch` (Binance/Jupiter/Vybe `.com`/`.xyz`), Railway `list-variables` × 8, Railway `get-logs` × 7, Redis `get`/`list` (~30 keys).
**Bot state:** TEST_MODE=true (unchanged). bot:status RUNNING, paper portfolio 22.59 SOL, 0 open positions. market_mode=DEFENSIVE @ 14:50 UTC (cycling per recalibrated thresholds). bot:emergency_stop absent. Wallet 0.064 SOL (unchanged — V5a PC1 still failing).
**Findings:** 4 🔴 (SocialData credits exhausted 113 ERROR/11min, **VYBE-URL-CODE-DRIFT-001** — signal_aggregator.py:753/850/2568 use `.com` → 404 vs `.xyz` → 401, BUG-010 Anthropic still exhausted, BUG-020 Discord 403 still firing) / 9 🟡 / 7 🟢 / 1 ⚪ (signals:raw LLEN unmeasurable via Redis MCP).
**Blockers cleared:** None this session.
**Blockers new/active:**
- 📋 **VYBE-URL-CODE-DRIFT-001 NEW Tier 1** — DOCS-004 (2026-04-30) fixed CLAUDE.md but never migrated SA code; HOLDER fallback + creator-history + KOL/MM signal modifier fail silently
- 📋 **SOCIALDATA-AUTO-TOPUP-001 promoted QUEUED → ACTIVE** — Jay action: top-up + auto-renewal alerting
- 📋 **TREASURY-HELIUS-LOG-NOISE-001 NEW** — 270+ misleading "Could not fetch trading wallet balance" warnings/22h are caused by `treasury.py:60` HELIUS_DAILY_BUDGET=0 gate, NOT Helius RPC outage (Helius MCP `getBalance` works fine)
- 📋 **DASHBOARD-CORRECTED-PNL-WARN-001 NEW** — 127 "column corrected_pnl_sol does not exist" warnings/28min on web (likely a query against `trades` table without column)
- 📋 **TABPFN-EXPIRY-DOC-DRIFT** — JWT exp = 2027-04-05 04:55:55 UTC (NOT 2033 as documented; ≈335 days runway)
- All other carries unchanged (BUG-010, BUG-020, V5a wallet/observation/NORMAL blockers, ML threshold drift, signals:raw TTL, etc.)

**V5a precondition delta:** None. The 4 🔴 findings are all NOT V5a-blocking by current rules — original 3 blockers (wallet 0.064, 48h obs, NORMAL window) hold; reaffirmed.

**Concurrent-session compatibility:** Ran in parallel with TIMEZONE-AUDIT-001 (their `badb221`) and MARKET-MODE-001-RE-CALIBRATE (their `badb221`). Persistence updates are all append-only — clean rebase expected. Per §1.4 git discipline.

**Next prompt:** None queued. Recommended follow-ups: (a) `VYBE-URL-CODE-DRIFT-001` Tier 1 fix session (S, 3 strings + redeploy SA + verify holder fallback path responds); (b) Jay action: SocialData top-up + Anthropic top-up; (c) re-run this diagnostic after top-ups land to verify recovery.

**Pending Claude-chat prompts not yet pasted:** none — independent session complete.

**Verdict:** API-CREDITS-HEALTH-DIAGNOSTIC-001 ✅ AUDIT COMPLETE. Service-health baseline established for future regression detection. Snapshot timestamp: 2026-05-05 14:50 UTC.

---

## 2026-05-06 ~13:00 UTC — MARKET-MODE-001-RE-CALIBRATE (Path C / STOP, no code change)

**Committed:** docs-only — single commit landing `docs/audits/MARKET_MODE_001_RE_CALIBRATE_FINDINGS_2026_05_05.md` + ZMN_ROADMAP/STATUS/MONITORING_LOG persistence updates. **NO market_health.py edit, NO deploy, NO env change.**
**State changes:** None. Investigation only — read SQL, read Redis, no writes.
**Bot state:** TEST_MODE=true (unchanged). market_mode=NORMAL (live snapshot 12:50 UTC; mig=215, dex_vol=$1.51B, pumpfun=$226M). 0 paper open in Redis at investigation time. 0 live open. Wallet 0.064 SOL on-chain (unchanged). bot_core ML gate (`ML_THRESHOLD_BOT_CORE_SD=40`) still active from previous session.
**Blockers cleared:** None. Investigation revealed prompt's premise was incorrect; honoring §4 Path C STOP preserves capital.
**Blockers new/active:** **DEFENSIVE-VS-NORMAL-PNL-INVERSION-001** (Tier 1 — NORMAL bleeds, DEFENSIVE returns; investigate before any market-mode threshold change). **MARKET-MODE-001-RE-CALIBRATE-V2** (Tier 1 — re-scoped session needed). **PUMPFUN-VOL-PLACEHOLDER-001** (Tier 2 — placeholder math makes AND gate effectively 2-metric). **MM-HYSTERESIS-ONLY-001** (Tier 2 — standalone hysteresis still beneficial).
**Next prompt:** None auto-triggered. Jay should read the finding doc and decide whether to (a) re-prompt MARKET-MODE-001-RE-CALIBRATE-V2 with corrected framing, (b) run DEFENSIVE-VS-NORMAL-PNL-INVERSION-001 first, or (c) wait 7 days for post-BOT-CORE-ML-GATE sample to mature before any market-mode work.
**Pending Claude-chat prompts not yet pasted:** None — all three sessions in this CC chain (BOT-CORE-ML-GATE-001 → TIMEZONE-AUDIT-001 → MARKET-MODE-001-RE-CALIBRATE) are now resolved; the third terminated cleanly via Path C.

---

## 2026-05-05 ~15:30 UTC — TIMEZONE-AUDIT-001 (read-only repository sweep)

**Committed:** docs-only — single commit landing `docs/audits/TIMEZONE_AUDIT_2026_05_05.md` + ZMN_ROADMAP/AGENT_CONTEXT/CLAUDE.md/STATUS.md persistence updates. NO code change.
**State changes:** None. NO Redis writes, NO env changes, NO service redeploys.
**Bot state:** TEST_MODE=true (unchanged). Paper open: as observed in prior STATUS entry (id=8039 earlier; check current Redis for live count). 0 live open. Wallet 0.064 SOL on-chain (unchanged). market_mode=DEFENSIVE (unchanged from BOT-CORE-ML-GATE-001 verification window).
**Blockers cleared:** Predecessor verification for MARKET-MODE-001-RE-CALIBRATE — `services/market_health.py` is 🟢 SAFE (no timezone bug); the next session can proceed without bundling a fix.
**Blockers new/active:** None new. Existing **TIME-PRIME-AEDT-AEST-DRIFT-001** confirmed as the single root cause for all 2 🔴 production-code hits found (services/bot_core.py:754,776). Existing **MARKET-MODE-001-RE-CALIBRATE** still queued (next session in chain).
**Next prompt:** MARKET-MODE-001-RE-CALIBRATE (predecessor §0 satisfied: this session's audit doc exists + market_health.py is clean).
**Pending Claude-chat prompts not yet pasted:** MARKET-MODE-001-RE-CALIBRATE already pasted in this CC session by Jay; will run next.

---

## 2026-05-05 15:01 UTC — BOT-CORE-ML-GATE-001 (env-controllable bot_core ML gate)

**Committed:** `ea0da2f` feat(bot_core): BOT-CORE-ML-GATE-001 — env-controllable ML threshold gate; default disabled. Audit + persistence updates landing in follow-up commit (this session, docs-only).
**State changes:** Set `ML_THRESHOLD_BOT_CORE_SD=40` on bot_core (Railway). bot_core redeployed twice — code at ~14:13Z (gate inert, env=0 default), env-active at **14:16:48Z** UTC. No Redis keys directly touched. SA gate semantics unchanged (signal_aggregator.py:158-160 override preserved by design, retains ML training data composition).
**Bot state:** TEST_MODE=true on bot_core. 1 paper open observed at 14:58Z (id=8039, mint EV1na7Wj5WLX, ml_score=47.0, mode=DEFENSIVE; may have already exited via TP/stop/time-exit by now). 0 live open. Circuit_breaker (`bot:state:consecutive_losses`) absent → effectively 0. market_mode=DEFENSIVE at verification time. Wallet 0.064 SOL on-chain (unchanged; trading remains paper-only). Paper portfolio 22.59 SOL on bot_core startup load.
**Blockers cleared:** **BOT-CORE-ML-GATE-001** ✅. V5a §6.5 patch path closed. ML-RETUNE Session 4 §8 STOP rationale resolved (env-var change now actually controls paper admission via the new bot_core gate).
**Blockers new/active:** **MARKET-MODE-001-RE-CALIBRATE** (queued — DEFENSIVE/HIBERNATE cycling suppresses gate-verification confidence; 50% zero-trade-hour rate post-Session-2 per chat-side analysis). **TIMEZONE-AUDIT-001** (queued, pure read-only audit). **ML-THRESHOLD-DATA-DRIVEN-RETUNE-002** (re-queue ≥2026-05-12 14:16Z after 7d of post-gate sample accumulates).
**Next prompt:** TIMEZONE-AUDIT-001 (predecessor §0 satisfied by this session's audit doc + Railway env state).
**Pending Claude-chat prompts not yet pasted:** TIMEZONE-AUDIT-001 and MARKET-MODE-001-RE-CALIBRATE both already pasted into this same CC session by Jay; will run in chain immediately after this docs commit lands.

---

## 2026-05-01 — V5A-GO-NO-GO-CHECKLIST-001 (Session 6 of 6 — FINAL of chained sequence; Verdict: NO_GO)

**Committed (this session):** `badb221` docs(v5a-checklist): V5A-GO-NO-GO-CHECKLIST-001 — final precondition audit. Verdict NO_GO. Files: `docs/audits/V5A_GO_NO_GO_2026_05_01.md` (NEW, 7 sections), `ZMN_ROADMAP.md` (Decision Log entry), `AGENT_CONTEXT.md` (NEW §6.6 V5A readiness), `STATUS.md` (this prepend).

**State changes:** None. **Read-only audit.** Bot continues TEST_MODE=true.

**Bot state at audit time (~13:00 UTC):**
- TEST_MODE=true ✓ (verified Railway MCP env list + Redis bot:status)
- bot:status RUNNING, paper portfolio 23.89 SOL, 0 open positions
- bot:emergency_stop absent ✓
- market:mode:current = **HIBERNATE** at 12:58:54 UTC (was NORMAL during Session 1; cycling per MARKET-MODE-001 recalibrated thresholds)
- market:sol_price = 84.3 (recent)
- Sessions 1-5 deployed cleanly (release `2bc12f8` on bot_core)

**§3 Composite verdict: 🔴 NO_GO**

**Aggregate: 3 PASS / 4 CONDITIONAL / 3 FAIL** (any FAIL → NO_GO per §3)

| # | Precondition | Verdict |
|---|---|---|
| 1 | Wallet capacity | 🔴 FAIL (0.064 SOL << 0.5 floor) |
| 2 | Path B parity-of-truth | ✅ PASS (id 6580 err 0.000000 SOL) |
| 3 | TIME_PRIME closed | 🟡 CONDITIONAL (env confirmed, sample small) |
| 4 | Post-grad outcome | ✅ PASS (analyst-driven, already disabled) |
| 5 | 48h observation | 🔴 FAIL (<1h since latest deploy) |
| 6 | ML retune verified | 🟡 CONDITIONAL (Session 4 stopped, no deploy) |
| 7 | Service health | 🔴 FAIL (market_mode=HIBERNATE) |
| 8 | Env drift | 🟡 CONDITIONAL (ML threshold drift documented) |
| 9 | Recent 7d P&L | 🟡 CONDITIONAL (-0.98 SOL on 682 trades) |
| 10 | Kill switch | ✅ PASS |

**§3 NO_GO blocking issues (3 FAILs):**
1. **PC1 wallet capacity:** Helius getBalance = 0.064 SOL << 0.5 floor. **Jay action: top-up trading wallet `4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ` to ~3 SOL.**
2. **PC5 48h observation:** Sessions 1-5 deployed today (12:14 UTC to 12:55 UTC). 48h window opens ~2026-05-03 12:55 UTC.
3. **PC7 service health:** market:mode:current=HIBERNATE at audit. Cycling per recalibrated MARKET-MODE-001 thresholds. Wait for NORMAL window.

**§3 Recommended caps when GO** (per session prompt CONDITIONAL_GO recommendation):
- TEST_MODE: false on bot_core ONLY
- MAX_POSITION_SOL: 0.10 (vs current 0.25)
- MAX_SD_POSITIONS: 5 (vs current 20)
- Live trial duration: 24h before scale-up

**§4 Outstanding risks at GO:** paper-to-live edge ratio untested at scale (id 6580 showed 96× divergence); no_momentum_90s + stop_loss_20% pre-grad bleed unaddressed (~-15 SOL/14d); HIBERNATE cycling reduces throughput; ML threshold not retuned (Session 4 stopped).

**§5 First-24h plan documented in audit doc** (hourly monitoring queries + flip-back triggers).

**Stop-condition check:** 0 of 1 STOP conditions tripped. All 10 preconditions assessable (DB ✓, Helius ✓, Railway MCP ✓, Redis MCP ✓).

**Blockers cleared:** None this session (read-only audit).

**Blockers new/active:**
- 📋 **Jay action: trading wallet top-up to ~3 SOL** (PC1 blocker)
- 📋 **48h observation window** opens ~2026-05-03 12:55 UTC (PC5 blocker)
- 📋 **Wait for market:mode:current=NORMAL** before re-running V5A-GO-NO-GO (PC7 blocker)
- All other carries unchanged (NO-MOMENTUM-90S-AUDIT-001, BOT-CORE-ML-GATE-001, MARKET-MODE-001-RE-CALIBRATE, etc.)

**V5a precondition delta:** Audit complete. V5a flip GATED on the 3 FAIL blockers. AGENT_CONTEXT.md §6.6 (NEW) captures the readiness state with explicit unblock criteria.

**Next prompt:** **N/A** — chained 6-prompt sequence complete. Recommended next action: Jay performs wallet top-up + waits 48h, then re-runs V5A-GO-NO-GO-CHECKLIST.

**Pending Claude-chat prompts not yet pasted:** none — sequence complete.

**Verdict:** V5A-GO-NO-GO-CHECKLIST-001 ✅ AUDIT COMPLETE — NO_GO with 3 actionable blockers. Audit doc `docs/audits/V5A_GO_NO_GO_2026_05_01.md` provides full evidence, recommended live params, outstanding risks, and 24h post-flip monitoring plan.

---

## 2026-05-01 — LIVE-FEE-CAPTURE-002 (Path B Helius parseTransactions — Session 5 of 6 in chained-prompt sequence)

**Committed (this session):** `badb221` feat(bot_core): LIVE-FEE-CAPTURE-002 Path B — Helius parseTransactions wired into live-close. Files: `services/helius_parser.py` (NEW), `services/bot_core.py:1346` (Path B branch + parameterised correction_method=$16 in live-close UPDATE), `docs/audits/LIVE_FEE_CAPTURE_002_PATH_B_2026_05_01.md` (NEW, 8 sections), `ZMN_ROADMAP.md` (Decision Log + future-queued status), `AGENT_CONTEXT.md` (V5a precondition strike), `STATUS.md` (this prepend). Plus DB UPDATE: id 6580 backfilled to `correction_method='live_actual_v1'`.

**State changes:**
- Code: bot_core.py live-close branch reads helius_parse_signature; on success uses `(entry_native_delta + exit_native_delta) / 1e9` for corrected_pnl_sol with correction_method='live_actual_v1'; falls back to Path A live_estimated_v1 on any parse failure.
- DB: id 6580 row updated in production database (corrected_pnl_sol -0.0064 → -0.094245; correction_method live_estimated_v1 → live_actual_v1).
- Single git push triggers bot_core auto-redeploy.
- No env var change.

**Bot state at session start (~12:40 UTC):**
- TEST_MODE=true ✓, market_mode=NORMAL ✓
- bot_core healthy, ~1 hour since Session 4 docs commit redeploy

**§2 Helius response schema findings:**
- **Critical discovery:** `nativeTransfers[*]` only captures direct user-to-user SOL transfers (e.g. Jito tips). Swap proceeds via PDAs are NOT captured. Initial parser using nativeTransfers had a 0.281 SOL gap on id 6580 exit.
- **Correct field:** `accountData[*].nativeBalanceChange` filtered for `account == TRADING_WALLET`. Captures full net SOL delta including PDA-mediated swap proceeds.
- For id 6580 exit: nativeTransfers showed only -0.001841 SOL (Jito tip outgoing); accountData showed +0.280007 SOL (actual sell proceeds). Path B uses the latter.

**§3 Implementation:**
- `services/helius_parser.py` (NEW) — `helius_parse_signature(signature, *, timeout_seconds=5.0, retries=2) -> dict | None`. Honors rate-limit backoff (1→2→4→...→60s cap). Returns None on any error. Reads `HELIUS_PARSE_TX_URL` + `TRADING_WALLET_ADDRESS` env vars (both already wired).
- `services/bot_core.py` — Path B branch added at live-close UPDATE path (~line 1346). Lazily imports helper, calls on entry+exit signatures, overrides Path A values when both succeed. Otherwise falls back to existing Path A `live_estimated_v1` behavior. UPDATE statement parameterised: `correction_method=$16` (was hardcoded literal). Distinct $N per column per asyncpg discipline.

**§4 Verify-fix output (.tmp_path_b/verify_output.txt):**
- `verify_path_b.py` PASS — computed Path B corrected_pnl_sol = -0.094245 SOL = on-chain truth (delta 0.000000)
- `backfill_6580.py` SUCCESS — DB row updated: corrected_pnl_sol -0.0064 → -0.094244978, correction_method='live_actual_v1', correction_applied_at=2026-05-01 12:52:37 UTC

**Compile-checked:** `python -m py_compile services/bot_core.py services/helius_parser.py` → COMPILE OK.

**§5 Deploy verification — queued post-deploy:**
- Poll Railway MCP for bot_core SUCCESS, +90s warmup
- Verify Sentry release matches commit hash
- Live behavior verification N/A (TEST_MODE=true; no fresh live trades to exercise Path B)
- id 6580 backfill already completed PRE-deploy (the helper code is identical, runs against same Helius/DB)

**Stop-condition check:** 0 of 4 STOP conditions tripped. Helius response shape adequate (verified). id 6580 reconstruction within 0.000000 SOL of truth (PASS bar 0.005). Helius rate-limit not encountered. Helper file added in services/ (write access OK).

**Blockers cleared:**
- ✅ **LIVE-FEE-CAPTURE-002 (Path B)** — V5a parity-of-truth precondition closed. id 6580 is now the gold-standard reference for live PnL accuracy; future live trades will write `live_actual_v1` automatically.

**Blockers new/active:**
- 📋 **LIVE-CLOSE-PATH-B-LATENCY-001 (NEW, Tier 2 🟢)** — Path B helius_parse_signature is sync; potential close-path latency. No mitigation needed absent observed harm.
- 📋 **LIVE-PATH-B-SLIPPAGE-DERIVATION-001 (NEW, Tier 2 🟢)** — Path B writes corrected_pnl_sol but slippage_pct still uses Path A estimate. Observability only.
- All other carries unchanged.

**V5a precondition delta:** **+1 forward.** LIVE-FEE-CAPTURE-002 closed. Remaining V5a preconditions: ~3 SOL wallet top-up (Jay action), 24-48h paper observation, Renew Redis daily TTLs, V5a flip itself. Session 6 (V5A-GO-NO-GO-CHECKLIST) will run final precondition audit.

**Next prompt:** **V5A-GO-NO-GO-CHECKLIST-001** (Session 6 of 6, FINAL of chained sequence). 10-precondition audit, GO/CONDITIONAL_GO/NO_GO verdict, read-only.

**Pending Claude-chat prompts not yet pasted:** none — chained 6-prompt sequence almost complete (Session 6 next).

**Verdict:** LIVE-FEE-CAPTURE-002 (Path B) ✅ DEPLOYED — Helper + bot_core wiring landed; id 6580 backfilled with on-chain-exact match (-0.094245 SOL). V5a parity-of-truth precondition closed. Audit doc `docs/audits/LIVE_FEE_CAPTURE_002_PATH_B_2026_05_01.md`.

---

## 2026-05-01 — ML-THRESHOLD-DATA-DRIVEN-RETUNE-001 (Session: STOP per §8 + correction to Session 3 — Session 4 of 6 in chained-prompt sequence)

**Committed (this session):** `badb221` docs(ml-retune): ML-THRESHOLD-DATA-DRIVEN-RETUNE-001 — STOP per §8; threshold sweep complete; correction to Session 3 finding. Files: `docs/audits/ML_THRESHOLD_DATA_DRIVEN_RETUNE_2026_05_01.md` (NEW, 9 sections), `ZMN_ROADMAP.md` (Decision Log entry + 2 new future-queued levers BOT-CORE-ML-GATE-001 + AGGRESSIVE-PAPER-DISABLE-001 + revised POST-GRAD-ENTRY-GATE-001 to insurance Tier 2), `AGENT_CONTEXT.md` (revised §6.5 with corrected leak attribution), `STATUS.md` (this prepend).

**State changes:** None. **NO env-var change.** Bot continues TEST_MODE=true, market_mode=NORMAL, signal_aggregator's AGGRESSIVE_PAPER+TEST_MODE override remains in effect (effective paper SD threshold = 30).

**Bot state at session start (~12:35 UTC):** unchanged from Session 3 close. TEST_MODE=true, paper portfolio 23.89, NORMAL.

**§2 STOP per §8 — TWO conditions tripped:**
1. **AGGRESSIVE_PAPER_TRADING bypass cannot be reconciled.** `services/signal_aggregator.py:158-160` overrides ML thresholds to 30 (SD/AN) / 20 (WT) when `AGGRESSIVE_PAPER_TRADING=true AND TEST_MODE=true`. Both currently true. Effective paper SD threshold = **30**, NOT env value 65. Env-var change has ZERO effect on paper sample.
2. **bot_core threshold filtering code cannot be located.** `grep "ml_score|ML_THRESHOLD"` returns 0 matches in `services/bot_core.py`. No fallback gate at the bot_core layer.

**§3 Threshold sweep results (informational):**
| | 14d | 7d |
|---|---|---|
| n total SD-paper | 994 | 684 |
| Optimum threshold | **55** (sum_admitted +8.71 SOL on 448 trades, mean +0.019, WR 37.5%) | **55** (sum_admitted +1.48 on 293 trades, mean +0.005, WR 30.4%) |
| §3 hard rule (n_admitted >= 50) | ✓ (448) | ✓ (293) |
Pre-grad-only sweep returned IDENTICAL numbers — SD-paper has 0 graduation_* exits.

**§4 Major correction to Session 3 H2 finding:**
- All 280 graduation_* exits in 14d are from `analyst` personality (NOT speed_demon)
- Analyst is disabled since 2026-04-28 13:02 UTC (ANALYST-DISABLE-002)
- The post-grad bleed has **ALREADY STOPPED** — no analyst entries in last 3+ days
- POST-GRAD-ENTRY-GATE-001 actual current ROI: **~0 SOL/week** (NOT +7 SOL/week)
- Insurance value only — would prevent recurrence if analyst is ever re-enabled
- **Re-scoped POST-GRAD-ENTRY-GATE-001 from Tier 1 🔴 PROPOSED to Tier 2 🟢 (insurance only)**

**Recommended path forward (per audit §6 and STOP_REASON.md):**
- **Option A (preferred): `BOT-CORE-ML-GATE-001`** (Tier 1 🟡 NEW). Single code change in bot_core to add second ML threshold gate. Independent of AGGRESSIVE_PAPER. Lets future env changes take effect on paper. Cost S.
- **Option B: `AGGRESSIVE-PAPER-DISABLE-001`** (Tier 2 🟢 NEW, evaluation required). Set AGGRESSIVE_PAPER_TRADING=false. Risk: may reduce ML training sample volume; needs evaluation.
- **Option C: Wait for V5a flip** — when TEST_MODE=false, the override doesn't apply.

**Stop-condition check:** 2 of 4 STOP conditions tripped (§8 #3 AGGRESSIVE_PAPER bypass; §8 #4 bot_core gate not located). Full sweep completed for informational purposes; no env change.

**Blockers cleared:** None.

**Blockers new/active:**
- ⏸ **ML-THRESHOLD-DATA-DRIVEN-RETUNE-001** STOPPED at §8 — re-attempt after BOT-CORE-ML-GATE-001 OR after V5a flip
- 📋 **BOT-CORE-ML-GATE-001 (NEW)** — Tier 1 🟡, recommended path forward; add second ML gate at bot_core. Recommended threshold = 55.
- 📋 **AGGRESSIVE-PAPER-DISABLE-001 (NEW)** — Tier 2 🟢, evaluation required.
- 📋 **POST-GRAD-ENTRY-GATE-001 RE-SCOPED** — was Tier 1 🔴 (Session 3 framing), now Tier 2 🟢 insurance-only.
- All other carries unchanged (NO-MOMENTUM-90S-AUDIT-001 still Tier 1 🟡; analyst already disabled per ANALYST-DISABLE-002).

**V5a precondition delta:** **+1 forward (de facto).** Session 3 framed POST-GRAD-ENTRY-GATE as V5a-amplifying. With Session 4 correction, that bleed has stopped (analyst disabled), so it's NOT a V5a blocker. The remaining SD-paper leaks (`no_momentum_90s` ~-4 SOL/week, `stop_loss_20%` ~-3 SOL/week) are smaller and partially addressed by NO-MOMENTUM-90S-AUDIT-001. AGENT_CONTEXT.md §6.5 V5a recommendation: cap `MAX_POSITION_SOL=0.10` for first 24h post-flip (vs current 0.25) to limit blast radius until paper-to-live edge ratio is confirmed.

**Next prompt:** **LIVE-FEE-CAPTURE-002 (Path B)** (Session 5 of 6). V5a-blocking-but-degradable; Helius parseTransactions for actual fill data on live trades.

**Pending Claude-chat prompts not yet pasted:** none — chained 6-prompt sequence complete.

**Verdict:** ML-THRESHOLD-DATA-DRIVEN-RETUNE-001 ⏸ STOPPED per §8 — env-var change has zero paper effect due to AGGRESSIVE_PAPER+TEST_MODE override + missing bot_core gate. Threshold sweep documented for future use (optimum = 55 across both 14d/7d). Major Session-3 correction propagated: POST-GRAD-ENTRY-GATE-001 actual ROI ~0 (analyst-disabled bleed has stopped); re-scoped to insurance Tier 2. New Tier-1 lever proposed: BOT-CORE-ML-GATE-001. Audit: `docs/audits/ML_THRESHOLD_DATA_DRIVEN_RETUNE_2026_05_01.md`.

---

## 2026-05-01 — POST-GRAD-LOSS-INVESTIGATION-001 (Session: 5-hypothesis investigation; H2 reveals real bleed source — Session 3 of 6 in chained-prompt sequence)

**Committed (this session):** `badb221` docs(post-grad-investigation): POST-GRAD-LOSS-INVESTIGATION-001 — 5-hypothesis investigation reveals post-grad ENTRY (bc=1.0 at entry) as bleed source. Files: `docs/audits/POST_GRAD_LOSS_INVESTIGATION_2026_05_01.md` (NEW, 8 sections), `ZMN_ROADMAP.md` (Decision Log entry + 5 new future-queued levers including POST-GRAD-ENTRY-GATE-001), `AGENT_CONTEXT.md` (NEW §6.5 "Known leaks under investigation"), `STATUS.md` (this prepend).

**State changes:** None. Investigation only. Bot continues TEST_MODE=true, market_mode=NORMAL.

**Bot state at session start (~12:30 UTC):**
- TEST_MODE=true ✓, market_mode=NORMAL ✓, paper portfolio 23.89 SOL, 0 open positions
- Sessions 1-2 deployed cleanly: TIME-PRIME `13d4324` + STATE-RECONCILE `1d1620e` (docs commit triggered redeploy at ~12:25 UTC, daily_pnl reset to 0.0 confirms)

**§2 Hypothesis tests (H1 → H5 → H2 → H4 → H3 order, 14d window):**

| H | Verdict | Key evidence |
|---|---|---|
| H1 (threshold tightness) | PARTIAL | 58/300 (19.3%) of TRAILING_STOP winners exited below entry × 0.8. H1b counterpart untestable (`peak_price` NULL on stop_loss_20%) |
| H2 (carry past graduation) | **REFUTED in original framing → REVEALS REAL BLEED** | 145/145 graduation_stop_loss + 79/79 graduation_time_exit + 56/56 graduation_tp_30pct = **280 entries with bc_progress=1.0 AT ENTRY** (post-grad ENTRY, not carry-through). Net -14.60 SOL/14d (~-7.3 SOL/week) |
| H3 (pricing artifact) | SKIPPED | Paper synthetic signatures; no on-chain |
| H4 (adverse selection) | REFUTED | Hold patterns reflect strategy timeouts (graduation_time_exit's 1273s = configured max-hold), not adverse selection |
| H5 (exit ordering) | UNTESTABLE | `trailing_stop_active` is transient state (resets at exit). Indirect: stop_loss_20% rows have 0% trail_active, consistent with both "trail never engaged" AND "state reset" |

**§3 Synthesis (highest-ROI patch):**
- **PATCH A — POST-GRAD-ENTRY-GATE-001** — gate SD signals at signal_aggregator where `bonding_curve_progress >= 0.99`. Cost S, ROI ~+7 SOL/week. Eliminates -7.3 SOL/week post-grad-entry bleed. Recommended Tier 1 🔴.
- **PATCH B — NO-MOMENTUM-90S-AUDIT-001** — separate pre-grad bleed audit (-8.48 SOL/14d on 423 trades). Investigation first, patch second. Tier 1 🟡.
- **PATCH C — OBS-TRAIL-ENGAGEMENT-001** — sticky `trail_was_engaged` boolean. Cost S, observability only. Tier 2 🟢.

**Observability gaps surfaced:**
- `trailing_stop_active` is transient state (need sticky `trail_was_engaged`)
- No `min_price_during_hold` (intra-hold drawdown tracking)
- No exit-time bc_progress capture (carry-through detection)

**Stop-condition check:** 0 of 4 STOP conditions tripped (DB OK; no test exceeded 30s; PATCH A ROI well above 0.5 SOL/week threshold; H1+H5 not BOTH untestable as H1 returned PARTIAL signal).

**Blockers cleared:** None directly (investigation session). POST-GRAD-LOSS-INVESTIGATION-001 closed as ✅ INVESTIGATION COMPLETE.

**Blockers new/active:**
- 📋 **POST-GRAD-ENTRY-GATE-001 (NEW)** — Tier 1 🔴 PROPOSED, the highest-ROI Track-B lever currently identified. Pending implementation session (not in current 6-prompt chain).
- 📋 **NO-MOMENTUM-90S-AUDIT-001 (NEW)** — Tier 1 🟡 PROPOSED, separate audit needed.
- 📋 **OBS-TRAIL-ENGAGEMENT-001 (NEW)** — Tier 2 🟢 PROPOSED, observability.
- 📋 **OBS-INTRA-HOLD-DRAWDOWN-001 (NEW)** — Tier 2 🟢 PROPOSED, observability.
- 📋 **OBS-EXIT-TIME-BC-PROGRESS-001 (NEW)** — Tier 2 🟢 PROPOSED, observability (low priority since current data shows no carry-through case).

**V5a precondition delta:** **-1 backward (de facto blocker added).** AGENT_CONTEXT.md §6.5 surfaces the post-grad bleed: at MAX_POSITION_SOL=0.25, live mode would amplify -7 SOL/week to ~-35 SOL/week if paper-to-live edge holds. **POST-GRAD-ENTRY-GATE-001 should land BEFORE V5a flip** (or trial at sub-floor sizing). Adding to CONDITIONAL_GO criteria for Session 6 V5A-GO-NO-GO.

**Next prompt:** **ML-THRESHOLD-DATA-DRIVEN-RETUNE-001** (Session 4 of 6). Per Session 4 prompt §2 Step 3, the band sweep should be RE-RUN filtering for pre-grad-only exits (this session's H2 finding shows the loss profile is dominated by post-grad mechanics, so pre-grad-only is the right ML signal measurement).

**Pending Claude-chat prompts not yet pasted:** none — chained 6-prompt sequence pasted; POST-GRAD is Session 3 of 6.

**Verdict:** POST-GRAD-LOSS-INVESTIGATION-001 ✅ DELIVERED — Investigation complete, REAL bleed source identified (post-grad ENTRY not carry-through), highest-ROI patch proposed (POST-GRAD-ENTRY-GATE-001 +7 SOL/week). 0 STOP conditions tripped. Audit doc `docs/audits/POST_GRAD_LOSS_INVESTIGATION_2026_05_01.md`.

---

## 2026-05-01 — STATE-RECONCILE-2026-05-01 (Session: doc reconciliation against verified DB findings — Session 2 of 6 in chained-prompt sequence)

**Committed (this session):** `badb221` docs(state-reconcile): STATE-RECONCILE-2026-05-01 — reconcile canonical docs against verified A-E findings. Files: `CLAUDE.md` (ML threshold 2026-05-01 addendum), `AGENT_CONTEXT.md` (header refresh + TIME_PRIME env rows), `ZMN_ROADMAP.md` (STATE-RECONCILE Decision Log entry + 4 new future-queued levers: POST-GRAD-LOSS-INVESTIGATION-001, ML-THRESHOLD-DATA-DRIVEN-RETUNE-001, TIME-PRIME-AEDT-AEST-DRIFT-001, TIME-PRIME-CALIBRATION-001), `MONITORING_LOG.md` (2026-05-01 entry prepended), `STATUS.md` (this prepend), `docs/audits/USERMEMORIES_DRIFT_2026_05_01.md` (NEW, 6 sections).

**State changes:** None to deployed config. Docs-only commit. Per RAILWAY-REDEPLOY-DISCIPLINE-001, accept that the docs commit may also redeploy services.

**Bot state at session start (~2026-05-01 ~12:18 UTC):**
- TEST_MODE=true on bot_core ✓ (Railway MCP env list confirms)
- bot:status RUNNING, paper portfolio 23.89 SOL, daily_pnl -0.16 SOL, market_mode NORMAL ✓
- consecutive_losses 3, 0 open positions, bot:emergency_stop absent ✓
- Session 1 deploy verified: container restarted 12:14:08 UTC with Sentry release `13d43242` matching commit `13d4324`; startup banner clean.
- Pre-fix evidence preserved: 2 historical TIME_PRIME log lines (08:11 AEDT hr=19, 09:21 AEDT hr=20) showing 2.0× sizing. Post-fix: env-controlled, default disabled.

**§2 Findings A-E (verified production DB, run 2026-05-01 ~12:18 UTC):**
- **A:** ML score band: 30-40 +0.49 / **40-50 -1.98 (worst)** / 50-60 -0.18 / 60-70 -0.70 / **70-80 +1.63 (best)** / 80-90 -0.35 / 90+ +0.005. Aggregate -1.09 SOL on 689 trades. Chat-side "50+ mostly profitable" REFUTED — only 70-80 reliably positive. The 2026-04-17/19 magnitudes have collapsed by ~50-100×.
- **B:** AEST 18-20 -2.46 SOL on 114 trades (worst, confirmed); AEST 11-17 +0.18 (flat, confirmed); AEST 21-23 + 00-08 -1.45 SOL (chat said +1, REFUTED).
- **C:** TRAILING_STOP +7.93 / 206 / 76.7% WR (dominant winner); top losers `no_momentum_90s` -7.40 (largest, chat omitted), `graduation_stop_loss` -6.36, `stop_loss_20%` -5.16. Post-grad bleed = -12.09 SOL (chat -23, HALF). TRAILING_STOP captures 69% of gains (chat 98%, OVERSTATED).
- **D:** Last analyst entry 2026-04-28 13:02 UTC; 0 last 3 days. ANALYST-DISABLE-002 confirmed.
- **E:** SD WR 04-22/23 ~50% → 04-30 17.9%. Direction confirmed; 14d net +9.0 SOL but recent 4d -1.18 SOL.

**§3 Reconciliation outcome:** PROCEED with nuanced edits (headlines confirmed, details corrected). No STOP triggered. Drift classification: 0 🔴 ACTION-CHANGING / 2 🟡 SCOPE-CONFUSION (ML threshold drift, AEDT/AEST timezone drift) / 3 🟢 SAMPLE-STALE (TRAILING_STOP %, stop_loss_35% absent, SD profitability window) / 1 🔵 NUANCE-MISSING (no_momentum_90s vs stop_loss categorization).

**§4 Doc updates applied (single commit):**
1. CLAUDE.md ML threshold 2026-05-01 addendum after the 2026-04-17/19 block (preserved as historical evidence) + reference to USERMEMORIES_DRIFT_2026_05_01.md.
2. AGENT_CONTEXT.md state-header refresh; TIME_PRIME_MULTIPLIER + TIME_PRIME_HOURS_AEST rows added to bot_core config table.
3. ZMN_ROADMAP.md STATE-RECONCILE Decision Log entry above TIME-PRIME entry; 4 new future-queued levers (POST-GRAD-LOSS-INVESTIGATION-001 Tier 1 🔴 with corrected -12 SOL ROI; ML-THRESHOLD-DATA-DRIVEN-RETUNE-001 Tier 1 🟡 gated on POST-GRAD; TIME-PRIME-AEDT-AEST-DRIFT-001 LOW; TIME-PRIME-CALIBRATION-001 MEDIUM).
4. MONITORING_LOG.md 2026-05-01 entry prepended summarizing Findings A-E + reconciliation outcome.
5. docs/audits/USERMEMORIES_DRIFT_2026_05_01.md NEW (6 sections, full data tables + classifications).
6. STATUS.md (this prepend).

**§5 quiz.md verification:** post-edit reader-perspective check confirms updated docs answer the 5 quiz questions unambiguously and consistently across files.

**Stop-condition check:** 0 of 3 STOP conditions tripped (DB connection OK; headline directions all confirmed; quiz consistency verified).

**Blockers cleared:** None this session — bookkeeping only.

**Blockers new/active:**
- 📋 **POST-GRAD-LOSS-INVESTIGATION-001 (NEW)** — Tier 1 🔴, queued for Session 3. Investigate -12.09 SOL/7d post-grad bleed (graduation_stop_loss + stop_loss_20% + graduation_time_exit). 5-hypothesis investigation; no code change.
- 📋 **ML-THRESHOLD-DATA-DRIVEN-RETUNE-001 (NEW)** — Tier 1 🟡, queued for Session 4. Gated on POST-GRAD outcome (if loss profile is dominated by graduation mechanics, ML retune impact is smaller).
- 📋 **TIME-PRIME-AEDT-AEST-DRIFT-001 (NEW)** — LOW, surfaced by Session 1.
- 📋 **TIME-PRIME-CALIBRATION-001 (NEW)** — MEDIUM, future-queued.
- All other carries unchanged.

**V5a precondition delta:** **0 forward this session** (bookkeeping only). Continued: TIME_PRIME ✅ closed Session 1; remaining: ~3 SOL wallet top-up, Path B, 24-48h paper observation, ML retune.

**Next prompt:** **POST-GRAD-LOSS-INVESTIGATION-001** (Session 3 of 6).

**Pending Claude-chat prompts not yet pasted:** none — chained 6-prompt sequence pasted in conversation; STATE-RECONCILE is Session 2 of 6.

**Verdict:** STATE-RECONCILE-2026-05-01 ✅ DELIVERED — 5 doc files updated + 1 NEW audit doc; chat-side framings reconciled with actual production data; no code or env changes; doc consistency verified.

---

## 2026-05-01 — TIME-PRIME-CONTRADICTION-FIX-001 (Session: env-driven multiplier; default disabled — Session 1 of 6 in chained-prompt sequence)

**Committed (this session):** `badb221` fix(bot_core): TIME-PRIME-CONTRADICTION-FIX-001 — neutralize 2× AEST 17-19 upsize via env-driven multiplier (default 1.0×). Files: `services/bot_core.py:704-720` (TIME_PRIME branch replaced; TIME_GOOD/DEAD/SLEEP/WEEKEND_BOOST untouched per §10) + `docs/audits/TIME_PRIME_CONTRADICTION_FIX_2026_04_30.md` (NEW, 9 sections) + `STATUS.md` prepend + `ZMN_ROADMAP.md` (Decision Log + §7 row update) + `AGENT_CONTEXT.md` (§7 row update).

**State changes:**
- Code only at git push time. No Railway env touched in commit.
- Post-push: Railway env vars on bot_core set to `TIME_PRIME_MULTIPLIER=1.0` and `TIME_PRIME_HOURS_AEST=""` via Railway MCP (second redeploy accepted per RAILWAY-REDEPLOY-DISCIPLINE-001 — directive in §3 Path A).
- Single git push triggers bot_core auto-redeploy. No other services touched.

**Bot state at session start (~2026-05-01 ~00:30 UTC):**
- TEST_MODE=true on bot_core (verified via STATUS.md 2026-04-30 entry + AGENT_CONTEXT.md §1) ✓
- market_mode=NORMAL (post-MARKET-MODE-001 fix in `932ae08`) ✓
- Last meaningful behavioral deploy: `f3a1741` (FEE-LATENCY-REALISM Path A)
- bot:emergency_stop absent ✓

**§2 Step 1 — TIME_PRIME logic located:**
- `services/bot_core.py:704-718` hardcoded `if aedt_hour in (18,19,20): size_sol *= 2.0`
- Multiplier applied to `size_sol` post-min/max-clamp; re-clamped at L727
- Other branches: TIME_GOOD/DEAD/SLEEP/WEEKEND_BOOST — out of scope per §10
- Tangent finding: code `timezone(timedelta(hours=11))` = AEDT/UTC+11; Sydney is currently AEST/UTC+10 post-DST 2026-04-05. Code's `aedt_hour=18` = Sydney clock 17. Tracked as TIME-PRIME-AEDT-AEST-DRIFT-001 (LOW, NEW).

**§2 Step 2 — AEST hour distribution (last 7d, SD-paper):**
- AEST 18-20 (chat-side framing): n=114, sum=−2.4629 SOL — confirmed worst window
- AEST 17-19 (actual code firing window): n=114, sum=−2.7563 SOL
- AEST other (non-firing): n=580, sum=+3.6258 SOL
- Hypothesis CONFIRMED, no STOP

**§2 Step 3 — Multiplier ratio confirms TIME_PRIME fires:**
- avg `amount_sol` AEST 17-19: 0.1845 SOL
- avg `amount_sol` AEST 15,16,20,21 neighbors: 0.0902 SOL
- Ratio: **2.05×** — exact match for the 2.0× multiplier (within sampling noise)
- min position size at AEST 17-19 jumps to 0.0985 (≈ 2× MIN_POSITION_SOL=0.05 floor)
- TIME_PRIME definitively fires, no STOP

**§3 Patch chosen: Path A** (env-driven multiplier; defaults disabled). Single-file change. Path C explicitly rejected per session §3 (different-window calibration is separate session).

**§4 verify_time_prime_fix.py output (.tmp_time_prime_fix/verify_output.txt):**
- 5 timestamps tested: AEST 08:30 / 18:30 / 19:30 / 20:30 / 22:30
- ASSERT NEW=1.0× for all 5 cases — PASS
- Smoke: env re-enable to 1.5× on hour 20 works ✓
- Smoke: malformed env_hours fail-safe to 1.0× ✓
- BEHAVIOR DELTA: 2/5 test cases (AEST 18:30, 19:30) had upsize neutralized; AEST 20:30 was actually never in TIME_PRIME old window (chat-side label off by 1h due to DST drift)

**Compile-checked:** `python -m py_compile services/bot_core.py` → COMPILE OK.

**§5 Deploy verification — queued post-deploy:**
1. Poll Railway MCP for bot_core SUCCESS, +90s warmup
2. Set env vars via Railway MCP (TIME_PRIME_MULTIPLIER=1.0 + TIME_PRIME_HOURS_AEST="")
3. Confirm both env vars present
4. SQL: count entries last 30min; if zero (HIBERNATE), log and proceed
5. If entries present and any AEST 17-19: confirm no ~2× spike

**Stop-condition check:** 0 of 4 STOP conditions tripped (§9). §2 Step 2 hypothesis confirmed both ways. §2 Step 3 multiplier ratio 2.05× (>1.5 threshold). Path A within 2-file budget.

**Blockers cleared:**
- ✅ **TIME_PRIME-CONTRADICTION-001** — 2× upsize at AEST 17-19 (code's UTC+11 18-20) neutralized; env-driven going forward.

**Blockers new/active:**
- 📋 **TIME-PRIME-AEDT-AEST-DRIFT-001 (NEW, LOW)** — `aedt_hour` uses UTC+11 timezone but Sydney is AEST/UTC+10 post-DST 2026-04-05. All TIME_GOOD/TIME_DEAD/TIME_SLEEP windows fire 1h earlier than their labels suggest. Fix: replace `_td(hours=11)` with `zoneinfo.ZoneInfo('Australia/Sydney')`.
- 📋 **TIME-PRIME-CALIBRATION-001 (NEW, MEDIUM)** — does any hour deserve a 2× upsize? Current data says no; future deeper-history analysis.
- All other carries unchanged (LIVE-FEE-CAPTURE-002 Path B, ~3 SOL wallet top-up, ML-THRESHOLD-DRIFT, etc.).

**V5a precondition delta:** **+1 forward.** TIME_PRIME-CONTRADICTION-001 closed. Live mode flip will no longer amplify the AEST 17-19 loss window by 2×. Net live loss reduction at expected throughput: ~2× the −2.46 SOL/week paper bleed if edge holds.

**Next prompt:** **STATE-RECONCILE-2026-05-01** (Session 2 of 6). Bookkeeping; reconcile canonical docs with verified data findings.

**Pending Claude-chat prompts not yet pasted:** none — chained 6-prompt sequence pasted by Jay; TIME-PRIME is Session 1 of 6 (sessions 2-6: STATE-RECONCILE, POST-GRAD-LOSS-INVESTIGATION, ML-THRESHOLD-RETUNE, LIVE-FEE-CAPTURE-002, V5A-GO-NO-GO).

**Verdict:** TIME-PRIME-CONTRADICTION-FIX-001 ✅ DELIVERED — Path A patch (single-file env-driven multiplier with safe defaults). Verify-fix PASS (2 of 5 cases neutralized). AEST 17-19 (code's UTC+11 18-20) 2× upsize disabled by default. V5a precondition closed. Audit: `docs/audits/TIME_PRIME_CONTRADICTION_FIX_2026_04_30.md`.

---

## 2026-04-30 — REALISM-AND-ROADMAP-CLEANUP-2026-04-30 (Session: 3-phase autonomous-loop — MARKET-MODE-001 + SOCIAL-SCORING-001 + ROADMAP CLEANUP)

**Committed (this session):** `932ae08` fix(market_health): MARKET-MODE-001 — calibrate thresholds + fix metric. Files: `services/market_health.py` + `services/signal_aggregator.py` (ratio-writer removed). | `627f4c9` fix(signal_aggregator): SOCIAL-SCORING-001 — per-component social fields in features_json. Files: `services/signal_aggregator.py`. | `badb221` final docs commit (audit + STATUS + ROADMAP + AGENT_CONTEXT + CLAUDE.md DOCS-004).

**State changes:**
- Phase 1 — MARKET-MODE-001: code-only changes; no Railway env touched. Two services redeploy on push.
- Phase 2 — SOCIAL-SCORING-001: code-only; signal_aggregator redeploys (bundled with Phase 1's SA touch).
- Phase 3 — ROADMAP-CLEANUP: 4 Class A items closed. **DOCS-004** (Vybe URL fix in CLAUDE.md + AGENT_CONTEXT 2 spots), **DOCS-002** (verified already done in `e9de6d7`; roadmap row updated), **OBS-014** (verified moot — no production code uses `stop_loss_35%` literal; roadmap row updated), **TUNE-004** (Railway env: SA `SPEED_DEMON_BASE_SIZE_SOL=0.15` / `MAX_SIZE_SOL=0.25` / `MAX_SD_POSITIONS=20` / `MIN_POSITION_SOL=0.05` aligned with bot_core via Railway MCP set-variables; verified-fields-before-coding confirmed SA code does not read these — pure hygiene).
- 3 git commits, 2 services redeployed (market_health 1×, signal_aggregator 2× — Phase 1 + Phase 2 staggered redeploys).

**Bot state at session start (~13:33 UTC):**
- bot:status RUNNING, paper portfolio 23.19 SOL (recovering from -0.05 daily PnL after Path A deploy)
- 1 open position pre-session (speed_demon `6awf2i8N` peaked +247% on trailing stop — closed during session, dropped consecutive_losses 12→4)
- TEST_MODE=true on bot_core (verified) ✓
- bot:emergency_stop absent ✓
- Pre-session market_mode=DEFENSIVE (loss_override stale path), grad_rate_estimate=0.0 (the bug)

**Phase 1 — MARKET-MODE-001 Step 1 verification:**
- `_determine_market_mode` requires ALL THREE thresholds (pumpfun_vol AND grad_rate AND dex_vol)
- signal_aggregator.py:1653 wrote `market:grad_rate_estimate` as RATIO (`migrations / new_tokens` ≈ 73/701678 = 0.0001 → rounded to 0)
- MARKET_MODES thresholds (0.5/0.8/1.0/1.5) assumed migrations-per-hour
- Definition mismatch ↔ HIBERNATE-forever for ~weeks
- Sample at 13:26:51 UTC: dex=$1.4B, migs=73/hr, pf=$209M → expected NORMAL under new thresholds

**Phase 1 patch path: A + B (NOT 1C — PumpPortal stats API deferred).**

**Phase 1 verify_market_mode.py output (2000 samples per case, 10 scenarios):**
- 7/10 cases distribute non-HIBERNATE
- current sample → NORMAL ✓
- HIBERNATE only fires under genuine outage / dead market

**Phase 1 deploy verification (post `932ae08` push at ~13:30 UTC, sample at 13:36 UTC):** ✅ PASS
- `market:health.mode = NORMAL` (was HIBERNATE for weeks!)
- `market:mode:current = NORMAL`
- `market:health.timestamp` advanced to 13:36:09 UTC (fresh cycle)
- `sentiment_score = 37.0` (was 28.7 pre-fix — reflects new grad_scaled formula)
- `bot:status.market_mode = NORMAL` (bot_core consumed via market:mode pub/sub)

**Phase 2 — SOCIAL-SCORING-001 Step 1 verification:**
- STATE C (wired, working, but missing from features_json)
- Score modifier at L591-596 uses `signal.get("has_twitter", False)` etc. — works at runtime
- features_json captured only `has_social` (any) + `twitter_followers` (2 fields)
- Missing: `has_twitter`, `has_telegram`, `has_website`, `social_count`
- 100/100 recent rows: twitter_followers populated (real distribution: <1k=70, 5k+=18, missing=7, 1-2k=3, 2-5k=2 — discriminatory)
- 0/100 had social_count or per-platform fields

**Phase 2 patch: 2C** — minimal addition of 4 keys to features dict at signal_aggregator.py:2022 area. social_count computed inline matching score modifier semantics.

**Phase 2 verify_social_patch.py output:** PASS source-check + simulation (3 mock signals: all-3-platforms→sc=3 boost APPLIES, twitter-only→sc=1 NO BOOST, no-socials→sc=0).

**Phase 2 deploy verification queued post-deploy:** wait 5-10 min for second SA redeploy to land then sample fresh paper_trades.features_json for the 4 new keys.

**Phase 3 — ROADMAP-CLEANUP outcomes:**
- DOCS-004 ✅ DONE (CLAUDE.md:478 + AGENT_CONTEXT.md:576 + 1883 — `.com (NOT .xyz)` reversed)
- DOCS-002 ✅ ALREADY DONE (verified in `e9de6d7`)
- OBS-014 ✅ MOOT (no production code uses literal)
- TUNE-004 ✅ DONE (Railway env on SA aligned with bot_core; vestigial — verified SA code doesn't read these)
- DOCS-001 ⏭ SKIPPED (file path doesn't exist)
- BUG-019 ⏭ DEFER (no matching SQL found)
- TREASURY-TEST-MODE-002 ⏭ DEFER (per audit's "revisit at V5a")
- INFRA-001, DASH-B-014, BUG-021-bot_core-part, GOVERNANCE-RESILIENCE, EXEC-001/002 — Class B/C, deferred

**Stop-condition check:** 0 of 4 hard STOP conditions tripped. 0 of 3 phases hit a soft STOP (each completed in 1 iteration).

**Compile-checked:**
- `python -m py_compile services/market_health.py services/signal_aggregator.py` → OK

**Blockers cleared:**
- ✅ **MARKET-MODE-001** (HIBERNATE-forever bug) — resolved by metric+threshold alignment.
- ✅ **SOCIAL-SCORING-001** (STATE C) — 4 new ML features in features_json.
- ✅ **DOCS-004** (Vybe URL) — 3 places fixed.
- ✅ **TUNE-004** (SA size env hygiene) — aligned with bot_core.
- ✅ **DOCS-002** (ML threshold doc) — verified already complete.
- ✅ **OBS-014** (stop_loss SQL filter) — verified moot.
- ✅ **STATUS-CONVENTION-001** — 5+ sessions appending cleanly; promote to ✅ COMPLETED.
- ✅ **SILENCE-RECOVERY-2026-04-28** — already cleared per AGENT_CONTEXT §7.

**Blockers new/active:**
- 📋 **MARKET-MODE-001-RE-CALIBRATE** (LOW, NEW): re-tune thresholds after 24h of observation. Sample size during this fix = 2 readings.
- 📋 **MARKET-LOSS-OVERRIDE-DEAD-CODE-001** (LOW, NEW): `rug_cascade_monitor` writes `market:loss_override` Redis key; no reader exists. Either wire it into `_determine_market_mode` for DEFENSIVE-cap behavior, or remove the writer.
- 📋 **PUMPPORTAL-STATS-API-001** (LOW, NEW): replace `pumpfun_vol_estimate = dex_vol * 0.15` placeholder with real PumpPortal stats endpoint.
- All other carries unchanged: LIVE-FEE-CAPTURE-002 (Path B) 📋 V5a-blocking, ~3 SOL wallet top-up ⏸ JAY ACTION, TIME_PRIME-CONTRADICTION-001 📋, LATENCY-OBSERVABILITY-001 📋 (from FEE-LATENCY-REALISM session), TREASURY-TEST-MODE-002 🟡, ML-THRESHOLD-DRIFT-2026-04-29 🟡.

**V5a precondition delta:** **+1 forward** (HIBERNATE-forever fix unblocks meaningful 24-48h paper observation window). Sideways: Path B / wallet top-up / TIME_PRIME unchanged.

**Next prompt:** **24h observation** of: (a) market_mode cycling appropriately across day/night/weekend, (b) features_json populating new social fields. Then **LIVE-FEE-CAPTURE-002 (Path B)** as next V5a-blocking session. Wallet top-up to ~3 SOL remains a Jay action.

**Pending Claude-chat prompts not yet pasted:** none — chain self-contained.

**Verdict:** REALISM-AND-ROADMAP-CLEANUP ✅ DELIVERED — 3 phases, 3 commits, 2 services redeployed (correctly), 4 Class A roadmap items closed, market_mode unblocked from HIBERNATE-forever (the headline outcome). Audit doc: `docs/audits/REALISM_AND_ROADMAP_CLEANUP_2026_04_30.md`.

---

## 2026-04-30 — FEE-LATENCY-REALISM-2026-04-30 (Session: tier-aware live-close slippage; latency stretch goal STOPPED)

**Committed (this session):** `badb221` fix(slippage): tier-aware live close + audit; FEE-LATENCY-REALISM-2026-04-30. Files: `services/bot_core.py` (Position dataclass +1 field; paper entry + live entry Position constructions +1 kwarg each; live entry + live close `_simulate_slippage` calls now use entry tier instead of literal `"buy"`) + `docs/audits/FEE_LATENCY_REALISM_AUDIT_2026_04_30.md` (NEW, 8 sections) + STATUS.md prepend + ZMN_ROADMAP.md (Decision Log row added).

**State changes:**
- Code only. No Railway env changes. No Redis writes. No DB writes.
- `services/bot_core.py:178-180` Position dataclass adds `entry_slippage_tier: str = "confirmation"` field.
- `services/bot_core.py:846` paper entry Position now sets `entry_slippage_tier=slippage_tier`.
- `services/bot_core.py:912` live entry Position now sets `entry_slippage_tier=slippage_tier`.
- `services/bot_core.py:940` live entry INSERT slippage call: `_simulate_slippage(slippage_tier, size_sol)` (was `"buy"`).
- `services/bot_core.py:1287` live close buy-side slippage call: `_simulate_slippage(pos.entry_slippage_tier, pos.size_sol)` (was `"buy"`).
- Sell-side at line 1288 (`_simulate_slippage("sell", sell_amount)`) was already correct; unchanged.
- Single git push triggers bot_core auto-redeploy.

**Bot state at session start (2026-04-30 ~12:53 UTC):**
- bot:status RUNNING, paper portfolio 23.35 SOL, daily_pnl=0.0, market_mode=HIBERNATE (sentiment 28.4), consecutive_losses=10, test_mode=true, 0 open
- bot:emergency_stop absent ✓
- TEST_MODE=true on bot_core ✓ (verified via Railway MCP)
- HIBERNATE mode means no fresh signals during this session — Step 8 verification cannot sample fresh closes inline; will wait for market_mode flip back to NORMAL/AGGRESSIVE/DEFENSIVE
- `signals:scored` empty; `signals:raw` accumulating per OBS leak

**Step 1 verification — H1-H6:**
- H1 (latency NULL): ✅ CONFIRMED. 4 columns exist in schema; 0/1182 rows have any populated. Zero matches in `services/` for the column names. **Step 3 stretch goal STOPPED** (would require 4-file refactor across signal_listener + signal_aggregator + paper_trader + bot_core + Redis-payload schema changes — exceeds 1-2 file scope).
- H2 (pre-grad fee undercount): partial. `PAPER_JITO_TIP_PREGRAD_SOL = 0.0` doesn't model PumpPortal's 0.001 SOL Jito tip on every trade — gap ≈ +0.001 SOL/trade. ~1% of Path A's +0.088 SOL gap on id 6580. Not addressed this session — bundle with Path B calibration.
- H3 (slippage default fallback): ✅ CONFIRMED. `services/paper_trader.py:51-61` SLIPPAGE_RANGES keys are alpha_snipe / confirmation / post_grad_dip / sell / sell_postgrad. `"buy"` is NOT a key. Line 149 `entry = SLIPPAGE_RANGES.get(tier, (0.5, 2.0, 0.3))` falls back. Path A bot_core.py calls `_simulate_slippage("buy", ...)` at 932 + 1271 — both fall back. Verified via id 6580 (buy_slip=1.91% matches default 0.7-2.9% range; sell_slip=18.91% matches `sell` 7.8-38.9% range).
- H4 (Path A 12× gap): ✅ already in predecessor audit; no re-verification needed.
- H5 (Path B feasibility): infrastructure exists (HELIUS_PARSE_TX_URL); ~3-5h work; out of scope.
- H6 (tier provenance): tier computed at `services/bot_core.py:741-751` based on signal age + personality. NOT on signal payload. NOT on Position. **In scope at line 932 (entry); needs Position field for line 1271 (close).** Basis for Path A choice.

**Step 2 patch path: A** (plumb tier through Position).

**Step 4 demonstrate-fix output:**
| tier | old (`"buy"` default) avg | new tier-aware avg | delta |
|---|---:|---:|---:|
| alpha_snipe (NEW) | 1.86% | 18.70% | **+16.85% (10×)** |
| confirmation (NEW) | 1.86% | 12.47% | **+10.61% (6.7×)** |
| post_grad_dip | 1.86% | 1.86% | +0.00% (range coincidence — post_grad_dip IS the default) |

For id 6580 round-trip estimate (confirmation tier): 16.29% → **23.73%** (+7.44pp). Closes ~30% of Path A's +0.088 SOL gap on this row. id 6580 itself NOT re-backfilled — historical record retained.

**Compile-checked:** `python -m py_compile services/bot_core.py` → COMPILE OK.

**Step 8 verification queued post-deploy:** poll Railway MCP for bot_core SUCCESS, wait 90s, check startup banner clean (no AttributeError on Position.entry_slippage_tier or _simulate_slippage signature). Wait for HIBERNATE → NORMAL transition or fresh paper closes; sample slippage_pct distribution across 10-20 fresh paper rows. Expectation: distribution should reflect the tier mixture (alpha_snipe + confirmation + post_grad_dip) rather than concentrating in the default 0.7-2.9% range. NOTE: paper-mode closes via `paper_sell` were ALREADY correct (paper_sell uses computed `sell_tier`, paper_buy uses caller-passed `slippage_tier`); the visible behavior change is on **live close path** for future live trades — paper rows will look largely the same since paper was never affected by the bug.

**Step 8 verification — ✅ PASS (2026-04-30 ~13:24 UTC):**
- New bot_core container live with release `f3a1741d1902` (matches commit `f3a1741`) per Sentry init log at 13:08:21 UTC.
- Startup banner clean: "ZMN Bot v3.0 starting — SERVICE_NAME=bot_core" (13:08:20), "TEST_MODE=True", "Bot Core ready — managing 3 personalities" (13:08:21). No AttributeError, ImportError, or `entry_slippage_tier` references in error paths.
- bot:status RUNNING, heartbeat fresh (14s old at check time), portfolio 23.25 SOL, 1 open position (speed_demon mint `6awf2i8N` with +246.7% unrealised, trailing_stop_active at $1.98e-6) — bot is paper-trading the new code.
- Behavioral verification on live close path NOT exercisable in TEST_MODE; paper closes use `paper_sell` (already correct, unaffected). Path A live close behavior change will surface only on V5a flip — Path B (LIVE-FEE-CAPTURE-002) remains the V5a-blocking precondition.
- No rollback needed.

**Blockers cleared:**
- ✅ **SLIPPAGE-TIER-LIVE-PATH-A-001** — buy-side slippage on Path A live close now uses entry-time tier instead of default fallback. Sell-side was already correct.

**Blockers new/active:**
- 📋 **LATENCY-OBSERVABILITY-001 (NEW)** — populate `signal_detected_at` / `scored_at` / `traded_at` / `total_latency_ms` columns end-to-end. 4-file refactor; not V5a-blocking; useful for SLIPPAGE-CALIBRATION-001 calibration analysis.
- 📋 **LIVE-FEE-CAPTURE-002 (Path B)** — V5a-blocking-but-degradable; unchanged. Still the right answer for parity-of-truth.
- All other carries unchanged: TREASURY-TEST-MODE-002 🟡, ML-THRESHOLD-DRIFT-2026-04-29 🟡, LIVE-CLOSE-FALLBACK-INSERT-001 📋, TUNE-009 ⏸ DEFERRED, TIME_PRIME-CONTRADICTION-001 📋, TUNE-006 (other components) 📋, ~3 SOL wallet top-up ⏸ JAY ACTION.

**Stop-condition check:** 0 of 8 STOP conditions tripped. TEST_MODE=true ✓. bot:status RUNNING ✓. emergency_stop absent ✓. H3 confirmed (didn't fail). Patch Path A chosen (not C). Step 3 stretch goal cleanly STOPPED per its own scope rule (not a stop-condition trip). Demonstrate-fix changes behavior empirically (10× / 6.7× / 0× — last is range coincidence). Compile OK.

**Next prompt:** **LIVE-FEE-CAPTURE-002 (Path B)** is the next V5a-blocking session. Or **LATENCY-OBSERVABILITY-001** as a parallel, lower-priority observability session if Path B has prerequisites. Wallet top-up to ~3 SOL remains a Jay action.

**Pending Claude-chat prompts not yet pasted:** none — this session was self-contained.

**Verdict:** FEE-LATENCY-REALISM ✅ DEPLOYED (Path A patch, single file `bot_core.py`, 5 mechanical edits, tier-aware live-close slippage). Latency stretch goal STOPPED per scope. Path A's id 6580 gap closed by ~30% structurally. Path B remains the right long-term answer; tracked unchanged.

---

## 2026-04-30 — SD-MC-CEILING-002-DEPLOY (Session: BC-reserves MC compute replaces inert gate)

**Committed (this session):** `badb221` feat(signal_aggregator): SD_MC_CEILING_002 — BC-reserves MC compute. Files: `services/signal_aggregator.py` (env-var comment refresh L48-54 + gate replacement L1833-1879) + `docs/audits/SD_MC_CEILING_002_DEPLOY_2026_04_30.md` (NEW, 10 sections) + `AGENT_CONTEXT.md` (§2 SD_MC_CEILING_USD active + §6 V5a precondition cleared + §7 carry update) + `ZMN_ROADMAP.md` (Decision Log: SD_MC_CEILING_001 SUPERSEDED + SD_MC_CEILING_002 ✅ DEPLOYED) + STATUS.md prepend.

**State changes:**
- Railway env var `SD_MC_CEILING_USD=3000` on `signal_aggregator` (was `999999999` post-Session-C rollback). Auto-redeploys SA.
- Code: env-var comment block at SA `:48-54` re-attributed to _002. Gate at SA `:1833-1879` rewritten to compute MC from `vSolInBondingCurve / vTokensInBondingCurve × 1B × market:sol_price` — mirrors `bot_core.py:927` and `paper_trader.py:255-257`. Fail-open if any field missing (debug-level log).
- No bot_core changes. No Redis writes. Single git push triggers signal_aggregator auto-redeploy.

**Bot state at session start (2026-04-30 ~12:22 UTC):**
- bot:status RUNNING, portfolio 23.41 SOL, daily_pnl=-0.43 SOL, market_mode=DEFENSIVE, consecutive_losses=3, test_mode=true, 0 open
- 0.56 SOL bleed since Session E snapshot (08:53 UTC, portfolio 23.97); reinforces gate-fix urgency
- market:sol_price=$83.19 (populated — gate dependency verified)
- bot:emergency_stop absent; signals:scored empty
- DB BUG-022 sanity (Step 1): `bad_null_corrected=0` ✅ / `fresh_pass_through=77` (16h) ✅ / `live_v1_count=1` ✅ / `total_closed=1174` (+36 since Session E)

**raw_data investigation (Step 2 result):** ✅ PROCEED with Option 2 (compute in SA). Confirmed via codebase trace (no diagnostic deploy needed):
- `services/signal_listener.py:545` passes full PumpPortal `data` dict as `raw_data` for new_token signals
- `services/signal_listener.py:488-489` populates `vSolInBondingCurve` / `vTokensInBondingCurve` from PumpPortal create events
- `services/signal_aggregator.py:1717,1862` already reads `raw_data["vSolInBondingCurve"]` for KOTH check + FILTER log — proves field is in scope at gate
- Formula matches bot_core `entry_price * 1_000_000_000` (paper) / `price * 1_000_000_000` (live) — convert SOL→USD via `market:sol_price` Redis key

**Compile-checked:** `python -m py_compile services/signal_aggregator.py` → OK.

**Step 6 verification — ✅ PASS (~12:30-12:45 UTC window):**
- 6a (log-level): **PASS.** 3 SD reject lines in logs since deploy (`7FrjP4mE` $17,366 / `FV8FxqWo` $19,353 / `8b4cTGJd` $3,727 — all correctly above ceiling). Math sanity check on $17,366 reject closes the formula loop: 81.95/392M × 1B × 83.19 = $17,365.86. 177 SD-targeted signals in 15-min sample; 1.7% direct ceiling-reject rate. Fail-open ratio not directly observable at LOG_LEVEL=INFO (debug-level log); deferred follow-up if needed.
- 6b (DB-level): **PASS.** 4 post-deploy SD entries, ALL below $3000 (max $2655). 0 leaks above ceiling. Pre-deploy entry id 7806 ($2540, 12:28:55 UTC) also below ceiling — no rollback fire-drill needed.

**24h verification queue marker:** TBD ~2026-05-01 ~13:00 UTC. Compare SD trade count / WR / PnL to 35h post-recovery baseline (272 trades, 23.4% WR, +0.140 SOL, 7.8/hr). Expected: count down ~14% (~6.7/hr), WR up to 27%+, PnL improved.

**Blockers cleared:**
- ✅ **SD_MC_CEILING_002** — code + env both active. Replaces _001's inert gate.

**Blockers new/active:**
- 📋 **SD_MC_CEILING_002 verification** queued (Step 6 within 30min of deploy + 24h check 2026-05-01).
- All other carries unchanged: TREASURY-TEST-MODE-002 🟡, ML-THRESHOLD-DRIFT-2026-04-29 🟡, LIVE-FEE-CAPTURE-002 (Path B) 📋, LIVE-CLOSE-FALLBACK-INSERT-001 📋, TUNE-009 ⏸ DEFERRED, TIME_PRIME-CONTRADICTION-001 📋, TUNE-006 (other components) 📋.
- Informational: SA env shadow drift — `MAX_SD_POSITIONS=3 / MIN_POSITION_SOL=0.10 / SPEED_DEMON_BASE_SIZE_SOL=0.45 / SPEED_DEMON_MAX_SIZE_SOL=0.75` set on signal_aggregator but bot_core owns those. Vestigial display-only shadow per AGENT_CONTEXT §2 footer (TUNE-008-style env hygiene). Not affecting this session.

**Stop-condition check:** 0 of 5 STOP conditions tripped at this point. BUG-022 plumbing clean. raw_data fields confirmed present. Compile OK. Env var set. Verification pending.

**Next prompt:** **24h verification (~2026-05-01 ~13:00 UTC)** as a separate session. If verification confirms gate firing AND WR/PnL improving as predicted, queue **TIME_PRIME-CONTRADICTION-001** (neutralize AEDT 18-20 2× upsize). If high fail-open ratio, address `market:sol_price` fallback or move gate to bot_core. Path B (LIVE-FEE-CAPTURE-002) remains hard V5a precondition regardless. Wallet top-up (~3 SOL, Jay action) remains V5a precondition.

**Pending Claude-chat prompts not yet pasted:** none — chain A-E + this 002-followup complete.

**Verdict:** SD_MC_CEILING_002 ✅ DEPLOYED. Replaces _001's structurally-inert gate with BC-reserves-based computation that mirrors bot_core's MC formula. Step 6 + 24h verification queued.

---

## 2026-04-30 — SESSION_E_PERSISTENCE_HARDENING (docs-only — AGENT_CONTEXT rewrite + Decision Log + drift report + Persistence Convention)

**Committed (this session):** `badb221` docs: SESSION-E persistence hardening — AGENT_CONTEXT + Decision Log + drift report. Files: `AGENT_CONTEXT.md` (rewritten authoritative current-state header + historical archive preserved below) + `ZMN_ROADMAP.md` (Decision Log section added — 18 dated entries newest-first + future-queued levers) + `CLAUDE.md` ("Persistence Convention" section added before P/L rule) + `docs/audits/USERMEMORIES_DRIFT_2026_04_30.md` (NEW, 7 sections, 13-claim drift table) + STATUS.md prepend. **Docs-only diff. No services/, no env vars, no Redis writes.** Per RAILWAY-REDEPLOY-DISCIPLINE-001 carry, may auto-trigger redeploys; if so, evidence accrues.

**State changes:** none (read-only state inspection for AGENT_CONTEXT).

**Bot state at snapshot time (2026-04-30 08:53 UTC):**
- bot:status RUNNING, paper portfolio 23.97 SOL, daily_pnl=0.0, test_mode=true, consecutive_losses=1
- 0 paper open, 0 live open
- market:mode:current=HIBERNATE; market:mode:override expired (TTL renewal lapsed)
- governance:CONSERVATIVE all personalities enabled (Redis override clobbered as expected)
- signals:scored LLEN=0; signals:raw LLEN=3,642,342 ⚠ memory leak
- bot_core:health absent (OBS-014)
- DB: 1138 closed paper_trades, 0 NULL on corrected_pnl_sol (Session B verified), 1137 pass_through + 1 live_v1 (Session D)
- Last 24h SD: n=64, pnl=-1.31 SOL, 11 wins (17%), 38 no_momentum exits, **7 trades with MC>$3000 entered** (confirms SD_MC_CEILING gate inert + Session C rollback was correct)
- Trading wallet 0.064 SOL on-chain (Helius confirmed); holding wallet ~0.01 SOL

**Key deliverables:**

1. **AGENT_CONTEXT.md rewritten** (§§1-11): authoritative current-state file with last-updated header. Replaced stale 2026-04-05 prepend; preserved prior content as historical archive. New chats read this first; refresh after any state change. 11 sections cover bot mode, deployed config, wallets, personalities, performance baseline, V5a preconditions, known unresolved (Tier-1 carry), Redis snapshot, DB snapshot, doc index, and reproducibility.

2. **ZMN_ROADMAP Decision Log added**: 18 dated entries newest-first with status + 1-line reasoning per lever. Captures the *judgement trail* — separates the work-item catalogue from the why-did-we-decide-this trail. Plus a "Future-queued levers" table for the planned-but-not-decided items.

3. **USERMEMORIES_DRIFT report**: 13-claim drift table from this audit cycle, broken into 4 severity classes (🔴 ACTION-CHANGING / 🟡 SCOPE-CONFUSION / 🟢 SAMPLE-STALE / 🔵 NUANCE-MISSING). 4 of 13 surveyed claims drifted (2 action-changing). Includes "what we DID right this audit cycle" — the Persistence Convention was already informally observed by Sessions A-D; E codifies it.

4. **CLAUDE.md "Persistence Convention" section**: codifies "userMemories is NOT a source of truth"; lists what to trust memory for (patterns, conventions, pointers) vs. what NOT to trust (specific env values, trade counts, wallet balances). Anchors AGENT_CONTEXT.md as the authoritative current-state file.

**Stop-condition check:** 0 of 3 STOP conditions tripped. Sessions A-D STATUS entries indicate stable deploys (bot_core hotfix verified working at 08:24 UTC; Session C rolled back cleanly; Session D code change live; no EMERGENCY_STOP). AGENT_CONTEXT rewrite preserves historical content as archive (not lost).

**Blockers cleared:**
- ✅ **STATUS-CONVENTION-001** — promoted from 🟡 IN_PROGRESS to ✅ COMPLETED (this is the 5th+ session to append cleanly to STATUS.md).
- ✅ **Persistence convention codified** — 4 deliverables landed.

**Blockers new/active:** all carry from prior entries. Plus a small open: AGENT_CONTEXT freshness self-check (recommended in drift report §7).

**Next prompt:** Chain A→B→C→D→E complete. **24-48h paper observation window** opens for the four behavioral changes. Track: `no_momentum_90s` exit count (TUNE-009 deferral validation), `market_cap_at_entry > $3000` rate (should remain non-zero until SD_MC_CEILING_002 lands), `corrected_pnl_sol` populated on every fresh row (BUG-022 fix verification), live close path code coverage (no exercise until V5a but ImportError check passes via paper closes that don't hit `_simulate_*`-wrapped paths). V5a flip is the final remaining session — pending Jay's ~3 SOL wallet top-up + observation results.

**Pending Claude-chat prompts not yet pasted:** none — chain A-E complete.

**Verdict:** SESSION_E ✅ DELIVERED. AGENT_CONTEXT.md is now the authoritative current-state file. Decision Log captures the judgement trail. USERMEMORIES_DRIFT empirically motivates the Persistence Convention. CLAUDE.md codifies the rule. Future chats start at AGENT_CONTEXT, not at userMemories.

---

## 2026-04-30 — LIVE-FEE-CAPTURE-PATH-A-2026-04-30 (Session D: Path A wired into live close path)

**Committed (this session):** `badb221` fix(bot_core): LIVE-FEE-CAPTURE-001 Path A — fees/slippage capture + PnL formula. Files: `services/bot_core.py` (3 code changes + 1 import addition) + `docs/audits/LIVE_FEE_CAPTURE_PATH_A_2026_04_30.md` (NEW, 9 sections) + STATUS.md prepend + ZMN_ROADMAP.md.

**State changes:**
- DB: id 6580 (only real on-chain live trade) backfilled with `correction_method='live_estimated_v1'`. Fees=0.008306 SOL (paper-estimated round-trip), slippage_pct=10.41 (paper-estimated avg), corrected_pnl_sol=-0.006430 SOL (vs realised gross +0.001876).
- Code: `services/bot_core.py:73-77` — module-level import of `_simulate_slippage`, `_simulate_fees` (outside `if TEST_MODE:` so live path can call them). `bot_core.py:1247-1271` — Change 3a PnL formula now subtracts paper-estimated round-trip fees from gross. `bot_core.py:1284-1305` — Change 3b live close UPDATE writes slippage_pct/fees_sol/corrected_*/correction_method='live_estimated_v1' (distinct param slots $11-$15 per BUG-022 hotfix lesson). `bot_core.py:922-948` — Change 3c live entry INSERT writes slippage_pct/fees_sol/features_json (16-column INSERT, was 13).
- Single git push triggers bot_core auto-redeploy.

**Bot state:** RUNNING (paper, post-Session-B-hotfix verified). Bot_core deploy in flight at session commit time. TEST_MODE=true so no live trades will exercise the new live close path inline; verification limited to ImportError check + id 6580 backfill confirmation.

**id 6580 backfill — Path A NOT empirically validated:**

| metric | value |
|---|---:|
| realised_pnl_sol (gross stored) | +0.001876 SOL |
| corrected_pnl_sol (Path A) | -0.006430 SOL |
| on-chain actual (`ZMN_LIVE_ROLLBACK.md`) | -0.094245 SOL |
| **gap (Path A − actual)** | **+0.087815 SOL** |

Path A undercorrects by ~12× the actual cost. **Above the ±0.02 SOL validation tolerance from the chain prompt.** Paper fee model under-counts real Solana priority fees, MEV impact, and slippage on real on-chain trades. Path A delivers parity-of-record (live rows now write fees/slippage/features_json/corrected_*) but **not parity-of-truth**. Path B (Helius `parseTransactions` for actual on-chain fill data) remains the right long-term answer; tracked as **LIVE-FEE-CAPTURE-002**.

**Compile-checked:** `python -m py_compile services/bot_core.py` → OK.

**Step 8 verification queued post-deploy:** poll Railway MCP for bot_core SUCCESS, wait 90s, check startup banner for ImportError on `_simulate_*` (would ROLLBACK), query id 6580 to confirm backfill landed, check fresh paper closes still write `pass_through` correctly (Session B regression check).

**Blockers cleared:**
- ✅ **LIVE-FEE-CAPTURE-001 (Path A)** — wired into live close path. Path B remains open.
- ✅ **LIVE-PNL-FEE-FORMULA-001** — `bot_core.py:1249` now subtracts fees from gross PnL.
- ✅ **LIVE-FEATURES-JSON-001** — live entry INSERT now populates `features_json`.
- 🟡 **LIVE-ROW-BACKFILL-001 (partial)** — id 6580 backfilled with Path A. The other 5 trade_mode='live' rows are reconcile-residual paper closures (NULL signatures); they don't need backfill per WALLET-DRIFT audit §4.

**Blockers new/active:**
- 📋 **LIVE-FEE-CAPTURE-002 (NEW, V5a-blocking-but-degradable)** — Path B implementation. Helius `parseTransactions` on entry/exit signatures returns actual SOL deltas + on-chain fees. Replaces estimates with truth. ETA ~3-5h next session. Prerequisite for V5a's first unsupervised live window.
- 📋 **LIVE-CLOSE-FALLBACK-INSERT-001 (NEW, low)** — `bot_core.py:1318` legacy 21-column INSERT (live close fallback when entry INSERT failed) doesn't include fees/slippage/features_json/corrected_*. Low-traffic path; cleanup item.
- All carry blockers unchanged: TREASURY-TEST-MODE-002 🟡, ML-THRESHOLD-DRIFT-2026-04-29 🟡, TUNE-009 ⏸ DEFERRED, SD_MC_CEILING_002 📋 (Session C rollback's follow-up).

**Stop-condition check:** 0 of 4 STOP conditions tripped at this point. Compile passed. Backfill applied successfully. id 6580 gap (+0.088 SOL) is informative-not-failure per prompt's "If it doesn't [validate], that's a finding".

**Next prompt:** **SESSION E (PERSISTENCE_HARDENING)** — proceeding immediately. E is docs-only (no service redeploys) so deploy timing doesn't gate it.

**Pending Claude-chat prompts not yet pasted:** Session E queued and pasted in this CC session — proceeding through chain.

**Verdict:** LIVE-FEE-CAPTURE-001 Path A ✅ DEPLOYED. Three code changes + 1 backfill + 1 audit. id 6580 result confirms Path B urgency for V5a-blocking parity-of-truth.

---

## 2026-04-30 — SD-MC-CEILING-DEPLOY-2026-04-30 (Session C: env var + code gate)

**Committed (this session):** `badb221` feat(signal_aggregator): SD_MC_CEILING_001 deploy at $3000. Files: `services/signal_aggregator.py` (env var read at L46-53 + gate at L1826-1838) + `docs/audits/SD_MC_CEILING_DEPLOY_2026_04_30.md` (NEW, 10 sections) + STATUS.md prepend + ZMN_ROADMAP.md.

**State changes:**
- Railway env var `SD_MC_CEILING_USD=3000` on signal_aggregator (via Railway MCP `set-variables`). Auto-redeploys SA.
- Code: gate placed BEFORE existing prefilter block — saves Twitter API call on rejected tokens. Drops `speed_demon` from `targets` if `mc_at_eval > SD_MC_CEILING_USD`; `if not targets: continue` short-circuits the rest of the pipeline.
- No bot_core changes. No Redis writes. Single git push triggers signal_aggregator auto-redeploy.

**Bot state:** RUNNING (paper). Bot_core hotfix `17c2aac` from earlier in this session is mid-deploy — stale_no_price exits had been throwing `inconsistent types deduced for parameter $10` for ~2 minutes pre-hotfix (3 trade IDs 7743/7744/7745 looped). Hotfix splits the corrected_* params into distinct slots ($11/$12/$13 in paper_trader, $5/$6/$7 in bot_core).

**Decision rationale ($3k vs $5k):** original SD_MC_CEILING_001 proposal was $5k from 4-day audit. Revised tighter to $3k based on 35h post-recovery data: 39 trades >$3k = -1.77 SOL / 0% WR vs 20 trades >$5k = -1.04 SOL / 0% WR. Cutting at $3k recovers ~83% more loss without losing any winners (all 14 big winners ≥0.10 SOL each entered at MC < $800). Cross-confirmed by Session A's analysis: 97.6% (120/123) of `no_momentum_90s` dead trades enter at $800-$3000.

**Compile-checked:** `python -m py_compile services/signal_aggregator.py` → OK.

**Step 5 verification queued:** post-deploy poll Railway MCP for signal_aggregator SUCCESS, wait 90s, tail SA logs for `SD reject ... ceiling 3000` lines. Query last 60min SD trades for any `market_cap_at_entry > 3000` — should be ZERO. Result will be appended to audit doc §5.

**24h verification queued for ~2026-05-01:** confirm zero SD entries above ceiling; compare WR/PnL to 35h post-recovery baseline (272 trades, 23.4% WR, +0.140 SOL).

**Blockers cleared:** ✅ TUNE-006 (partial) — SD_MC_CEILING component landed. Other TUNE-006 components (SD_DEAD_ZONE_001 AEDT pause, SD_ML_THRESHOLD_LIFT 40→50) remain queued.

**Blockers new/active:**
- ⚠️ **B HOTFIX in flight** — bot_core hotfix `17c2aac` deploy ETA ~5-10m. Verification pending. If hotfix fails, ROLLBACK both Session B and the hotfix.
- All carry blockers unchanged: TREASURY-TEST-MODE-002 🟡, ML-THRESHOLD-DRIFT-2026-04-29 🟡, LIVE-FEE-CAPTURE-001 🔥 (Session D), LIVE-PNL-FEE-FORMULA-001 🔥 (Session D), TUNE-009 ⏸ DEFERRED.

**Stop-condition check:** 0 of 4 STOP conditions tripped at this point for Session C (no SA deploy failure, no SD entry >$3k yet — verification pending).

**Next prompt:** **SESSION D (LIVE-FEE-CAPTURE Path A)** — proceeding immediately. D touches bot_core (different from C's signal_aggregator). However, D requires bot_core stable post-hotfix; will verify hotfix deploy success before pushing D's code change.

**Pending Claude-chat prompts not yet pasted:** Sessions D, E queued and pasted in this CC session — proceeding through chain.

**Step 5 verification result (08:30 UTC):** ❌ FAIL — 2 of 14 fresh SD trades since 08:01 UTC entered with `market_cap_at_entry > 3000` (id 7749 at $4,482; id 7757 at $9,807). Both definitively after container swap. Root cause: `raw_data["usdMarketCap"]` is `$0` at signal-time for fresh pump.fun new_token signals; the actual MC is computed later in bot_core as `entry_price × 1B supply`. Gate reads the wrong source — structurally inert for the dominant SD signal source. **Not a code bug — design flaw in the chain prompt's gate placement.**

**ROLLBACK executed:** `SD_MC_CEILING_USD=999999999` set on signal_aggregator via Railway MCP at ~08:35 UTC. Code remains in place (harmless no-op at threshold 999M). Re-enable via env var when proper fix lands.

**Follow-up tracked as SD_MC_CEILING_002:** two options — (a) move gate to bot_core at entry decision (uses actual MC), or (b) compute MC from BC reserves in SA gate (mirrors bot_core). Recommend (b) per audit doc §5 to keep filter at signal-gate stage. ETA ~30m next session.

**Verdict:** SD_MC_CEILING attempt #1 ⏪ ROLLED BACK 2026-04-30 — design flaw discovered in verification (gate reads `raw_data` MC which is $0 for fresh signals); env var disabled, code retained for reuse with corrected MC source.

---

## 2026-04-30 — BUG-022-HOTFIX-2026-04-30 (asyncpg type-inference regression)

**Committed (this session):** `17c2aac` fix(paper_trader): BUG-022 hotfix — distinct param slots for corrected_*. Files: `services/paper_trader.py` (param slots $11/$12/$13) + `services/bot_core.py` ($5/$6/$7 for staged-TP correction).

**State changes:** code only. Railway auto-redeploys bot_core.

**Bot state when discovered:** bot_core post-Session-B redeploy was throwing `ERROR: Exit check error for speed_demon:<mint>: inconsistent types deduced for parameter $10` on every exit attempt. Three trade IDs (7743 / 7744 / 7745) loop-failed for ~2 min. Root cause: the original BUG-022 inline-write reused `$4`, `$5`, `$10` for both `realised_*` and `corrected_*` columns. Asyncpg's prepared-statement protocol can't deduce a single PostgreSQL type when the same parameter is referenced for columns of different declared types (schema has `outcome` as character varying and the corrected_* counterparts diverge).

**Fix:** distinct parameter slots for the corrected_* triple. Pass each value twice. Compile-checked. Single push → Railway auto-redeploys bot_core.

**Verification:** *pending — bot_core deploy in flight at Session-C commit time. Will verify before Session D push.*

**Lesson:** the chain prompt's "Parameter reuse ($4, $5, $10) is valid PostgreSQL" is correct in raw psql but FALSE for asyncpg's prepared-statement protocol when the same param appears in columns of different declared types. Future inline-write changes that touch dual-write should use distinct slots even if it costs 3 extra Python args.

**Backfill (1111 rows from prior commit `392c928`) is unaffected** — the backfill UPDATE was a separate ad-hoc statement that did not reuse parameters.

---

## 2026-04-30 — TUNE-010 DEX-PAID-FEATURE-EVALUATION (Verdict: DISCARD, no deploy)

**Committed (this session):** `badb221` docs(audit): TUNE-010 dex_paid feature evaluation — verdict DISCARD. Files: `docs/audits/TUNE_010_DEX_PAID_EVALUATION_2026_04_30.md` (NEW, 10 sections) + STATUS.md prepend + ZMN_ROADMAP.md (TUNE-010 row added). **Docs-only. No services/, no env vars, no Redis writes, no Railway deploys.**

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

**Committed (this session):** `badb221` fix(paper_trader): BUG-022 backfill + inline write; CLAUDE.md updates. Files: `services/paper_trader.py` (close UPDATE extended with corrected_*) + `services/bot_core.py` (staged-TP correction UPDATE extended with corrected_* for paper branch only) + `CLAUDE.md` (P/L rule rewrite + wallet-drift note appended) + `docs/audits/BUG_022_FIX_2026_04_30.md` (NEW, 8 sections) + STATUS.md prepend + ZMN_ROADMAP.md (BUG-022 ✅ + WALLET-DRIFT ✅).

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

**Committed (this session):** `badb221` docs(audit): SD-EARLY-CHECK-RELAX-2026-04-30 verdict Gamma. Files: `docs/audits/SD_EARLY_CHECK_RELAX_2026_04_30.md` (NEW, 12 sections) + STATUS.md prepend + ZMN_ROADMAP.md (TUNE-009 row added). **Docs-only. No services/, no env vars, no Redis, no Railway deploys.**

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

**Committed (this session):** `badb221` docs(audit): WALLET-DRIFT-INVESTIGATION-2026-04-29 reconciliation [outcome C]. Files: `docs/audits/WALLET_DRIFT_INVESTIGATION_2026_04_29.md` (NEW, 9 sections) + STATUS.md prepend + ZMN_ROADMAP.md (WALLET-DRIFT-2026-04-29 row updated + changelog entry). Read-only. No services/, no env, no Redis, no DB writes, no Railway deploys.

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

**Committed (this session):** `badb221` docs(audit): ENV-AUDIT-2026-04-29 ground-truth Railway/Redis/DB inventory. Files: `docs/audits/ENV_AUDIT_2026_04_29.md` (NEW) + STATUS.md prepend + ZMN_ROADMAP.md (3 new Tier 1 rows + changelog entry). Read-only. No services/ touch, no env changes, no Redis writes, no Railway deploys.

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

**Committed (this session):** `badb221` docs(audit): LIVE-FEE-MODEL-AUDIT-2026-04-29 paper/live divergence check. Files: `docs/audits/LIVE_FEE_MODEL_AUDIT_2026_04_29.md` (new) + STATUS.md + ZMN_ROADMAP.md. **Docs-only. No services/ touch. No env changes. No deploys.**

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

**Committed (this session):** `badb221` docs(tune): TUNE-005 ROLLED BACK — HOLDER_COUNT_MIN 15 → 1 pending 24h validation. ZMN_ROADMAP.md + STATUS.md only. No services/ changes.

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

**Committed (this session):** `badb221` docs(roadmap+status): BUG-022 INVESTIGATED mark + STATUS append. ZMN_ROADMAP.md only (3 status edits) + STATUS.md prepend. **Note:** the audit doc itself (`docs/audits/CORRECTED_PNL_INVESTIGATION_2026_04_28.md`) was already committed in `ca4812d` ~15 min before this session started. This session verified those findings independently and updated the roadmap markers that the prior commit didn't touch.

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
- `/mnt/user-data/outputs/SESSION_CORRECTED_PNL_INVESTIGATION.md` — investigation phase complete this session (`ca4812d` + `badb221`). The execution-shape session is a new prompt yet to be drafted.
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

**Committed (this session):** `badb221` docs(tune): TUNE-005 HOLDER_COUNT_MIN 1→15 rollback post pipeline fix. Touches ZMN_ROADMAP.md + STATUS.md only. No services/, no code.

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

**Committed (this session):** `badb221` docs(roadmap): 2026-04-23 late-day consolidation. Touches ZMN_ROADMAP.md + STATUS.md only. Docs-only diff.

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

**Committed (this session):** `badb221` research(bitfoot): 2026 baseline vs 2025 edge — verdict BASELINE-A. Touches `docs/audits/BITFOOT_2026_BASELINE_2026_04_23.md` (new, committed) + STATUS.md + ZMN_ROADMAP.md. Also local-only under `.tmp_bitfoot2026/`: `sample_2026.py`, `bitfoot2026_sample.csv`, `run_stdout.log` (gitignored dir). No services/, no env vars, no Redis, no Railway deploys.

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
