# FLIP-NIGHT-PREP-001 — off-live-path flip tooling (2026-06-03)

**Type:** read-only audit + standalone operational scripts. **NO live-branch code change, NO bot-behaviour change, NO deploy of bot code.** Writes = the 2 new scripts + docs. Safe to run in the 24h before the flip precisely because none of it touches the `TEST_MODE=false` path. Companion to `FLIP_READINESS_REVIEW_001` (operationalises §5–§7) and the FLIP NIGHT PLAYBOOK.

---

## PART A — #9 HIBERNATE veto gates ENTRIES, not EXITS — ✅ GREEN (load-bearing)
Verified by direct trace + 3 independent adversarial refuters (workflow `wf_31c3e3f5`; all 3 → `entries-only`, no mode-gate-on-exit). Full detail: `.tmp_flipprep/A_hibernate_exit_safety.md`.
- **Entry gates (block NEW positions only):** `bot_core.py:752-766` (#9 live veto, in `process_signal`), `:817-818` (governance HIBERNATE/PAUSE, in `process_signal`), `risk_manager.py:223-225` (`mode_mult==0` in `calculate_position_size` — entry sizing).
- **Exits run regardless of mode:** `bot_core.py:2028 _check_exits` (only pause = `self.emergency_stopped` :2031, NOT mode), `:1946 _evaluate_trailing_stop`, `:1357 _close_position` (paper + live branches), `:2324 _exit_check_listener`, `:642 emergency_stop` (CALLS `_close_position` to liquidate), `:697 _handle_failed_live_sell` (parks by failure-count, leaves position OPEN), `risk_manager.py:295 check_emergency_conditions` (daily-loss/drawdown only), `execution.py` (zero mode refs on sell path).
- **Conclusion:** a position opened before a HIBERNATE dip is still price-checked, trailing-stopped, staged-TP'd, time/stale-exited, and closed. **The PLAYBOOK's "a HIBERNATE dip is NOT a rollback trigger" is verified.** No 🔴.
- *Bonus:* `risk_manager.py:94 TRAILING_STOP_MARKET_MULTIPLIERS` (HIBERNATE=0.50) is dead config (never consumed); even if wired it tightens the trail, never blocks.

## PART B — `scripts/flip_preflight_check.py` (standalone, read-only verifier)
One-shot GREEN/YELLOW/RED table + overall verdict; idempotent, no side effects; exit 0 = ALL-GREEN, 1 = any RED. **Items:** bot_core env (`TEST_MODE` report, `MAX_POSITION_SOL==0.10`, `DAILY_LOSS_LIMIT_SOL==1.5`, `AGGRESSIVE_PAPER_TRADING==false`, `MAX_CONCURRENT_POSITIONS==10`, `HELIUS_DAILY_BUDGET>0`, HELIUS_*_URL/PARSE_TX set, `JUPITER_API_KEY` set, `TRADING_WALLET_PRIVATE_KEY` present-only, `BOT_CORE_FILL_MC_CEILING_USD>0`); signal_aggregator (`AGGRESSIVE_PAPER_TRADING==false`, `HOLDER_COUNT_MIN==15`); Redis (`market:mode:current`, `bot:emergency_stop` unset, `bot:consecutive_losses==0`, `bot:loss_pause_until` unset, `market:mode:override` TTL); on-chain getBalance within 0.05 of LIVE_ONCHAIN snapshot; Postgres open-live-positions==0; API reachability (Helius/Jupiter/PumpPortal OPTIONS — no submit). Plus an informational row: **effective SD concurrency = 3 (per-personality), total cap=10**.
- **Dry-run NOW (`.tmp_flipprep/B_preflight_dryrun.txt`, EXIT=1):** 6 RED = exactly the §6 flip-config items still to apply (`MAX_POSITION_SOL`, `DAILY_LOSS_LIMIT_SOL`, `AGGRESSIVE_PAPER_TRADING`×2, `HELIUS_DAILY_BUDGET`, `HOLDER_COUNT_MIN`). All safety rows GREEN: mode=NORMAL, emergency_stop unset, consecutive_losses=0, **0 open live positions**, wallet **5.0641 SOL**, `MAX_CONCURRENT_POSITIONS=10`. The RED-until-config state is correct pre-flip — the script *works*.
- **Windows note:** resolves the `railway` npm-shim via `shutil.which` + shell fallback (Jay runs on win32); ASCII-only output.

## PART C — `scripts/flip_rollback.sh` (tested, NOT executed)
One command restoring the pre-flip config via `railway variables --set`; CONFIRM-gated; `--dry-run` + `--show-current` modes. **Does NOT touch `bot:emergency_stop` or any safety Redis key; does NOT roll back `MAX_CONCURRENT_POSITIONS`.** Restore set (captured 2026-06-03):
- **bot_core:** `TEST_MODE=true`, `MAX_POSITION_SOL=0.25`, `SPEED_DEMON_MAX_SIZE_SOL=0.25`, `SPEED_DEMON_BASE_SIZE_SOL=0.15`, `DAILY_LOSS_LIMIT_SOL=4.0`, `AGGRESSIVE_PAPER_TRADING=true`.
- **signal_aggregator:** `AGGRESSIVE_PAPER_TRADING=true`, `HOLDER_COUNT_MIN=1`.
- **Verified:** `bash -n` SYNTAX OK; `--dry-run` emits the exact railway commands (runs nothing); `--show-current` read-back matches (`.tmp_flipprep/C_rollback_dryrun.txt`). NOT executed.

## PART D — dashboard watch-readiness — ✅ GREEN (authenticated)
Display references market_mode (analytics), open_positions (dashboard+wallet), recent-trades+execution+exit_reason (all three HTML), PnL incl corrected/live_actual (dashboard+wallet). Unauth `curl`→401 = JWT auth (`DASHBOARD_SECRET`) fail-closed (security positive); authenticated browser returns 200 (deploy-observer). DASH-CORRECTED-PNL panel RESOLVED (0 errors in window). Detail: `.tmp_flipprep/D_dashboard_readiness.md`. **Operator: confirm login works before the window.**

---

## 🚩 FLAGS (new this session — documented, NOT fixed; live path frozen)
1. **`HELIUS_DAILY_BUDGET` unset on bot_core** → preflight RED. The pre-live checklist requires >0. Set it as part of the flip-config (or confirm raw-RPC sends aren't budget-gated). Verify before flip.
2. **Jupiter price API → HTTP 403** with the deployed `JUPITER_API_KEY` (preflight, `api.jup.ag/price/v3`). Could be a test artifact (free vs paid tier / `lite-api.jup.ag` host / IP) OR a real pricing-auth gap. The bot's live **post-grad sells** depend on Jupiter; paper pricing has Redis/BC fallbacks so it hasn't surfaced. **Verify Jupiter price auth/endpoint before the flip** — filed `JUPITER-PRICE-AUTH-VERIFY-001`.
3. **Effective concurrency = 3, not 10** (SIZING-CAPS-WIRING-001-B) — the PLAYBOOK's `[CAPS] cap=10` is the *total*; the per-personality cap binds SD at 3. Surfaced as an informational verifier row so the operator isn't misled.

## Runbook integration
`flip_preflight_check.py` is the canonical pre-flight gate (PLAYBOOK Steps 0 & 3 — require ALL-GREEN except TEST_MODE before Step 4). `flip_rollback.sh` is the PLAYBOOK Step 8 one-command rollback.
