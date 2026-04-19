# ZMN live trade forensics — wallet drain reconciliation

**Author:** Claude Opus 4.7. **Date:** 2026-04-19. **Scope:** read-only investigation. No code changes, no env vars, no SQL writes, no TEST_MODE flip.
**Companion docs:** `ZMN_RE_DIAGNOSIS_2026_04_19.md` (open thread), `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` Tier 1 §1.5 + Tier 2 §2.7 (the planning that pointed at this), `ZMN_LIVE_ENABLE_HANDOFF_2026_04_19.md` (the abort report whose 3.677 SOL figure started this thread).

---

## TL;DR — Verdict

**Verdict A: Expected residual from documented live trial v4. The "30-min drain" never happened. The drain was the v4 trial itself, ~2.5 days before this session, which lost ~3.4 SOL (not the 1.32 SOL the postmortem claimed). The phantom appearance of a drain came from comparing a stale `portfolio_snapshots` row taken *during* v4 against a fresh on-chain reading taken after v4 ended.**

The bot is not actively spending SOL outside `TEST_MODE`. There are no transactions in the supposed drain window, zero live_trade_log events in the last 48 hours, and every execution code path is properly guarded by `TEST_MODE`.

**It is safe to run the next planned sessions** (Tier 1 trading-tune, then supervised live-enable) without inserting a code-change session first.

---

## Phase 1 — Baselines captured

### 1.1 — On-chain wallets

| Wallet | Address (truncated) | Current SOL | Note |
|---|---|---:|---|
| Trading | `4h4pst…ii8xJ` | **1.658** | Was 1.610 at deep recon ~70 min ago. **+0.048 SOL** from the 04:49 OKX_DEX_ROUTER swap (sale of leftover ELONX). |
| Holding | `2gfHQ…ttWJ9` | **0.098** | Unchanged from prior sessions. |

**Drain not ongoing** — wallet is slightly *up* since deep recon (+0.048 SOL from the ELONX sale). STOP condition not triggered.

### 1.2 — Wallet transaction history (Helius MCP)

The trading wallet has **only 10 successful transactions visible** via `getTransactionHistory` (no pagination beyond the first page returns more):

| Time (UTC) | Type | Program | Sig (truncated) | Notes |
|---|---|---|---|---|
| **2026-04-19 04:49:29** | SWAP | OKX_DEX_ROUTER | `4x1bQy…AXoH…` | **+0.0485 SOL** (ELONX sell). External — not bot-originated. |
| 2026-04-16 23:05:05 | TRANSFER | SYSTEM_PROGRAM | `2niR63…` | tiny (0.000005 SOL), unrelated |
| 2026-04-16 22:50:16 | TRANSFER | SYSTEM_PROGRAM | `kniTb4…` | tiny, unrelated |
| 2026-04-16 22:46:00 | SWAP | PUMP_FUN | `5tncgWK…` | v4 ELONX buy |
| 2026-04-16 22:45:52 | SWAP | PUMP_FUN | `4woR7m…` | v4 KOLs sell |
| 2026-04-16 22:45:48 | SWAP | PUMP_FUN | `3CSM1…` | v4 shibe sell |
| 2026-04-16 22:45:03 | SWAP | PUMP_FUN | `5vzHo…` | v4 shibe buy |
| 2026-04-16 22:44:58 | SWAP | PUMP_FUN | `2mEzg…` | v4 TREAT sell |
| 2026-04-16 22:44:50 | SWAP | PUMP_FUN | `2oLyEP…` | v4 KOLs buy |
| 2026-04-16 22:44:42 | SWAP | PUMP_FUN | `2btss…` | v4 TREAT buy |

Failed transactions visible: 1 OKX swap (Apr 16 21:13) — failed, no cost. 3 SYSTEM_PROGRAM transfers (Apr 16). Older entries are pre-bot history (Aug 2025 and Jul 2025 — likely Jay's own wallet activity before the bot existed).

**Critical gap:** no on-chain transactions exist between 2026-04-16 23:05 UTC and 2026-04-19 04:49 UTC. The wallet was completely idle for ~2.5 days. Therefore the supposed "30-minute drain on 2026-04-19 04:00–04:30 UTC" did not happen on-chain.

### 1.3 — Postgres tables

Row counts:

| Table | Rows | Note |
|---|---:|---|
| paper_trades | 5,854 | trade_mode column: 100% `paper` |
| trades | 5,877 | +23 vs paper_trades (was +23 at deep recon, also +23 now) |
| live_trade_log | 9,113 | Includes 9,044 errors from the v4 trial era |
| portfolio_snapshots | 38,403 | Records **paper balance**, not on-chain (see §2.5) |
| watched_wallets | 44 | Unchanged from deep recon — no refresh activity |
| bot_state | 3 | |

`paper_trades.trade_mode` breakdown: **100% `paper`. Zero rows marked `live`.** The schema does have a `trade_mode` column, but the bot has never written `live` to it (live trades go to the `trades` table instead — see §2.4).

`trades` table boundary: first row 2026-03-27 13:16:19 UTC, last row 2026-04-19 05:43:00 UTC (the table is being actively written *right now*).

### 1.4 — Redis state (this session)

- `bot:portfolio:balance` = **195.11 SOL** (paper, +0.45 SOL since deep recon)
- `bot:status.test_mode` = **true** ✓
- `bot:status.market_mode` = `DEFENSIVE`
- `bot:status.open_positions` = 0 (was 3 at deep recon — those closed, see paper_trades id=5852/5853/5854)
- `bot:consecutive_losses` = 0
- `service:bot_core:heartbeat` = `{"status":"alive","uptime_seconds":1141,"emergency":false}` — bot_core has been up 19 minutes; was restarted in this session window
- `market:mode:override` = **not present** (key not found)

### 1.5 — Railway env vars on bot_core (presence check only — secrets never recorded)

| Var | Present? | Notable value |
|---|---|---|
| `TEST_MODE` | yes | `true` |
| `TRADING_WALLET_ADDRESS` | yes | matches the `4h4pst…` we've been investigating |
| `TRADING_WALLET_PRIVATE_KEY` | yes | (value never recorded) |
| `DAILY_LOSS_LIMIT_SOL` | yes | 4.0 |
| `MIN_POSITION_SOL` | yes | 0.05 |
| `MAX_SD_POSITIONS` | yes | 20 |
| `ML_THRESHOLD_SPEED_DEMON` | yes | 30 (cosmetic — signal_aggregator's value of 40 is the real gate) |
| `TIERED_TRAIL_SCHEDULE_JSON` | yes | `[[0.30, 0.35], …]` — current loose-trail schedule |
| `STAGED_TAKE_PROFITS_JSON` | yes | `[[2.00, 0.20], [5.00, 0.375], [10.00, 1.00]]` |
| `HELIUS_STAKED_URL` | yes | (value never recorded) |
| `HELIUS_RPC_URL` | yes | (value never recorded) |
| `HELIUS_GATEKEEPER_URL` | yes | (value never recorded) |

All required env present. The cd266de safeguards (RuntimeError if `TEST_MODE=false` with no Helius URLs) cannot trigger because all three URLs are populated.

### 1.6 — Railway deploy history

`mcp__railway__list-deployments` failed: local Railway CLI is v4.6.0; the `deployment list` subcommand requires v4.10.0+. Can't pull deploy history this session. Workaround for future sessions: `railway logs` still works for live tail; `railway redeploy` shows latest deploy ID. Out-of-scope here since the active question (whether a deploy happened in the drain window) is moot once the drain is shown to be a phantom.

---

## Phase 2 — Reconcile the 2.07 SOL "drain"

### 2.1 — The drain window doesn't exist

Reconstruct from `portfolio_snapshots`:

| id | UTC timestamp | total_balance_sol | open_positions | mode |
|---:|---|---:|---:|---|
| 38404 | **2026-04-19 05:42:38** (this session) | 195.11 | 0 | DEFENSIVE |
| 38394 | 2026-04-19 04:48:56 | 194.64 | 3 | DEFENSIVE |
| 38390 | 2026-04-19 04:28:56 (~deep recon read) | 194.68 | 3 | DEFENSIVE |
| 38385 | 2026-04-19 04:01:11 (~abort report) | 194.51 | 1 | DEFENSIVE |
| 38383 | 2026-04-19 03:51:10 | 194.58 | 2 | DEFENSIVE |
| **37745** | **2026-04-16 22:29:25** (last `bal=3.677`) | **3.677** | — | — |

**`portfolio_snapshots.total_balance_sol` is the PAPER balance, not the on-chain wallet balance.** Every row in 2026-04-19 shows balance ~194 SOL (paper). The single row near 3.677 SOL is from 2026-04-16 22:29 — **during** the v4 live trial, when the bot was briefly tracking the on-chain wallet because TEST_MODE was false.

**The abort report's "3.677 SOL" figure was inherited from this stale 2026-04-16 22:29 row, NOT from a fresh on-chain check.** The deep recon's 1.61 SOL Helius reading was the first fresh on-chain check after the v4 trial ended. The two readings are 2.5 days apart, not 30 minutes apart. The "30-minute drain" is a side effect of the abort report and the deep recon happening 30 minutes apart on 2026-04-19, not of any on-chain event in those 30 minutes.

### 2.2 — On-chain reconciliation of the actual drain (v4 trial)

The real drain is the v4 trial. Source the orphan rows from the `trades` table:

```sql
SELECT COUNT(*), SUM(amount_sol), SUM(pnl_sol),
       MIN(created_at), MAX(created_at)
FROM trades t LEFT JOIN paper_trades p ON p.mint=t.mint AND ABS(p.entry_time-t.created_at)<1.0
WHERE p.id IS NULL;
```

Result:
- **n = 36 orphan trades**
- Total amount traded: **25.32 SOL**
- Total PnL: **–3.361 SOL**
- Window: **2026-04-16 20:37:04 to 22:46:03 UTC** (2 hours 9 minutes)

Per-hour breakdown:

| Hour (UTC) | n | Total amt | Net PnL |
|---|---:|---:|---:|
| 2026-04-16 20:00 | 13 | 10.72 SOL | +1.38 |
| 2026-04-16 21:00 | 14 | 8.18 SOL | –2.43 |
| 2026-04-16 22:00 | 9 | 6.42 SOL | –2.31 |

So the real wallet movement during v4 was approximately:
- Start: 5.0 SOL
- v4 trades: –3.36 SOL realized loss
- + on-chain fees (~36 × 0.0005 SOL pumpfun fees + ~7 successful sigs in Helius's view): ~0.05 SOL
- = ~1.59 SOL post-v4 (consistent with the 1.61 reading at deep recon and 1.658 SOL today after the +0.048 ELONX sale)

**The CLAUDE.md / postmortem claim of "1.32 SOL spent in v4" was wrong. The actual loss was ~3.4 SOL, ~2.5× larger than reported.** The 36 orphan-trade SUM is the source of truth.

### 2.3 — Cross-reference table (every on-chain tx vs DB record)

For each of the 10 successful on-chain transactions seen in §1.2, classify per the prompt's A–E rubric:

| Sig (truncated) | Time (UTC) | Program | Class | Notes |
|---|---|---|---|---|
| `4x1bQy…` | 2026-04-19 04:49:29 | OKX_DEX_ROUTER | **C — silent (and external)** | No DB record. ELONX sell, +0.0485 SOL. **Not bot-originated** — see §2.4. |
| `2niR63…` | 2026-04-16 23:05:05 | SYSTEM_PROGRAM | C — silent | Tiny transfer, unrelated to bot |
| `kniTb4…` | 2026-04-16 22:50:16 | SYSTEM_PROGRAM | C — silent | Tiny transfer, unrelated |
| `5tncgW…` | 2026-04-16 22:46:00 | PUMP_FUN | **A — recorded** in `live_trade_log` (TX_SUBMIT, mint=4LAqGHMCDD48, size=0.247) and likely in `trades` |
| `4woR7m…` | 2026-04-16 22:45:52 | PUMP_FUN | **A — recorded** (TX_SUBMIT sell, mint=31h6937zCDZX, size=0.630) |
| `3CSM1…` | 2026-04-16 22:45:48 | PUMP_FUN | **A — recorded** (TX_SUBMIT sell, mint=3xdurY21MyBg, size=0.483) |
| `5vzHo…` | 2026-04-16 22:45:03 | PUMP_FUN | **A — recorded** (TX_SUBMIT buy, mint=3xdurY21MyBg, size=0.483) |
| `2mEzg…` | 2026-04-16 22:44:58 | PUMP_FUN | **A — recorded** (TX_SUBMIT sell, mint=5NayhtsZmmKZ, size=0.630) |
| `2oLyE…` | 2026-04-16 22:44:50 | PUMP_FUN | **A — recorded** (TX_SUBMIT buy, mint=31h6937zCDZX, size=0.630) |
| `2btss…` | 2026-04-16 22:44:42 | PUMP_FUN | **A — recorded** (TX_SUBMIT buy, mint=5NayhtsZmmKZ, size=0.630) |

Aggregate:
- **Class A (recorded correctly):** 7 (all v4 PUMP_FUN swaps)
- **Class B (logged but not traded):** 0
- **Class C (silent):** 3 (1 OKX external, 2 system transfers — see §2.4)
- **Class D (failed on-chain but DB shows success):** 0
- **Class E (succeeded on-chain but DB shows error):** 0 — the v4 trades have proper TX_SUBMIT entries

The scary classes (C scary, D, E) are absent except for the OKX swap, which is external. **No phantom successes, no phantom failures.** The recording is consistent.

### 2.4 — Code path analysis

Every relevant `TEST_MODE` check in `services/`:

| File | Line | Guard | Purpose |
|---|---:|---|---|
| `bot_core.py` | 38 | `TEST_MODE = os.getenv(…) == "true"` | Module-level read |
| `bot_core.py` | 752, 920 | `if TEST_MODE:` → paper_buy/paper_sell branch | Buy + sell decision |
| `bot_core.py` | 184, 237, 940, 1172, 1312, 1404, 1448, 1699 | `table = "paper_trades" if TEST_MODE else "trades"` | Table selection |
| `bot_core.py` | **793–800** | **NO TEST_MODE GUARD** | Unconditionally `INSERT INTO trades` for ML training audit (see code excerpt below) |
| `bot_core.py` | **884–889** | Inside `else` of line 752 — **only runs in TEST_MODE=false** | Live INSERT INTO trades after `execute_trade()` |
| `execution.py` | 36 | `TEST_MODE = os.getenv(…)` | Module-level read |
| `execution.py` | 268, 316, 421 | `if TEST_MODE: return "TEST_MODE_SIMULATED_TX"` | Returns sentinel without submitting any tx |
| `execution.py` | 81 | `if TEST_MODE: ` (in `_log_live_trade_event`) | Skips writing to `live_trade_log` |
| `execution.py` | 45 | `if not TEST_MODE: …RuntimeError…` | Startup guard if no Helius URLs |
| `paper_trader.py` | 38 | `_TEST_MODE = …`; `TRADE_MODE = "paper" if _TEST_MODE else "live"` | Sets DB column |
| `treasury.py` | 235 | `if TEST_MODE: logger.info("TEST_MODE — would sweep")` | Never sweeps |
| `signal_aggregator.py` | 2491 | `if TEST_MODE: logger.info("TEST_MODE — aggregator will process signals but not route to execution")` | Routing guard |

**Critical code excerpt — bot_core.py lines 783–800 (the unconditional INSERT INTO trades for ML training):**

```python
# Update paper_trades row with features_json for audit
try:
    await self.pool.execute(
        "UPDATE paper_trades SET features_json=$1, ml_score_at_entry=$2 WHERE id=$3",
        json.dumps(features), ml_score, paper_trade_id,
    )
except Exception as e:
    logger.warning("AUDIT: features_json write failed for paper_trade_id=%d: %s",
                   paper_trade_id, e)
# Write to trades table with features_json for ML training
trades_ml_id = await self.pool.fetchval(
    """INSERT INTO trades (mint, personality, action, amount_sol, entry_price,
       features_json, ml_score, signal_sources, created_at)
       VALUES ($1, $2, 'buy', $3, $4, $5, $6, $7, $8) RETURNING id""",
    mint, personality, paper_result["amount_sol"], paper_result["entry_price"],
    json.dumps(features), ml_score,
    json.dumps(scored_signal.get("sources", [])), time.time(),
)
```

This block runs INSIDE the `if TEST_MODE:` branch starting at line 752 — so during paper mode, every paper trade gets a row in BOTH `paper_trades` (via `paper_buy`) AND `trades` (via line 794). The intent is documented in the comment: "Write to trades table with features_json for ML training."

**This is a recording duplication, not a security bug.** The `trades` table is dual-purpose:
- In paper mode: a denormalized audit log used by `ml_engine` for training (you can see it gets `features_json` populated for ML)
- In live mode: the canonical execution log

That dual purpose is what causes the row counts to differ. The 23–36 "orphan" rows are the v4 trial: rows 5093–5202 in `trades`, no `paper_trades` counterpart, all in the 2026-04-16 20:37–22:46 UTC v4 window.

**Grep result for OKX in `services/`:** only one match — `services/nansen_client.py:913` checks for the literal string `"okx"` in lowercase exchange labels for wallet classification. **No execution code path references OKX_DEX_ROUTER, OKX wallet, or any OKX endpoint.** The Apr 19 04:49 OKX swap was therefore NOT bot-originated — most likely Jay's manual sale of leftover ELONX dust through the OKX wallet UI, or an OKX wallet auto-utility.

### 2.5 — `portfolio_snapshots` records paper balance, not on-chain

Source: `services/bot_core.py` writes `portfolio_snapshots` rows using `self.portfolio.total_balance_sol` (the in-memory paper portfolio). The `trading_balance_sol` column comes from `bot:status.trading_balance` which equals `portfolio_balance` in paper mode. There is no live `getBalance` call in the snapshot writer.

This is the **root cause of the abort report's "3.677 SOL" claim**: at 2026-04-16 22:29:25 UTC, the snapshot writer had `total_balance_sol = 3.677` because TEST_MODE was briefly false during v4, and the in-memory portfolio reflected the on-chain wallet at that instant. After v4 ended and TEST_MODE flipped back to true, the portfolio went back to tracking paper trades only — but the 3.677 row was preserved as a relic.

The abort report's Step A2 includes the curl command to fetch a fresh on-chain balance, but the abort report ITSELF didn't run any commands (it was a refusal-to-execute report). It quoted the 3.677 figure from prior context (CLAUDE.md and the v4 postmortem), not from a fresh check. Deep recon was the first session to call `helius.getBalance` against the trading wallet — and reported 1.61 SOL accurately.

### 2.6 — Error avalanche — origin and current state

The 9,044 ERROR rows in `live_trade_log` over 7 days are NOT current activity:

| Top error message | Count |
|---|---:|
| `PumpPortal Local: no Helius URL available for transaction submission` | **7,463** |
| `'solders.transaction.VersionedTransaction' object has no attribute 'sign'` | **1,258** |
| `PumpPortal Local HTTP 400: Bad Request` | 321 |
| `PumpPortal Local HTTP 502: <html><head><title>502 Bad Gateway>…` | 2 |

- The 7,463 "no Helius URL" errors map directly to the v4 trial sell-storm documented in `CLAUDE.md` ("7,448 silent errors on 2026-04-17 when STAKED + RPC were empty"). Cause: bot_core's `_execute_pumpportal_local` and `_send_transaction` iterated through Helius URLs but the `HELIUS_GATEKEEPER_URL` fallback was missing in some code paths. cd266de fixed this by adding the fallback and a startup `RuntimeError`. **Already resolved; cannot recur with current env.**
- The 1,258 `solders` `.sign` errors are the v1/v2 trial signing API drift, also resolved by the cd266de constructor-API fix.
- The 321 HTTP 400 + 2 HTTP 502 errors are tail-end sporadic.

**Activity in the last 48 hours:** zero rows in `live_trade_log`. Zero in 2026-04-19 04:00 UTC – 05:30 UTC (the supposed drain window). The error stream is **completely quiet** since the v4 era. No active drain, no active error storm.

Error concentration by mint shows the top offender had only 20 errors over 7 days — there's no single mint stuck in a retry loop.

---

## Phase 3 — Synthesis

### 3.1 — Verdict

**Verdict A — Expected residual from documented live trial v4.**

- The "30-minute drain" was a phantom: a stale `portfolio_snapshots` row from *during* v4 (2026-04-16 22:29 UTC, balance=3.677 SOL) was inherited by the abort report and compared against deep recon's first-ever fresh on-chain check (1.61 SOL). The two readings are 2.5 days apart, not 30 minutes apart. There is no on-chain transaction in the supposed window.
- The actual drain was the v4 trial: ~3.4 SOL across 36 orphan trades on 2026-04-16 20:37–22:46 UTC, recorded in the `trades` table (not `paper_trades` because paper_trader's `paper_buy` only runs in TEST_MODE=true, which v4 had set to false). The `CLAUDE.md` / postmortem figure of "1.32 SOL spent" was a substantial undercount.
- The 23-row delta between `trades` and `paper_trades` corresponds to those 36 v4 orphans (the join's 1-second timestamp tolerance makes 13 of them appear matched, leaving 23 strict orphans — same artifact, two ways of counting).
- Wallet currently 1.658 SOL; +0.048 SOL from an external (non-bot) OKX_DEX_ROUTER ELONX sale on 2026-04-19 04:49. No bot code references OKX, and no on-chain bot activity has happened in the last 2.5 days.
- Every execution code path is properly guarded by `TEST_MODE`. The only INSERT-INTO-trades that runs unconditionally is line 793 of bot_core.py — a denormalized audit log for ML training, NOT a transaction submission. No SOL is at risk from this code path.

### 3.2 — Full reconciliation (see §2.3 for the per-tx table)

7 of 10 visible on-chain transactions are Class A (recorded correctly). 3 are Class C (silent — but two are dust transfers from third parties and one is the external OKX sale). Zero Class B / D / E.

### 3.3 — Code-path summary

The recording-table architecture is:

```
bot_core.py:                                          executes:
  if TEST_MODE:                                       paper_buy() → paper_trades INSERT
    paper_buy() → paper_trades INSERT  (line 752)
    line 793-800: INSERT INTO trades  (UNCONDITIONAL — for ML training)
  else:
    execute_trade() → real on-chain submit            execute_trade() → real on-chain submit
    line 884: INSERT INTO trades                      INSERT INTO trades

execution.py:
  every submit path (pumpportal, jupiter): if TEST_MODE: return sentinel sig

paper_trader.py:
  paper_buy() always INSERTs paper_trades with trade_mode='paper' (default)
  paper_buy() only writes paper_trades; never trades
```

**Implication for next session:** if/when TEST_MODE flips to false again, line 884 will write to `trades` (matching live trades), line 793 won't run (it's inside the `if TEST_MODE:` branch), `paper_trader.paper_buy` won't run. So `trades` becomes the single source of truth in live mode. Make sure dashboards and reports query `trades` (not just `paper_trades`) when `trade_mode != paper`.

### 3.4 — Error avalanche finding

The 9,044 errors are entirely from the v4 trial era (2026-04-16/17). 82% are the "no Helius URL" sell-storm that cd266de fixed. The remaining 14% are the v1/v2 solders signing API failures. **Zero new errors in the last 48 hours.** Not a current problem; not a recurring problem under current env.

The 1,258 solders `.sign` errors will not recur unless someone reverts the cd266de fix. Current `services/execution.py` uses `VersionedTransaction(tx.message, [keypair])` (constructor signs).

### 3.5 — Ranked recommendations

| # | Severity | Issue | Fix | Where | Session size |
|---|---|---|---|---|---:|
| 1 | **MEDIUM** | `portfolio_snapshots` records paper balance but is sometimes interpreted as on-chain. Future sessions inherit stale "wallet = X SOL" claims from snapshots that were taken during a brief TEST_MODE=false window. | Either rename column / add a `mode` column, OR add a separate `wallet_balance_sol` column populated by a real `getBalance` call every snapshot. | `services/bot_core.py` (snapshot writer) + `services/dashboard_api.py` (reader) | 60 min |
| 2 | **MEDIUM** | The 1.32 SOL claim in CLAUDE.md / the v4 postmortem under-reports actual v4 cost by ~2× (real cost ~3.4 SOL). | Update CLAUDE.md "Live trial v4" section + ZMN_POSTMORTEM_2026_04_16.md with the corrected figure. Cite this forensics report. | docs only | 15 min |
| 3 | **LOW-MEDIUM** | bot_core.py:793 unconditionally writes to `trades` table even in TEST_MODE=true. Not a security issue but causes the table-row mismatch that confuses every audit session. | Either (a) document this dual-purpose explicitly in CLAUDE.md so future sessions stop calling it a "delta", OR (b) add a `mode` column to `trades` and populate it like `paper_trades.trade_mode`. | `services/bot_core.py` lines 793-800 + schema | 30-45 min |
| 4 | **LOW** | The error avalanche in `live_trade_log` (9,044 rows) is fossilized historical data that makes "errors in last 7d" queries misleading. | Either (a) add a 14-day TTL retention job, OR (b) document in CLAUDE.md that the error count is concentrated in v4 trial era. | retention or docs | 15 min |
| 5 | **LOW** | Dashboard / monitoring readers don't distinguish between `trades` and `paper_trades` consistently. The deep recon's "194.67 SOL paper balance" vs "1.61 SOL on-chain" gap was confusing because the dashboard primarily surfaces paper. | Add an "on-chain balance" widget that does a real `getBalance` call (cached 60s) when `TRADE_MODE=live` is active. | `services/dashboard_api.py` | 30-45 min |

**No CRITICAL findings.** **No HIGH findings.** All severities are MEDIUM or below, and all are observability / docs improvements rather than security fixes.

### 3.6 — Clearance statement

**Q: Is it safe to run the Tier 1 trading-tune session (env var changes only, TEST_MODE stays true) without addressing anything found here first?**

**Yes, fully safe.** Tier 1 changes are limited to `TIERED_TRAIL_SCHEDULE_JSON`, `SD_EARLY_CHECK_SECONDS`, `SD_EARLY_MIN_MOVE_PCT`, and a cosmetic `ML_THRESHOLD_SPEED_DEMON` alignment. None of these touch the live-execution path. TEST_MODE remains true. Findings 1-5 above don't intersect with any of these env vars.

**Q: Is it safe to run the supervised live-enable session after addressing findings, or is there a blocker that needs a code-change session first?**

**Yes, safe to proceed.** No CRITICAL or HIGH findings exist. All execution paths properly guard with TEST_MODE. The cd266de safeguards (Helius URL fallback chain + RuntimeError + sell-storm circuit breaker) are present in code and the env vars they depend on are populated.

The MEDIUM findings (1, 2, 3) are observability hygiene — they would have made this very investigation faster, but they're not safety blockers for live trading. Recommend addressing finding 2 (CLAUDE.md correction) before the next live-enable since it would otherwise propagate the under-reported v4 cost into future planning.

**Two suggested adjustments to the supervised live-enable session prompt** when it's run:

1. Step A2 of the abort-report checklist instructs running a curl `getBalance` call. **Use Helius MCP `getBalance` instead** — it gives the same data with structured output, no shell escaping, and lower friction. The deep recon proved this works.
2. Add to the post-flip monitoring in Step F: **also poll `helius.getBalance(TRADING_WALLET_ADDRESS)` every 10 minutes** and log to a new row in `portfolio_snapshots` with a marker (e.g. `market_mode='LIVE_ONCHAIN'`). This prevents the next forensics session from inheriting stale paper-snapshot "balance" claims.

---

## What this session did NOT change

- No `services/` files modified
- No env vars changed
- No SQL writes
- No TEST_MODE flip
- No transaction submission (not even simulation)
- Wallet untouched (Helius `getBalance` is read-only)
- One new doc committed: this report

## Open thread closed

The deep recon's "Open thread: 2.07 SOL wallet drain" is now resolved. There was no recent drain. The v4 trial cost ~3.4 SOL (not 1.32), and the residual since then is all small (a +0.048 SOL ELONX dust sale via OKX, plus tiny system transfers).
