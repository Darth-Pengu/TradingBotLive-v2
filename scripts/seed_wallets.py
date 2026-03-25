"""
Seed whale_wallets.json from Vybe Network + Nansen APIs.

Usage:
    python scripts/seed_wallets.py

Requires VYBE_API_KEY and NANSEN_API_KEY in .env (or environment).
Writes combined, deduplicated list to data/whale_wallets.json.
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


def fetch_vybe_wallets() -> list[dict]:
    """Fetch top-performing Solana wallets from Vybe Network."""
    if not VYBE_API_KEY:
        print("[vybe] VYBE_API_KEY not set — skipping")
        return []

    url = "https://api.vybenetwork.com/v4/wallets/top-traders"
    headers = {"X-API-Key": VYBE_API_KEY}
    params = {"resolution": "30d", "limit": 100, "sortByDesc": "realizedPnlUsd"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[vybe] API error: {e}")
        return []

    # Response is a list or has a data/results key
    traders = data if isinstance(data, list) else data.get("data", data.get("results", []))
    if not isinstance(traders, list):
        print(f"[vybe] Unexpected response shape: {type(data)}")
        return []

    wallets = []
    for t in traders:
        address = t.get("accountAddress", t.get("address", ""))
        if not address:
            continue
        metrics = t.get("metrics", t)
        win_rate = metrics.get("winRate")
        pnl = metrics.get("realizedPnlUsd")
        # winRate is 0-100 from Vybe, use directly as score (capped)
        score = min(100, int(win_rate)) if win_rate is not None else 75
        wallets.append({
            "address": address,
            "score": score,
            "label": "Top Trader",
            "source": "vybe",
            "win_rate": round(win_rate, 1) if win_rate is not None else None,
            "realized_pnl_30d": round(pnl, 2) if pnl is not None else None,
            "last_scored": TODAY,
            "active": True,
        })

    return wallets


def fetch_nansen_wallets() -> list[dict]:
    """Fetch smart money wallets on Solana from Nansen."""
    if not NANSEN_API_KEY:
        print("[nansen] NANSEN_API_KEY not set — skipping")
        return []

    url = "https://api.nansen.ai/api/v1/smart-money/holdings"
    headers = {
        "apikey": NANSEN_API_KEY,
        "Content-Type": "application/json",
    }
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
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[nansen] API error: {e}")
        return []

    holdings = data if isinstance(data, list) else data.get("data", data.get("result", []))
    if not isinstance(holdings, list):
        print(f"[nansen] Unexpected response shape: {type(data)}")
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


def merge_and_dedup(vybe: list[dict], nansen: list[dict]) -> list[dict]:
    """Combine both lists, deduplicate by address. Vybe wins on conflicts (has richer data)."""
    seen: dict[str, dict] = {}

    # Nansen first so Vybe overwrites with richer data
    for w in nansen:
        seen[w["address"]] = w
    for w in vybe:
        addr = w["address"]
        if addr in seen:
            # Merge: keep Vybe score/stats, note both sources
            w["label"] = f"{w['label']} / {seen[addr]['label']}"
            w["source"] = "vybe+nansen"
        seen[addr] = w

    return list(seen.values())


def main():
    print("Fetching whale wallets...\n")

    vybe_wallets = fetch_vybe_wallets()
    print(f"[vybe]   {len(vybe_wallets)} wallets")

    nansen_wallets = fetch_nansen_wallets()
    print(f"[nansen] {len(nansen_wallets)} wallets")

    combined = merge_and_dedup(vybe_wallets, nansen_wallets)
    print(f"\n[total]  {len(combined)} unique wallets after dedup")

    if not combined:
        print("\nNo wallets found — check your API keys.")
        sys.exit(1)

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"\nWrote {len(combined)} wallets to {OUTPUT_PATH}")

    # Summary by source
    sources = {}
    for w in combined:
        sources[w["source"]] = sources.get(w["source"], 0) + 1
    for src, count in sorted(sources.items()):
        print(f"  {src}: {count}")


if __name__ == "__main__":
    main()
