"""LIVE-FEE-CAPTURE-002 (Path B) — Helius parseTransactions helper.

Resolves on-chain reality for live trades. Returns native + token deltas
for the trading wallet, computed from `accountData[*].nativeBalanceChange`
(NOT `nativeTransfers` — that field only captures direct user-to-user
transfers like Jito tips, not swap proceeds via PDAs).

Returns None on any error; callers should fall back to Path A (_simulate_*
estimates).

Verified against id 6580 (entry_sig cG4DC2... + exit_sig 4bHzZZ...):
reconstruction = -0.094245 SOL == on-chain truth (within float precision).
See docs/audits/LIVE_FEE_CAPTURE_002_PATH_B_2026_05_01.md.
"""
import asyncio
import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


def _get_helius_url() -> str:
    return os.getenv("HELIUS_PARSE_TX_URL", "")


def _get_trading_wallet() -> str:
    return os.getenv("TRADING_WALLET_ADDRESS", "")


async def helius_parse_signature(
    signature: str,
    *,
    timeout_seconds: float = 5.0,
    retries: int = 2,
) -> Optional[dict]:
    """Parse a transaction signature via Helius parseTransactions.

    Returns:
        dict with keys:
          - 'signature': str (echoed)
          - 'fee_lamports': int (network fee)
          - 'native_delta_lamports': int (signed; for trading wallet)
          - 'token_deltas': dict[mint -> int] (raw token units, signed; for trading wallet)
          - 'success': bool (transactionError is None)
          - 'parse_method': 'helius_v1'
          - 'raw_response_size': int (bytes-ish, debugging)
        OR None on any error (timeout, 5xx, malformed, parse failure).

    Honors rate-limit backoff (1s -> 2s -> 4s -> ... -> 60s cap).
    Does NOT raise on parse failure — returns None.
    """
    url = _get_helius_url()
    wallet = _get_trading_wallet()
    if not url or not wallet:
        logger.debug("helius_parse_signature: env unset (HELIUS_PARSE_TX_URL or TRADING_WALLET_ADDRESS)")
        return None
    if not signature or signature.startswith("PAPER_"):
        return None

    payload = {"transactions": [signature]}
    backoff_s = 1.0
    last_err: Optional[str] = None

    for attempt in range(retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds),
                ) as resp:
                    if resp.status == 429:
                        last_err = "rate limited (429)"
                        await asyncio.sleep(min(backoff_s, 60.0))
                        backoff_s = min(backoff_s * 2, 60.0)
                        continue
                    if resp.status != 200:
                        last_err = f"HTTP {resp.status}"
                        return None
                    data = await resp.json()
                    if not data or not isinstance(data, list):
                        last_err = "empty/invalid response"
                        return None
                    tx = data[0]
                    if not isinstance(tx, dict):
                        last_err = "tx is not a dict"
                        return None

                    success = tx.get("transactionError") is None

                    native_delta = 0
                    token_deltas: dict = {}
                    for ad in tx.get("accountData") or []:
                        if ad.get("account") == wallet:
                            native_delta += int(ad.get("nativeBalanceChange", 0) or 0)
                        for tbc in ad.get("tokenBalanceChanges") or []:
                            if tbc.get("userAccount") != wallet:
                                continue
                            mint = tbc.get("mint")
                            ra = tbc.get("rawTokenAmount") or {}
                            try:
                                amt = int(ra.get("tokenAmount", "0") or 0)
                            except (TypeError, ValueError):
                                amt = 0
                            if mint:
                                token_deltas[mint] = token_deltas.get(mint, 0) + amt

                    return {
                        "signature": signature,
                        "fee_lamports": int(tx.get("fee", 0) or 0),
                        "native_delta_lamports": native_delta,
                        "token_deltas": token_deltas,
                        "success": success,
                        "parse_method": "helius_v1",
                        "raw_response_size": len(str(tx)),
                    }
        except asyncio.TimeoutError:
            last_err = "timeout"
            if attempt < retries:
                await asyncio.sleep(min(backoff_s, 60.0))
                backoff_s = min(backoff_s * 2, 60.0)
                continue
            break
        except Exception as e:
            last_err = f"exception: {type(e).__name__}: {e}"
            break

    if last_err:
        logger.warning("helius_parse_signature failed sig=%s err=%s", (signature or "")[:16], last_err)
    return None
