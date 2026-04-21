"""
Nansen API v2 client — production-grade parallel module (Session A).

This module is INTENTIONALLY SEPARATE from services/nansen_client.py. The old
client is preserved and still used by the 9 existing callers. This v2 module
is called by nothing yet; Session B migrates callers.

Design notes (per session spec):
- Base URL: https://api.nansen.ai/api/v1
- Auth header: ``apikey: <KEY>`` (lowercase, NOT ``Authorization: Bearer``)
- All requests POST with JSON body
- Single module-level httpx.AsyncClient (HTTP/2, bounded timeouts + limits)
- tenacity retry (5 attempts, exponential jitter)
- Per-second token bucket at 15 rps (under the 20 rps ceiling)
- Async semaphore at 10 concurrent
- Never return a zero-sentinel dict on failure — raise NansenUnavailable so
  callers can emit ``nansen_available=False`` + null (None) features that the
  feature builder treats as missing (not zero). Feature-builder change is
  Session B scope; the client's contract is "raise, don't fake".
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger("nansen_client_v2")

NANSEN_BASE_URL = os.getenv("NANSEN_BASE_URL", "https://api.nansen.ai/api/v1")
NANSEN_API_KEY = os.getenv("NANSEN_API_KEY", "")
NANSEN_RPS_LIMIT = float(os.getenv("NANSEN_RPS_LIMIT", "15"))
NANSEN_MAX_CONCURRENT = int(os.getenv("NANSEN_MAX_CONCURRENT", "10"))
NANSEN_RETRY_ATTEMPTS = int(os.getenv("NANSEN_RETRY_ATTEMPTS", "5"))


# ----------------------------- exceptions ---------------------------------


class NansenUnavailable(Exception):
    """Raised when the Nansen API is unreachable or returned a terminal error.

    Callers MUST NOT fall back to a zero-sentinel dict. Instead, propagate or
    emit ``nansen_available=False`` and null (None) features so the feature
    builder can encode them as missing (not zero) once Session B lands.
    """


class NansenServerError(Exception):
    """Retryable 5xx response from Nansen."""


class NansenRateLimit(Exception):
    """Retryable 429 response. ``retry_after`` is seconds to sleep (may be 0)."""

    def __init__(self, retry_after: float, message: str = ""):
        super().__init__(message or f"rate limited, retry_after={retry_after}")
        self.retry_after = retry_after


# ----------------------------- rate limiter --------------------------------


class _TokenBucket:
    """Simple monotonic-clock token bucket. One bucket per process."""

    def __init__(self, rate_per_sec: float):
        self.rate = rate_per_sec
        self.capacity = rate_per_sec
        self._tokens = rate_per_sec
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                needed = (1.0 - self._tokens) / self.rate
                await asyncio.sleep(needed)


# ----------------------------- client singleton ----------------------------


_client_lock = asyncio.Lock()
_client: httpx.AsyncClient | None = None
_bucket = _TokenBucket(NANSEN_RPS_LIMIT)
_semaphore = asyncio.Semaphore(NANSEN_MAX_CONCURRENT)


@dataclass
class _CreditTracker:
    calls: int = 0
    estimated_credits: int = 0
    by_endpoint: dict[str, int] = field(default_factory=dict)


_credits = _CreditTracker()


# Per-endpoint credit-cost estimate. Nansen's published costs vary per plan;
# these are conservative defaults logged at INFO so the caller can reconcile
# against Nansen's dashboard. Override via env if needed.
_ENDPOINT_COSTS = {
    "/smart-money/dex-trades": 10,
    "/smart-money/netflow": 5,
    "/smart-money/holdings": 10,
    "/tgm/flow-intelligence": 5,
    "/tgm/who-bought-sold": 5,
    "/tgm/holders": 5,
    "/profiler/address/pnl-summary": 5,
    "/profiler/address/pnl": 5,
    "/profiler/address/transactions": 10,
}


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                _client = httpx.AsyncClient(
                    base_url=NANSEN_BASE_URL,
                    http2=True,
                    timeout=httpx.Timeout(connect=3.0, read=15.0, write=5.0, pool=5.0),
                    limits=httpx.Limits(
                        max_connections=50, max_keepalive_connections=25
                    ),
                    headers={
                        "apikey": NANSEN_API_KEY,
                        "accept": "application/json",
                        "content-type": "application/json",
                    },
                )
    return _client


async def aclose() -> None:
    """Close the module-level client. Test-only/shutdown hook."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_credit_usage() -> dict[str, Any]:
    """Return a snapshot of the credit-usage counter for observability."""
    return {
        "calls": _credits.calls,
        "estimated_credits": _credits.estimated_credits,
        "by_endpoint": dict(_credits.by_endpoint),
    }


def _credit_cost(path: str) -> int:
    return _ENDPOINT_COSTS.get(path, 5)


# ----------------------------- core POST -----------------------------------


async def _post_once(path: str, payload: dict) -> dict:
    """Single HTTP POST. Translates status codes to retryable exceptions.

    5xx -> NansenServerError (retry)
    429 -> NansenRateLimit (retry, honor Retry-After)
    401/403/404/400 -> NansenUnavailable (terminal; callers encode as missing)
    2xx -> json body
    """
    client = await _get_client()
    logger.debug("nansen POST %s body=%s", path, payload)
    try:
        resp = await client.post(path, json=payload)
    except httpx.HTTPError as e:
        # Network-level failure. tenacity will decide if retry-worthy.
        logger.info("nansen %s network_error=%s", path, type(e).__name__)
        raise

    status = resp.status_code
    est = _credit_cost(path)
    logger.info("nansen %s status=%d est_credits=%d", path, status, est)

    # Log first 500 bytes at DEBUG. Avoid .text (which decodes full body).
    try:
        snippet = resp.content[:500]
        logger.debug("nansen %s response_head=%r", path, snippet)
    except Exception:
        pass

    if status == 429:
        retry_after = 0.0
        try:
            retry_after = float(resp.headers.get("Retry-After", "0") or 0)
        except (TypeError, ValueError):
            retry_after = 0.0
        raise NansenRateLimit(retry_after, message=f"429 on {path}")

    if 500 <= status < 600:
        raise NansenServerError(f"{status} on {path}")

    if 400 <= status < 500:
        # Terminal client errors — auth, bad request, not found. Do not retry.
        raise NansenUnavailable(f"{status} on {path}: {resp.text[:200]}")

    # success
    _credits.calls += 1
    _credits.estimated_credits += est
    _credits.by_endpoint[path] = _credits.by_endpoint.get(path, 0) + 1

    try:
        return resp.json()
    except ValueError as e:
        raise NansenUnavailable(f"non-json body on {path}: {e}") from e


async def _post(path: str, payload: dict) -> dict:
    """Retrying POST with rate-limit + concurrency bound.

    Retries on network errors, ReadTimeout, 5xx, and 429 (honoring Retry-After).
    Terminal 4xx (auth, 404, 400) raise NansenUnavailable and are NOT retried.
    """
    async def _sleep_for_rate_limit(exc: BaseException) -> None:
        # Callback: sleep for ``Retry-After`` on a 429 before tenacity retries.
        if isinstance(exc, NansenRateLimit) and exc.retry_after > 0:
            await asyncio.sleep(min(exc.retry_after, 30.0))

    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(NANSEN_RETRY_ATTEMPTS),
            wait=wait_exponential_jitter(initial=0.5, max=30),
            retry=retry_if_exception_type(
                (
                    httpx.TransportError,
                    httpx.ReadTimeout,
                    NansenServerError,
                    NansenRateLimit,
                )
            ),
            # reraise=False so that on final failure tenacity raises RetryError
            # and we translate to NansenUnavailable below. With reraise=True the
            # original retryable exception bubbles up and the caller never sees
            # the unified NansenUnavailable contract.
            reraise=False,
        ):
            with attempt:
                # On a 429 from the previous attempt, honor Retry-After before
                # the next wait. tenacity's wait is applied additionally; the
                # sleep here just ensures we respect the server's hint.
                last = attempt.retry_state.outcome
                if last is not None and last.failed:
                    exc = last.exception()
                    await _sleep_for_rate_limit(exc)  # type: ignore[arg-type]
                await _bucket.acquire()
                async with _semaphore:
                    return await _post_once(path, payload)
    except RetryError as e:
        # All retries exhausted.
        last = e.last_attempt.exception() if e.last_attempt else None
        raise NansenUnavailable(f"retries exhausted on {path}: {last!r}") from e
    except NansenUnavailable:
        # Terminal 4xx surfaced by _post_once — don't double-wrap.
        raise

    # Should be unreachable — tenacity either returns the success value from
    # inside the `with attempt:` block or raises. Defensive:
    raise NansenUnavailable(f"unexpected retry flow on {path}")


# ----------------------------- wrappers ------------------------------------


def _order(field: str, direction: str = "DESC") -> list[dict[str, str]]:
    return [{"field": field, "direction": direction}]


def _page(page: int = 1, per_page: int = 200) -> dict[str, int]:
    return {"page": page, "per_page": per_page}


def _default_date_window(days: int = 7) -> dict[str, str]:
    """Default date window for profiler endpoints that require a ``date`` field.

    Returns ``{"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}`` with ``to`` = today
    (UTC) and ``from`` = today - ``days``. Profiler endpoints reject requests
    without this field; callers may override via explicit ``date_from`` /
    ``date_to`` kwargs on the wrappers.
    """
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    return {"from": start.isoformat(), "to": end.isoformat()}


async def sm_dex_trades(
    chains: list[str] | None = None,
    value_usd_min: int = 1000,
    labels: list[str] | None = None,
    limit: int = 200,
) -> dict:
    """Smart Money DEX trades (POST /smart-money/dex-trades).

    Body shape: flat root. Verified via Phase-1 live probe on
    ``/smart-money/holdings`` (2026-04-21) — Nansen SM endpoints reject
    the ``{"parameters": {...}}`` envelope with 422.
    """
    chains = chains or ["solana"]
    labels = labels or ["Smart Trader", "Fund", "180D Smart Trader"]
    payload = {
        "chains": chains,
        "filters": {
            "include_smart_money_labels": labels,
            "value_usd": {"min": value_usd_min},
        },
        "pagination": _page(per_page=limit),
        "order_by": _order("block_time"),
    }
    return await _post("/smart-money/dex-trades", payload)


async def sm_netflow(chains: list[str] | None = None, limit: int = 200) -> dict:
    """Smart Money net-flow (POST /smart-money/netflow), ordered by 24h flow."""
    chains = chains or ["solana"]
    payload = {
        "chains": chains,
        "pagination": _page(per_page=limit),
        "order_by": _order("net_flow_24h_usd"),
    }
    return await _post("/smart-money/netflow", payload)


async def sm_holdings(chains: list[str] | None = None, limit: int = 200) -> dict:
    """Smart Money holdings (POST /smart-money/holdings)."""
    chains = chains or ["solana"]
    payload = {
        "chains": chains,
        "pagination": _page(per_page=limit),
    }
    return await _post("/smart-money/holdings", payload)


async def tgm_flow_intel(token_address: str, chain: str = "solana") -> dict:
    """Token Granular Metrics — flow intelligence (POST /tgm/flow-intelligence).

    Body shape: flat root. Verified via Phase-1 live probe (2026-04-21) —
    Nansen returns 422 ``"body -> chain" missing`` if wrapped in ``parameters``.
    """
    payload = {
        "chain": chain,
        "token_address": token_address,
    }
    return await _post("/tgm/flow-intelligence", payload)


async def tgm_who_bought_sold(token_address: str, chain: str = "solana") -> dict:
    """TGM — who-bought-sold (POST /tgm/who-bought-sold)."""
    payload = {
        "chain": chain,
        "token_address": token_address,
    }
    return await _post("/tgm/who-bought-sold", payload)


async def tgm_holders(token_address: str, chain: str = "solana") -> dict:
    """TGM — holders (POST /tgm/holders)."""
    payload = {
        "chain": chain,
        "token_address": token_address,
    }
    return await _post("/tgm/holders", payload)


async def profiler_pnl(
    address: str,
    chain: str = "solana",
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Address PnL summary (POST /profiler/address/pnl-summary).

    Body shape: flat root, with ``date: {from, to}`` envelope. Required by
    Nansen — omitting it returns 422 ``"body -> date" missing``. Defaults to
    last 7 days when ``date_from`` / ``date_to`` are omitted.
    """
    date = (
        {"from": date_from, "to": date_to}
        if (date_from and date_to)
        else _default_date_window(days=7)
    )
    payload: dict[str, Any] = {
        "address": address,
        "chain": chain,
        "date": date,
    }
    return await _post("/profiler/address/pnl-summary", payload)


async def profiler_pnl_token(
    address: str,
    token_address: str,
    chain: str = "solana",
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Per-token PnL for an address (POST /profiler/address/pnl).

    Nansen's ``/profiler/address/pnl`` returns a paginated list of all tokens
    traded by ``address`` within the date window; it does NOT support a
    server-side ``token_address`` filter. This wrapper preserves the
    token-specific contract by applying a client-side filter to the response.

    Body shape: flat root, with ``date: {from, to}`` envelope (required).
    Defaults to last 7 days when ``date_from`` / ``date_to`` are omitted.

    Response: same top-level shape as the raw Nansen response (``data``
    list + ``pagination``) but ``data`` is filtered to rows matching
    ``token_address``. If no rows match, ``data`` is empty.
    """
    date = (
        {"from": date_from, "to": date_to}
        if (date_from and date_to)
        else _default_date_window(days=7)
    )
    payload: dict[str, Any] = {
        "address": address,
        "chain": chain,
        "date": date,
    }
    raw = await _post("/profiler/address/pnl", payload)
    rows = raw.get("data") or []
    filtered = [r for r in rows if r.get("token_address") == token_address]
    return {"data": filtered, "pagination": raw.get("pagination", {})}


async def profiler_transactions(
    address: str,
    chain: str = "solana",
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Address transactions (POST /profiler/address/transactions).

    Body shape: flat root, with ``date: {from, to}`` envelope (required).
    Defaults to last 7 days when ``date_from`` / ``date_to`` are omitted.
    """
    date = (
        {"from": date_from, "to": date_to}
        if (date_from and date_to)
        else _default_date_window(days=7)
    )
    payload: dict[str, Any] = {
        "address": address,
        "chain": chain,
        "date": date,
    }
    return await _post("/profiler/address/transactions", payload)


__all__ = [
    "NansenUnavailable",
    "NansenServerError",
    "NansenRateLimit",
    "aclose",
    "get_credit_usage",
    "sm_dex_trades",
    "sm_netflow",
    "sm_holdings",
    "tgm_flow_intel",
    "tgm_who_bought_sold",
    "tgm_holders",
    "profiler_pnl",
    "profiler_pnl_token",
    "profiler_transactions",
]
