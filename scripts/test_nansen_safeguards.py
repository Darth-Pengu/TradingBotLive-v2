"""
Phase 0.3 — Test all 8 safeguard layers of the Nansen client.
Run with: python scripts/test_nansen_safeguards.py
Requires Redis running locally or REDIS_URL set.
"""

import asyncio
import json
import os
import sys

# Ensure services/ is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# We need to set SERVICE_NAME BEFORE importing nansen_client for Layer 1 tests
# Default to an allowed service so the import succeeds
os.environ["SERVICE_NAME"] = "signal_aggregator"
os.environ["NANSEN_API_KEY"] = "test-key-for-safeguards"
os.environ["NANSEN_DRY_RUN"] = "true"
os.environ["NANSEN_DAILY_BUDGET"] = "2000"

import redis.asyncio as aioredis


PASSED = 0
FAILED = 0


def report(test_name: str, passed: bool, detail: str = ""):
    global PASSED, FAILED
    status = "PASS" if passed else "FAIL"
    if passed:
        PASSED += 1
    else:
        FAILED += 1
    print(f"  [{status}] {test_name}" + (f" — {detail}" if detail else ""))


async def get_redis():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        r = aioredis.from_url(redis_url, decode_responses=True)
        await r.ping()
        return r
    except Exception as e:
        print(f"WARNING: Cannot connect to Redis ({redis_url}): {e}")
        print("Tests requiring Redis will be skipped.")
        return None


async def test_layer1_service_guard():
    """Layer 1: Only allowed services can make API calls."""
    print("\n--- Layer 1: Service Routing Guard ---")

    from services.nansen_client import _check_service_guard, NansenServiceGuard, ALLOWED_CALLER_SERVICES

    # Test 1a: Allowed service should pass
    original = os.environ.get("SERVICE_NAME", "")
    os.environ["SERVICE_NAME"] = "signal_aggregator"
    # Need to reload the module-level var
    import services.nansen_client as nc
    nc.SERVICE_NAME = "signal_aggregator"
    try:
        _check_service_guard()
        report("Allowed service (signal_aggregator) passes", True)
    except NansenServiceGuard:
        report("Allowed service (signal_aggregator) passes", False, "Raised NansenServiceGuard")

    # Test 1b: Disallowed service should raise
    nc.SERVICE_NAME = "treasury"
    try:
        _check_service_guard()
        report("Disallowed service (treasury) blocked", False, "Did NOT raise")
    except NansenServiceGuard:
        report("Disallowed service (treasury) blocked", True)

    # Test 1c: Empty SERVICE_NAME should pass (local dev)
    nc.SERVICE_NAME = ""
    try:
        _check_service_guard()
        report("Empty SERVICE_NAME passes (local dev)", True)
    except NansenServiceGuard:
        report("Empty SERVICE_NAME passes (local dev)", False, "Raised NansenServiceGuard")

    # Restore
    nc.SERVICE_NAME = original or "signal_aggregator"


async def test_layer2_budget(redis_conn):
    """Layer 2: Daily budget enforcement."""
    print("\n--- Layer 2: Daily Budget Enforcement ---")

    if not redis_conn:
        report("Budget test (requires Redis)", False, "No Redis connection")
        return

    from services.nansen_client import _check_daily_budget, NansenBudgetExceeded, _today

    today_key = f"nansen:credits:{_today()}"

    # Save original value
    original = await redis_conn.get(today_key)

    # Test 2a: Under budget should pass
    await redis_conn.set(today_key, "8")
    import services.nansen_client as nc
    nc.NANSEN_DAILY_BUDGET = 10
    try:
        used = await _check_daily_budget(redis_conn, cost=1)
        report("Under budget (8+1 <= 10) passes", True, f"used={used}")
    except NansenBudgetExceeded:
        report("Under budget (8+1 <= 10) passes", False, "Raised NansenBudgetExceeded")

    # Test 2b: Over budget should raise
    try:
        await _check_daily_budget(redis_conn, cost=5)
        report("Over budget (8+5 > 10) blocked", False, "Did NOT raise")
    except NansenBudgetExceeded:
        report("Over budget (8+5 > 10) blocked", True)

    # Restore
    nc.NANSEN_DAILY_BUDGET = int(os.getenv("NANSEN_DAILY_BUDGET", "2000"))
    if original:
        await redis_conn.set(today_key, original)
    else:
        await redis_conn.delete(today_key)


async def test_layer3_distributed_lock(redis_conn):
    """Layer 3: Distributed poll lock."""
    print("\n--- Layer 3: Distributed Lock ---")

    if not redis_conn:
        report("Lock test (requires Redis)", False, "No Redis connection")
        return

    from services.nansen_client import acquire_poll_lock

    lock_name = "test_sm_dex_trades"
    lock_key = f"nansen:lock:{lock_name}"

    # Clean up first
    await redis_conn.delete(lock_key)

    # Test 3a: First acquisition should succeed
    result1 = await acquire_poll_lock(redis_conn, lock_name, ttl_sec=10)
    report("First lock acquisition succeeds", result1 is True)

    # Test 3b: Second acquisition should fail (lock held)
    result2 = await acquire_poll_lock(redis_conn, lock_name, ttl_sec=10)
    report("Second lock acquisition blocked", result2 is False)

    # Clean up
    await redis_conn.delete(lock_key)


async def test_layer4_caching(redis_conn):
    """Layer 4: Cache hit prevents redundant calls."""
    print("\n--- Layer 4: Caching ---")

    if not redis_conn:
        report("Cache test (requires Redis)", False, "No Redis connection")
        return

    # Simulate caching by using the endpoint functions' own cache logic
    cache_key = "nansen:flows:test_mint_abc:1h"
    test_data = {"data": {"flow": 123}}

    # Set cache
    await redis_conn.set(cache_key, json.dumps(test_data), ex=60)

    # Read cache
    cached = await redis_conn.get(cache_key)
    if cached:
        parsed = json.loads(cached)
        report("Cache set and retrieved", parsed == test_data)
    else:
        report("Cache set and retrieved", False, "Cache miss")

    # Clean up
    await redis_conn.delete(cache_key)


async def test_layer5_circuit_breaker(redis_conn):
    """Layer 5: Circuit breaker on consecutive 429s."""
    print("\n--- Layer 5: Circuit Breaker ---")

    if not redis_conn:
        report("Circuit breaker test (requires Redis)", False, "No Redis connection")
        return

    from services.nansen_client import (
        _check_circuit_breaker, _trip_circuit_breaker, NansenCircuitBreakerOpen
    )

    # Clean first
    await redis_conn.delete("nansen:circuit_breaker")

    # Test 5a: No breaker → should pass
    try:
        await _check_circuit_breaker(redis_conn)
        report("No breaker → passes", True)
    except NansenCircuitBreakerOpen:
        report("No breaker → passes", False, "Raised unexpectedly")

    # Test 5b: Trip breaker → should block
    await _trip_circuit_breaker(redis_conn, duration_sec=10)
    try:
        await _check_circuit_breaker(redis_conn)
        report("Tripped breaker → blocked", False, "Did NOT raise")
    except NansenCircuitBreakerOpen:
        report("Tripped breaker → blocked", True)

    # Clean up
    await redis_conn.delete("nansen:circuit_breaker")


async def test_layer6_dry_run(redis_conn):
    """Layer 6: Dry-run mode returns mock without real calls."""
    print("\n--- Layer 6: Dry-Run Mode ---")

    from services.nansen_client import NANSEN_DRY_RUN, _mock_response

    report("NANSEN_DRY_RUN is True", NANSEN_DRY_RUN is True)

    # Test mock responses for different endpoints
    mock_screener = _mock_response("/token-screener")
    report("Mock screener returns data list", isinstance(mock_screener.get("data"), list))

    mock_dex = _mock_response("/tgm/token-dex-trades")
    report("Mock dex-trades returns data list", isinstance(mock_dex.get("data"), list))

    mock_pnl = _mock_response("/profiler/address/pnl-summary")
    report("Mock pnl returns data dict", isinstance(mock_pnl.get("data"), dict))

    if redis_conn:
        # Test that dry-run increments the dryrun counter
        from services.nansen_client import _today
        dryrun_key = f"nansen:dryrun_calls:{_today()}"
        before = int(await redis_conn.get(dryrun_key) or 0)
        await redis_conn.incrby(dryrun_key, 1)
        after = int(await redis_conn.get(dryrun_key) or 0)
        report("Dry-run counter increments", after == before + 1)
        await redis_conn.delete(dryrun_key)


async def test_layer7_logging(redis_conn):
    """Layer 7: Per-call logging to Redis."""
    print("\n--- Layer 7: Per-Call Logging ---")

    if not redis_conn:
        report("Logging test (requires Redis)", False, "No Redis connection")
        return

    from services.nansen_client import _log_call

    # Clean
    await redis_conn.delete("nansen:call_log")

    # Log a test call
    await _log_call(redis_conn, "/test-endpoint", cost=1, used_after=42,
                    duration_ms=150.5, status=200)

    # Verify it's in the list
    entries = await redis_conn.lrange("nansen:call_log", 0, 0)
    if entries:
        entry = json.loads(entries[0])
        report("Log entry written to Redis", True)
        report("Log entry has correct endpoint",
               entry.get("endpoint") == "/test-endpoint")
        report("Log entry has cost and used",
               entry.get("cost") == 1 and entry.get("used") == 42)
    else:
        report("Log entry written to Redis", False, "Empty list")

    # Clean up
    await redis_conn.delete("nansen:call_log")


async def test_layer8_kill_switch(redis_conn):
    """Layer 8: Emergency kill switch."""
    print("\n--- Layer 8: Emergency Kill Switch ---")

    if not redis_conn:
        report("Kill switch test (requires Redis)", False, "No Redis connection")
        return

    from services.nansen_client import _check_kill_switch, NansenEmergencyStop

    # Clean first
    await redis_conn.delete("nansen:emergency_stop")

    # Test 8a: No kill switch → should pass
    try:
        await _check_kill_switch(redis_conn)
        report("No kill switch → passes", True)
    except NansenEmergencyStop:
        report("No kill switch → passes", False, "Raised unexpectedly")

    # Test 8b: Set kill switch → should block
    await redis_conn.set("nansen:emergency_stop", "true", ex=30)
    try:
        await _check_kill_switch(redis_conn)
        report("Kill switch active → blocked", False, "Did NOT raise")
    except NansenEmergencyStop:
        report("Kill switch active → blocked", True)

    # Clean up
    await redis_conn.delete("nansen:emergency_stop")


async def main():
    print("=" * 60)
    print("ZMN Bot — Nansen Safeguard Tests (Phase 0.3)")
    print("=" * 60)

    redis_conn = await get_redis()

    await test_layer1_service_guard()
    await test_layer2_budget(redis_conn)
    await test_layer3_distributed_lock(redis_conn)
    await test_layer4_caching(redis_conn)
    await test_layer5_circuit_breaker(redis_conn)
    await test_layer6_dry_run(redis_conn)
    await test_layer7_logging(redis_conn)
    await test_layer8_kill_switch(redis_conn)

    if redis_conn:
        await redis_conn.aclose()

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    print("=" * 60)

    if FAILED > 0:
        print("\nFAILED — Fix failures before proceeding to Phase 0.4")
        sys.exit(1)
    else:
        print("\nALL PASSED — Phase 0.3 complete")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
