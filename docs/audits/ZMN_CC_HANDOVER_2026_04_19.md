# ZMN CC handover pack — 2026-04-19

> **STATUS (2026-04-19):** This audit's actionable items are consolidated in `ZMN_ROADMAP.md`. Refer there for current status, priority, and dependencies. This doc is retained as evidence / deep-dive detail.
>
> **Corrections since original authoring [2026-04-19, post Session 1 + Session 2 v2]:**
> - **Sentry MCPs row below now says "0 ZMN projects — SDK not yet integrated" — that was true at authoring time. As of commit `cb45d6b` (Session 1 precursor) there are 8 live ZMN Sentry projects in the `rz-consulting` org. Session 1 (commit `35bdfe6`) classified all 5 unresolved issues as Class A operational noise with 0 Class B real bugs. Regression checks PASS for Solders `.sign()`, missing Helius URL, PumpPortal HTTP 400 — 0 events in 14 days.**
> - **The "Current ZMN state" table's `Sentry projects | 0` is obsolete.** Current value: 8 projects live, actively capturing.
> - **Session 2 v2 (commit `5ac30cd`) closed the dashboard live close-path gap.** Recent Trades + aggregates + Treasury now surface live-closed trades. Open Positions widget for live remains empty by design until **DASH-ENTRY-001** (Session 2b) lands the entry-path INSERT. Dashboard live-mode coverage is ~80% post-`5ac30cd`.
> - **Redis parity in bot_core's live branch is NOT a gap.** `traded:mints` SADD (+ 7200s EXPIRE) and `bot:consecutive_losses` INCR/reset are already present in live branch at `services/bot_core.py:L1126-1151`. Do not re-list these as gaps in future audits. (Original Session 2 v1 prompt flagged them incorrectly; Session 2 v2 Phase 1 recon verified parity.)
> - **`pos.trade_id` is id-space-ambiguous** (paper → paper_trades.id, live → trades.id; id-spaces overlap). Near-corruption bug caught in Session 2 v2 Phase 1 recon. Tracked as **REFACTOR-001**. Interim mitigation: use INSERT (not UPDATE) at live close — already in `5ac30cd`.
> - **Open threads list below**: `ZMN-SIGNAL-AGGREGATOR-1` is resolved-as-tracked (Pattern B silent no-op, deferred to ML-009). The 2.07 SOL phantom drain is resolved (see `ZMN_LIVE_TRADE_FORENSICS_2026_04_19.md`). New open threads surfaced by Sessions 1 + 2 v2 are tracked in `ZMN_ROADMAP.md` under their IDs.
> - **v4 cost**: actual was ~3.4 SOL, not 1.32 SOL — prior figures were mid-trial snapshots. Fixed in `CLAUDE.md` in the roadmap-consolidation commit.
>
> **Corrections since last update [2026-04-20, post Session 3 + Session 4 gate + chat-layer analysis]:**
> - **Session 3 verdict amended** from "B: spec matches code, 261 HTTP 400s are transient" to "B-conditional: spec matches code, but routing state is likely stale — the 261 HTTP 400s are predominantly mid-graduation pool drift." Mechanism + fix tracked as EXEC-001 + EXEC-002 (paired, both PRE-LIVE BLOCKERS). Session 3 audit doc has a dated correction block at top; body preserved.
> - **Session 4 T+24h gate:** strict FAIL on `stop_loss_35%` count reduction (23% vs 50% target), PASS on total PnL (+28% vs pro-rated baseline). Jay-accepted on PnL-up read. Yellow flags on TRAILING_STOP WR drop (91.8%→70.9%) and `no_momentum` per-trade worsening (33%). See `docs/audits/TUNE_T24H_GATE_2026_04_20.md`.
> - **Paper fee model gap:** `fees_sol` models ~0.5% flat round-trip only. Misses 1.5pp platform delta, priority fees (~0.001 SOL fixed), Jito tips (~0.001-0.005 SOL fixed), and realized slippage on 95.8% of trades. Paper PnL overstates live by ~0.004 SOL/trade at 0.05 SOL sizing. Tracked as FEE-MODEL-001 (Tier 2). Real-time paper-vs-live delta tracker during live windows tracked as OBS-011 (Tier 2). Prerequisite execution-path audit tracked as EXEC-003 (Tier 2, read-only, informs FEE-MODEL-001 default values).
> - **Jupiter NameError at `execution.py:491`** (undefined `amount_sol` + `action` vars) tracked as EXEC-002. Pre-existing latent bug surfaced in Session 3 leftover concern #3. Must land paired with EXEC-001; neither alone is safe.
> - **Devnet routing override** tracked as DEVNET-001 (Tier 3) — Session 3 Phase 2 was blocked by hardcoded mainnet URLs in `execution.py` (Jupiter + PumpPortal). Low priority; unblocks future devnet validation sessions.
> - **SEC-001 waiver:** Jay accepted for LIVE-002's one supervised window ONLY, with Session 5 v2 Redis sentinel monitoring as compensating control. Required for all unsupervised future windows.
> - **Routing state freshness** is now an Operating Principle in `CLAUDE.md` (after the `pos.trade_id` ambiguity principle). Future CC sessions must refresh `bonding_curve_progress` before passing to `execute_trade` on sells.
> - **Paper fee-model divergence from live reality** is now an Operating Principle in `CLAUDE.md` (after the routing-freshness principle). When comparing paper P&L to live, subtract ~0.004 SOL/trade at 0.05 SOL sizing.
>
> **Correction block 2026-04-21 (post Session 5 v4 rollback + FIX-1/FIX-2 sessions):**
> Session 5 v4 outcome: ROLLBACK at T+12:00. Single live trade executed (mint `yh3n441...`, 0.365 SOL, -0.094 SOL net). T5 trigger fired on benign position state, not real loss. Handover implications:
>
> 1. **FEE-MODEL-001 is now PRE-LIVE BLOCKER and has landed (commit `e078b4c`).** Paper model under-counts live by ~96× on pre-grad pump.fun round-trips. Re-baselined historical edge is the gate for any Session 5 v5 attempt. See FIX-2 output: `docs/audits/PAPER_EDGE_REBASELINE_2026_04_20.md`.
> 2. **T5 trigger definition is unusable for small wallets.** v4's `(T0 - now) / T0 > 20%` fired at 22.57% on benign 0.365-SOL position state (real loss was 5.68%). Replaced by T5a (position-adjusted drawdown) + T5b (single-trade catastrophic loss) in the next Session 5 v5 prompt. `MAX_POSITION_SOL_FRACTION=0.10` env var (landed via `e078b4c`) adds proportional sizing so future positions cap at ~10% of wallet.
> 3. **Reconcile-residual is a known gap (CLEAN-003 landed).** Paper positions leak into live memory on TEST_MODE flip. Mitigation is scripted pre-flip cleanup via `scripts/live_flip_prep.sh` (FIX-1). CLAUDE.md "Live-flip pre-flight procedure (CLEAN-003)" section codifies the procedure. Don't flip without running it.
> 4. **ML gate bypass path identified (ML-012).** Mint traded at displayed `ml=31.5` despite gate=40. Root cause: `AGGRESSIVE_PAPER_TRADING=true` on signal_aggregator overrides `ML_THRESHOLDS` to `{"speed_demon": 30, ...}` at module load regardless of TEST_MODE. Outcome (C) — actual bug. Fix required before next supervised live window. See `docs/audits/ML_BYPASS_INVESTIGATION_2026_04_20.md`.
> 5. **Slippage on pre-grad is 20-30× worse than old paper estimates.** Real-world cost on 0.3-0.5 SOL positions is 10-25% of position. Rebaseline under corrected model: 7d Speed Demon paper edge moves from +556.60 SOL to -587.15 SOL (edge DOES NOT SURVIVE at current sizing distribution). Required v5 sizing caps: `MAX_POSITION_SOL=0.25` (hard blocker), `SPEED_DEMON_BASE_SIZE_SOL≈0.15`, `SPEED_DEMON_MAX_SIZE_SOL≈0.25`. See `docs/audits/PAPER_EDGE_REBASELINE_2026_04_20.md`.
> 6. **Rollback machinery worked correctly.** Trigger fired, bot was restored to TEST_MODE=true within 15 min of T+0, zero trapped positions, Redis sentinels clean. The safety system did its job even on a false-positive trigger — which is the correct failure mode for this class of system.
> 7. **Helius STAKED URL (`ardith-mo8tnm-fast-mainnet`) returned 522 errors during v4 window.** Already noted as occasionally-unreliable; has recurred. For v5: either health-check before use, or demote to last in resolver chain. Tracked indirectly via DEPLOY-DISCIPLINE-001 + existing resolver-chain Operating Principle.
>
> **New roadmap items from this consolidation:** EXEC-005 (Tier 2), SLIPPAGE-CALIBRATION-001 (Tier 2), OBS-012 (Tier 3), DEPLOY-DISCIPLINE-001 (Tier 3). FIX-1 earlier landed T5-DESIGN-001, CLEAN-003 ✅, ML-012 as separate items.
> **Escalated + landed:** FEE-MODEL-001 → Tier 1 PRE-LIVE BLOCKER ✅ `e078b4c`.
> **Session 5 v5 pre-flight gate summary:** (1) FEE-MODEL-001 ✅, (2) CLEAN-003 ✅, (3) ML-012 fix, (4) T5a/T5b in v5 prompt, (5) MAX_POSITION_SOL_FRACTION active ✅, (6) position-size caps from rebaseline applied in Railway env.


**Author:** Claude Opus 4.7. **Audience:** the next CC session, or a fresh Claude chat that needs to get caught up on ZMN in one read.
**Length budget:** intentionally short. For depth, follow the links.

---

## What Claude Code now has in its toolkit

### MCPs (14 in `.mcp.json`, mostly callable)

- **Solana / crypto:** `helius` (~60 tools), `nansen` (28 tools), `vybe` (47 endpoints), `coingecko` (60+), `dexpaprika` (12), `defillama`, `birdeye` (~90 — session-flaky), `rugcheck` (stub).
- **Infra / observability:** `railway`, `redis`, `sentry` (authed; **0 ZMN projects** — SDK not yet integrated), `github` (PAT, int-arg JSON-typing issues), `gmail` / `gcal` / `gdrive` (auth pending).
- **Dev loop:** `playwright` (24 tools, **headless instability on Win11**), `shadcn`, `socket`, `context7` (plugin).

### Skills (4 installed, all project-scoped under `.claude/skills/`)

- `mcp-builder` — scaffolds new MCPs (TS SDK + Streamable HTTP recommended). Use for the missing PumpPortal / Jito / SocialData / LetsBonk MCPs.
- `skill-creator` — create / iterate / eval skills.
- `frontend-design` — distinctive, production-grade UI; counsels against generic AI-slop aesthetics. Used in `DASHBOARD_REDESIGN_2026_04_19.md`.
- `webapp-testing` — Playwright-based local-webapp testing; pairs with Playwright MCP.

### CLI tools (laptop pipx-installed, NOT MCPs)

- `ruff 0.15.11`, `black 26.3.1`, `mypy 1.20.1`, `semgrep 1.159.0`, `solana-keygen 3.1.13`, `postgres-mcp` (installed but **not registered in `.mcp.json`** — use the asyncpg shim at `Scripts/export_paper_trades.py` until it is).

### Cross-cutting failure mode to remember

Many MCPs reject integer / array args from Claude Code's tool-call envelope as "expected number, received string". Affected this session: `helius` (ints), `github` (`perPage`), `shadcn` (`registries`), `socket` (`packages`), `context7` (`query`). Workaround: omit the int arg, or pass arrays as JSON-array literals.

For full deep-dive details: `CC_TOOL_SURFACE_2026_04_19.md`.

---

## Current ZMN state (as of 2026-04-19 ~04:30 UTC)

| Field | Value | Source |
|---|---|---|
| TEST_MODE | true (paper) | Railway env, bot_core |
| Paper balance | **194.67 SOL** (up from CLAUDE.md's stale 31.86) | Redis `bot:portfolio:balance` |
| On-chain wallet (real) | **1.61 SOL** (down from 3.677 at abort report ~30 min prior) | Helius `getBalance` 4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ |
| Open positions (paper) | 3 (all Speed Demon) | Redis `bot:status` |
| Active personalities | Speed Demon (sole) | env: `ANALYST_DISABLED=true`, Whale Tracker dormant-but-routing |
| Total paper trades | 5,833 | Postgres |
| Total `trades` rows | 5,856 (23-row delta from paper_trades — **OPEN THREAD**) | Postgres |
| Live `TX_SUBMIT` events (7d) | 36 buys + 33 sells + 9,044 errors | live_trade_log |
| Speed Demon 7d perf | 2,256 trades, +428 SOL, 43.3% WR | Postgres |
| BREAKEVEN_STOP | **fixed structurally** (last firing 2026-04-16) | Postgres + bot_core.py:1232 |
| stop_loss_35% 7d | 272 trades, **–56.35 SOL** (largest bleeder) | Postgres |
| no_momentum_90s 7d | 775 trades, –41.42 SOL | Postgres |
| TRAILING_STOP 7d | 834 trades, +395.80 SOL @ 93% WR | Postgres |
| ML threshold | 40 (signal_aggregator gate); 30 (bot_core, unused) | Railway env |
| TIERED_TRAIL_SCHEDULE_JSON | `[[0.30, 0.35], …]` (loose trail deployed) | Railway env |
| STAGED_TAKE_PROFITS_JSON | `[[2.00, 0.20], [5.00, 0.375], [10.00, 1.00]]` | Railway env |
| watched_wallets | 44 rows, 0 active in 14 days | Postgres (stale) |
| Sentry projects | **0** (no SDK integration in services/) | Sentry MCP `find_projects` |
| Anthropic credits | exhausted (governance LLM dead) | per CLAUDE.md, unverified this session |

**For the data behind every number, see `ZMN_RE_DIAGNOSIS_2026_04_19.md`.**

---

## Priority list (ranked, from `ZMN_OPTIMIZATION_PLAN_2026_04_19.md`)

### Tier 1 — env-var changes / docs / read-only forensics

1. Lower trail-activation tier `[[0.10, 0.30], …]` — addresses the 272-trade / –56 SOL stop_loss_35% bleeder (15 min).
2. Tighten 90s momentum check: `SD_EARLY_CHECK_SECONDS=60`, `SD_EARLY_MIN_MOVE_PCT=3.0` (15 min).
3. Cosmetic: align bot_core `ML_THRESHOLD_SPEED_DEMON=40` with signal_aggregator (5 min).
4. CLAUDE.md docs refresh: remove stale "ML inverts above 40" claim; add 7d ML-band table; note BREAKEVEN_STOP solved (30 min).
5. Live-trade forensics: explain the 2.07 SOL wallet drain since abort report (60 min, read-only).

### Tier 2 — 1-session MCP integrations

1. Sentry SDK integration in 8 services (45 min).
2. DexPaprika fallback in exit-price cascade (45 min + 24h obs).
3. Helius `getPriorityFeeEstimate` in execution.py (90 min, devnet test).
4. Vybe pre-entry concentration measurement (60 min plumbing + 7-day obs).
5. Nansen-MCP-based watched_wallets refresh job (120 min).
6. Playwright headless triage (30 min).

### Tier 3 — multi-session

1. Dashboard v2 build (Concept C per `frontend-design` skill).
2. Whale Tracker entry-decision wiring (post-2.5).
3. PumpPortal MCP build (per `mcp-builder` skill).
4. ZMN-specific `zmn-trade-analysis` skill (per `skill-creator`).
5. Analyst revival decision.
6. ML retrain on corrected labels (existing roadmap).
7. **Live-enable supervised session** — only after Tier 1+2 pass cleanly.

### Tier 4 — gating prerequisite

**Rules-refresh prompt** must land first. CLAUDE.md still says "Paper mode is non-negotiable" — every session that touches live state will refuse until that rule is updated. Recommended replacement language is in the abort report Step B3.

---

## Open threads (things half-explored — next session should finish)

1. **The 2.07 SOL wallet drain.** `paper_trades` shows zero live rows, `trades` table has 23 more rows than paper_trades, `live_trade_log` has 36 TX_SUBMIT buys in 7d. The bot has been spending real SOL outside the recorded `trade_mode='live'` path. **Forensics task.** See optimization plan Tier 1 §1.5 + Tier 2 §2.7.
2. **`ML_THRESHOLD_SPEED_DEMON` env var split.** bot_core has 30, signal_aggregator has 40. Confirm signal_aggregator is the only gate; if so, remove the bot_core var or align.
3. **Playwright headless instability on Win11.** Blocks dashboard regression suite. 30 min triage.
4. **Birdeye session expiry on first call.** Need a session-refresh story.
5. **`watched_wallets` is stale.** 44 rows / 0 active in 14d. Whale Tracker entries are coming from pumpportal feed, not from this table — so the personality routing must be doing something else useful. Worth understanding before either wiring or ripping out the table.
6. **Nansen MCP arg-shape.** Most tools want `request: {…}` wrapper, not flat kwargs. Document during the watched_wallets refresh build.
7. **Vybe `execute-request`** wants a HAR-shaped body. Use `get-endpoint` first.
8. **Postgres MCP** is pipx-installed but not registered in `.mcp.json`. Add the registration block.

---

## Pointers to every audit doc written this session

| Doc | What it answers |
|---|---|
| `CC_TOOL_SURFACE_2026_04_19.md` | What can CC do now? Per-MCP deep-dives. |
| `ZMN_RE_DIAGNOSIS_2026_04_19.md` | What does the data say about ZMN's bleeders today? Six pain points re-examined. |
| `MCP_BUILDER_CANDIDATES_2026_04_19.md` | Which missing MCPs would unlock what? Ranked. |
| `DASHBOARD_TESTING_PLAN_2026_04_19.md` | Playwright + webapp-testing regression suite plan (blocked on Playwright stability). |
| `DASHBOARD_ANALYSIS_2026_04_19.md` | frontend-design skill applied to dashboard bugs (3-paragraph addendum). |
| `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` | Tier 1/2/3 ranked plan + ranked-next-5-sessions list. |
| `ZMN_CC_HANDOVER_2026_04_19.md` | This file. |

Plus the prior session's docs in the same directory: `DASHBOARD_REDESIGN_2026_04_19.md`, `DEPLOYMENT_BLOAT_2026_04_19.md`, `ORPHAN_FILES_2026_04_19.md`, `SECRETS_SCAN_2026_04_19.md`, `ZMN_LIVE_ENABLE_HANDOFF_2026_04_19.md`.

---

## Paste-able "Step 0" block for a future CC session

```markdown
Step 0 — Read in this order:
1. CLAUDE.md (project root)
2. docs/audits/ZMN_CC_HANDOVER_2026_04_19.md (this file — single-shot context catch-up)
3. docs/audits/ZMN_OPTIMIZATION_PLAN_2026_04_19.md (the plan)
4. The specific audit doc relevant to your task:
   - Tool / MCP question → CC_TOOL_SURFACE_2026_04_19.md
   - Trading edge question → ZMN_RE_DIAGNOSIS_2026_04_19.md
   - Dashboard work → DASHBOARD_TESTING_PLAN_2026_04_19.md + DASHBOARD_ANALYSIS_2026_04_19.md + DASHBOARD_REDESIGN_2026_04_19.md
   - Build a new MCP → MCP_BUILDER_CANDIDATES_2026_04_19.md + .claude/skills/mcp-builder/SKILL.md
   - Live-enable → docs/audits/ZMN_LIVE_ENABLE_HANDOFF_2026_04_19.md AND check that the rules-refresh prompt has landed first

Acknowledge with one sentence per item read. Then proceed.
```

---

## Hard rules every session must respect

1. **No services/ writes this session** unless the session is explicitly scoped for it (this session was read-only docs only).
2. **TEST_MODE=true** until the rules-refresh prompt lands.
3. **No secrets in any committed file.** The Phase 6 grep gate enforces this. ANTHROPIC_API_KEY, HELIUS_API_KEY, NANSEN_API_KEY, VYBE_API_KEY, JUPITER_API_KEY, SOCIALDATA_API_KEY, TELEGRAM_API_HASH, TRADING_WALLET_PRIVATE_KEY, REDIS_URL with password, DATABASE_URL with password, DISCORD_WEBHOOK_URL, DISCORD_BOT_TOKEN, DASHBOARD_SECRET — never in any audit doc.
4. **One lever per execution session.** This deep-recon session is documentation-only; the action sessions that follow it should each change one thing.
5. **Verify with data before recommending.** Stale CLAUDE.md claims are how the abort report missed that BREAKEVEN_STOP was already structurally fixed.
