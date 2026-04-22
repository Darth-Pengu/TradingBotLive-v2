#!/usr/bin/env bash
# ZMN live-flip pre-flight cleanup (CLEAN-003 + CLEAN-004).
#
# Purpose: clear paper-mode position state from Redis BEFORE flipping
# TEST_MODE=false on bot_core. Without this, paper positions remain in
# Redis and can leak into bot_core's in-memory state across the flip,
# causing live-mode sell attempts on mints that only exist in paper.
# Also reset `consecutive_losses` so the sell-storm circuit breaker
# starts from a clean baseline rather than inheriting a stale paper-era
# count (CLEAN-004, 2026-04-22).
#
# Incidents:
#   - Session 5 v4 (2026-04-20) — 5 phantom mints attempted live sells,
#     25 wasted Helius RPC calls. See session_outputs/ZMN_LIVE_ROLLBACK.md.
#   - DASH-RESET 2026-04-21 — consecutive_losses=4 survived the paper
#     reset; one live loss in v5 would trip the sell-storm breaker at
#     5+ unnecessarily.
#
# Usage:
#   export REDIS_URL="redis://..."            # Railway Redis public URL
#   export DATABASE_PUBLIC_URL="postgres://…"  # Railway Postgres public URL (for CLEAN-004)
#   bash scripts/live_flip_prep.sh
#
# Run BEFORE changing the Railway env var. After the bot_core restart that
# the env-var change triggers, verify startup logs show "Startup
# reconciliation: 0 open positions in DB" — if N>0, STOP and investigate
# before any live trade can fire.

set -euo pipefail

echo "=== ZMN live-flip pre-flight cleanup (CLEAN-003) ==="
echo "Clears paper-mode state so live-mode reconcile starts clean."
echo

if [ -z "${REDIS_URL:-}" ]; then
    echo "ERROR: REDIS_URL not set. Export it before running:"
    echo "  export REDIS_URL='redis://default:<pass>@host:port'"
    exit 1
fi

# Sanity check that redis-cli is available.
if ! command -v redis-cli >/dev/null 2>&1; then
    echo "ERROR: redis-cli not found on PATH. Install redis-tools first."
    exit 1
fi

echo "Redis target: ${REDIS_URL%%@*}@<redacted>"
echo

# --- 1. bot:status ---
echo "1. Deleting bot:status key..."
if redis-cli -u "$REDIS_URL" EXISTS bot:status 2>/dev/null | grep -qx "1"; then
    redis-cli -u "$REDIS_URL" DEL bot:status > /dev/null
    echo "   deleted."
else
    echo "   (key did not exist — fine)"
fi
echo

# --- 2. paper:positions:* ---
echo "2. Scanning paper:positions:* keys..."
PAPER_KEYS=$(redis-cli -u "$REDIS_URL" --scan --pattern 'paper:positions:*' 2>/dev/null || true)
if [ -z "$PAPER_KEYS" ]; then
    echo "   (no paper position keys — fine)"
else
    echo "$PAPER_KEYS" | while IFS= read -r k; do
        [ -z "$k" ] && continue
        echo "   deleting: $k"
        redis-cli -u "$REDIS_URL" DEL "$k" > /dev/null
    done
fi
echo

# --- 3. bot:open_positions:* (defensive — key may or may not exist) ---
echo "3. Scanning bot:open_positions:* keys..."
OPEN_KEYS=$(redis-cli -u "$REDIS_URL" --scan --pattern 'bot:open_positions:*' 2>/dev/null || true)
if [ -z "$OPEN_KEYS" ]; then
    echo "   (no bot:open_positions keys — fine)"
else
    echo "$OPEN_KEYS" | while IFS= read -r k; do
        [ -z "$k" ] && continue
        echo "   deleting: $k"
        redis-cli -u "$REDIS_URL" DEL "$k" > /dev/null
    done
fi
echo

# --- 4. consecutive_losses reset (CLEAN-004) ---
echo "4. Resetting consecutive_losses counter (CLEAN-004)..."
echo "   a) Redis: SET bot:consecutive_losses 0"
if redis-cli -u "$REDIS_URL" SET bot:consecutive_losses 0 > /dev/null 2>&1; then
    echo "      done."
else
    echo "      WARN: could not SET bot:consecutive_losses (non-fatal; bot_core will rehydrate from Postgres)"
fi

echo "   b) Postgres: UPDATE bot_state SET value_text='0' WHERE key='consecutive_losses'"
if [ -z "${DATABASE_PUBLIC_URL:-}" ]; then
    echo "      SKIPPED: DATABASE_PUBLIC_URL not set."
    echo "      The Redis reset above handles the immediate runtime state but the"
    echo "      Postgres row will re-hydrate Redis on next bot_core restart. Either"
    echo "      export DATABASE_PUBLIC_URL and re-run, OR manually execute the UPDATE."
elif ! command -v psql >/dev/null 2>&1; then
    echo "      SKIPPED: psql not on PATH. Redis reset above is sufficient for current"
    echo "      runtime; Postgres will re-hydrate on next restart. Install psql to persist."
else
    if psql "$DATABASE_PUBLIC_URL" -v ON_ERROR_STOP=1 -q -c "INSERT INTO bot_state (key, value_text, updated_at) VALUES ('consecutive_losses', '0', NOW()) ON CONFLICT (key) DO UPDATE SET value_text='0', updated_at=NOW();" >/dev/null 2>&1; then
        echo "      done."
    else
        echo "      WARN: psql update failed. Redis reset above still holds for current runtime."
    fi
fi
echo

echo "=== Pre-flight cleanup complete ==="
echo
echo "Next steps (do these manually, in order):"
echo "  a. Flip TEST_MODE=false in Railway bot_core variables"
echo "  b. Wait ~90s for Railway to redeploy bot_core"
echo "  c. Tail bot_core startup log for:"
echo "       'Startup reconciliation: 0 open positions in DB'"
echo "       'Restored consecutive_losses=0 from PostgreSQL'"
echo "     If reconciliation N>0, STOP and investigate (phantom positions)."
echo "     If consecutive_losses != 0, CLEAN-004 didn't persist — re-run with DATABASE_PUBLIC_URL set."
echo "  d. Proceed with the live window per your session prompt."
