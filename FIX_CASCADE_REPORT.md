# Cascade Fix Report — 2026-04-09

## Outcome
**FIXED** — Paper trades flowing, exit pricing working, trailing stops firing.

## Root Cause
Exit pricing failed because bonding curve data from PumpPortal create events was only
cached in Redis for subscribed tokens (`_subscribed_tokens` gate at signal_listener.py:472).
New tokens aren't subscribed until AFTER position entry, creating a 5-30+ second gap where
the exit checker has zero pricing data. During this gap, all five price sources fail
(Redis empty, BC reserves empty, Jupiter fails for bonding curve tokens, GeckoTerminal too
new). This caused NO_EXIT_PRICE on every position → blind exits → 5 stop-loss exits in
30 minutes → rug cascade emergency stop → bot dead for 22+ hours.

## Steps Applied
1. **Step 1 diagnosis:** Exit pricing pipeline code was correct (keys match, priority order
   correct). The bug was data availability timing — BC reserves from create events gated
   behind `_subscribed_tokens` check, preventing initial price caching for new tokens.

2. **Step 2 pricing fix (commit 26e19b4):**
   - signal_listener.py:472 — removed `_subscribed_tokens` gate from create event BC caching.
     Now caches `token:latest_price:{mint}` and `token:reserves:{mint}` for ALL new tokens.
   - bot_core.py:773 — seeds `token:latest_price:{mint}` with BC price on position entry,
     providing immediate fallback before trade subscription delivers data.

3. **Step 3 emergency reset:** Not needed — emergency stop was in-memory only (not persisted
   to Redis by rug cascade path). Redeploying bot_core cleared it automatically. Old cascade
   trades were 23+ hours outside the 30-minute window.

4. **Step 4 MIN_POSITION_SOL:** Railway env var changed from 0.15 → 0.08 on bot_core.
   Position sizing multiplier stack (0.7 × 0.35 × 0.84 = 0.1256 SOL) now passes minimum.

5. **Step 5 cascade threshold:** market_health.py:396 — made RUG_CASCADE_THRESHOLD env-var
   configurable (default 5). Set to 15 on market_health Railway service for paper mode.

6. **Step 6 verification:** All success criteria met after 10-minute observation window.

## Verification Numbers
- Trades in new session: 1 new + 3 restored from DB
- NO_EXIT_PRICE count in new session: **0** (was hundreds per position before)
- TRAILING_STOP exits: 6 (exit strategy now actually working)
- Emergency stop re-triggered: **NO**
- Position size rejections: **0** (was blocking before)

## Exit Reason Distribution (new session)
| Reason | Count | Notes |
|--------|-------|-------|
| TRAILING_STOP | 6 | Exit strategy working — saw +30% peak, trailed down |
| stop_loss | 0 | No blind stop losses |
| NO_EXIT_PRICE | 0 | Pricing fix confirmed |

## Tier 2 Issues Documented (NOT FIXED)
- Feature derivation timing (see TIER2_FOLLOWUPS.md)
- Inline ML engine routing (see TIER2_FOLLOWUPS.md)
- Governance SQL type mismatch
- Paper trader exit price fallback
- Analyst auto-pause in fear markets

## Env Var Changes Made
| Service | Variable | Old | New |
|---------|----------|-----|-----|
| bot_core | MIN_POSITION_SOL | 0.15 | 0.08 |
| market_health | RUG_CASCADE_THRESHOLD | (not set, default 5) | 15 |

## Services Restarted
| Service | Time (UTC) | Reason |
|---------|-----------|--------|
| signal_listener | ~13:48 Apr 9 | BC price caching for all tokens |
| bot_core | 13:50 Apr 9 | BC seed on entry + emergency stop clear |
| market_health | ~13:50 Apr 9 | Configurable cascade threshold |

## What Jay Should Watch Tomorrow Morning
1. **Dashboard at zmnbot.com** — check "Last Trade" timestamp is recent (within 30 min)
2. **Check for emergency stop** — if bot goes silent, the cascade might have re-triggered
3. **Exit reasons** — TRAILING_STOP and target_hit appearing means pricing is healthy.
   If 100% stop_loss returns, pricing may have regressed
4. **Paper trade count** — should be steady stream (5-20/hour depending on market activity)
5. **Balance** — will slowly decrease in extreme fear market, but losses should be small
   (-0.5% to -3.5% per trade, not -50% blind exits)
