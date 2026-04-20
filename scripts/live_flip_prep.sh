#!/usr/bin/env bash
# ZMN live-flip pre-flight cleanup (CLEAN-003).
#
# Purpose: clear paper-mode position state from Redis BEFORE flipping
# TEST_MODE=false on bot_core. Without this, paper positions remain in
# Redis and can leak into bot_core's in-memory state across the flip,
# causing live-mode sell attempts on mints that only exist in paper.
#
# Incident: Session 5 v4 (2026-04-20) — 5 phantom mints attempted live
# sells, 25 wasted Helius RPC calls. See session_outputs/ZMN_LIVE_ROLLBACK.md.
#
# Usage:
#   export REDIS_URL="redis://..."   # Railway Redis public URL
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

echo "=== Pre-flight cleanup complete ==="
echo
echo "Next steps (do these manually, in order):"
echo "  a. Flip TEST_MODE=false in Railway bot_core variables"
echo "  b. Wait ~90s for Railway to redeploy bot_core"
echo "  c. Tail bot_core startup log for:"
echo "       'Startup reconciliation: 0 open positions in DB'"
echo "     If N>0, STOP and investigate (phantom positions still present)."
echo "  d. Proceed with the live window per your session prompt."
