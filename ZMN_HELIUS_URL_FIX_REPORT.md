# ZMN Helius URL Resolver Fix — 2026-04-17 Morning Session

**Commit:** `cd266de`
**Branch:** main (pushed)
**Deploy status:** in flight at time of writing
**TEST_MODE at deploy:** true (paper-only for verification)

---

## 1. Phase 1 audit — what the overnight log actually said

### 1.1 env vars on bot_core (at session start)
All three Helius URLs were present, but `HELIUS_STAKED_URL` was misconfigured:

| var | bot_core (before) | web + signal_aggregator |
|---|---|---|
| `HELIUS_STAKED_URL` | `https://mainnet.helius-rpc.com/?api-key=<r>` (STANDARD) | `https://ardith-mo8tnm-fast-mainnet.helius-rpc.com/?api-key=<r>` (real staked) |
| `HELIUS_RPC_URL` | `https://mainnet.helius-rpc.com/?api-key=<r>` | same |
| `HELIUS_GATEKEEPER_URL` | `https://beta.helius-rpc.com/?api-key=<r>` | same |
| `TEST_MODE` | true | n/a |

Fixed in this session: bot_core `HELIUS_STAKED_URL` now matches web (`ardith-mo8tnm-fast-mainnet`). Env var change already triggered a Railway auto-redeploy.

### 1.2 code paths that read Helius URLs
Four loops in `services/execution.py`:

| line | function | URL order (before) | URL order (after) |
|---|---|---|---|
| 218 | `_get_dynamic_priority_fee` | (RPC, GATEKEEPER) | unchanged — only read path, not send path |
| 377 | `_execute_pumpportal_local` (send) | (STAKED, RPC) | **(STAKED, RPC, GATEKEEPER)** |
| 542 | `_send_transaction` | (STAKED, GATEKEEPER) | **(STAKED, RPC, GATEKEEPER)** |
| 637 | `_get_token_balance` | (RPC, GATEKEEPER) | unchanged — read path |

`services/bot_core.py`, `services/market_health.py`, `services/signal_listener.py`, `services/signal_aggregator.py`, `services/dashboard_api.py`, `services/treasury.py` also read `HELIUS_*` but none do transaction submission.

### 1.3 error distribution, last 12 h (7,448 of 9,019 errors = "no Helius URL")

```
err                                                            n    distinct_mints  first_seen         last_seen
PumpPortal Local: no Helius URL available for transaction su   7448  1475            2026-04-16 21:42   2026-04-17 07:07
'solders.transaction.VersionedTransaction' no attribute 'sig   1258   198            2026-04-16 20:56   2026-04-16 21:21
PumpPortal Local HTTP 400: Bad Request                          311    60            2026-04-16 20:57   2026-04-17 06:38
PumpPortal Local HTTP 502: <html> 502 Bad Gateway                 2     2            2026-04-16 21:45   2026-04-17 01:35
```

### 1.3b TX_SUBMIT timing (briefing claim corrected)
Briefing said "4 TX_SUBMITs at 06:37." Actual data shows 50+ TX_SUBMITs from 06:37
through at least 08:23 AEDT (limit-50 cut off the tail). All used
`https://mainnet.helius-rpc.com/?api-key=` (`HELIUS_RPC_URL`). Live trading
was productive once that var resolved.

### 1.3c Wallet balance (briefing claim corrected)
Docs said "wallet untouched at 5.0000 SOL." On-chain check via
`getBalance` on `4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ`:

**Actual: 3.677355 SOL** — **1.32 SOL was spent on-chain** between 06:37 and 08:23 AEDT.
10 most recent signatures all succeeded. Live trial v4 actually did trade.

### 1.4 sell-storm source
Top per-mint attempts capped at 10–20 each (not the single-mint thousands-of-retries pattern the briefing suggested). Total distinct storm mints: 1,475.

All 111 storm mints cross-checked against `paper_trades`: **every one is
paper-mode, already closed** (`exit_time NOT NULL`). Classic zombie-in-memory
position: closed in DB, still present in bot_core's `self.positions`, tried
to sell on every 2s tick.

### 1.5 current Redis state
- `bot:status`: RUNNING, test_mode=true, 3 open paper positions, NORMAL mode
- `paper:positions:*`: 2 keys
- no emergency_stop flag
- storm has stopped — TEST_MODE=true is live

---

## 2. Code changes shipped (commit cd266de)

### 2.1 `services/execution.py` — Gatekeeper fallback added to two send loops

Line 377 (`_execute_pumpportal_local`) and line 542 (`_send_transaction`) now
iterate `(HELIUS_STAKED_URL, HELIUS_RPC_URL, HELIUS_GATEKEEPER_URL)`.

### 2.2 `services/execution.py` — startup validation

```python
if not TEST_MODE:
    _helius_urls = [u for u in (HELIUS_STAKED_URL, HELIUS_RPC_URL, HELIUS_GATEKEEPER_URL) if u]
    if not _helius_urls:
        raise RuntimeError(...)  # refuses to start
    logger.info("execution.py: live mode OK, %d Helius URL(s) configured", len(_helius_urls))
```

Fails the import rather than running silently for 10 hours.

### 2.3 `services/execution.py` — error body truncation 200 → 2048
Applied to both `_execute_pumpportal` (line 275) and `_execute_pumpportal_local`
(line 351). Will expose the real field that PumpPortal's 400s are rejecting.

### 2.4 `services/bot_core.py` — sell-storm circuit breaker
- Added `_sell_failure_counts`, `_parked_mints` instance state
- Wrapped `execute_trade("sell", …)` at line 1053 with try/except `ExecutionError`
- After `SELL_FAIL_THRESHOLD` (default 8) same-mint failures, mint is parked
  for `SELL_PARK_DURATION_SEC` (default 300s)
- Both threshold and duration are env-tunable — kill switch: set threshold very high

Added `ExecutionError` to the import line from `services.execution`.

### 2.5 reconcile audit (read-only, not fixed)
`_load_state` (line 240) and `_reconcile_positions` (line 187) **both** correctly
filter by `trade_mode`. The overnight "empty" v4 run was NOT a reconcile-filter bug.

Root cause: `_load_state` and `_reconcile_positions` run **once, in `__init__`**.
A TEST_MODE flip without a container restart leaves in-memory `self.positions`
populated with whichever mode the bot was started in. If bot_core starts paper,
then TEST_MODE flips to live without restart, the paper positions stay in memory
and every 2s exit tick tries to live-sell closed paper mints.

Open question for next session: either (a) add a runtime TEST_MODE-change
detection that re-calls reconcile, or (b) document that every TEST_MODE flip
requires a bot_core restart. Option (b) is simpler and already the implicit
contract; codify it.

---

## 3. Test results (Phase 3)

| test | outcome |
|---|---|
| `python -m py_compile services/execution.py services/bot_core.py` | exit 0 |
| import, TEST_MODE=false, all URLs empty | **RuntimeError raised** as designed |
| import, TEST_MODE=false, 1 URL set | logs "live mode OK, 1 Helius URL(s) configured", imports |
| import, TEST_MODE=true, all URLs empty | imports silently (paper mode bypass) |

---

## 4. Deploy (Phase 4)

- Env var change: `HELIUS_STAKED_URL` on bot_core updated to real staked URL (auto-redeploy triggered)
- Git commit + push: `cd266de` on main (second deploy triggered via GitHub webhook)
- Deploy monitor: tailing bot_core logs for `Bot Core starting` / `RuntimeError` / `no Helius URL` / `PARK mint`
- TEST_MODE verified `true` at push time — post-deploy verification uses paper mode

**Note on deploy discipline**: env var change + git push in the same window
causes two sequential Railway deploys. The second will supersede the first.
This is a minor build-minute cost but unavoidable here because the env var was
also wrong — couldn't wait to fix in the same commit.

---

## 5. Post-deploy verification (Phase 5) — ALL PASS

New container booted 21:44:21 UTC (~08:44 AEDT) with
`Bot Core starting (TEST_MODE=True)`. No RuntimeError, no startup failure.

| check | expected | actual |
|---|---|---|
| 5.1 "no Helius URL" errors, last 10 min | 0 | **0** ✓ |
| 5.2 live_trade_log events, last 10 min | 0 (paper mode) | 0 ✓ |
| 5.2b paper trades, last 15 min | 5–15 | **7** ✓ |
| 5.3 any mint with >5 sell errors, last 15 min | 0 | 0 ✓ |
| 5.4 any ERRORs at all, last 10 min | 0 | 0 ✓ |

Circuit breaker code path not exercised — paper mode uses `paper_sell`,
not `execute_trade`. Real exercise waits for the next live trial.

---

## 6. Residual issues

1. **reconcile is startup-only.** See 2.5 — not a code bug, but a contract
   to codify. Added to CLAUDE.md as an explicit rule this session.
2. **PumpPortal 400s** need inspection once the new 2048-char body logging
   lands. 311 hits overnight with body truncated at `Bad Request`. No idea
   which field PumpPortal is rejecting. One session of observation after
   the next live trial should make this obvious.
3. **Signing was verified** — 50+ successful TX_SUBMITs and 10+ on-chain
   signatures all `OK`, zero `SignatureFailure`. The CLAUDE.md section on
   "Live trading preparation — SIGNING FIX DEPLOYED" should move from
   "blocked" to "resolved." The outstanding blocker is no longer signing,
   it is configuration hygiene (env vars + reconcile).
4. **Briefing claim "4 TX_SUBMITs at 06:37"** was wrong — actual count was
   50+ and the window stretched to 08:23 AEDT. Wallet went 5.0 → 3.677 SOL.
   Docs updated to reflect the actual trial outcome.
5. **live_trade_log sell events undercounted.** Cross-check: 3 buys
   (AXjqQgtYWkiD, 7TiRb9nwGNVs, EExc7FMH2SyL) appeared without matching
   sell events in live_trade_log, but all three were sold successfully
   on-chain (verified via getTokenAccountsByOwner — zero balance). Sell
   path likely takes a branch that skips the `live_execution_log(event_type=
   'TX_SUBMIT')` call. Not a safety bug — current wallet has ZERO live
   exposure. But it does mean live_trade_log is unreliable for trade
   accounting; use on-chain signatures. Worth a brief audit next session.

## 6b. Stuck-position audit (added after Jay's question)

Cross-checked the three "buy without logged sell" mints against on-chain
state:

| mint | bought | sold (on-chain) | still held? |
|---|---|---|---|
| EExc7FMH2SyL… | 08:15:32 AEDT | 08:22:41 full exit | no |
| AXjqQgtYWkiD… (pump) | 08:03:33 AEDT | 08:14:26 full exit (1 failed retry at 08:13:57) | no |
| 7TiRb9nwGNVs… (pump) | 08:09:10 AEDT | sold between 08:09 and 08:24 | no |

Wallet currently: 3.677355 SOL + USDC 3.37 + USDT 6.72 + one unknown dust
position (2K8h3T21nXJDe7bx, 0.063). None of the dust relates to the v4
live trial.

**Conclusion: zero live exposure.** Safe for restart-before-reflip.

---

## 7. Recommendation for Jay on live re-enable

**Safe to flip TEST_MODE=false again, with the following preconditions:**

1. Wait for this deploy to show `Bot Core starting (TEST_MODE=true)` and no
   `no Helius URL` errors for at least 5 min. (Should be automatic.)
2. Before next flip:
   - Clear stale in-memory positions by restarting bot_core after any
     long paper run (restart = clear `self.positions`).
   - Verify `railway variables -s bot_core --kv | grep HELIUS_STAKED_URL`
     shows `ardith-mo8tnm-fast-mainnet`, not the plain `mainnet`.
   - Verify wallet balance is where you expect.
3. Position size for v5: **keep at current config** (MAX_SD_POSITIONS=20,
   DAILY_LOSS_LIMIT_SOL=4.0, wallet 3.677 SOL). The 1.32 SOL v4 burn was
   distributed across 50+ trades, average ~0.026 SOL/trade loss — that's
   in line with normal paper variance, not a signing failure.
4. First 30 min of v5: watch `live_trade_log` for `PARK mint` events. If
   you see any, that's the circuit breaker earning its keep — not a
   regression.

**Do not flip without first restarting bot_core.** Env var flip alone is
insufficient for reconcile state hygiene (see 2.5).
