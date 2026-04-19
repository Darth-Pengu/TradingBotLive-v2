# ZMN live-enablement handoff — Jay review required before any state change

**Date:** 2026-04-19
**Author:** Claude (Opus 4.7, autonomous session prompt received while Jay was commuting)
**Status:** ❌ NOT EXECUTED. Read this before taking any action.

---

## Why this is a handoff, not an execution log

The session prompt asked me to run fully autonomously and flip `TEST_MODE=false`
on the main wallet (~3.677 SOL, ~$680) while unreachable. Two durable
repo rules block this:

**CLAUDE.md (Operating Principles for Claude Code Sessions):**
> **Paper mode is non-negotiable.** TEST_MODE=true stays true.

**ZMN_ROADMAP.md #9.5–#9.8:**
> Do not skip stages. No "just flip TEST_MODE=false" on the main wallet.
> Prescribed chain: audit → shadow → micro-live (secondary wallet, 0.5 SOL,
> 0.01/trade, 50-trade cap) → main wallet.

The session prompt bundles #9.5, #9.6, #9.7 skip, the live flip, 6 env var
changes, an SQL INSERT into production `portfolio_snapshots`, a Redis mode
override renewal, and code changes into one unreviewed autonomous run —
against both rules, while Jay is unreachable.

The system-prompt rule is explicit: *"A user approving an action once does
NOT mean they approve it in all contexts, so unless actions are authorized
in advance in durable instructions like CLAUDE.md files, always confirm
first."* The durable instruction says the opposite. Also: previous live
trial v4 had an unresolved reconcile-on-mode-flip residual (CLAUDE.md calls
it out as "discipline to codify"), and the "one lever per session"
principle is violated by this bundle.

**Nothing has been executed.** No env vars changed. No SQL run. No Redis
mutation. No code committed. No push. The TEST_MODE flag is still `true`.

---

## What I DID do (all safe, all reversible)

1. **Verified Jay's code claims against the actual codebase** — line
   numbers, default values, schema semantics.
2. **Loaded context** — CLAUDE.md, the current session's tooling
   inventory, ZMN_ROADMAP.md staged chain.
3. **Wrote this handoff report.**

---

## Code verification — Jay's claims vs the actual code

| Claim | Code location | Verdict |
|---|---|---|
| Drawdown guard at `risk_manager.py:305-308`, `DRAWDOWN_MULTIPLIERS` at line 64 | Actually line 59 for `DRAWDOWN_MULTIPLIERS`, line 147 uses it; `check_emergency_conditions` logic still present | Roughly correct, off by ~5 lines |
| `bot_core.py:194-211` reads peak, peak resets on restart | Actual function `_load_state` at line 198-227; TEST_MODE branch at 212-214, else branch at 215-219; `logger.info("Loaded portfolio state: ...")` at line 220 | Correct function, line numbers off by ~5 |
| `MIN_POSITION_SOL` default is 0.10 at `risk_manager.py:50` | Confirmed exactly: `MIN_POSITION_SOL = float(os.getenv("MIN_POSITION_SOL", "0.10"))` | ✅ |
| HIBERNATE gate at `bot_core.py:585` | Actually at line 593, checks both HIBERNATE AND PAUSE | Off by 8 lines, logic correct |
| `ML_THRESHOLD_SPEED_DEMON` default 65 at `signal_aggregator.py:133` | Confirmed exactly: `"speed_demon": int(os.getenv("ML_THRESHOLD_SPEED_DEMON", "65"))` | ✅ |
| `_DEFAULT_TRAIL_SCHEDULE[0] = [0.30, 0.0]` at line 82 | Confirmed exactly: `[0.30, 0.0],    # +30-50%: breakeven lock` | ✅ |
| `_DEFAULT_STAGED_TPS` at line 72 | Confirmed: `[[0.50, 0.25], [1.00, 0.25], [2.00, 0.25], [4.00, 0.25]]` — NOT the 30/30/20/10/10 claim; that's the current live env var override, not the default | ✅ (default is 25/25/25/25 at +50/100/200/400%) |

**Schema question (briefing 1.5) resolved:** the second number per
`STAGED_TAKE_PROFITS_JSON` tuple is **percent of remaining position**,
not percent of original.

Evidence chain:
- `bot_core.py:109` maps `[g, s]` to `{"at_gain": g, "sell_pct": s}`
- `bot_core.py:1381` passes `sell_pct=exit_rule["sell_pct"]` into `_close_position`
- `bot_core.py:907`: `sell_amount = pos.size_sol * pos.remaining_pct * sell_pct`
- `bot_core.py:931`: `pos.remaining_pct *= (1 - sell_pct)` (multiplicative decay)

So `sell_pct` is a fraction of what's currently remaining. **Schema A is the correct encoding** of the briefing's intent.

To bank 20/30/50 of ORIGINAL at +200/500/1000% (matches the commit message's
"20% banked at +200%, 30% at +500% of remaining, close at +1000%, 80% rides trailing"):
- At +200%: sell 20% of remaining 100% = 20% original ✅
- At +500%: sell 37.5% of remaining 80% = 30% original ✅
- At +1000%: sell 100% of remaining 50% = 50% original ✅ (close)

Confirms: `STAGED_TAKE_PROFITS_JSON=[[2.00, 0.20], [5.00, 0.375], [10.00, 1.00]]`

---

## What Jay needs to do to proceed — ready-to-paste, in order

**Do NOT run this unless you've decided to supersede the CLAUDE.md
"Paper mode is non-negotiable" rule this session. If you do decide, update
CLAUDE.md FIRST (see end of this document for the rule update) before
running steps below — so the durable rule matches your intent when the
next CC session reads it.**

### Step A — Pre-flight (read-only, run on laptop)

Paste each, confirm output before proceeding.

```bash
# A1 — current env state, all three services
echo "=== bot_core ==="
railway variables -s bot_core --kv | grep -Ei '^(TEST_MODE|MIN_POSITION_SOL|POSITION_SIZE_SOL|MAX_SD_POSITIONS|DAILY_LOSS_LIMIT_SOL|ANALYST_DISABLED|AGGRESSIVE_PAPER_TRADING|TIERED_TRAIL_SCHEDULE_JSON|STAGED_TAKE_PROFITS_JSON|HELIUS_STAKED_URL|HELIUS_RPC_URL|HELIUS_GATEKEEPER_URL|TRADING_WALLET_ADDRESS)='

echo "=== signal_aggregator ==="
railway variables -s signal_aggregator --kv | grep -Ei '^(ML_THRESHOLD_|TEST_MODE)='

echo "=== market_health ==="
railway variables -s market_health --kv | grep -Ei '^(TEST_MODE|CFGI)'
```

**Save the output.** These are your rollback baselines.

```bash
# A2 — on-chain wallet balance via Helius
# Replace <WALLET_ADDRESS> and <HELIUS_RPC_URL> from A1 output, or use env var expansion:
RPC=$(railway variables -s bot_core --kv | grep '^HELIUS_RPC_URL=' | cut -d= -f2-)
WALLET=$(railway variables -s bot_core --kv | grep '^TRADING_WALLET_ADDRESS=' | cut -d= -f2-)
curl -s "$RPC" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getBalance","params":["'"$WALLET"'"]}' \
  | python -c "import sys, json; r=json.load(sys.stdin); print(f'On-chain: {r[\"result\"][\"value\"]/1e9:.4f} SOL')"
```

**Expected: ≥ 3.0 SOL. If < 3.0, STOP — something is bleeding.**

```bash
# A3 — portfolio_snapshots state
# Uses DATABASE_PUBLIC_URL from Railway — needs psql installed locally
psql "$(railway variables -s Postgres --kv | grep DATABASE_PUBLIC_URL | cut -d= -f2-)" -c "
SELECT id,
       to_timestamp(EXTRACT(EPOCH FROM timestamp)) AT TIME ZONE 'Australia/Sydney' AS t,
       total_balance_sol, open_positions, daily_pnl_sol, market_mode
FROM portfolio_snapshots
ORDER BY id DESC LIMIT 5;

SELECT MAX(total_balance_sol) AS historic_peak FROM portfolio_snapshots;"
```

```bash
# A4 — Redis mode override state
# You can either use redis-cli with REDIS_PUBLIC_URL or the Railway Redis MCP in a CC session
REDIS_URL=$(railway variables -s Redis --kv | grep REDIS_PUBLIC_URL | cut -d= -f2-)
redis-cli -u "$REDIS_URL" GET market:mode:override
redis-cli -u "$REDIS_URL" TTL market:mode:override
redis-cli -u "$REDIS_URL" GET market:mode:current
```

```bash
# A5 — sell-storm check (last 15 min)
psql "$(railway variables -s Postgres --kv | grep DATABASE_PUBLIC_URL | cut -d= -f2-)" -c "
SELECT event_type, COUNT(*)
FROM live_trade_log
WHERE ts_ms > (EXTRACT(EPOCH FROM NOW() - INTERVAL '15 minutes') * 1000)::bigint
GROUP BY 1;

SELECT mint, COUNT(*) AS n
FROM live_trade_log
WHERE event_type = 'ERROR' AND action = 'sell'
  AND ts_ms > (EXTRACT(EPOCH FROM NOW() - INTERVAL '15 minutes') * 1000)::bigint
GROUP BY mint HAVING COUNT(*) > 5;"
```

**Expected: empty or small. Any mint with > 5 errors in 15 min = sell-storm,
STOP.**

```bash
# A6 — confirm breakeven-stop 7d pattern (Jay's finding 2)
psql "$(railway variables -s Postgres --kv | grep DATABASE_PUBLIC_URL | cut -d= -f2-)" -c "
SELECT exit_reason, COUNT(*) AS n,
       ROUND(AVG(COALESCE(corrected_pnl_pct, realised_pnl_pct))::numeric, 2) AS avg_pct,
       ROUND(SUM(COALESCE(corrected_pnl_sol, realised_pnl_sol))::numeric, 2) AS total_pnl,
       ROUND(AVG(((peak_price - entry_price) / NULLIF(entry_price, 0)) * 100)::numeric, 1) AS avg_peak_pct
FROM paper_trades
WHERE personality = 'speed_demon'
  AND exit_time > NOW() - INTERVAL '7 days'
  AND exit_reason IN ('BREAKEVEN_STOP','TRAILING_STOP','no_momentum_90s','stop_loss_35%')
GROUP BY 1 ORDER BY n DESC;"
```

**Expected: BREAKEVEN_STOP ~130-140 rows, avg_peak_pct 35-45%, avg_pct -10 to -12%.**

---

### Step B — Code + doc edits (apply locally, review `git diff`, do NOT push yet)

**B1 — edit `services/bot_core.py`**

Around lines 81-87 (currently):
```python
_DEFAULT_TRAIL_SCHEDULE = [
    [0.30, 0.0],    # +30-50%: breakeven lock
    [0.50, 0.25],   # +50-100%: 25% trail from peak
    [1.00, 0.20],   # +100-200%: 20% trail
    [2.00, 0.15],   # +200-500%: 15% trail
    [5.00, 0.12],   # +500%+: 12% trail (moonshot)
]
```

Change to:
```python
# 2026-04-19: first tier changed from breakeven lock [0.30, 0.0] to loose trail
# [0.30, 0.35]. 7d SD data showed BREAKEVEN_STOP fired 137x for -8.22 SOL
# (all peak +30-50%, all realized ~-11% due to fees+slippage). Loose trail
# exits cleanly when peak holds, captures gain if peak extends. Live value
# overridden via TIERED_TRAIL_SCHEDULE_JSON env var.
_DEFAULT_TRAIL_SCHEDULE = [
    [0.30, 0.35],   # +30-50%: loose trail (was breakeven lock — caused 137 -11% exits in 7d)
    [0.50, 0.25],   # +50-100%: 25% trail from peak
    [1.00, 0.20],   # +100-200%: 20% trail
    [2.00, 0.15],   # +200-500%: 15% trail
    [5.00, 0.12],   # +500%+: 12% trail (moonshot)
]
```

Around line 220 (after `logger.info("Loaded portfolio state: ...")`), add a
new block:

```python
                # Startup drawdown telemetry — turns silent "blocked bot" into observable
                dd_pct = 0.0
                if self.portfolio.peak_balance_sol > 0:
                    dd_pct = (self.portfolio.peak_balance_sol - self.portfolio.total_balance_sol) / self.portfolio.peak_balance_sol
                logger.info(
                    "Startup drawdown state: peak=%.4f balance=%.4f dd=%.1f%% (guard fires at 20%%)",
                    self.portfolio.peak_balance_sol, self.portfolio.total_balance_sol, dd_pct * 100,
                )
```

Then compile check:
```bash
python -m py_compile services/bot_core.py && echo OK_bot_core
```

**B2 — update `CLAUDE.md`** — append to the "Lessons Learned" area or wherever ML context lives:

```markdown
### ML threshold — corrected 2026-04-19

**Old (now incorrect) claim:** "ML model inverts above 40; working range is 35–40 only."

**Corrected:** As of the feature-default fix (commit a8a390b, ~2026-04-12), the ML model no longer inverts. Data from last 7 days (1,698 SD trades):

| ML band | n | WR | PnL |
|---|---:|---:|---:|
| 35–40 | 21 | 4.76% | –1.16 SOL (the only loss band above 0–35) |
| 40–50 | 496 | 39.1% | +88.9 SOL |
| 50–60 | 432 | 43.8% | +64.5 SOL |
| 60–70 | 333 | 50.5% | +67.7 SOL |
| 80+   | 172 | 52.9% | +57.5 SOL |

**Current policy:** `ML_THRESHOLD_SPEED_DEMON=40`, no upper bound. Higher
scores win more often.

### Drawdown guard — session-scoped (2026-04-19)

`bot_core._load_state` initializes `peak_balance_sol=0.0` on every process
start, then does `max(0.0, current_balance)`. The 20% drawdown guard in
`risk_manager.check_emergency_conditions` therefore operates on a
*per-process* drawdown, not a *cumulative* one. A wallet can lose 26%
overnight, the bot restarts, and the guard resets.

Proper fix: track peak in a dedicated Redis key independent of
`portfolio_snapshots`. Queued — not urgent unless live trading extends
beyond 7 days without restart.
```

**B3 — IF you're superseding the "paper mode non-negotiable" rule this
session, also edit the Operating Principles in CLAUDE.md:**

Change:
```markdown
- **Paper mode is non-negotiable.** TEST_MODE=true stays true.
```

To:
```markdown
- **Paper mode is the default; live mode is deliberate.** Flipping
  `TEST_MODE=false` requires: (1) wallet balance ≥ 3.0 SOL, (2) no active
  sell-storm, (3) fresh portfolio_snapshots row inserted at on-chain
  balance to reset drawdown baseline, (4) `market:mode:override=NORMAL`
  set fresh with 24h TTL. See docs/audits/ZMN_LIVE_ENABLE_HANDOFF_2026_04_19.md
  for the commissioning checklist.
```

**Without B3, the next CC session reading CLAUDE.md will refuse live mode
again, consistent with this session's refusal.** That's either desired
(live mode should always be session-by-session opt-in) or undesired
(you've decided live is the new normal).

---

### Step C — Portfolio baseline reset (run ONE SQL statement)

**Only after Steps A and B pass.** Replace `<ON_CHAIN_BALANCE>` with the
exact value from A2:

```bash
ON_CHAIN=$(curl -s "$RPC" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getBalance","params":["'"$WALLET"'"]}' \
  | python -c "import sys, json; r=json.load(sys.stdin); print(f'{r[\"result\"][\"value\"]/1e9:.6f}')")
echo "Will insert: $ON_CHAIN SOL"

psql "$(railway variables -s Postgres --kv | grep DATABASE_PUBLIC_URL | cut -d= -f2-)" -c "
INSERT INTO portfolio_snapshots (timestamp, total_balance_sol, open_positions, daily_pnl_sol, market_mode)
VALUES (NOW(), ${ON_CHAIN}, 0, 0.0, 'NORMAL');
SELECT id, total_balance_sol FROM portfolio_snapshots ORDER BY id DESC LIMIT 1;"
```

### Step D — Redis mode override

```bash
REDIS_URL=$(railway variables -s Redis --kv | grep REDIS_PUBLIC_URL | cut -d= -f2-)
redis-cli -u "$REDIS_URL" SET market:mode:override NORMAL EX 86400
redis-cli -u "$REDIS_URL" TTL market:mode:override
redis-cli -u "$REDIS_URL" GET market:mode:override
```

**Note the exact UTC time this was set — it expires 24 hours later. Set a
calendar reminder to renew.**

### Step E — Env var batch (triggers ONE bot_core redeploy)

Only include vars that DIFFER from your Phase A1 baseline. If any are
already set to the target, omit them.

```bash
railway variables -s bot_core \
  --set TEST_MODE=false \
  --set MIN_POSITION_SOL=0.05 \
  --set POSITION_SIZE_SOL=0.05 \
  --set MAX_SD_POSITIONS=20 \
  --set DAILY_LOSS_LIMIT_SOL=4.0 \
  --set 'TIERED_TRAIL_SCHEDULE_JSON=[[0.30, 0.35], [0.75, 0.25], [2.00, 0.18], [5.00, 0.14], [10.00, 0.12]]' \
  --set 'STAGED_TAKE_PROFITS_JSON=[[2.00, 0.20], [5.00, 0.375], [10.00, 1.00]]'
```

Then signal_aggregator (triggers ONE signal_aggregator redeploy):

```bash
railway variables -s signal_aggregator --set ML_THRESHOLD_SPEED_DEMON=40
```

Verify:
```bash
railway variables -s bot_core --kv | grep -E '^(TEST_MODE|MIN_POSITION_SOL|TIERED_TRAIL|STAGED_TAKE)='
railway variables -s signal_aggregator --kv | grep '^ML_THRESHOLD_SPEED_DEMON='
```

### Step F — Wait for deploys + verify startup (~20 min)

Poll Railway MCP or dashboard. Wait for SUCCESS + 90 seconds for container
to settle.

Then verify bot_core logs contain:

- ✅ `execution.py: live mode OK, N Helius URL(s) configured`
- ✅ `Startup drawdown state: peak=<X> balance=<X> dd=<Y>%` with `dd < 5%`
- ✅ `Loaded portfolio state: <X> SOL` where X matches on-chain within 0.01 SOL
- ❌ NO `RuntimeError`, NO `EMERGENCY_STOP`, NO `JSONDecodeError`, NO `Drawdown >20%`

```bash
railway logs -s bot_core 2>&1 | tail -200 | grep -E "live mode OK|Startup drawdown state|Loaded portfolio state|RuntimeError|EMERGENCY_STOP|JSONDecodeError|Drawdown"
```

If any ❌ item appears, immediate rollback (Step H).

### Step G — Observation (30 min)

At +10 min and +30 min post-deploy:

```bash
psql "$(railway variables -s Postgres --kv | grep DATABASE_PUBLIC_URL | cut -d= -f2-)" -c "
-- New live entries since flip
SELECT COUNT(*) FROM paper_trades
WHERE trade_mode = 'live' AND entry_time > NOW() - INTERVAL '30 minutes';

-- ML score distribution on new entries — must be >= 40
SELECT MIN(ml_score_at_entry) AS min_ml, MAX(ml_score_at_entry) AS max_ml,
       AVG(ml_score_at_entry) AS avg_ml, COUNT(*)
FROM paper_trades
WHERE entry_time > NOW() - INTERVAL '30 minutes' AND personality = 'speed_demon';

-- Live trade log activity
SELECT event_type, action, COUNT(*)
FROM live_trade_log
WHERE ts_ms > (EXTRACT(EPOCH FROM NOW() - INTERVAL '30 minutes') * 1000)::bigint
GROUP BY 1, 2;

-- BREAKEVEN_STOP check — expected <= 1 (legacy in-flight positions only)
SELECT exit_reason, COUNT(*),
       ROUND(AVG(COALESCE(corrected_pnl_pct, realised_pnl_pct))::numeric, 2) AS avg_pct
FROM paper_trades
WHERE exit_time > NOW() - INTERVAL '30 minutes' AND personality = 'speed_demon'
GROUP BY 1 ORDER BY COUNT(*) DESC;

-- First live TX_SUBMIT after flip
SELECT to_timestamp(ts_ms/1000.0) AT TIME ZONE 'Australia/Sydney' AS t,
       action, substring(mint,1,12), size_sol, substring(signature,1,16)
FROM live_trade_log
WHERE event_type='TX_SUBMIT'
  AND ts_ms > (EXTRACT(EPOCH FROM NOW() - INTERVAL '30 minutes') * 1000)::bigint
ORDER BY ts_ms LIMIT 5;"
```

Pass criteria: `min_ml >= 40`, no JSONDecodeError, BREAKEVEN_STOP ≤ 1,
no sell-storm (any mint with > 8 errors = fail).

### Step H — Rollback (if ANYTHING fails in F or G)

```bash
# Immediate safety — always succeeds
railway variables -s bot_core --set TEST_MODE=true

# Restore old env values — use YOUR A1 baseline, not these placeholders
railway variables -s bot_core \
  --set 'TIERED_TRAIL_SCHEDULE_JSON=<YOUR_OLD_VALUE>' \
  --set 'STAGED_TAKE_PROFITS_JSON=<YOUR_OLD_VALUE>' \
  --set MIN_POSITION_SOL=<YOUR_OLD_VALUE>

railway variables -s signal_aggregator --set ML_THRESHOLD_SPEED_DEMON=<YOUR_OLD_VALUE>

# Revert local code if not committed
git checkout services/bot_core.py CLAUDE.md
```

### Step I — Commit + push (ONLY if F and G passed)

```bash
git add services/bot_core.py CLAUDE.md
git diff --cached --stat
git commit -m "feat(live+exits): enable live trading, raise ML threshold 35→40, replace breakeven lock with loose trail, flatten TP ladder

Data basis (last 7d speed_demon, n=1698):

ML threshold — 'inverts above 40' claim is stale (pre-a8a390b).
- ML 35-40: 21 trades, 4.76% WR, -1.16 SOL — only loss band
- ML 40-50: 496 trades, 39% WR, +89 SOL
- ML 80+:   172 trades, 53% WR, +57 SOL (best per-trade edge)
- Raise signal_aggregator ML_THRESHOLD_SPEED_DEMON: prior → 40

Breakeven lock removed.
- _DEFAULT_TRAIL_SCHEDULE[0] = [0.30, 0.0] fired BREAKEVEN_STOP 137x in 7d
- All peak +30-50%, all realized ~-11% (fees+slippage turn breakeven to loss)
- Total cost: -8.22 SOL realized. Counterfactual with loose trail: +14 SOL.
- Changed default to [0.30, 0.35]. Live value via TIERED_TRAIL_SCHEDULE_JSON.

TP ladder flattened.
- New schema-A value: [[2.00, 0.20], [5.00, 0.375], [10.00, 1.00]]
- At +200%: bank 20% of original; at +500%: bank 30% more; at +1000%: close remaining
- 80% of position rides pure trailing. Schema is pct-of-remaining (verified).

Live enablement blockers cleared.
- Inserted fresh portfolio_snapshots row at on-chain balance (clean drawdown baseline)
- MIN_POSITION_SOL=0.05 (from 0.10 default)
- market:mode:override=NORMAL renewed (24h TTL)
- TEST_MODE=false flipped after verification (see Phase F/G checklist output)

Observability.
- Added startup drawdown telemetry log in _load_state
- Documented drawdown-guard-non-persistence in CLAUDE.md (session-scoped, not cumulative)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"

git push origin main
```

This is the ONLY push of the sequence.

---

## Key residuals Jay should know going in

1. **Reconcile-on-mode-flip**: still unresolved. CLAUDE.md flags it as
   "discipline to codify." Mitigation: circuit breaker (`SELL_FAIL_THRESHOLD=8`,
   `SELL_PARK_DURATION_SEC=300`) will park misbehaving mints, but this is
   a protection, not a fix. If sell-storm recurs despite paper positions
   being cleaned, circuit breaker is Jay's safety net.

2. **Drawdown guard is session-scoped** (B2 note explains). A 26%
   overnight loss resets on restart. Acceptable for today's trial; real
   fix needs Redis-backed peak tracking.

3. **Helius URL tier** — make sure `HELIUS_STAKED_URL`, `HELIUS_RPC_URL`,
   `HELIUS_GATEKEEPER_URL` are all populated. The execution.py startup
   `RuntimeError` guard (cd266de) will refuse to start if all three are
   empty in live mode — that's the failsafe.

4. **Anthropic credits** for governance LLM are still exhausted (per
   CLAUDE.md); governance falls back to default NORMAL-mode JSON.
   Step D explicitly sets `market:mode:override=NORMAL` which bypasses
   this anyway.

5. **`TEST_MODE` flip alone doesn't reset in-memory state** — CLAUDE.md
   calls this out explicitly. The env var change triggers a deploy which
   restarts the container, so this is handled by the redeploy sequence
   above (not by a manual env var change alone — which wouldn't work).

---

## If Jay wants me to revisit this in a fresh session

Paste into a new CC session:

```
Review docs/audits/ZMN_LIVE_ENABLE_HANDOFF_2026_04_19.md. I have decided
to proceed with live enablement. I am here to supervise. Execute the
checklist Step A through I, pausing after each for my go/no-go. Update
CLAUDE.md per Step B3 first, so the durable rule matches intent.
```

That framing gives me supervised execution authority — durable rule
override is explicit, Jay is present, the staged-progression concern is
his to waive consciously rather than mine to bypass silently.

---

## Nothing was committed or pushed this session

```
git status
```

shows only this handoff report as an untracked addition. Branch unchanged
from `de7601c` (previous session's audit/cleanup commit).

Bot continues in paper mode. Wallet untouched.
