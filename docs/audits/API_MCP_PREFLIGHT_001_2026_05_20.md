# API-MCP-PREFLIGHT-001 — read-only verification of live-execution dependencies pre-V5A-flip

**Date:** 2026-05-20 ~08:58 UTC (Sydney 18:58 AEST — D-S5 flip window OPEN per V5A_GO_LIVE_DECISIONS)
**Type:** Read-only investigation. NO services/* code change, NO env change, NO Redis writes, NO DB writes, NO deploy.
**Trigger:** Jay-authored preflight audit before tonight's V5A flip (Wed 2026-05-20 19:00 AEST).
**Predecessor:** `STOP-LOSS-20-NO-MOMENTUM-90S-COMBINED-EVAL-001` (commit `35a5b18`, 2026-05-20) — PC2 SATISFIED.

---

## §1 Verdict — ⚠ CONDITIONAL READY

**Material change since carry-forward state:** wallet on-chain balance is **5.064095633 SOL** (previously believed to be 0.064 SOL per multiple prior sessions earlier today). This represents a **+5.000000000 SOL top-up** — exactly the D-S3 V5A trial budget. **PC1 is now SATISFIED.**

**Bottom line:**

- **Technical/operational readiness: GO.** All critical-for-tonight items that can be verified are GO. Wallet ≥5 SOL ✅. Bot RUNNING in paper with 0 open positions, 0 consecutive losses, no emergency stop ✅. All 9 Phase 4 code checks PASS ✅. No-auth API probes (Binance, Jito, GeckoTerminal, Rugcheck) all 200 ✅. Server-side `service:health` confirms Helius, Vybe, DexPaprika, Rugcheck, Jito, Jupiter all OK from the bot's own probe-perspective ✅.

- **Process readiness: NO-GO via CC-automated flip.** `mcp__railway__*` returned "Not logged in to Railway CLI" (STOP-A FIRED). Without Railway MCP, CC cannot autonomously set `TEST_MODE=false` or reconcile `DAILY_LOSS_LIMIT_SOL=4.0 → 1.5` per D-S3. **Two paths forward:**
  - **Path A:** Jay runs `railway login` interactively (the CC session can suggest `! railway login`) to restore MCP access — then a CC-driven flip session can proceed normally.
  - **Path B:** Jay flips manually via Railway dashboard — the technical preconditions are all GO; CC's role is just verification, which we've done in this audit.

- **Operational flag at flip time:** `market:mode:current=DEFENSIVE` (not NORMAL). Per D-S4 of V5A_GO_LIVE_DECISIONS, the market-mode check at flip time is **manual** (operator decides whether to override to NORMAL via `SET market:mode:override NORMAL EX 86400`). This is not a blocker — it's the flip session's natural Phase 1 decision.

- **Known degraded, NOT blocking:** BUG-010 Anthropic credits exhausted (governance falls back to CONSERVATIVE); `mcp__socket__*` broken (non-critical); SocialData credits (twitter_followers sentinel -1 corpus-wide).

---

## §2 STOP evaluation

| STOP | Trigger | Status | Detail |
|---|---|---|---|
| **A** | Railway MCP not callable | **FIRED** | "Not logged in to Railway CLI" — Phase 2 env-read path blocked; Phases 3-4 continued via non-Railway tools |
| **B** | Wallet balance < 5.0 SOL | **DID NOT FIRE** | **5.064095633 SOL** ≥ 5.0 SOL D-S3 target — PC1 SATISFIED |
| **C** | Critical API non-200 OR Path B parser mismatch on id 6580 | **DID NOT FIRE** (with caveat) | All probed APIs returned 200 or proxy-OK. Path B end-to-end re-validation against id 6580 was deferred because DB query path is blocked (no DATABASE_PUBLIC_URL without Railway). Parser file + integration code verified Phase 4 #3-4. |
| **D** | Code presence check fails | **DID NOT FIRE** | 9/9 Phase 4 checks PASS. One prompt-side expectation correction: `ANALYST_DISABLED` is at SA only (the right design — bot_core never sees Analyst signals). |
| **E** | Open positions > 0 | **DID NOT FIRE** | 0 paper (`paper:positions:*` empty + `bot:status.positions={}`), 0 live (`bot:open_positions:*` empty) |
| **F** | Portfolio snapshot vs on-chain delta > 0.01 SOL | **CANNOT EVALUATE** | DB query blocked. The flip session's Phase 1 (which will have Railway access either via re-auth or dashboard) should run this check. |
| **G** | Git push conflict | **N/A pre-push** | Pull-rebase before push at session end |
| **H** | Phase 0 precedence file missing | **DID NOT FIRE** | All files read: CLAUDE.md + AGENT_CONTEXT.md + STATUS.md + ZMN_ROADMAP.md |
| **I** | `bot:consecutive_losses` ≥ 3 | **DID NOT FIRE** | Value = 0 |
| **J** | Concurrent CC session detected | **DID NOT FIRE** | Last commit `98145ab` (combined-eval) from this same chat; no other in-flight session |
| **K** | Claude code limit hit | **DID NOT FIRE** | Within budget |

---

## §3 Phase 1 — MCP no-op verification battery

Full evidence: `.tmp_api_preflight/01_mcp_battery.md`. Summary:

- **10 of 12 succeeded:** Helius (5.064 SOL ✅), Redis (14 `bot:*` keys), GitHub project-scoped (1 hit), Vybe (47 v4 endpoints), DexPaprika (35 networks), CoinGecko (11 search hits), Playwright (1 tab), shadcn (`@shadcn` registry), Context7 (5 React matches), Google Drive (1 file).
- **2 failed:** `mcp__railway__*` (re-auth needed — STOP-A), `mcp__socket__*` (no valid session — known, non-blocking).

---

## §4 Phase 2 — External API probes (CONSTRAINED)

Full evidence: `.tmp_api_preflight/02_external_probes.md`. Constraint: STOP-A blocked Railway env reads for API keys. Ran **no-auth probes** + used Redis `service:health` as **server-side proxy** for authenticated APIs.

### Critical-for-tonight verdicts

| # | API | Verdict | Evidence |
|---|---|---|---|
| 1 | Helius RPC | **PROXY-GO** | `service:health.helius_rpc=ok (cached, rate-limit protected)`, gatekeeper + parse also OK |
| 2 | Helius parseTx + Path B parser | **PROXY-GO** | service:health OK; parser file `services/helius_parser.py` verified present with id-6580 reconstruction docstring (Phase 4 #3); integration in `bot_core.py:1436-1442` confirmed |
| 3 | PumpPortal Local | **PROXY-GO** | `service:health.pumpportal=warn ("no signals")` but `market:new_token_count_1h=10257` + `market:migration_count_1h=67` — **the "no signals" WARN is a `last_signal` key-write quirk in `dashboard_api.py:2041`, NOT a signal-pipeline outage** (10K+ signals/hour observed live). `PUMPPORTAL_API_KEY` not used anywhere in `services/*` (local API is unauthenticated). Tier 3 follow-up filed: `DASHBOARD-PUMPPORTAL-HEALTH-PROBE-001`. |
| 4 | Jito tip accounts | **GO** | `POST https://mainnet.block-engine.jito.wtf/api/v1/getTipAccounts` → 200, 8 accounts in 693ms |
| 5 | Binance SOL price | **GO** | `$85.02` vs Redis `market:sol_price=84.9` → delta **0.14%** (well within 2% tolerance) in 699ms |

### Degradable verdicts

| # | API | Verdict | Evidence |
|---|---|---|---|
| 6 | Jupiter V6 quote | **PROMPT ERROR — current Jupiter GO** | `quote-api.jup.ag` DNS unreachable; CLAUDE.md "Jupiter API Reference" lists current host as `api.jup.ag/swap/v2/*`. `service:health.jupiter=ok HTTP 200` confirms current endpoint works. |
| 7 | GeckoTerminal | **GO** | First pool address from prompt (`5quBtoi...`) → 404; canonical Raydium SOL/USDC v4 (`58oQChx4...`) → 200, `base_token_price_usd=$85.08`, valid pool data in 351ms |
| 8 | DexPaprika | **GO** | Phase 1 #6 — 35 networks, Solana = $7.16B 24h vol |
| 9 | Rugcheck | **GO** | SOL token report 200 — `score=1, risks=[], jup_verified=true` in 986ms |
| 10 | SocialData | **DEGRADED expected** | Not in `service:health`; known credits exhausted; sentinel -1 used corpus-wide |
| 11 | Vybe (.xyz) | **PROXY-GO** | `service:health.vybe=ok`; Phase 1 #5 returned 47 v4 endpoints. Code drift to `.com` (VYBE-URL-CODE-DRIFT-001) is unfixed but the bot's effective Vybe state is "key valid, code calls wrong host on some paths" — degraded but unchanged from prior state. |
| 12 | Anthropic governance | **DEGRADED — known (BUG-010)** | `service:health.anthropic=ok ("key configured")` but `governance:latest_decision.reasoning` shows "classification failed: Error code: 400 ... Your cred[its exhausted]". Fallback to CONSERVATIVE default. Non-blocking. |
| 13 | Discord webhook | **PROXY-GO** | `service:health.discord_webhook=ok ("configured")` and `discord_bot=ok` |
| 14 | Sentry DSN | **STATUS UNKNOWN** | Railway env blocked; `mcp__sentry__*` needs auth (per CLAUDE.md MCP index). Non-blocking. |

---

## §5 Phase 3 — State snapshot (CONSTRAINED)

Full evidence: `.tmp_api_preflight/03_state_snapshot.md`.

**Wallets:**
- **Trading: 5.064095633 SOL** ← PC1 SATISFIED (exact +5.0 SOL top-up vs. 0.064 carry-forward)
- Jito tip account #1: 0.001 SOL (non-issue; destination address)

**Redis state (highlights):**
- Bot RUNNING in paper (`bot:status.test_mode=true`, `status=RUNNING`)
- **0 open positions** (paper + live both clean) — STOP-E does NOT fire
- `bot:consecutive_losses=0` — STOP-I does NOT fire
- `bot:emergency_stop` absent ✅
- `bot:loss_pause_until` absent ✅
- **`market:mode:current=DEFENSIVE`** ⚠ — operator-decides at flip time per D-S4 (manual market-mode check)
- `market:mode:override` absent ✅
- `market:sol_price=84.9` ✅ (Binance live delta 0.14%)
- `market:session.session=TRANSITION, sydney_hour=19` — D-S5 flip window OPEN (Wed/Thu 18:00-21:00 AEST)
- `service:bot_core:heartbeat`: alive, 2h+ uptime, 0 positions, no emergency
- `nansen:disabled` absent (migrated to env `NANSEN_DRY_RUN=TRUE`) ✅
- `bot:onchain:balance` absent (expected — only set post-flip)
- `governance:latest_decision`: CONSERVATIVE fallback (BUG-010, known)
- Paper portfolio: 66.59 SOL, daily P&L +2.88 SOL today

**DB queries: BLOCKED.** `DATABASE_URL` in local `.env` is `sqlite:///toxibot.db` (local dev, not production). `DATABASE_PUBLIC_URL` not in local `.env`. Without Railway access, no path to production DB. The four DB queries in the prompt are deferred to the flip session (which will have Railway access via re-auth or dashboard).

---

## §6 Phase 4 — Code presence checks

Full evidence: `.tmp_api_preflight/04_code_checks.md`. **9 of 9 PASS:**

1. ✅ C1 gate in paper path (`paper_trader.py:253-255`)
2. ✅ C1 gate in live path / PC3 (`bot_core.py:953-965` — LIVE-MODE-FILTER-PARITY-001-V2 intact)
3. ✅ Path B parser exists (`services/helius_parser.py` — id-6580 verification in docstring)
4. ✅ Path B integration in bot_core live close (`bot_core.py:1436-1442`)
5. ✅ ML gate at bot_core / BOT-CORE-ML-GATE-001 (`bot_core.py:60, 130-144, 674`)
6. ✅ Sell-storm circuit breaker (`bot_core.py:221-222, 1342-1361` — armed at 8 fails / 300s park, << 1000 kill switch)
7. ✅ CLEAN-003 script (`scripts/live_flip_prep.sh` — executable, CLEAN-003+CLEAN-004 logic intact)
8. ✅ TIME_PRIME env-driven (`bot_core.py:755-756` — empty hours default = branch never fires)
9. ✅ Analyst disabling (`signal_aggregator.py:153` + bot_core `ML_THRESHOLD_BOT_CORE_ANALYST=0` reserved-not-active — prompt expected ANALYST_DISABLED in both but actual design has it at SA only, the correct architectural layer)

---

## §7 Phase 5 — GO / NO-GO matrix

### Critical for tonight

| Dependency | Verdict | Latency / detail |
|---|---|---|
| Railway MCP | **❌ NO-GO** (STOP-A) | Not logged in to Railway CLI — Jay action: `railway login` |
| Wallet balance ≥5 SOL | ✅ **GO** | 5.064 SOL (PC1 SATISFIED) |
| Helius RPC | ✅ GO (proxy via service:health) | OK cached |
| Helius parseTx + Path B parser | ✅ GO (proxy + Phase 4 code) | service:health OK; parser file + bot_core integration verified |
| PumpPortal Local | ✅ GO (proxy via observed pipeline) | 10K+ signals/hour despite dashboard WARN |
| Jito tip account | ✅ GO (direct probe) | 8 accounts, 693ms |
| Binance SOL price | ✅ GO (direct probe) | $85.02, 0.14% delta vs Redis |
| Open positions = 0 | ✅ GO (Redis) | 0 paper, 0 live |
| Code state intact | ✅ GO (Phase 4) | 9/9 PASS |

### Degradable

| Dependency | Verdict | Detail |
|---|---|---|
| Jupiter (current host) | ✅ GO | service:health OK HTTP 200 |
| GeckoTerminal | ✅ GO | 200, valid pool data |
| Rugcheck | ✅ GO | 200, full report |
| DexPaprika | ✅ GO | 35 networks |
| Vybe | ✅ GO (proxy) | service:health OK |
| SocialData | DEGRADED expected | Twitter sentinel -1 corpus-wide |
| Anthropic governance | DEGRADED known (BUG-010) | Fallback to CONSERVATIVE |
| Discord webhook | GO (proxy) | configured |
| Sentry DSN | STATUS UNKNOWN | Non-blocking |

---

## §8 Final verdict

⚠ **CONDITIONAL READY**

All critical-for-tonight items verified GO **except Railway MCP itself**, which means the flip session needs one of two paths:

**Path A — re-auth Railway CLI:**
```
! railway login
```
(Jay must run interactively — this requires browser interaction. After re-auth, the flip session can proceed CC-driven.)

**Path B — manual flip via Railway dashboard:**
1. Verify wallet on-chain via Helius MCP (already done: 5.064 SOL ✅)
2. Verify `bash scripts/live_flip_prep.sh` ran clean (Redis pre-flip cleanup)
3. Decide on `market:mode:current=DEFENSIVE` → either accept DEFENSIVE or set `market:mode:override=NORMAL EX 86400` via Redis MCP per D-S4 manual judgment
4. Set `TEST_MODE=false` on bot_core via Railway dashboard
5. Set `DAILY_LOSS_LIMIT_SOL=1.5` on bot_core via Railway dashboard (per D-S3; currently 4.0)
6. Verify post-restart logs show `Startup reconciliation: 0 open positions in DB`
7. Monitor for ≥30 min per CLAUDE.md "Live trading mode" rule

Both paths are technically unblocked; choice is operational.

---

## §9 Follow-up roadmap items (filed this session)

- **`DASHBOARD-PUMPPORTAL-HEALTH-PROBE-001` Tier 3 🟢** — `dashboard_api.py:2041` reports "no signals" WARN when the `last_signal` Redis key hasn't been written, even though `market:new_token_count_1h` and `signals:evaluated` show the pipeline is alive. The probe should fall back to checking `market:new_token_count_1h > 0` (or equivalent live counter) when `last_signal` is absent, instead of warning. Caught when investigating service:health output for the V5A flip preflight; 10K+ signals/hour are flowing but the dashboard says "no signals" — operator-facing observability defect, not a real signal outage. Not V5A-blocking.

No new Tier 1/2 items. **Railway MCP re-auth is a Jay action, not a session** — surfaced for the flip session's awareness but not filed as a roadmap entry.

---

## §10 Scope discipline

- NO services/* code change
- NO env change (Railway env not even readable this session due to STOP-A)
- NO Redis writes (only reads via mcp__redis__get)
- NO DB writes (only reads attempted; blocked by STOP-A path)
- NO deploy
- NO TEST_MODE flip (that is the V5A flip session's role, not this preflight)
- NO investigation of TabPFN JWT, dashboard rebuild, ML training corpus, BUG-010 governance fix, VYBE code drift fix (all explicit non-goals per §6)
- NO attempt to "fix" DEGRADED items — surfaced only

---

## §11 Recommendations for the V5A flip session

1. **Begin with the precedence rule read** (CLAUDE.md + AGENT_CONTEXT + STATUS + ZMN_ROADMAP + this audit + V5A_GO_LIVE_DECISIONS).
2. **Decide CC-automated vs manual flip path** based on Jay's preference and whether Railway CLI re-auth happens at session start.
3. **Re-verify wallet at flip time** via Helius MCP (should still be 5.064 SOL unless Jay does another transfer; flag if changed).
4. **Make the D-S4 manual market-mode decision** for `market:mode:current=DEFENSIVE`. Options: accept DEFENSIVE (more conservative); override to NORMAL (full SD live with current size graduation). Per D-S4 this is operator judgment, not autonomous.
5. **Reconcile `DAILY_LOSS_LIMIT_SOL=4.0 → 1.5`** per D-S3 (surfaced 2026-05-20 by PC1-WALLET-TARGET-RECONCILE-001, in-cell PC4 flag).
6. **Run `bash scripts/live_flip_prep.sh`** for Redis cleanup (CLEAN-003).
7. **Set `TEST_MODE=false`** on bot_core only (NOT signal_aggregator — SA stays in paper-eval mode per AGENT_CONTEXT §2).
8. **Monitor ≥30 min post-flip** per CLAUDE.md "Live trading mode" rule; revert on any RuntimeError, EMERGENCY_STOP trip, sell-storm, HIBERNATE rejection, or >5% drawdown.

---

**Files produced this session:**
- `docs/audits/API_MCP_PREFLIGHT_001_2026_05_20.md` (this file)
- `AGENT_CONTEXT.md` (header refresh — no §6 substantive change because PC1 status flip happens at flip session, not this preflight)
- `STATUS.md` (entry prepend)
- `MONITORING_LOG.md` (entry prepend)
- `ZMN_ROADMAP.md` (Decision Log row + Tier 3 `DASHBOARD-PUMPPORTAL-HEALTH-PROBE-001` row)
- Scratch (untracked): `.tmp_api_preflight/{PROGRESS.md, 01_mcp_battery.md, 02_external_probes.md, 03_state_snapshot.md, 04_code_checks.md}`

**Commit:** single push at session end per CLAUDE.md discipline.
