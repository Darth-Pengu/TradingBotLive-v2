# FLIP NIGHT PLAYBOOK — first live trial

**Canonical operator runbook for the `TEST_MODE=false` flip.** Single doc for the window.
**Target:** Thu 2026-06-04, 18:00–21:00 Sydney (or any authorized non-HIBERNATE window).
**Assumes landed:** `SIZING-CAPS-WIRING-001` ✅ + `FLIP-NIGHT-PREP-001` ✅ (both did, 2026-06-03).
**Wallet:** 5.064 SOL on-chain (`4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ`).
**Governance:** dead-and-conservative by decision (no Anthropic credits — intended; applies a 0.8× size haircut + provides no regime signal; #9's `market:mode` veto is the live regime control).
**Goal of the trial:** verify the live execution path works + bank a few real Path-B data points + nothing catastrophic. **NOT** volume, **NOT** matching paper's +8.9/day.

> **Execution note:** the flip (STEP 4) is the operator's authorized in-window action. Claude Code does **not** auto-execute the flip; it is session-gated (explicit authorization + rollback + on-chain-balance ack per CLAUDE.md "Live trading mode — session-gated").

> **Companion docs:** `docs/audits/FLIP_READINESS_REVIEW_001_2026_06_03.md` (go/no-go + env matrix §5 + flip-config §6), `docs/audits/FLIP_NIGHT_PREP_001_2026_06_03.md` (the tooling + #9 exit-safety proof), `docs/audits/REMEDIATION_PHASE_0_1_2026_06_03.md` (per-fix detail + flip-confirmed-only caveat).

---

## STEP 0 — before you start (can be earlier in the day)
- Run the pre-flight verifier: **`python scripts/flip_preflight_check.py`**. Expect env rows RED/YELLOW until you apply the config in Step 2 — that's fine now. Confirm the **non-env** rows are clean: **0 open live positions**, `bot:emergency_stop` unset, `bot:consecutive_losses=0`, wallet ≈5.064, APIs reachable.
- **The two FLIP-NIGHT-PREP-001 flags are now CLEARED (2026-06-04):**
  1. **`HELIUS_DAILY_BUDGET`** — ✅ set `=100000` on bot_core + treasury. (Note: it does NOT gate the live exec path — only treasury balance-polling + dashboard display; the live Helius proof is the GREEN on-chain getBalance row.)
  2. **Jupiter price API 403** — ✅ resolved: it was the preflight's `Python-urllib` User-Agent hitting Jupiter's WAF, NOT a bot/auth problem. The deployed key + `api.jup.ag/price/v3` return 200 + valid price; the bot (aiohttp) is unaffected. Verifier fixed (browser UA) → Jupiter row GREEN.
  (Re-run `flip_preflight_check.py` to confirm: only the §6 flip-config rows should be RED, applied at Step 2.)
- Confirm `market:mode:current`. NORMAL/DEFENSIVE = trade. HIBERNATE = entries pause (Step 7) — not a blocker, but ideally start non-HIBERNATE.
- Be set up for a 4–6h watch: bot_core logs streaming, dashboard open + **logged in** (JWT — confirm login works), Discord alerts visible, this doc + the rollback command ready.

## STEP 1 — pre-flight clean (CLEAN-003)
`export REDIS_URL=$(railway variables -s Redis --kv | grep -E '^REDIS_URL=' | cut -d= -f2-)` then `bash scripts/live_flip_prep.sh` — clears `bot:status`, `paper:positions:*`, `bot:open_positions:*`. Confirm it reports clean. (`bot:consecutive_losses` already 0; leave safety keys alone.)

## STEP 2 — apply the flip-config (batched, ONE redeploy per service)
**bot_core** — set all together (15–25 min redeploy):
```
MAX_POSITION_SOL=0.10
SPEED_DEMON_MAX_SIZE_SOL=0.10
SPEED_DEMON_BASE_SIZE_SOL=0.10
DAILY_LOSS_LIMIT_SOL=1.5
AGGRESSIVE_PAPER_TRADING=false
HELIUS_DAILY_BUDGET=<set >0>        # NEW — clear the flag from Step 0
# MAX_CONCURRENT_POSITIONS=10       ← already set by SIZING-CAPS-WIRING-001; VERIFY, do not re-set
# TEST_MODE=false                   ← DO NOT set yet — Step 4
```
**signal_aggregator:**
```
AGGRESSIVE_PAPER_TRADING=false
HOLDER_COUNT_MIN=15                 # SA-only (bot_core does NOT read it — confirmed)
```
Apply, let both redeploy. Do not flip mid-deploy.

> **⚠️ Concurrency reality (SIZING-CAPS-WIRING-001-B, open):** `MAX_CONCURRENT_POSITIONS=10` is the **total** cross-personality cap. The **effective** Speed-Demon concurrency is **3** (per-personality `risk_manager.MAX_CONCURRENT_PER_PERSONALITY`, hardcoded, NOT wired). So the trial will hold **at most 3 concurrent positions**, not 10. That is fine for a first supervised window — just know the real cap is 3. The startup `[CAPS] concurrency cap=10` line reflects the total, not the effective.

## STEP 3 — re-run pre-flight, require ALL-GREEN (except TEST_MODE)
`python scripts/flip_preflight_check.py`. Every row GREEN except `TEST_MODE` (still `true` — flips last). Any RED → fix it; **do not proceed on a RED.** Especially: 0 open positions, wallet ≈5.064, `emergency_stop` unset, `MAX_CONCURRENT_POSITIONS=10`, `DAILY_LOSS_LIMIT_SOL=1.5`, `MAX_POSITION_SOL=0.10`, `AGGRESSIVE_PAPER_TRADING=false` on both services, `HELIUS_DAILY_BUDGET>0`.

## STEP 4 — THE FLIP
Set **`TEST_MODE=false`** on bot_core. Let it redeploy. *(Operator action — session-gated authorization required.)*

## STEP 5 — post-flip startup verification (watch the bot_core log on boot)
All must be true or **roll back (Step 8)**:
- `Startup reconciliation: 0 open positions` (if N>0 → phantom leak → STOP/rollback).
- **On-chain balance seed ≈ 5.064 SOL, NOT 132.6** (fix #12 — if it logs ~132.6, the exposure/drawdown denominators are wrong and the safety rails are miscalibrated → rollback).
- `TEST_MODE=false` propagated; sell-storm breaker present; no `RuntimeError`/import error.
- `[CAPS] concurrency cap=10 (env=10, gov=10)` present (total cap; effective SD cap = 3).

## STEP 6 — first live trades: sequence them deliberately
The first window is the **only** runtime test of the flip-confirmed-only fixes. Don't throw the full strategy at the first signal:
1. **Let exactly one small full round-trip happen** (buy → full exit). Exercises buy-idempotency (#6), failed-sell result-check (#4), and on-chain confirm with minimal exposure. Watch it land + close.
2. **Watch that first live close write `live_actual_v1`** (Path B). If `live_estimated_v1` instead, flag it (do NOT auto-rollback on that alone — accounting fidelity, not capital risk).
3. **Then** let staged-TP / partial-sell logic run on subsequent trades (exercises #5 partial sizing + #7 routing + #14 cumulative PnL).

## STEP 7 — what's NORMAL during the watch (do NOT panic-rollback)
- **`market:mode` dips to HIBERNATE** → new entries pause; **open positions keep managing + exiting** (#9 working correctly — VERIFIED, FLIP_NIGHT_PREP_001 Part A: exits run regardless of mode). Wait for recovery or end the window. **NOT a rollback trigger.**
- **Very few trades / long gaps** → expected. Live admits far fewer signals than paper (no AGGRESSIVE bypass; SA threshold 65 vs paper's 30). A quiet window is the system working.
- **Position sizes < 0.10 SOL** (often ~0.08 or less) → the 0.8× dead-governance haircut + time-of-day multiplier. Expected; smaller = safer.
- **≤3 concurrent positions** → the per-personality cap. Expected (see Step 2 note).
- **A failed sell that parks the position** (stays open, retried by `_check_exits`) → #4 working as designed. Watch it retry + eventually exit; escalate only if stuck (Step 8).

## STEP 8 — ROLLBACK TRIGGERS → `bash scripts/flip_rollback.sh` (type CONFIRM)
Roll back immediately on ANY of:
- `RuntimeError`/import error at startup, or balance seeded wrong (~132.6 not ~5.064).
- **EMERGENCY_STOP trips** (daily-loss limit 1.5 SOL hit, or the emergency path fires).
- **Sell-storm** — any mint exceeds the sell-fail threshold (>8 errors).
- **Drawdown >5%** on a fresh restart.
- **Any stranded/trapped position that does not resolve** (parked and not exiting after retries).
- Anything that looks like real SOL leaving the wallet without a corresponding recorded position.

`flip_rollback.sh` sets `TEST_MODE=true` + restores the pre-flip config; it does **NOT** clear `bot:emergency_stop` (if that fired, review it manually before any re-flip) and does **NOT** roll back `MAX_CONCURRENT_POSITIONS`.

**NOT triggers** (Step 7): a HIBERNATE pause, low volume, small sizes, ≤3 concurrent, a single parked sell that then retries/exits, a `live_estimated_v1` (vs `live_actual_v1`) label.

## STEP 9 — after the window
- **If completed:** capture the live trades + how many `live_actual_v1` (Path B) rows landed; note WR / PnL with the caveat that it's a tiny sample carrying full real costs (fees + slippage + latency + **MEV**, Jito off) — a conservative lower bound, the right way to read a go/no-go. Upload the result; assess whether to widen (raise sizing ladder / wire 001-B for >3 concurrent / restore governance).
- **If aborted:** next session defaults to `TEST_MODE=true`; **no re-flip without new explicit authorization.** Capture what tripped it → documented follow-up.

---

**Frozen for the window:** no live-branch code changes after `SIZING-CAPS-WIRING-001`. The flip-confirmed-only fixes (#4/#5/#6/#7/#9/#10/#11/#12/#13/#14) are being runtime-tested for the FIRST time here — adding new live-path code now would put untested logic into the trial. Anything that surfaces tonight is a documented follow-up, not a same-night patch.
