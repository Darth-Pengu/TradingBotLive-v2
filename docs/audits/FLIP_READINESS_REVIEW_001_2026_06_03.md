# FLIP READINESS REVIEW — FLIP-READINESS-REVIEW-001

**Date:** 2026-06-03 (Sydney AEST) · **Mode:** read-only audit, ZERO state writes · **Author:** CC (Opus 4.8)
**Purpose:** Single durable go/no-go reference for the `TEST_MODE=false` flip on `bot_core`. Built from **live state verified this session** (Railway env / Redis / Postgres / on-chain), cross-referenced with the standing findings docs. Designed to persist across chats — upload alongside `STATUS.md` + `ZMN_ROADMAP.md`. Re-verify live state if this doc is >~3 days old (per the CLAUDE.md persistence convention).

---

## 0. VERDICT — CONDITIONAL GO (technical), HOLD pending 4 decisions + flip-time confirmation

**The §B remediation that blocked the flip is wholly complete and deploy-verified (Phases 0–3).** The bot is healthy, recovered from the 05-28 outage, hardened, and observable. PC1/PC2/PC3 are satisfied; **PC4 (the flip itself) is Jay-authorization-gated.**

The flip is **NOT yet a clean GO** because of items that are *operator decisions / config*, not remediation code:

| Gate | State |
|---|---|
| §B Phases 0–3 (remediation code) | ✅ COMPLETE + DEPLOY-VERIFIED |
| PC1 wallet ≥ operational min | ✅ 5.064 SOL on-chain (verified) |
| PC2 validation edge supports continuing | ✅ (+8.91 SOL/day, 91.9% WR, n=1066; cost-corrected +32.5 SOL/76.7%) |
| PC3 technical (reconcile filter / mode parity) | ✅ deployed |
| **BUG-010** Anthropic credits (governance LLM dead) | 🔴 **OPEN — real prerequisite** |
| **Sizing/caps vs V5A intent** (4 env discrepancies, §5) | 🔴 **must set at flip** |
| **Live-only fixes runtime confirmation** | 🟠 confirms only at supervised first live trades |
| PC4 flip authorization + Wed/Thu 18:00–21:00 Sydney window + non-HIBERNATE | ⏳ Jay-gated |

**Recommendation:** resolve BUG-010 (credits) + apply the §6 flip-config, then flip in a supervised non-HIBERNATE window with the §7 runbook. Do NOT flip with the current env as-is (it sizes 2.5× the V5A first-24h intent and allows 10 concurrent vs the intended 5).

---

## 1. LIVE STATE SNAPSHOT (verified 2026-06-03)

| Surface | Value | Source |
|---|---|---|
| `TEST_MODE` (bot_core) | **true** (paper) | Railway env |
| On-chain wallet `4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ` | **5.064095633 SOL** | Helius getBalance |
| `market:mode:current` | **NORMAL** | Redis |
| `market:mode:override` | not set (computed mode governs) | Redis |
| `bot:emergency_stop` | not set (clean) | Redis |
| `bot:consecutive_losses` | 0 | Redis |
| `bot:loss_pause_until` | not set (clean) | Redis |
| `bot:portfolio:balance` (PAPER) | 132.6 SOL | Redis |
| `market:sol_price` | $74.85 | Redis |
| latest `portfolio_snapshots` | id 49756, 132.6 SOL, daily_pnl +0.197, 0 open, NORMAL, 12:32Z | Postgres |
| latest `LIVE_ONCHAIN` snapshot | 5.064 SOL @ 2026-05-20 (last live activity) | Postgres |
| `paper_trades` | 4282 paper + 20 live rows; **only 1 real on-chain live row** (id 6580); 0 open | Postgres |
| `trades` ML corpus | 10,935 rows; now carries corrected_* cols (migration 003) | Postgres |
| governance:latest_decision | CONSERVATIVE / size_mult **0.8** / max_concurrent **10** — LLM DEAD (BUG-010) | Redis |

**Note the 132.6 SOL (paper) vs 5.064 SOL (real) gap** — this is exactly the inflated-denominator case Phase-2 #12 corrects: at live startup `_load_state` now seeds `total_balance_sol` from on-chain getBalance, not the paper snapshot.

---

## 2. §B REMEDIATION STATUS (all deploy-verified)

Full per-fix detail: `docs/audits/REMEDIATION_PHASE_0_1_2026_06_03.md` (single oversight record, Phases 0–3). Audit source: `docs/audits/FULL_CODE_AUDIT_001_2026_06_02.md`.

| Phase | Scope | Commits | Status |
|---|---|---|---|
| 0 restore/harden/observe | pubsub-isolation (`supervise`), market-mode misclassification, redis hardening, deploy observability | `f343295 9fa45b0 e30d41b 2337565 34f2515` | ✅ runtime-confirmed |
| 1 live-execution correctness | failed-sell result-check + emergency-stop, buy-idempotency + Jito-off, partial-sell sizing, unconditional pool-state refresh | `2a85508 29fca1b 09f71c1 94457ef` | ✅ deploy-clean; **behaviour flip-confirmed-only** |
| 2 safety rails | live HIBERNATE veto, governance cfgi-read, live startup-state (daily-loss + on-chain seed), fill-MC fail-CLOSED | `7e83949 7fe2ad1 78cc45c c70aba1` | ✅ deploy-verified; live-only |
| 3 accounting integrity | live staged-TP cumulative PnL + Path-B multi-exit + on-chain reconcile; dashboard mode-fidelity + entry-sentinel; DASH-CORRECTED-PNL (subquery alias) + api_stats f-string | `b6c52fc 888e2f5 89ca0a1 d89a803` + prod migration 003 | ✅ deploy-verified (`/api/status→200`, error gone) |

**Critical caveat (carries to the flip):** every Phase-1 and most Phase-2/#14 fixes live in the `TEST_MODE=false` (live `else:`) branch → **NOT paper-observable**. They are verified by py_compile + unit/structural tests + prod query-replay + code review; their **runtime behaviour confirms only at the first supervised live trades.** This is inherent, not a gap — but it means the first live window IS the final test of the execution path.

---

## 3. EXTERNAL API / DEPENDENCY MATRIX

Criticality = impact on the **live execution path** specifically.

| Dependency | Used for | Live-path criticality | Status (verified/known) |
|---|---|---|---|
| **Helius RPC** (`HELIUS_STAKED_URL`→`HELIUS_RPC_URL`→`HELIUS_GATEKEEPER_URL`, 3-tier) | tx submit (`_send_transaction`), `getBalance` (balance seed + close snapshot), `getSignatureStatuses` (#6 idempotency), `getAccountInfo` (BC pool-state refresh #7) | 🔴 CRITICAL — no live trade or confirmation without it | All 3 URLs SET (redacted) on bot_core. Helius API family reachable (getBalance succeeded this session). **VERIFY at flip:** `HELIUS_DAILY_BUDGET` (not set as env → code default; CLAUDE.md pre-live checklist requires >0; budget-gated pricing/enrichment ≠ raw RPC send, but confirm RPC path isn't budget-blocked). |
| **Helius parseTransactions** (`HELIUS_PARSE_TX_URL`) | Path B on-chain native-delta (correct PnL, #14) | 🟠 accounting only (Path A fallback if it fails) | URL SET. Engine intact (id 6580 native delta −374,251,786 lamports exact). |
| **Jupiter** (`api.jup.ag`, `JUPITER_API_KEY`) | price v3 (`_get_token_price`); post-grad swap order/execute (`_execute_jupiter`) | 🔴 CRITICAL for post-grad sells + pricing | KEY SET. EXEC-002 (Jupiter NameError) confirmed RESOLVED in audit. |
| **PumpPortal Local** (`pumpportal.fun/api/trade-local`) | pre-grad buy/sell tx build (`_execute_pumpportal_local`) | 🔴 CRITICAL for pre-grad (the common SD case) | No key required. Sell payload audited spec-correct (Session 3). |
| **PumpPortal WS** (signal_listener) | token discovery, early trade subscriptions, `token:stats` | 🟠 feed quality (not the send path) | ALIVE. |
| **Jito** (`JITO_ENDPOINT` set) | (intended) MEV-protected bundle submit | ⚪ DISABLED in code (#6 forces `use_jito=False` — bundle path returns UUID-not-sig + no tip). Live uses local-RPC `_send_transaction`. | `JITO-REIMPLEMENT-001` follow-up. No MEV protection on live submits — acceptable for supervised micro-window. |
| **Anthropic** (`ANTHROPIC_API_KEY`, `GOVERNANCE_MODEL=claude-haiku-4-5`) | governance LLM (regime classification, size_multiplier, max_concurrent) | 🔴 **DEAD — BUG-010** | KEY valid but **account credits exhausted** → every call 400s → fallback `CONSERVATIVE/0.8×/max_concurrent 10`. **This is a real prerequisite** (§4.1). |
| **GeckoTerminal** | holder-count / token info enrichment | 🟢 feature input (fail-safe handles drift per HOLDER-DATA-PIPELINE-001) | known; not send-path. |
| **Vybe** (`VYBE_API_KEY`) | Solana analytics (whale/holders) | 🟢 non-critical for SD live | KEY SET; v3 URL drift deferred. |
| **Nansen** (`NANSEN_DRY_RUN=TRUE`) | smart-money (Analyst) | ⚪ DISABLED by design | not re-enable without budget decision. |
| **SocialData** (`SOCIALDATA_API_KEY`) | social enrichment | 🟢 credits exhausted (dead); non-critical | known. |
| **Discord** (`DISCORD_WEBHOOK_URL`) | alerts (emergency-stop, internal-down, sell-storm) | 🟠 observability during the watch | SET. |
| **Sentry** (`SENTRY_DSN`) | error capture | 🟠 observability | SET. |
| **Postgres** (`postgres.railway.internal/railway`) | permanent state (trades, snapshots) | 🔴 CRITICAL | healthy; migration 003 applied. |
| **Redis** (`redis.railway.internal`) | live cache, mode, safety keys, pubsub | 🔴 CRITICAL | healthy; client hardened (keepalive/health_check/retry). Environmental read-timeouts tolerated (REDIS-CLIENT-HARDENING-001). |

---

## 4. THE 4 DECISION-GATED ITEMS (flip blockers that are NOT code)

### 4.1 BUG-010 — governance LLM dead (Anthropic credits) 🔴 REAL PREREQUISITE
- **Now:** every paper trade sized **0.8×** (silent CONSERVATIVE haircut); governance gives **zero real regime signal**; concurrency cap defaults to governance's `max_concurrent_positions=10`.
- **At live:** #9 (`market:mode:current` HIBERNATE veto) is the **only** live regime control while governance is dead. The 0.8× haircut and the 10-cap also apply live.
- **Decision:** restore Anthropic credits before flip (recommended) OR explicitly accept dead-governance posture (`GOVERNANCE-STALENESS-POLICY-001`). A "stale→halt" rule would currently halt the bot; a "stale→cap" is a permanent live haircut. **Do not flip blind to this.**

### 4.2 SIZING-CAPS-WIRING-001 — concurrency caps 🔴 [UPDATED 2026-06-03 — partial fix landed + correction]
- **TWO caps exist (this review's first pass cited only the total — corrected here):**
  - **Total (cross-personality)** at `bot_core.py:831`: `len(self.positions) >= max_concurrent`. ✅ **SIZING-CAPS-WIRING-001 landed** (`<see commit>`): now `min(MAX_CONCURRENT_POSITIONS env, gov)`, env=**10** set, governance can only tighten. `MAX_SD_POSITIONS`(20) stays phantom.
  - **Per-personality** at `risk_manager.py:51 MAX_CONCURRENT_PER_PERSONALITY=3` (WHALE=2), enforced in `calculate_position_size` (returns 0.0 → bot_core `:898` blocks). **HARDCODED, NOT wired.**
- **🚩 EFFECTIVE TRIAL CONCURRENCY = 3, not 10.** SD-only (Analyst off, Whale dormant) → SD per-personality cap **3** binds before the total-10 is ever reached. The total-cap wiring is robustness/determinism, not a behaviour change at the current value.
- **Decision/follow-up:** to set the trial's effective concurrency to the V5A ladder (5 → 5 → 7), wire `risk_manager.MAX_CONCURRENT_PER_PERSONALITY` → **SIZING-CAPS-WIRING-001-B** (open). If 3 is acceptable for the supervised first window, no action needed — but the operator should know the cap is 3, not 10.

### 4.3 TIMEZONE-SIZING-FIX-001 🟠
- TIME_GOOD/DEAD/SLEEP/WEEKEND sizing multipliers fire on a hardcoded UTC+11 clock (1h off in AEST) AND time-of-day is applied twice (risk_manager UTC + bot_core UTC+11). Changes *paper* sizing → needs a semantics decision before fixing. Correctness, not money-loss.

### 4.4 GOVERNANCE-STALENESS-POLICY-001 🟡
- Defines how live treats stale/dead governance (ties to 4.1). Decision-gated.

---

## 5. ENVIRONMENT VARIABLE MATRIX (deployed vs V5A-intent)

Verified on `bot_core` / `signal_aggregator` this session. **"FLIP ACTION" = change required before/at flip.**

| Var (service) | Deployed | V5A intent / correct | Read by | FLIP ACTION |
|---|---|---|---|---|
| `TEST_MODE` (bot_core) | `true` | `false` to flip | all | **SET false** (the flip) |
| `AGGRESSIVE_PAPER_TRADING` (bot_core+SA) | `true` | `false` at live | SA HIBERNATE bypass (#9), loss-pause | **SET false** (#9 runbook; else paper-bypass logic only gated correctly by TEST_MODE — but defense-in-depth) |
| `MAX_POSITION_SOL` (bot_core) | **0.25** | **0.10** (first 24h) | risk_manager sizing cap | **SET 0.10** ← currently 2.5× intent |
| `SPEED_DEMON_BASE_SIZE_SOL` | 0.15 | ≤0.10 to respect cap | sizing base | review vs 0.10 cap |
| `SPEED_DEMON_MAX_SIZE_SOL` | 0.25 | 0.10 | sizing | align to MAX_POSITION_SOL |
| `MIN_POSITION_SOL` (bot_core) | 0.05 | 0.05 (note: risk_manager default 0.10; bot_core env 0.05 wins in-process) | risk_manager | confirm intended floor |
| `DAILY_LOSS_LIMIT_SOL` (bot_core) | **4.0** | **1.5** realized (V5A decision) | risk_manager → EMERGENCY_STOP | **SET 1.5** ← currently 2.7× the stated tolerance |
| `DAILY_LOSS_LIMIT_PCT` | 0.10 | — | risk_manager | confirm interaction w/ SOL limit |
| total concurrency cap | `min(MAX_CONCURRENT_POSITIONS=10, gov)` ✅ wired | 10 (Jay) | bot_core:831 | ✅ SIZING-CAPS-WIRING-001 landed |
| **per-personality cap (BINDING for SD-only)** | **3** (hardcoded) | 5 (V5A first-24h) | risk_manager.py:51 | 🔴 NOT wired — effective trial cap is 3; **SIZING-CAPS-WIRING-001-B** to raise |
| `MAX_SD_POSITIONS` (all) | 20 | phantom — unread | (nothing) | do NOT rely on it |
| `MAX_CONCURRENT_POSITIONS` (bot_core) | **10** ✅ now read | 10 | bot_core:831 | wired (total cap ceiling) |
| `STOP_LOSS_PCT` | 0.20 | 0.20 (GATES-V5) | exit | ok |
| `BOT_CORE_FILL_MC_CEILING_USD` | 1000 | live fill-MC gate (fail-CLOSED #13) | bot_core live buy | ok (set >0 to keep gate active) |
| `SD_MC_CEILING_USD` (SA) | 3000 | signal-time MC ceiling | SA | ok |
| `ML_THRESHOLD_SPEED_DEMON` | bot_core **40** / SA **65** | — | gate | **note:** paper SA→30 (AGGRESSIVE+TEST override); at live SA=65 binds (more restrictive than bot_core 40). Confirm intended live floor. |
| `ML_THRESHOLD_BOT_CORE_SD` | 40 | the paper-effective gate | bot_core | ok |
| `HOLDER_COUNT_MIN` (SA) | **1** | GATES-V5 set 15 | SA entry gate | **REVIEW** — loosened to 1 (admits ~any holder count); confirm intended for live |
| `BUY_SELL_RATIO_MIN` (SA) | 3.0 | GATES-V5 | SA gate | ok |
| `PRE_FILTER_SCORE_MIN` (SA) | 1.15 | GATES-V5 | SA gate | ok |
| `CFGI_MIN` (SA) | 20 | GATES-V5 | SA gate | ok |
| `ANALYST_DISABLED` (SA) | true | true (Analyst hard-disabled) | SA | ok |
| `HELIUS_*_URL` (bot_core) | all SET | required | execution | ok (verify budget) |
| `HELIUS_DAILY_BUDGET` | **not set** (code default) | **>0** (CLAUDE.md pre-live) | pricing/enrichment | **VERIFY** before flip |
| `JUPITER_API_KEY` | SET | required | price/swap | ok |
| `JITO_ENDPOINT` | SET | (disabled in code #6) | — | no action (use_jito forced false) |
| `SELL_FAIL_THRESHOLD` / `SELL_PARK_DURATION_SEC` | not set → 8 / 300s | sell-storm breaker | bot_core | defaults ok |
| `RUG_CASCADE_THRESHOLD` | not set → 5 (paper 15) | rug cascade | market_health | confirm live value |
| `MAX_WALLET_EXPOSURE` | not set → 0.25 code constant | 0.25 (25%) | risk_manager | ok |
| `GRADUATION_THRESHOLD` | not set → 0.95 | routing | execution | ok |
| `TRADING_WALLET_PRIVATE_KEY` | SET (redacted) | required | execution signing | ok (NEVER exposed to MCP/logs) |
| `ANTHROPIC_API_KEY` | SET | valid key, **0 credits** | governance | §4.1 — top up credits |

**Headline env discrepancies to fix at flip:** `MAX_POSITION_SOL` 0.25→0.10, `DAILY_LOSS_LIMIT_SOL` 4.0→1.5, concurrency 10→5, `AGGRESSIVE_PAPER_TRADING` true→false, and decide `HOLDER_COUNT_MIN` (1 is very loose for live).

---

## 6. FLIP CONFIG (apply together, in one batched env change per service)

On `bot_core` (triggers one redeploy):
```
MAX_POSITION_SOL=0.10
SPEED_DEMON_MAX_SIZE_SOL=0.10
SPEED_DEMON_BASE_SIZE_SOL=0.10        # (or keep 0.15 only if you accept base>cap clamping)
DAILY_LOSS_LIMIT_SOL=1.5
AGGRESSIVE_PAPER_TRADING=false
TEST_MODE=false                       # ← the flip; set LAST, after pre-flight (§7)
```
Concurrency to 5: either restore Anthropic credits so governance issues a real `max_concurrent_positions` (and pin/verify it ≤5), or land SIZING-CAPS-WIRING-001 wiring a real env to 5 — **do not assume `MAX_SD_POSITIONS=20` does anything.**
On `signal_aggregator`: set `AGGRESSIVE_PAPER_TRADING=false`; review `HOLDER_COUNT_MIN` (→15 if you want GATES-V5 strictness live).

---

## 7. LIVE-FLIP RUNBOOK (sequence)

1. **Resolve BUG-010** (Anthropic credits) — or explicitly accept dead-governance posture in writing.
2. **Window check:** non-HIBERNATE `market:mode:current` (currently NORMAL ✅), Wed/Thu 18:00–21:00 Sydney, Jay present for 4–6h supervised watch (V5A_GO_LIVE_DECISIONS).
3. **Pre-flight (CLEAN-003):** `export REDIS_URL=...` (from `railway variables -s Redis --kv`), run `bash scripts/live_flip_prep.sh` (clears `bot:status`, `paper:positions:*`, `bot:open_positions:*`). Confirm clean. Also reset `bot:consecutive_losses`→0 + DB `bot_state` (already 0 this session) and set `market:mode:override=NORMAL EX 86400` if forcing.
4. **Apply §6 flip-config** (batched env change → triggers redeploy). Set `TEST_MODE=false` LAST.
5. **Verify startup:** bot_core log shows `Startup reconciliation: 0 open positions` (if N>0, STOP — phantom positions leaking, per CLEAN-003); on-chain balance seed ≈ 5.064 SOL (not 132.6); `TEST_MODE=false` propagated; sell-storm breaker present; no RuntimeError.
6. **Pre-flight verifications (CLAUDE.md live-flip gate):** `DAILY_LOSS_LIMIT_SOL` set; `market:mode:override=NORMAL` TTL>3600 (if used); on-chain balance within 0.01 SOL of latest snapshot; sell-storm breaker present.
7. **Monitor ≥30 min, then through the window.** This is the first real test of all flip-confirmed-only fixes (§2 caveat) — watch the first live close especially: it exercises #4 (failed-sell handling), #5/#7 (partial sell + routing), #14 (cumulative PnL + Path B). First live close should write `live_actual_v1` (Path B); if `live_estimated_v1`, flag (don't auto-rollback on that alone).
8. **Immediate rollback to `TEST_MODE=true` on any of:** RuntimeError at startup, EMERGENCY_STOP trip, sell-storm (any mint >8 errors), HIBERNATE rejection, drawdown >5% on fresh restart, wallet hits DAILY_LOSS_LIMIT, or any stranded/trapped position.
9. **If aborted:** next session defaults back to `TEST_MODE=true`; no re-flip without new explicit authorization.

---

## 8. RISK REGISTER

| Risk | Severity | Mitigation / status |
|---|---|---|
| Flip-confirmed-only fixes mis-behave at first live trade | 🟠 | Supervised 4–6h watch; per-position rollback triggers (§7.8); first-close Path-B check |
| Governance dead → no regime signal, 0.8× haircut, 10-cap | 🔴 | §4.1 — restore credits; #9 market:mode veto is the live regime backstop |
| Env sizes 2.5× V5A intent (0.25 vs 0.10), loss limit 2.7× (4.0 vs 1.5) | 🔴 | §6 flip-config (must apply) |
| Cost-fidelity gap (training corpus calibrated to ~17.6× too-cheap costs, zero fill latency) | 🟠 | `docs/findings/COST_FIDELITY_GAP.md` — paper PnL overstates live; first-24h tiny sizing gathers Path-B calibration data |
| No MEV protection (Jito off) | 🟡 | acceptable for supervised micro-window; `JITO-REIMPLEMENT-001` |
| Helius budget unconfirmed | 🟠 | §3 / §5 — verify `HELIUS_DAILY_BUDGET>0` pre-flip |
| HOLDER_COUNT_MIN=1 (loose) | 🟠 | §5 — decide live value |
| Redis environmental read-timeouts | 🟢 | hardened (retry/keepalive); bot trades through them |
| Market mode = pipeline-outage misclassification | 🟢 | Phase-0 #2 fixed (abstain-on-missing-data); MARKET_REGIME_GAP.md |

---

## 9. PERSISTENCE / HANDOFF (for Claude web + future sessions)

- **This doc is the go/no-go reference.** It reflects state verified 2026-06-03. Treat env values as decay-prone — re-verify against Railway/Redis/DB/on-chain before relying on them (USERMEMORIES_DRIFT precedent).
- **Companion docs:** `REMEDIATION_PHASE_0_1_2026_06_03.md` (per-fix remediation detail, Phases 0–3), `FULL_CODE_AUDIT_001_2026_06_02.md` (the audit), `findings/V5A_GO_LIVE_DECISIONS.md` (the 7 strategic decisions + sizing ladder), `findings/COST_FIDELITY_GAP.md`, `findings/MARKET_REGIME_GAP.md`.
- **Open follow-ups (filed in ZMN_ROADMAP):** SIZING-CAPS-WIRING-001, TIMEZONE-SIZING-FIX-001, GOVERNANCE-STALENESS-POLICY-001, BUG-010 (credits), LIVE-TRADES-CORRECTED-POPULATE-001, AMOUNT-SOL-SEMANTICS-001, JITO-REIMPLEMENT-001, SELL-STORM-PARK-PERSISTENCE-001, EXEC-FORCE-ABANDON-001, MARKET-MODE-THRESHOLD-RECALIBRATE-003, AUDIT-001-SECURITY-HYGIENE.
- **Wallet:** `4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ` (declared `TRADING_WALLET_ADDRESS`); never trade any other wallet; private key never exposed to MCP/logs.
- **One-line status:** *Remediation done + verified; bot healthy in paper (NORMAL, 5.064 SOL on-chain); flip blocked only by BUG-010 credits + the §6 sizing/cap config + Jay's authorized supervised window.*
