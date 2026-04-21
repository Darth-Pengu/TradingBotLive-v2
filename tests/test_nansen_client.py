"""Tests for services/nansen_client_v2.py.

Asserts the three session-spec invariants:
1. Auth header name is ``apikey`` (lowercase), NOT ``Authorization: Bearer``.
2. Zero-sentinel dicts are NEVER returned on exception — the client raises
   NansenUnavailable instead.
3. A 401 response raises NansenUnavailable (terminal; no retry, no fallback).

Also exercises the per-endpoint wrappers enough to catch gross payload-shape
regressions (e.g. missing ``parameters`` envelope).
"""

from __future__ import annotations

import importlib
import os
import sys

import httpx
import pytest
import respx

# Ensure a deterministic API key + shortened retries for the test suite.
os.environ["NANSEN_API_KEY"] = "test-api-key-abc123"
os.environ["NANSEN_RETRY_ATTEMPTS"] = "2"
os.environ["NANSEN_RPS_LIMIT"] = "1000"  # effectively disable rate limiting


def _load_client():
    # Fresh import so env overrides apply and the module-level client/bucket
    # singleton is recreated per test run.
    if "services.nansen_client_v2" in sys.modules:
        del sys.modules["services.nansen_client_v2"]
    return importlib.import_module("services.nansen_client_v2")


@pytest.mark.asyncio
async def test_auth_header_is_lowercase_apikey():
    client = _load_client()
    captured: dict[str, str] = {}

    def _capture(request: httpx.Request):
        # httpx normalizes header key case on Headers access; check raw bytes
        # to distinguish ``apikey`` vs ``Apikey`` vs ``APIKEY``. Headers()
        # preserves case on .raw; normalize both sides to lower for the
        # "present" test, then use .raw to confirm lowercase on the wire.
        for name, value in request.headers.raw:
            captured[name.decode("latin-1")] = value.decode("latin-1")
        return httpx.Response(200, json={"data": []})

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/smart-money/holdings").mock(side_effect=_capture)
        await client.sm_holdings()

    # Lowercase ``apikey`` must be present, ``Authorization`` must NOT be.
    assert "apikey" in captured, (
        f"expected lowercase 'apikey' header, got keys {list(captured.keys())}"
    )
    assert captured["apikey"] == "test-api-key-abc123"
    assert "Authorization" not in captured and "authorization" not in captured, (
        "must not send Authorization header — Nansen uses 'apikey' only"
    )
    await client.aclose()


@pytest.mark.asyncio
async def test_401_raises_nansen_unavailable_not_zero_sentinel():
    client = _load_client()

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/smart-money/dex-trades").mock(
            return_value=httpx.Response(401, json={"error": "invalid key"})
        )

        with pytest.raises(client.NansenUnavailable):
            await client.sm_dex_trades()

    await client.aclose()


@pytest.mark.asyncio
async def test_5xx_retries_then_raises_unavailable_not_zero_sentinel():
    """Repeated 500 responses must exhaust retries and raise NansenUnavailable.

    Crucially, the function does NOT return ``{}`` or ``{"data": []}`` or any
    zero-sentinel dict — that contract would let callers silently treat absent
    Nansen data as zero, which is the exact behavior the Session A spec forbids.
    """
    client = _load_client()

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/tgm/flow-intelligence").mock(
            return_value=httpx.Response(500, text="upstream down")
        )

        result = None
        exc = None
        try:
            result = await client.tgm_flow_intel("So11111111111111111111111111111111111111112")
        except client.NansenUnavailable as e:
            exc = e

    assert exc is not None, (
        "5xx must raise NansenUnavailable after retries exhausted; "
        f"instead returned {result!r} (zero-sentinel leak)"
    )
    assert result is None, "no return value should reach the caller on failure"
    await client.aclose()


@pytest.mark.asyncio
async def test_transport_error_never_returns_zero_sentinel():
    """A pure network error (no HTTP response) must also raise, not fake-zero."""
    client = _load_client()

    def _raise_connect(_request: httpx.Request):
        raise httpx.ConnectError("dns failure")

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/smart-money/netflow").mock(side_effect=_raise_connect)

        with pytest.raises(client.NansenUnavailable):
            await client.sm_netflow()

    await client.aclose()


@pytest.mark.asyncio
async def test_wrapper_payload_shapes():
    """Each wrapper posts the spec-expected JSON envelope."""
    client = _load_client()
    seen: list[tuple[str, dict]] = []

    def _capture(request: httpx.Request):
        import json as _json

        path = request.url.path.replace("/api/v1", "")
        seen.append((path, _json.loads(request.content)))
        return httpx.Response(200, json={"ok": True})

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        for p in (
            "/smart-money/dex-trades",
            "/smart-money/netflow",
            "/smart-money/holdings",
            "/tgm/flow-intelligence",
            "/tgm/who-bought-sold",
            "/tgm/holders",
            "/profiler/address/pnl-summary",
            "/profiler/address/pnl",
            "/profiler/address/transactions",
        ):
            mock.post(p).mock(side_effect=_capture)

        await client.sm_dex_trades(value_usd_min=5000, limit=50)
        await client.sm_netflow()
        await client.sm_holdings()
        await client.tgm_flow_intel("mintAddr")
        await client.tgm_who_bought_sold("mintAddr")
        await client.tgm_holders("mintAddr")
        await client.profiler_pnl("walletAddr")
        await client.profiler_pnl_token("walletAddr", "mintAddr")
        await client.profiler_transactions("walletAddr", date_from="2026-04-01")

    paths = [p for p, _ in seen]
    assert paths == [
        "/smart-money/dex-trades",
        "/smart-money/netflow",
        "/smart-money/holdings",
        "/tgm/flow-intelligence",
        "/tgm/who-bought-sold",
        "/tgm/holders",
        "/profiler/address/pnl-summary",
        "/profiler/address/pnl",
        "/profiler/address/transactions",
    ], paths

    # Each body carries the ``parameters`` envelope (Nansen POST contract).
    for path, body in seen:
        assert "parameters" in body, f"missing 'parameters' envelope on {path}: {body}"

    # Spot-check the SM DEX trades payload matches the spec exactly.
    sm_body = seen[0][1]["parameters"]
    assert sm_body["chains"] == ["solana"]
    assert sm_body["filters"]["include_smart_money_labels"] == [
        "Smart Trader",
        "Fund",
        "180D Smart Trader",
    ]
    assert sm_body["filters"]["value_usd"]["min"] == 5000
    assert sm_body["pagination"]["per_page"] == 50
    assert sm_body["order_by"][0]["field"] == "block_time"
    assert sm_body["order_by"][0]["direction"] == "DESC"

    await client.aclose()


@pytest.mark.asyncio
async def test_credit_usage_counter_increments_on_success_only():
    client = _load_client()

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/smart-money/holdings").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        mock.post("/tgm/holders").mock(
            return_value=httpx.Response(401, json={"error": "bad key"})
        )

        await client.sm_holdings()
        with pytest.raises(client.NansenUnavailable):
            await client.tgm_holders("mintAddr")

    usage = client.get_credit_usage()
    assert usage["calls"] == 1, usage
    assert usage["by_endpoint"].get("/smart-money/holdings") == 1
    assert "/tgm/holders" not in usage["by_endpoint"], (
        "failed calls must not increment credit counter"
    )
    await client.aclose()
