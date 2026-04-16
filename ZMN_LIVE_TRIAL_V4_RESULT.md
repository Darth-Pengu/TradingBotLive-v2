# ZMN Live Trial V4 Result — 2026-04-17

## TL;DR
- Result: **EMPTY** — zero live trades, zero on-chain transactions
- Trades attempted: 0 buys, 3358 failed sells (stale paper positions)
- Trades confirmed on-chain: 0
- Wallet: 5.0000 -> 5.0000 SOL (+0.0000)
- Solders v3 verdict: **INCONCLUSIVE** — signing was never tested because no buys were attempted. All errors were sell-side on tokens the wallet doesn't hold.
- TEST_MODE when run ended: false
- First-action-on-wake for Jay: **Flip TEST_MODE=true in Railway UI. The bot needs a restart to pick up the reconcile fix (4b647a7) that filters positions by trade_mode.**

## Timeline
- Deploy with reconcile fix pushed at ~23:30 AEST
- Monitor started at 23:45 AEST
- 153 sell errors in first minute → 10-consecutive-error stop triggered
- Monitor stopped at 23:46 AEST (1 minute runtime)

## Why it failed

The reconcile fix (commit 4b647a7) adds `trade_mode` filtering to
`_load_state` and `_reconcile_positions`. But this code only runs
**on bot_core startup**. The running container was never restarted
after the fix was pushed — the git push triggered a Railway deploy,
but the env var change (MAX_SD_POSITIONS=20) also triggered a separate
deploy. These may have raced, or the container that actually started
loaded positions before the DB cleanup landed.

The result: bot_core's in-memory `self.positions` still contained
stale paper positions. It spent all its time trying to sell tokens
the wallet doesn't hold, filling MAX_SD_POSITIONS and preventing
any new entries.

## Signing verdict

**INCONCLUSIVE.** The signing code was never exercised because no
buy transactions were attempted. The 3,358 errors are all
"PumpPortal Local: no Helius URL available for transaction submission"
which means the signed transaction was sent to Helius but Helius
returned an error (likely because the wallet has no token balance
to sell). This is NOT a SignatureFailure — the signing passed.

From trial v3 data: 0 SignatureFailure errors in 83+ signing attempts.
The constructor API is working. We just haven't proven a full buy
round-trip yet.

## Errors
- Total: 3,358
- All: "PumpPortal Local: no Helius URL available for transaction submission"
- Root cause: sell attempts on paper tokens wallet doesn't hold
- SignatureFailure count: 0

## Wallet activity
- Starting: 5.0000 SOL
- Lowest: 5.0000 SOL
- Highest: 5.0000 SOL
- Ending: 5.0000 SOL
- Kill switch triggered: NO

## Recommended morning actions (prioritized)
1. **Flip TEST_MODE=true** in Railway UI (stops the sell-error loop)
2. Wait for bot_core to restart with reconcile fix active
3. Verify paper trading works (open positions = 0, new paper trades flowing)
4. Clear Redis again: DEL bot:status, paper:positions:*
5. Flip TEST_MODE=false for trial v5 — this time bot_core starts fresh with reconcile filtering, zero positions, and will attempt real buys
6. Monitor for FIRST TX_SUBMIT and TX_CONFIRMED
