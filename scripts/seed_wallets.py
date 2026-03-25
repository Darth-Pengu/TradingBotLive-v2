"""
Seed whale_wallets.json from Vybe Network + Nansen APIs.

Usage:
    python scripts/seed_wallets.py

Requires VYBE_API_KEY and NANSEN_API_KEY in .env (or environment).
Writes combined, deduplicated list to data/whale_wallets.json.
Falls back to known active whale addresses if both APIs return 0.
"""

import json
import os
import sys
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv()

VYBE_API_KEY = os.getenv("VYBE_API_KEY", "").strip()
NANSEN_API_KEY = os.getenv("NANSEN_API_KEY", "").strip()

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "whale_wallets.json")
TODAY = date.today().isoformat()

# Top Solana token mints to pull traders from
VYBE_TOKEN_MINTS = [
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",    # JUP
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
]

# Known active Solana whale addresses (fallback if APIs return 0)
FALLBACK_WALLETS = [
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
    "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH",
    "GUfCR9mK6azb9vcpsxgXyj7XRPAaGa35swRPRRKenTFG",
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",
    "CuieVDEDtLo7FypA9SbLM9saXFdb1dsshEkyErMqkRQq",
    "ArAQfbzsdwTAeDovfS7M3KFnbQRoBwFHhFzDt4PiABMa",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "Hax9LTgsQkze8VnNSCKdRzMSCBQBYhGPVxFHJQjfMGQe",
]


def fetch_vybe_wallets() -> list[dict]:
    """Fetch top traders from Vybe Network global endpoint."""
    if not VYBE_API_KEY:
        print("[vybe] VYBE_API_KEY not set -- skipping")
        return []

    url = "https://api.vybenetwork.xyz/v4/wallets/top-traders"
    headers = {"X-API-Key": VYBE_API_KEY}
    params = {"resolution": "30d", "limit": 100, "sortByDesc": "realizedPnlUsd"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"[vybe] HTTP {resp.status_code}")
            return []
        data = resp.json()
    except requests.RequestException as e:
        print(f"[vybe] API error: {e}")
        return []

    traders = data if isinstance(data, list) else data.get("data", data.get("results", []))
    if not isinstance(traders, list):
        print(f"[vybe] Unexpected response: {type(data)}")
        return []

    wallets = []
    for t in traders:
        address = t.get("ownerAddress", t.get("accountAddress", t.get("address", "")))
        if not address:
            continue
        metrics = t.get("metrics", t)
        win_rate = metrics.get("winRate")
        pnl = metrics.get("realizedPnlUsd", metrics.get("pnl"))
        score = min(100, int(win_rate)) if win_rate is not None else 75
        wallets.append({
            "address": address,
            "score": score,
            "label": "Top Trader",
            "source": "vybe",
            "win_rate": round(float(win_rate), 1) if win_rate is not None else None,
            "realized_pnl_30d": round(float(pnl), 2) if pnl is not None else None,
            "last_scored": TODAY,
            "active": True,
        })

    return wallets


def fetch_nansen_wallets() -> list[dict]:
    """Fetch smart money wallets on Solana from Nansen."""
    if not NANSEN_API_KEY:
        print("[nansen] NANSEN_API_KEY not set -- skipping")
        return []

    url = "https://api.nansen.ai/api/v1/smart-money/holdings"
    headers = {"apikey": NANSEN_API_KEY, "Content-Type": "application/json"}
    body = {
        "chains": ["solana"],
        "filters": {
            "include_smart_money_labels": ["Fund", "Smart Trader", "30D Smart Trader"],
        },
        "order_by": [{"field": "value_usd", "direction": "DESC"}],
        "pagination": {"page": 1, "per_page": 50},
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=15)
        if resp.status_code == 402:
            print("[nansen] 402 -- Pro subscription required, trying token-screener...")
            # Fallback: try token-screener which may be on free tier
            url2 = "https://api.nansen.ai/api/v1/token-screener"
            body2 = {"chains": ["solana"], "timeframe": "24h", "pagination": {"page": 1, "per_page": 20}}
            resp = requests.post(url2, headers=headers, json=body2, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[nansen] API error: {e}")
        return []

    holdings = data if isinstance(data, list) else data.get("data", data.get("result", []))
    if not isinstance(holdings, list):
        print(f"[nansen] Unexpected response: {type(data)}")
        return []

    wallets = []
    for h in holdings:
        address = h.get("owner", h.get("address", h.get("wallet_address", "")))
        if not address:
            continue
        labels = h.get("labels", h.get("smart_money_labels", []))
        label = labels[0] if isinstance(labels, list) and labels else "Smart Money"
        wallets.append({
            "address": address,
            "score": 75,
            "label": label,
            "source": "nansen",
            "win_rate": None,
            "realized_pnl_30d": None,
            "last_scored": TODAY,
            "active": True,
        })

    return wallets


def get_fallback_wallets() -> list[dict]:
    """Return hardcoded known active whale addresses as fallback."""
    return [{
        "address": addr,
        "score": 70,
        "label": "Known Whale",
        "source": "hardcoded",
        "win_rate": None,
        "realized_pnl_30d": None,
        "last_scored": TODAY,
        "active": True,
    } for addr in FALLBACK_WALLETS]


def merge_and_dedup(*sources: list[dict]) -> list[dict]:
    """Combine all lists, deduplicate by address. Later sources override earlier."""
    seen = {}
    for source_list in sources:
        for w in source_list:
            addr = w["address"]
            if addr in seen:
                w["label"] = f"{w['label']} / {seen[addr]['label']}"
                w["source"] = f"{w['source']}+{seen[addr]['source']}"
            seen[addr] = w
    return list(seen.values())


def main():
    print("Fetching whale wallets...\n")

    vybe_wallets = fetch_vybe_wallets()
    print(f"\n[vybe]   {len(vybe_wallets)} unique wallets")

    nansen_wallets = fetch_nansen_wallets()
    print(f"[nansen] {len(nansen_wallets)} wallets")

    combined = merge_and_dedup(nansen_wallets, vybe_wallets)

    if not combined:
        print("\nNo API wallets found -- using fallback list")
        combined = get_fallback_wallets()

    print(f"\n[total]  {len(combined)} unique wallets")

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"\nWrote {len(combined)} wallets to {OUTPUT_PATH}")

    sources = {}
    for w in combined:
        sources[w["source"]] = sources.get(w["source"], 0) + 1
    for src, count in sorted(sources.items()):
        print(f"  {src}: {count}")


if __name__ == "__main__":
    main()
