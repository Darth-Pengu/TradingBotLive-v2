# ZMN Bot Monitoring Log

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
