"""Tests for services/nansen_client_v2.py.

Two test groups:

1. **Contract tests** — one per wrapper. Each test asserts the OUTGOING body
   matches the shape verified against the live Nansen API during Session A'
   Phase 1 (2026-04-21). This guards against silent regressions to the buggy
   ``{"parameters": {...}}`` envelope pattern that Session A introduced and
   Session B's abort smoke test caught.

   Verified shapes (all three families use FLAT root body):
   - TGM: ``{chain, token_address}``
   - SM: ``{chains, pagination, ...}``
   - Profiler: ``{address, chain, date: {from, to}, ...}``

2. **Invariant tests** — orthogonal to payload shape:
   - Auth header is ``apikey`` (lowercase), NOT ``Authorization: Bearer``
   - 401 raises NansenUnavailable (terminal; no zero-sentinel dict leak)
   - 5xx retries then raises NansenUnavailable
   - Transport errors raise NansenUnavailable
   - Credit counter increments on 2xx only

A final regression-guard test asserts NO wrapper uses the nested-``parameters``
envelope — guaranteed by inspecting every outgoing body.
"""

from __future__ import annotations

import importlib
import json
import os
import sys

import httpx
import pytest
import respx

os.environ["NANSEN_API_KEY"] = "test-api-key-abc123"
os.environ["NANSEN_RETRY_ATTEMPTS"] = "2"
os.environ["NANSEN_RPS_LIMIT"] = "1000"


def _load_client():
    # Fresh import so env overrides apply and module-level singletons reset.
    if "services.nansen_client_v2" in sys.modules:
        del sys.modules["services.nansen_client_v2"]
    return importlib.import_module("services.nansen_client_v2")


# ==================== Invariant tests ====================


@pytest.mark.asyncio
async def test_auth_header_is_lowercase_apikey():
    client = _load_client()
    captured: dict[str, str] = {}

    def _capture(request: httpx.Request):
        for name, value in request.headers.raw:
            captured[name.decode("latin-1")] = value.decode("latin-1")
        return httpx.Response(200, json={"data": []})

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/smart-money/holdings").mock(side_effect=_capture)
        await client.sm_holdings()

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

    Crucially, no ``{}`` or ``{"data": []}`` zero-sentinel must leak to the
    caller — that would let callers silently treat absent Nansen data as zero,
    the exact behavior the Session A spec forbids.
    """
    client = _load_client()

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/tgm/flow-intelligence").mock(
            return_value=httpx.Response(500, text="upstream down")
        )

        result = None
        exc = None
        try:
            result = await client.tgm_flow_intel(
                "So11111111111111111111111111111111111111112"
            )
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
    client = _load_client()

    def _raise_connect(_request: httpx.Request):
        raise httpx.ConnectError("dns failure")

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/smart-money/netflow").mock(side_effect=_raise_connect)

        with pytest.raises(client.NansenUnavailable):
            await client.sm_netflow()

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


# ==================== Contract tests — TGM family ====================


@pytest.mark.asyncio
async def test_tgm_flow_intel_sends_flat_body():
    """TGM posts {chain, token_address} at body root. No 'parameters' envelope."""
    client = _load_client()
    captured: list[dict] = []

    def _capture(request: httpx.Request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"data": []})

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/tgm/flow-intelligence").mock(side_effect=_capture)
        await client.tgm_flow_intel(
            "So11111111111111111111111111111111111111112", chain="solana"
        )

    assert len(captured) == 1
    body = captured[0]
    assert "parameters" not in body, f"TGM must use flat body; got {body!r}"
    assert body == {
        "chain": "solana",
        "token_address": "So11111111111111111111111111111111111111112",
    }
    await client.aclose()


@pytest.mark.asyncio
async def test_tgm_who_bought_sold_sends_flat_body():
    client = _load_client()
    captured: list[dict] = []

    def _capture(request: httpx.Request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"data": []})

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/tgm/who-bought-sold").mock(side_effect=_capture)
        await client.tgm_who_bought_sold("mintAddr", chain="solana")

    body = captured[0]
    assert "parameters" not in body
    assert body == {"chain": "solana", "token_address": "mintAddr"}
    await client.aclose()


@pytest.mark.asyncio
async def test_tgm_holders_sends_flat_body():
    client = _load_client()
    captured: list[dict] = []

    def _capture(request: httpx.Request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"data": []})

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/tgm/holders").mock(side_effect=_capture)
        await client.tgm_holders("mintAddr", chain="solana")

    body = captured[0]
    assert "parameters" not in body
    assert body == {"chain": "solana", "token_address": "mintAddr"}
    await client.aclose()


# ==================== Contract tests — SM family ====================


@pytest.mark.asyncio
async def test_sm_dex_trades_sends_flat_body():
    """SM DEX trades posts {chains, filters, pagination, order_by} at body root."""
    client = _load_client()
    captured: list[dict] = []

    def _capture(request: httpx.Request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"data": []})

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/smart-money/dex-trades").mock(side_effect=_capture)
        await client.sm_dex_trades(value_usd_min=5000, limit=50)

    body = captured[0]
    assert "parameters" not in body, f"SM must use flat body; got {body!r}"
    assert body["chains"] == ["solana"]
    assert body["filters"]["include_smart_money_labels"] == [
        "Smart Trader",
        "Fund",
        "180D Smart Trader",
    ]
    assert body["filters"]["value_usd"]["min"] == 5000
    assert body["pagination"]["per_page"] == 50
    assert body["order_by"][0]["field"] == "block_time"
    assert body["order_by"][0]["direction"] == "DESC"
    await client.aclose()


@pytest.mark.asyncio
async def test_sm_netflow_sends_flat_body():
    client = _load_client()
    captured: list[dict] = []

    def _capture(request: httpx.Request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"data": []})

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/smart-money/netflow").mock(side_effect=_capture)
        await client.sm_netflow()

    body = captured[0]
    assert "parameters" not in body
    assert body["chains"] == ["solana"]
    assert body["pagination"]["per_page"] == 200
    assert body["order_by"][0]["field"] == "net_flow_24h_usd"
    await client.aclose()


@pytest.mark.asyncio
async def test_sm_holdings_sends_flat_body():
    client = _load_client()
    captured: list[dict] = []

    def _capture(request: httpx.Request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"data": []})

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/smart-money/holdings").mock(side_effect=_capture)
        await client.sm_holdings()

    body = captured[0]
    assert "parameters" not in body
    assert body == {
        "chains": ["solana"],
        "pagination": {"page": 1, "per_page": 200},
    }
    await client.aclose()


# ==================== Contract tests — Profiler family ====================


@pytest.mark.asyncio
async def test_profiler_pnl_sends_flat_body_with_date_envelope():
    """Profiler PnL summary posts {address, chain, date: {from, to}} flat."""
    client = _load_client()
    captured: list[dict] = []

    def _capture(request: httpx.Request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"data": []})

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/profiler/address/pnl-summary").mock(side_effect=_capture)
        await client.profiler_pnl(
            "walletAddr",
            chain="solana",
            date_from="2026-04-14",
            date_to="2026-04-21",
        )

    body = captured[0]
    assert "parameters" not in body, f"profiler must use flat body; got {body!r}"
    assert body == {
        "address": "walletAddr",
        "chain": "solana",
        "date": {"from": "2026-04-14", "to": "2026-04-21"},
    }
    await client.aclose()


@pytest.mark.asyncio
async def test_profiler_pnl_supplies_default_date_when_omitted():
    """When ``date_from``/``date_to`` are omitted, wrapper fills in 7-day window.

    Nansen rejects profiler requests without a ``date`` field (422). The
    wrapper must always send one; callers can override via kwargs.
    """
    client = _load_client()
    captured: list[dict] = []

    def _capture(request: httpx.Request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"data": []})

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/profiler/address/pnl-summary").mock(side_effect=_capture)
        await client.profiler_pnl("walletAddr")

    body = captured[0]
    assert "date" in body, f"date envelope always required on profiler; got {body!r}"
    assert set(body["date"].keys()) == {"from", "to"}
    # Date values are ISO dates (YYYY-MM-DD) — don't assert exact values
    # (test runs on different days); just format.
    for key in ("from", "to"):
        assert len(body["date"][key]) == 10 and body["date"][key][4] == "-", body
    await client.aclose()


@pytest.mark.asyncio
async def test_profiler_pnl_token_sends_flat_body_and_filters_client_side():
    """Per-token PnL wrapper: flat body (no server-side token filter) +
    client-side filter on the response.

    Nansen's ``/profiler/address/pnl`` does NOT accept a ``token_address``
    in the request body — verified via Phase-1 live probe. The wrapper
    sends ``{address, chain, date}`` only and filters the returned rows
    to match the caller's requested token.
    """
    client = _load_client()
    captured: list[dict] = []
    fake_response = {
        "pagination": {"page": 1, "per_page": 10, "is_last_page": True},
        "data": [
            {"token_address": "mintA", "realized_pnl_usd": 1.0},
            {"token_address": "mintB", "realized_pnl_usd": 2.0},
            {"token_address": "mintA", "realized_pnl_usd": 3.0},
        ],
    }

    def _capture(request: httpx.Request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=fake_response)

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/profiler/address/pnl").mock(side_effect=_capture)
        result = await client.profiler_pnl_token(
            "walletAddr",
            "mintA",
            chain="solana",
            date_from="2026-04-14",
            date_to="2026-04-21",
        )

    body = captured[0]
    assert "parameters" not in body
    # Outgoing body: no token_address (server-side filter not supported)
    assert body == {
        "address": "walletAddr",
        "chain": "solana",
        "date": {"from": "2026-04-14", "to": "2026-04-21"},
    }
    assert "token_address" not in body, (
        "Nansen /profiler/address/pnl rejects 'token_address' in body — "
        "filter must be applied client-side"
    )
    # Client-side filter worked: only mintA rows returned
    assert len(result["data"]) == 2
    assert all(r["token_address"] == "mintA" for r in result["data"])
    assert result["pagination"] == fake_response["pagination"]
    await client.aclose()


@pytest.mark.asyncio
async def test_profiler_transactions_sends_flat_body_with_date_envelope():
    """Profiler transactions posts {address, chain, date: {from, to}} flat."""
    client = _load_client()
    captured: list[dict] = []

    def _capture(request: httpx.Request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"data": []})

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        mock.post("/profiler/address/transactions").mock(side_effect=_capture)
        await client.profiler_transactions(
            "walletAddr",
            chain="solana",
            date_from="2026-04-20",
            date_to="2026-04-21",
        )

    body = captured[0]
    assert "parameters" not in body
    assert body == {
        "address": "walletAddr",
        "chain": "solana",
        "date": {"from": "2026-04-20", "to": "2026-04-21"},
    }
    # Also verify legacy flat date_from/date_to fields are NOT present —
    # Nansen uses the {date: {from, to}} envelope, not top-level date_from.
    assert "date_from" not in body
    assert "date_to" not in body
    await client.aclose()


# ==================== Regression guard ====================


@pytest.mark.asyncio
async def test_no_wrapper_uses_nested_parameters_envelope():
    """Regression guard: if any wrapper regresses to ``{"parameters": {...}}``
    the outgoing body will contain a ``parameters`` key and this test catches it.

    This is the single canonical guard for Session A's payload-shape bug —
    all 9 wrappers are covered in one pass.
    """
    client = _load_client()
    seen: list[tuple[str, dict]] = []

    def _capture(request: httpx.Request):
        path = request.url.path.replace("/api/v1", "")
        seen.append((path, json.loads(request.content)))
        return httpx.Response(200, json={"data": [], "pagination": {}})

    paths = [
        "/smart-money/dex-trades",
        "/smart-money/netflow",
        "/smart-money/holdings",
        "/tgm/flow-intelligence",
        "/tgm/who-bought-sold",
        "/tgm/holders",
        "/profiler/address/pnl-summary",
        "/profiler/address/pnl",
        "/profiler/address/transactions",
    ]

    with respx.mock(base_url="https://api.nansen.ai/api/v1") as mock:
        for p in paths:
            mock.post(p).mock(side_effect=_capture)

        await client.sm_dex_trades(value_usd_min=5000, limit=50)
        await client.sm_netflow()
        await client.sm_holdings()
        await client.tgm_flow_intel("mintAddr")
        await client.tgm_who_bought_sold("mintAddr")
        await client.tgm_holders("mintAddr")
        await client.profiler_pnl("walletAddr")
        await client.profiler_pnl_token("walletAddr", "mintAddr")
        await client.profiler_transactions("walletAddr")

    observed_paths = [p for p, _ in seen]
    assert observed_paths == paths, observed_paths

    for path, body in seen:
        assert "parameters" not in body, (
            f"regression: {path} sent nested 'parameters' envelope — "
            f"Nansen rejects this with 422. Body was: {body!r}"
        )

    await client.aclose()
