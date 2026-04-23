# ZMN Bot — Claude Code Instructions

## Tooling

This repo has a Claude-Code-specific tooling inventory at
`docs/CLAUDE_TOOLING_INVENTORY.md`. Read it during Step 0 of every session.

- MCP servers registered: 15 (active + stubbed) — see `.mcp.json`
- Skills installed: 4 (project-scoped under `.claude/skills/`)
- Last updated: 2026-04-19
- **New machine?** See `docs/SETUP_NEW_MACHINE.md` for the bootstrap checklist.

## Roadmap

The canonical work queue lives at `ZMN_ROADMAP.md` at repo root. Every session's
first step is to read that roadmap to know what's in flight, what's queued, and
what's blocked. Audit docs under `docs/audits/` remain as evidence/context — use
them for depth; use `ZMN_ROADMAP.md` for priorities.

Update `ZMN_ROADMAP.md` at the end of every session that completes or changes
an item's status. Append a changelog entry.

For Sentry-captured errors (8 services live as of `cb45d6b`):
```
mcp__sentry__search_issues(
  organizationSlug='rz-consulting',
  projectSlugOrId='zmn-<service>',
  naturalLanguageQuery='unresolved errors from last 24h')
```
Use `mcp__sentry__analyze_issue_with_seer` on any specific issue ID for AI-driven root cause.

Prefer registered MCPs over generic tools: Helius over curl-to-RPC, Postgres MCP
over raw psql (once installed), Playwright MCP over `requests` for dashboard
scraping, Railway MCP over shelling out to `railway` CLI. Inventory doc has a
usage cheat sheet listing when to reach for each MCP.

## Resolved Bugs (reference only — see MONITORING_LOG.md for details)
Key fixes: exit pricing pipeline (26e19b4), paper_trader price pass-through (9b880e1), HIBERNATE bypass (47de1fa), SERVICE_NAME routing (April 3). Do NOT revert main.py to asyncio.gather all services.

## Trade P/L Analysis Rule (added 2026-04-13)

When analyzing trade performance from paper_trades, ALWAYS use the
`corrected_pnl_sol` and `corrected_pnl_pct` columns, NOT `realised_pnl_sol`
or `realised_pnl_pct`. The latter are historically buggy for trades
with staged take-profits (44 trades affected, all with id <= 3564).

For ML retraining: use corrected_pnl_sol to determine win/loss labels.
For reporting: use corrected_pnl_sol for aggregate numbers.
For forensic trade inspection: compare both columns to understand
what the bug was hiding.

Post-fix trades (id > 3564) have identical values in both columns --
correction_method = 'pass_through' confirms this.

---

## Project
Solana memecoin trading bot. GitHub: Darth-Pengu/TradingBotLive-v2
Domain: zmnbot.com. Railway: 8 services. PostgreSQL + Redis.
Currently TEST_MODE=true (paper trading). Balance: 31.86 SOL.

## Services (each is a SEPARATE Railway service)
- signal_listener → services/signal_listener.py (PumpPortal WS, trade subscriptions, telegram)
- signal_aggregator → services/signal_aggregator.py (scoring, KOTH, enrichment, momentum gates)
- bot_core → services/bot_core.py (position management, exits, governance reading)
- ml_engine → services/ml_engine.py (CatBoost + LightGBM ensemble, Phase 3)
- market_health → services/market_health.py (CFGI, SOL price, market mode)
- governance → services/governance.py (JSON classification via Haiku, needs Anthropic credits)
- treasury → services/treasury.py (balance tracking)
- web → services/dashboard_api.py + dashboard/*.html (14-panel retro green dashboard)

## Current State (April 16, 2026)

### Financial state
- ~4,945 paper trades total
- Paper balance: ~50.95 SOL
- Trading wallet: 5.00 SOL real SOL on mainnet (for trial trading)

### Solders signing — THE CORRECT API (learned the hard way)
The ONLY correct way to sign a VersionedTransaction in solders >= 0.21:
```python
tx = VersionedTransaction.from_bytes(tx_bytes)
signed_tx = VersionedTransaction(tx.message, [keypair])  # constructor signs
```
- `.sign([keypair])` — REMOVED in 0.21 (AttributeError)
- `populate(msg, [sig])` — COMPILES but produces INVALID signatures
- `VersionedTransaction(msg, [keypair])` — CORRECT, verified locally
Devnet test before any mainnet live retry is mandatory.

### Live trading preparation — SIGNING FIX DEPLOYED (v3 constructor)
- Shadow analysis: 90.9% winner survival rate, STRONG edge
- Execution infrastructure exists but **signing is broken**
- **Live trial v1 FAILED:** 244/244 solders `.sign()` AttributeError
- **Live trial v2 FAILED:** populate() fix compiles but produces
  invalid signatures on-chain (`SignatureFailure` from validators)
- Root cause: `from_bytes() → .message → sign → populate()` round-trip
  loses message integrity. Need different serialization approach.
- Ghost positions: 1,458 stale Redis entries cleaned (bot:status + paper:positions:*)
- Helius budget restored to 100k/day
- Wallet untouched: 5.0 SOL (zero trades ever landed on-chain)

### Pre-live checklist (MUST verify before any TEST_MODE=false)
1. **Fix signing:** must produce valid on-chain signatures (test with
   actual PumpPortal tx bytes, not just dummy messages)
2. Verify signed tx passes simulation: `simulateTransaction` RPC call
3. Verify Helius budget > 0
4. Verify wallet balance >= 3 SOL
5. Verify TEST_MODE=false propagates (check startup log)
6. Clear stale Redis positions before going live

### Dashboard mode filter
All main dashboard widgets filter by trade_mode. LIVE view = zeros
until live trades exist. OPEN POSITIONS skips Redis bot:status when
mode=live (Redis only has paper). OPEN POSITIONS + RECENT TRADES both
use MCAP columns (USD) — consistent convention across all trade tables.

### Known Redis cache bugs
- bot:status accumulates positions but never removes closed ones.
  On restart, bot_core rebuilds from DB, but the stale Redis entries
  persist until manually deleted. Dashboard reads Redis first.
- paper:positions:* keys have no TTL and persist across restarts.
- **Workaround:** DEL bot:status + paper:positions:* before going live.

### Pipeline state (as of 2026-04-15)
- signal_listener: ALIVE
- signal_aggregator: ALIVE, hardened (Redis retry + health heartbeat),
  **ANALYST_DISABLED=true** env var set
- bot_core: ALIVE, trading Speed Demon only, **TP redesign experiment
  LIVE** (Option B2, observation ends 2026-04-17 ~11:32 UTC),
  **shadow measurement logging active** (SHADOW_MEASURE events to
  Redis shadow:measurements). DO NOT modify exit strategy.
- market_health: ALIVE, **Stage 2 CFGI cutover deployed** (cfgi.io SOL
  primary, credits topped up, SOL CFGI = 41.5 active).
- governance: ALIVE but **Anthropic credits exhausted** — LLM non-functional

### ML state
- CatBoost + XGBoost ensemble, 128 clean training samples
- LightGBM not loading (ensemble runs 2/3 models)
- 685 pre-fix trades excluded from ML training via contamination filter
- **ML threshold — corrected 2026-04-17.** Prior claim "ML inverts above 40; working range is 35-40 only" was accurate pre-2026-04-12 but became stale after the feature-default fix (commit a8a390b). Verified in 7d of SD paper data (also re-confirmed 2026-04-19 against 2,256 trades — `docs/audits/ZMN_RE_DIAGNOSIS_2026_04_19.md`):

| ML band | n | WR | Total PnL |
|---|---:|---:|---:|
| 35-40 | 21 | 4.76% | -1.16 SOL (only loss band above 0-35) |
| 40-50 | 496 | 39.1% | +88.9 SOL |
| 60-70 | 333 | 50.5% | +67.7 SOL |
| 80+ | 172 | 52.9% | +57.5 SOL |

  **Current policy:** `ML_THRESHOLD_SPEED_DEMON` floor = 40 (gated at signal_aggregator). No upper bound. Higher scores are better, not worse. The Issue #1 entry below is historical and superseded by this block.

### CFGI state
- Primary source: **cfgi.io Solana** — NOW ACTIVE (credits topped up)
- market:health.cfgi = 41.5 (cfgi.io SOL, primary)
- market:health.cfgi_btc = 23.0 (Alternative.me BTC, preserved)
- Stage 2 cutover code deployed (commit eebccf5)

### Personality state
- Speed Demon: sole active personality, 38.6% WR post-recovery
- Analyst: **HARD DISABLED** via ANALYST_DISABLED=true env var.
  0/3 WR with 0-2s holds pending investigation.
- Whale Tracker: dormant

### External API readiness (2026-04-16)
- Execution APIs: ALL working EXCEPT **Helius Staked RPC (522)**
- Helius standard RPC: OK (285ms), fallback viable for live
- Jupiter V2: OK (365ms), Jito: OK (629ms), PumpPortal: OK
- **Anthropic: CREDITS EXHAUSTED** — governance non-functional
- **SocialData: CREDITS EXHAUSTED** — social enrichment dead
- Go/No-Go: **READY WITH ONE FIX** (Helius Staked URL)

### Known blockers
- ~~Helius Staked URL 522~~ RESOLVED — switched to Standard RPC (48ms)
- TP redesign experiment active (ends 2026-04-17 ~11:32 UTC)
- B-013: DEFERRED — symbol column empty, needs paper_trader fix
- ML retrain blocked on 500+ clean samples
- Anthropic credits exhausted (governance dead)

## Known Issues (Priority Order, April 11)
1. ~~ML SCORE INVERSION: 70+ scores have 0% WR, -12.62% avg P/L.~~ **SUPERSEDED 2026-04-17/19.** See "ML threshold — corrected 2026-04-17" block above. Higher scores win more. Threshold floor = 40, no upper bound.
2. FEATURE SPARSITY: 42 of 55 FEATURE_COLUMNS are permanently zero. Only ~13 features populated per prediction. Model trained to ignore dead features = noise. Consider pruning to ~20 populated features.
3. no_momentum_90s BLEED: 51% of trades (88/171) exit via no_momentum_90s at -11.98% avg. Signal quality bottleneck.
4. LightGBM NOT LOADING: NIXPACKS_APT_PKGS=libgomp1 is set but ml_engine needs fresh deploy to pick it up. Ensemble runs 2/3 models.
5. Governance SQL type mismatch: `double precision > timestamp` in metrics query (cosmetic, governance still works).
6. Analyst paused in extreme fear: CFGI < 20 auto-pauses analyst. Zero training data during fear markets.
7. Treasury Helius errors: getBalance fails every 5min (HELIUS_DAILY_BUDGET=0 but treasury still calls).
8. Telegram: code ready but TELEGRAM_ENABLED=false

## Operating Principles for Claude Code Sessions

These were learned through several sessions in April 2026. Follow by
default unless Jay explicitly overrides.

- **One lever per session.** Each session changes ONE thing. Multiple
  parallel changes make failure attribution impossible.
- **Gated phases.** Multi-phase sessions have explicit pass/fail
  conditions between phases. If Phase N fails, later phases skip.
- **Always update all four canonical docs.** Every session that changes
  state must update MONITORING_LOG.md, ZMN_ROADMAP.md, CLAUDE.md, and
  AGENT_CONTEXT.md.
- **Auto-revert on failure.** `git revert <hash>` only. Never
  force-push, never rebase, never delete commits.
- **No agent loops on live services.** Single-pass, bounded,
  reversible deployments only.
- **Speed Demon trading logic is sacred.** Do not modify entry filter,
  ML scoring, position sizing, or exit strategy unless the session is
  specifically scoped to that change AND backed by data analysis.
- **Read-only diagnostic before write prompts.** When state is
  ambiguous, run a read-only audit BEFORE modifying anything.
- **Verify before shipping.** Don't ship optimization based on
  simulation alone. Always have actual instrumentation data.
- **Bounded scope, hard stops.** Every prompt has a max wall clock.
  When reached, commit whatever's done and stop. No "while we're here."
- **TEST_MODE flip doesn't reset positions.** bot_core reconcile MUST
  filter by trade_mode or paper positions block live MAX_SD_POSITIONS.
  Always clear stale positions before mode flip.
- **DAILY_LOSS_LIMIT_SOL=4.0** for trial v4: kill at wallet 1.0 SOL.
  risk_manager.py reads from env var (was hardcoded). Per Jay's choice.
- **Reconcile fix only works on restart.** DB cleanup of stale positions
  doesn't clear bot_core's in-memory self.positions. The reconcile code
  runs on startup only. Must restart bot_core (flip TEST_MODE or redeploy)
  after any position cleanup for it to take effect.
- **Deploy discipline — no duplicate deploys.** Railway auto-deploys
  on git push to main (GitHub webhook). `railway up` ALSO triggers a
  deploy. NEVER use both in the same session — it causes duplicate
  deploys, wastes build minutes, and doubles wait time. Default: use
  `git push` ONLY. Use `railway up` ONLY for deploying uncommitted
  local changes (rare) or explicitly bypassing git (very rare). Before
  any deploy, self-check: am I about to trigger two deploy paths?
- **Live trading mode — session-gated.**
  *Historical note:* earlier versions of this file said "paper mode is non-negotiable." That was accurate when written but became stale on 2026-04-16/17 when live trials v3 and v4 executed real on-chain trades. See `ZMN_HELIUS_URL_FIX_REPORT.md` (commit cd266de — 4+ TX_SUBMITs confirmed) and `ZMN_POSTMORTEM_2026_04_16.md`. **Wallet moved 5.0 → ~1.6 SOL via real trades (~3.4 SOL net cost).** (Cost corrected 2026-04-19 per forensics commit `1b40df3` — prior "1.32 SOL" / "3.677 SOL" figures were taken mid-trial and under-reported the actual v4 cost by ~2.5×.)
  *Current rule:* a session may set `TEST_MODE=false` on `bot_core` only when ALL of the following are true:
  1. The session prompt **explicitly** requests live enablement, naming the variable by name and stating intent. Generic "make the bot trade well" requests are not sufficient.
  2. The prompt includes explicit rollback steps and acknowledges the current on-chain balance.
  3. Before flipping, verify: (a) `DAILY_LOSS_LIMIT_SOL` is set on `bot_core` (default 1.0 is too loose for main wallet — current trials use 4.0); (b) `market:mode:override` Redis key is `NORMAL` with TTL > 3600s; (c) on-chain balance via Helius `getBalance` is within 0.01 SOL of the latest `portfolio_snapshots.total_balance_sol` row; (d) sell-storm circuit breaker from cd266de is present in `services/bot_core.py`.
  4. After flipping, monitor for ≥30 minutes. On any of these, revert immediately to `TEST_MODE=true`: RuntimeError at startup, EMERGENCY_STOP trip, sell-storm (any mint > 8 errors), HIBERNATE rejection, drawdown log > 5% on a fresh restart.
  5. If a live session aborts, the next session defaults back to `TEST_MODE=true` and does NOT re-flip without new explicit authorization.
  *What this rule does NOT allow:* silent live trading based on inferred intent; keeping `TEST_MODE=false` across sessions without re-verification of the 4 preconditions; bypassing `DAILY_LOSS_LIMIT_SOL` (if wallet hits the limit, `TEST_MODE` flips back to true regardless of session authorization); scaling position size above 0.05 SOL without a separate authorization; live trading on any wallet other than the declared `TRADING_WALLET_ADDRESS`.
  The staged-progression chain in `ZMN_ROADMAP.md` #9.5–9.8 was designed before any live trading. Stages 9.5 (execution audit), 9.6 (shadow mode), 9.7 (micro-live), and 9.8 (main wallet live) are now either complete or superseded by the 2026-04-16/17 live trials. That chain is historical reference, not a current gate.
- **Trust the data.** Speed Demon +22 SOL in 36h = real edge.
  Analyst 0/3 in 0-2s = real problem.
- **Helius URL resolver must include all three tiers.** `_execute_pumpportal_local`
  and `_send_transaction` must iterate `(HELIUS_STAKED_URL, HELIUS_RPC_URL,
  HELIUS_GATEKEEPER_URL)`. Missing GATEKEEPER as fallback caused 7,448 silent
  errors on 2026-04-17 when STAKED + RPC were empty. Also: `services/execution.py`
  now raises `RuntimeError` at import if TEST_MODE=false with no Helius URLs —
  fail loudly instead of looping quietly.
- **TEST_MODE flip alone does not reset in-memory state.** `_load_state` and
  `_reconcile_positions` run only in `__init__`. A mode flip without a bot_core
  container restart leaves stale paper positions in `self.positions`, causing
  zombie sell attempts on closed paper mints. Every TEST_MODE flip requires
  a bot_core restart (or env var change that triggers one).
- **Sell-storm circuit breaker is live.** After 8 consecutive `ExecutionError`s
  on the same mint during live sells, bot_core parks the mint for 5 min
  (env-tunable via `SELL_FAIL_THRESHOLD`, `SELL_PARK_DURATION_SEC`). Kill
  switch: set threshold to 1000 to disable.
- **Live branch Redis parity is already present** (verified in Session 2 v2 Phase 1 recon, commit `5ac30cd`). When investigating `bot_core._close_position` live-branch vs paper-branch divergence, `traded:mints` SADD + 7200s EXPIRE and `bot:consecutive_losses` INCR/`SET "0"` are already in the live branch at `services/bot_core.py:L1126-1151` with parity to paper. The remaining gaps (as of `5ac30cd`) are: (a) live ENTRY path doesn't INSERT paper_trades — tracked as **DASH-ENTRY-001** (Session 2b); (b) live CLOSE path paper_trades INSERT is landed in `5ac30cd`; (c) on-chain balance snapshot (portfolio_snapshots row tagged `market_mode='LIVE_ONCHAIN'` + Redis `bot:onchain:balance`) is landed in `5ac30cd`.
- **`pos.trade_id` is id-space ambiguous.** In paper mode it points to `paper_trades.id`; in live mode to `trades.id`. The two id-spaces overlap (paper 1..5974, trades 1..3175) — NEVER use `UPDATE paper_trades WHERE id=pos.trade_id` in the live branch; it would hit an unrelated paper row. Always use `INSERT INTO paper_trades` at live close with a fresh id. Cleanup tracked as **REFACTOR-001**.
- **Routing state must be fresh at `execute_trade` call time.** `execute_trade(side, token, amount_sol, *, bonding_curve_progress=...)` in `services/execution.py` routes to different execution paths (`_execute_pumpportal_local` vs `_execute_pumpportal` vs `_execute_jupiter`) based on the `bonding_curve_progress` kwarg (threshold `GRADUATION_THRESHOLD = 0.95`). **This kwarg must reflect the pool's state at call time, NOT the state captured at signal discovery or buy time.** Stale routing is the likely root cause of the 261 historical HTTP 400 sell errors (v3/v4 trial) — tokens that graduated during the hold were sold using the pump.fun path against a no-longer-existing bonding-curve pool. Before calling `execute_trade` from `_close_position` or any sell decision, refresh pool state via Helius `getAccountInfo` on the BC PDA (or an equivalent PumpPortal pool-status endpoint) and update `pos.bonding_curve_progress` (and/or a new `pos.pool_route` field). Tracked in **EXEC-001**. Must land paired with **EXEC-002** (Jupiter NameError at `services/execution.py:491`) — fixing EXEC-001 alone causes post-grad sells to hit Jupiter and crash on the NameError.
- **Paper fee model is under-cooked by ~0.004 SOL/trade at 0.05 SOL sizing.** `paper_trader.fees_sol` median is 0.503% of position size across all size buckets — models a single percentage fee only. Real round-trip costs include: (a) pump.fun platform 2% (bot models 0.5%; under by 1.5pp), (b) Jupiter/LP fee ~0.6%, (c) priority fee 0.001 SOL fixed per round-trip, (d) Jito tip 0.001-0.005 SOL fixed per round-trip, (e) realized slippage (absent on 95.8% of paper rows — verified: `realised_pnl_sol = (exit/entry - 1) * amount - fees_sol` holds exactly on 6,087 of 6,352 closed trades). **When comparing paper P&L to live, subtract ~0.004 SOL/trade** as the fee-model correction at current 0.05 SOL sizing. Break-even position size under realistic costs: 0.009 SOL @ 100% paper→live edge retention, 0.019 SOL @ 50%, 0.048 SOL @ 25%. Current `MIN_POSITION_SOL=0.05` sits at the pessimistic break-even — defensible for supervised windows, tight for unsupervised. Tracked in **FEE-MODEL-001**; companion observability (live-window delta tracker) in **OBS-011**; prerequisite execution-path audit in **EXEC-003**.
- **Paper results are hypotheses until validated against live data.** The paper model is an approximation. The first live data point (Session 5 v4, 2026-04-20, mint `yh3n441...`, 0.365 SOL pre-grad) showed paper overstating live PnL by ~96× (paper said +0.002 SOL win; live was -0.094 SOL loss). Any decision based purely on paper numbers — especially position sizing, personality activation, or edge-preservation claims — should be treated as a hypothesis pending live confirmation. Live data always overrides paper data where they conflict. FEE-MODEL-001 (commit `e078b4c`) is the corrected-paper-model work; SLIPPAGE-CALIBRATION-001 is the ongoing calibration loop that refines the model from accumulating live data. Before making sizing or strategy claims from paper-only inputs, state explicitly: "this is a paper-model hypothesis; live data can override."

### STATUS.md — single-file state tracker (MANDATORY for every session)

`STATUS.md` is the single source of truth for "what is the bot doing right now
and what's next." Every CC session MUST update `STATUS.md` as its final step
before the `present_files` call. Every Claude web/desktop chat begins with Jay
uploading `STATUS.md` + `ZMN_ROADMAP.md` for ground-truth context.

#### Contract — every session appends a dated entry at the TOP of STATUS.md

Entry shape (keep ≤ 15 lines — concise, scannable):

```
## 2026-04-DD HH:MM UTC — <session name>

**Committed:** <commit hashes + one-line description each, or "docs-only / no commit">
**State changes:** <env vars set, Redis keys touched, services redeployed, or "none">
**Bot state:** TEST_MODE=<true|false>, <N> paper open, <N> live open, circuit_breaker=<val>
**Blockers cleared:** <item IDs or "none">
**Blockers new/active:** <item IDs or "none">
**Next prompt:** <path to the next SESSION_*.md in outputs, or "none queued">
**Pending Claude-chat prompts not yet pasted:** <list or "none">
```

#### Rules

1. **Newest entry at TOP.** Scan-friendly. Old entries never deleted — they're
   the audit trail.
2. **Never delete prior entries.** Append-only. If something is wrong in a prior
   entry, add a CORRECTION entry at the top pointing to it; don't rewrite history.
3. **Every CC session completes with a STATUS.md update.** No exceptions. This
   is enforced by making it the second-to-last step in every session prompt
   (immediately before `present_files`).
4. **Bot state read is MANDATORY.** Pull TEST_MODE from Railway env, open
   position counts from Redis (`paper:positions:*`, `bot:open_positions:*`),
   circuit_breaker from `bot:state:consecutive_losses`. These are not allowed
   to be guessed or carried forward from a prior entry.
5. **"Pending Claude-chat prompts" means**: any `SESSION_*.md` file sitting in
   `/mnt/user-data/outputs/` on Jay's machine that hasn't been pasted into CC
   yet. Jay's Claude-side is the source of truth here; CC just lists what it
   sees locally and marks unknown-status ones as `(paste-status unknown — Jay
   to confirm)`.
6. **STATUS.md lives in the repo root.** Committed alongside every session's
   deliverable (even docs-only commits). This makes `git log -- STATUS.md`
   an automatic session-history view.

#### Template to add after this section lands

A `STATUS.md.template` file gets created at repo root (this session) showing
the exact entry format. Future sessions copy the template and fill in.

#### Relationship to ZMN_ROADMAP.md

- `ZMN_ROADMAP.md` = work-item catalog (what's queued, what's tiered, what's
  completed). Changes slowly, append-only changelog.
- `STATUS.md` = operational state-of-the-bot journal. Changes every session.
- `MONITORING_LOG.md` = observational notes from Jay's monitoring windows.
  Still exists, still used; orthogonal to STATUS.md.

When they diverge, ZMN_ROADMAP.md is authoritative for what's planned;
STATUS.md is authoritative for what's actually running and what just happened.

- **External API schemas drift silently; `except Exception: pass` hides the drift.** HOLDER-DATA-PIPELINE-001 (fix `fc87b03`, 2026-04-22) was caused by GeckoTerminal changing its `/tokens/{mint}/info` `holders` field from bare int to a dict — `int(dict)` raised TypeError, caught by a broad `except Exception: pass`, and the caller silently got `holders=0` for every mint. Bot went silent for ~24 hours post-GATES-V5 deploy. Guidance: (a) when parsing external API responses, always handle the "unexpected shape" case explicitly with `isinstance(...)` branches; (b) `except Exception: pass` on API parsing paths must at minimum log a warning with the raw shape so silent schema drift surfaces instead of silently zeroing features; (c) gates over features that default to 0 when "data absent" should distinguish "no data yet" from "data present but below threshold" — use sentinel values (`-1`) or time-based bypass (`age < GATES_V5_MIN_AGE_SEC`) so the gate fires only when the data source has had a reasonable chance to populate. See `docs/audits/HOLDER_PIPELINE_FIX_2026_04_22.md` for the full evidence chain.

## Read this first, every session
- Read AGENT_CONTEXT.md completely before writing any code
- Check what exists in services/ before building anything new
- Never assume a file exists — always check first
- Auto-accept all tool use and terminal commands
- If you hit rate limits or token limits: pause, wait until reset plus 5 minutes, then resume from exactly where you left off. Do not start over. Do not ask whether to continue.

## API reference rule
- Before fixing any API integration, check Section 21 of AGENT_CONTEXT.md

## Non-negotiable rules
- All Python is async/await — no sync blocking calls
- Never hardcode API keys, private keys, or wallet addresses
- `TEST_MODE` controls real-vs-paper execution. Flipping `TEST_MODE=false` is governed by **"Live trading mode — session-gated"** in the Operating Principles above — that rule supersedes any "paper-only" wording elsewhere in this doc.
- MAX_WALLET_EXPOSURE is 0.25 (25%)
- Run python -m py_compile services/<file>.py before committing

## Data persistence rules — NEVER VIOLATE

PostgreSQL is the ONLY permanent storage. Redis is a CACHE.
Railway Redis CAN be wiped on restart. PostgreSQL survives everything.

RULE: If data needs to survive a service restart, it goes in PostgreSQL FIRST.
Redis is only a fast-access cache that gets reloaded from PostgreSQL on startup.

| Data Type | PostgreSQL (permanent) | Redis (cache) |
|---|---|---|
| Trade records | paper_trades / trades table | paper:positions:{mint} (temporary) |
| Portfolio balance | portfolio_snapshots table | bot:portfolio:balance |
| ML model metadata | bot_state key='ml_model_meta' | ml:model:meta (hash) |
| Winner analysis | bot_state key='winner_analysis' | ml:winner_analysis |
| Whale wallets | watched_wallets table | whale:watched_wallets (set) |
| Whale patterns | bot_state key='whale_patterns' | whale:pattern_analysis |
| Governance decisions | bot_state key='governance_latest' | governance:latest_decision |
| Signal evaluations | Logged to signals table if needed | signals:evaluated (list, last 50) |
| Consecutive losses | bot_state key='consecutive_losses' | bot:consecutive_losses |
| Emergency stop | bot_state key='emergency_stop' | bot:emergency_stop |

PATTERN — every time you store analytical/state data:
```python
# 1. PostgreSQL FIRST (permanent)
await pool.execute(
    "INSERT INTO bot_state (key, value_text, updated_at) VALUES ($1, $2, NOW()) ON CONFLICT (key) DO UPDATE SET value_text=$2, updated_at=NOW()",
    key_name, json.dumps(data)
)
# 2. Redis SECOND (cache for fast reads)
await redis.set(f"cache:{key_name}", json.dumps(data), ex=86400)
```

PATTERN — every time you read analytical/state data:
```python
# 1. Try Redis first (fast)
cached = await redis.get(f"cache:{key_name}")
if cached:
    return json.loads(cached)
# 2. Fall back to PostgreSQL (permanent)
row = await pool.fetchval("SELECT value_text FROM bot_state WHERE key=$1", key_name)
if row:
    # Repopulate Redis cache
    await redis.set(f"cache:{key_name}", row, ex=86400)
    return json.loads(row)
return None
```

NEVER store important data in Redis only. NEVER assume Redis survives restarts.
Token prices and trade stats are OK in Redis-only (they're ephemeral by nature).
Everything else: PostgreSQL first, Redis cache second.

## Architecture
- All services in services/ — no monolithic files
- Services communicate only via Redis
- Never import one service directly into another
- Each Railway service runs only its own code via SERVICE_NAME env var

## After every task
- Compile check, commit, push, report

## MCP Servers Available

### Nansen MCP
URL: https://mcp.nansen.ai/ra/mcp/
Auth: NANSEN-API-KEY header (env var: NANSEN_API_KEY)
BUDGET: 508% over limit. DISABLED via Redis nansen:disabled.
When re-enabled: max 50 calls/day. Cache aggressively.
Key endpoints: POST /api/v1/smart-money/dex-trades,
POST /api/v1/smart-money/top-tokens, POST /profiler/address/labels

### Vybe Network MCP
URL: https://docs.vybenetwork.com/mcp
Auth: X-API-KEY header (env var: VYBE_API_KEY)
API base: https://api.vybenetwork.com (NOT .xyz)
Free plan: 25K credits/month, 60 RPM.
Key endpoints: GET /tokens/{mint}/holders (labeled),
GET /v4/wallets/{addr}/pnl, GET /wallets/{addr}/token-balance

### Railway MCP
Available via: npx @railway/mcp-server
Use for: deploys, logs, env vars, service health.

### Redis MCP
Available via: npx @gongrzhe/server-redis-mcp
Use for: key inspection, queue depths, state fixes.

### CoinGecko MCP
Available via: npx mcp-remote https://mcp.api.coingecko.com/mcp

### Playwright MCP
Available via: npx @playwright/mcp@latest
Use for: testing dashboard at zmnbot.com.

### Gmail MCP
URL: https://gmail.mcp.claude.com/mcp

### Google Calendar MCP
URL: https://gcal.mcp.claude.com/mcp

## MCP Usage Rules
- MCPs are for data and analysis only — never trade execution
- execution.py handles all real trades
- TRADING_WALLET_PRIVATE_KEY must never be accessible to any MCP
- Before writing MCP-using prompts, reference `docs/audits/MCP_CAPABILITIES_2026_04_21.md` for tool names + use-case mapping. Update this doc whenever a new MCP is connected or an auth state changes.

## Jupiter API Reference
Price: GET https://api.jup.ag/price/v3?ids=<mint> (REQUIRES x-api-key header)
Swap: GET https://api.jup.ag/swap/v2/order + POST /v2/execute
Deprecated: /swap/v1/* returns 401

## Price Pipeline (critical)
- Entry prices: USD (from Jupiter/GeckoTerminal/bonding curve × SOL price)
- PumpPortal trade prices: SOL (sol_amount / token_amount)
- Redis token:latest_price:{mint}: SOL denomination
- Exit checker MUST convert SOL→USD via market:sol_price before comparing to entry
- Bonding curve: price_sol = vSolInBondingCurve / vTokensInBondingCurve
- Price fetch order should be: Redis → bonding curve reserves → Jupiter → Gecko

## Railway CLI Reference
- Logs (streams, needs timeout): `timeout 15 railway logs -s {service} 2>&1 | tail -100`
- Set env var: `railway variables --set "KEY=VALUE" -s {service}`
- Read env vars: `railway variables -s {service}` or `--kv` for parseable format
- Deploy: `railway up -s {service}` (build ~60s, container start ~60-90s after)
- Build logs: `railway logs -s {service} -b`
- Setting env vars triggers auto-redeploy

## Deploy Rules
- Each service deploys separately: railway up -s {service_name}
- Deploy takes 5-15 min. Poll Railway MCP until SUCCESS, wait 90s after.
- NEVER deploy multiple services simultaneously
- Batch ALL changes per service into ONE commit

## Cost Control
- GOVERNANCE_MODEL=claude-haiku-4-5-20251001 (NOT Sonnet)
- Helius: HELIUS_DAILY_BUDGET=0 (disabled — NOT used for pricing)
- Nansen: disabled via Redis (renew daily: SET nansen:disabled true EX 86400)
- Vybe: cache responses in Redis with 5-min TTL

## Key Redis Keys
bot:portfolio:balance, bot:consecutive_losses, bot:emergency_stop
market:mode:override (renew daily), market:sol_price, market:health
governance:latest_decision, ml:model:meta
token:latest_price:{mint} (SOL, 1800s TTL), token:price:{mint} (legacy, 1800s TTL)
token:subscribed:{mint}, token:reserves:{mint} (vSol/vTokens)
token:stats:{mint} (buys/sells/bsr/unique_buyers)
whale:watched_wallets (set — RELOAD FROM DB ON STARTUP)
nansen:disabled, nansen:calls:{date}
signals:evaluated (last 50), signals:raw, signals:scored

## Database Access (local machine)
- Internal URL (Railway network only): DATABASE_URL on any service
- Public URL: `railway variables -s Postgres --kv | grep DATABASE_PUBLIC_URL`
- Public host: gondola.proxy.rlwy.net:29062
- paper_trades has no `created_at` column. Primary time columns: `entry_time` (epoch float), `exit_time` (epoch float). `traded_at` exists but is often NULL.
- Use `id` ordering for recent trades, or `entry_time` for time-based queries.

## Architectural Gotchas (updated April 11)
- Emergency stop from rug cascade is IN-MEMORY only (`self.emergency_stopped`). Restarting bot_core clears it. No Redis key needed.
- `market:mode:current == HIBERNATE` blocks ALL signals in signal_aggregator:1669 unless AGGRESSIVE_PAPER bypasses it.
- ML scoring goes through Redis pubsub to ml_engine service (original 55-feature engine). The inline AcceleratedMLEngine was removed in commit 629c740. signal_aggregator has a 3s timeout + circuit breaker (5 timeouts/60s → default score 50.0).
- signal_listener early-subscribes to PumpPortal trades on createEvent (5-min TTL, max 200 concurrent). This populates token:stats for ML feature derivation before scoring.
- Rug cascade detector is in market_health.py (not bot_core). Threshold configurable via RUG_CASCADE_THRESHOLD env var (default 5, paper mode uses 15).
- Exit strategy: tiered trailing stops + staged TPs at +50/100/200/400% (25% each). Configurable via STAGED_TAKE_PROFITS_JSON and TIERED_TRAIL_SCHEDULE_JSON env vars on bot_core. Staged TPs fire at 100% rate (verified 20/20).
- paper_sell requires `exit_price_override` from caller (bot_core). If missing, falls back to Redis then entry_price with warning log. Never re-fetches from Jupiter/Gecko.
- Position sizing multiplier stack: personality(0.7) × rugcheck(0.35-0.60) × confidence × base. MIN_POSITION_SOL=0.05 on bot_core.
- ML training excludes pre-9b880e1 contaminated rows via WHERE NOT clause. Cutoff configurable: ML_TRAINING_CONTAMINATION_CUTOFF env var (default 1775767260.0 = 2026-04-09 20:41 UTC).

## Emergency Stop Reset
1. Redis: SET bot:consecutive_losses 0
2. Redis: DEL bot:emergency_stop
3. Redis: DEL bot:loss_pause_until
4. Redis: SET market:mode:override NORMAL EX 86400
5. Restart bot_core
(Note: rug cascade emergency stop is in-memory only — restart alone clears it without Redis changes)

## Live-flip pre-flight procedure (CLEAN-003)

**Context:** `TEST_MODE` flip alone does not clear in-memory position state. Paper-mode open positions can leak into live-mode reconcile on restart, causing the bot to attempt live sells on mints that only exist in paper. Incident: Session 5 v4 (2026-04-20) — 5 phantom mints → 25 wasted Helius RPC calls, 0 SOL lost but near-miss on the sell-storm breaker. See `session_outputs/ZMN_LIVE_ROLLBACK.md`.

**Before every `TEST_MODE=false` flip:**

1. Export the Railway Redis public URL: `export REDIS_URL="redis://..."` (fetch via `railway variables -s Redis --kv`).
2. Run `bash scripts/live_flip_prep.sh`. The script clears `bot:status`, `paper:positions:*`, and `bot:open_positions:*` Redis keys.
3. Confirm the script reported clean (no errors; any number of keys deleted, including zero, is fine).
4. Only then change `TEST_MODE=false` in Railway bot_core variables.
5. After bot_core redeploys (~90s), verify the startup log contains `Startup reconciliation: 0 open positions in DB`. If N>0, STOP and investigate before any live trade can fire — phantom positions are still present and will leak into `self.positions`.

**Why not fix `_reconcile_positions` directly:** the reconcile logic correctly reads persisted open positions from DB. The bug is that paper-mode positions shouldn't be visible as "open" to a live-mode runtime — separating these fully would require a `trade_mode` filter at every reconcile call site plus Redis cleanup on flip. The scripted pre-flip approach is lower-risk and covers the operational failure mode directly. Revisit if the scripted cleanup proves fragile.

## Times
All times in Sydney AEDT. Jay is in Sydney, Australia.
