"""
ZMN Bot Environment Variable Audit
=====================================
Checks every env var the codebase references.
Shows present/missing, masked preview, format validation, and Railway warnings.

Usage: python scripts/env_audit.py
No API calls. Loads .env automatically.
"""

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── All env vars referenced in the codebase (auto-extracted) ──────────────

ENV_VARS = {
    # (var_name, required, services_that_use_it)
    "REDIS_URL": (True, "bot_core, dashboard_api, governance, market_health, ml_engine, signal_aggregator, signal_listener, treasury, paper_trader, risk_manager"),
    "DATABASE_URL": (True, "db (shared pool)"),
    "DATABASE_PRIVATE_URL": (False, "db (Railway fallback)"),
    "DATABASE_PUBLIC_URL": (False, "db (Railway fallback)"),
    "POSTGRES_URL": (False, "db (Railway fallback)"),
    "TEST_MODE": (True, "bot_core, execution, governance, market_health, ml_engine, signal_aggregator, signal_listener, treasury"),
    "TRADING_WALLET_ADDRESS": (True, "bot_core, execution, dashboard_api, treasury"),
    "TRADING_WALLET_PRIVATE_KEY": (True, "execution, treasury"),
    "HOLDING_WALLET_ADDRESS": (True, "dashboard_api, treasury"),
    "HELIUS_RPC_URL": (True, "bot_core, dashboard_api, execution, market_health, signal_aggregator, treasury"),
    "HELIUS_API_KEY": (True, "execution, signal_listener"),
    "HELIUS_STAKED_URL": (False, "execution, treasury"),
    "HELIUS_GATEKEEPER_URL": (False, "dashboard_api, execution, market_health, signal_aggregator, treasury"),
    "HELIUS_PARSE_TX_URL": (False, "dashboard_api, execution, signal_aggregator"),
    "HELIUS_PARSE_HISTORY_URL": (False, "signal_aggregator"),
    "HELIUS_WEBHOOK_SECRET": (False, "dashboard_api (HMAC verification)"),
    "JUPITER_API_KEY": (True, "bot_core, execution, dashboard_api, market_health, paper_trader"),
    "NANSEN_API_KEY": (False, "nansen_client, governance, signal_aggregator, bot_core, dashboard_api"),
    "ANTHROPIC_API_KEY": (False, "governance, signal_aggregator, dashboard_api"),
    "VYBE_API_KEY": (False, "signal_aggregator, seed_wallets"),
    "DISCORD_WEBHOOK_URL": (True, "bot_core, governance, signal_listener, treasury, dashboard_api"),
    "DISCORD_WEBHOOK_TREASURY": (False, "treasury"),
    "DISCORD_BOT_TOKEN": (False, "signal_listener, dashboard_api"),
    "DISCORD_NANSEN_CHANNEL_ID": (False, "signal_listener"),
    "DISCORD_OWNER_ID": (False, "signal_listener"),
    "DASHBOARD_SECRET": (True, "dashboard_api (JWT auth)"),
    "DASHBOARD_ALLOWED_IPS": (False, "dashboard_api (IP whitelist)"),
    "STARTING_CAPITAL_SOL": (False, "bot_core, risk_manager — default 20"),
    "APP_VERSION": (False, "dashboard_api — default v3.1.0"),
    "GOVERNANCE_MODEL": (False, "governance — default claude-sonnet-4-6"),
    "HAIKU_ENRICHMENT_ENABLED": (False, "signal_aggregator — default false"),
    "LOG_LEVEL": (False, "all services — default INFO"),
    "PORT": (False, "dashboard_api — default 8080"),
    "TREASURY_TRIGGER_SOL": (False, "dashboard_api — default 30.0"),
    "TREASURY_TARGET_SOL": (False, "dashboard_api — default 25.0"),
    "MIN_POSITION_SOL": (False, "risk_manager — default 0.10"),
    "ML_INCREMENTAL_INTERVAL": (False, "ml_engine — default 20"),
    "RUGCHECK_REJECT_THRESHOLD": (False, "signal_aggregator — default 2000"),
    "JITO_ENDPOINT": (False, "execution — default mainnet block-engine"),
    "RAILWAY_PUBLIC_DOMAIN": (False, "signal_listener (webhook URL)"),
    "RAILWAY_STATIC_URL": (False, "signal_listener (webhook URL fallback)"),
    "TS_SPD_ACTIVATION": (False, "risk_manager — default 15"),
    "TS_SPD_TRAIL": (False, "risk_manager — default 8"),
    "TS_ANL_ACTIVATION": (False, "risk_manager — default 25"),
    "TS_ANL_TRAIL": (False, "risk_manager — default 12"),
    "TS_WHL_ACTIVATION": (False, "risk_manager — default 20"),
    "TS_WHL_TRAIL": (False, "risk_manager — default 10"),
}

# ── Format validators ─────────────────────────────────────────────────────

def _validate(name: str, value: str) -> str | None:
    """Returns warning string if format is wrong, None if OK."""
    if not value:
        return None

    checks = {
        "REDIS_URL": lambda v: None if v.startswith("redis://") or v.startswith("rediss://") else "must start with redis:// or rediss://",
        "DATABASE_URL": lambda v: (
            "SQLite NOT supported on Railway — must be postgresql://" if v.startswith("sqlite")
            else None if v.startswith("postgresql://") or v.startswith("postgres://")
            else "must start with postgresql:// or postgres://"
        ),
        "HELIUS_RPC_URL": lambda v: None if "helius" in v.lower() and "api-key" in v.lower() else "should contain helius-rpc.com and api-key=",
        "TRADING_WALLET_ADDRESS": lambda v: None if 32 <= len(v) <= 44 else f"Solana pubkey should be 32-44 chars (got {len(v)})",
        "HOLDING_WALLET_ADDRESS": lambda v: None if 32 <= len(v) <= 44 else f"Solana pubkey should be 32-44 chars (got {len(v)})",
        "DISCORD_WEBHOOK_URL": lambda v: None if "discord.com/api/webhooks" in v else "should contain discord.com/api/webhooks",
        "ANTHROPIC_API_KEY": lambda v: None if v.startswith("sk-ant-") else "should start with sk-ant-",
        "TEST_MODE": lambda v: None if v.lower() in ("true", "false") else f"must be 'true' or 'false' (got '{v}')",
    }

    validator = checks.get(name)
    if validator:
        return validator(value)
    return None


def _mask(value: str) -> str:
    """Show first 4 chars + ... for non-empty values."""
    if not value:
        return "(empty)"
    if len(value) <= 4:
        return value[0] + "..."
    return value[:4] + "..."


def main():
    print("\n" + "=" * 70)
    print("  ZMN Bot — Environment Variable Audit")
    print("=" * 70)

    present = 0
    missing_required = []
    missing_optional = []
    warnings = []

    print(f"\n{'Variable':<35} {'Status':<10} {'Preview':<12} {'Services'}")
    print("-" * 95)

    for name, (required, services) in sorted(ENV_VARS.items()):
        value = os.getenv(name, "")
        status = "PRESENT" if value else "MISSING"
        preview = _mask(value) if value else "--"

        if value:
            present += 1
        elif required:
            missing_required.append(name)
        else:
            missing_optional.append(name)

        # Status coloring via prefix
        flag = "  " if value else "!!" if required else "  "
        print(f"{flag} {name:<33} {status:<10} {preview:<12} {services[:50]}")

        # Format validation
        warn = _validate(name, value)
        if warn:
            warnings.append((name, warn))
            print(f"   {'':33} {'':10} ^ FORMAT: {warn}")

    # ── Railway-specific warnings ─────────────────────────────────────────

    print(f"\n{'=' * 70}")
    print("  Railway-Specific Warnings")
    print(f"{'=' * 70}\n")

    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("sqlite"):
        print("  !! DATABASE_URL starts with sqlite — NOT supported on Railway.")
        print("     Railway auto-injects PostgreSQL. Delete manual DATABASE_URL override.\n")

    redis_url = os.getenv("REDIS_URL", "")
    if "localhost" in redis_url:
        print("  !! REDIS_URL points to localhost — will not work on Railway.")
        print("     Railway Redis plugin auto-injects the correct URL.\n")

    if not os.getenv("HELIUS_GATEKEEPER_URL"):
        print("  ** HELIUS_GATEKEEPER_URL missing — no fallback RPC for Helius.\n")

    anthropic = os.getenv("ANTHROPIC_API_KEY", "")
    if not anthropic:
        print("  ** ANTHROPIC_API_KEY blank — Haiku enrichment + governance agent disabled.")
        print("     This is expected if credits are exhausted.\n")

    haiku = os.getenv("HAIKU_ENRICHMENT_ENABLED", "false")
    if haiku.lower() != "true":
        print("  ** HAIKU_ENRICHMENT_ENABLED is off — Haiku signal enrichment disabled.")
        print("     Set to 'true' in Railway when credits are topped up.\n")

    if not os.getenv("HELIUS_API_KEY"):
        print("  !! HELIUS_API_KEY missing — Helius webhook registration will fail.\n")

    if not os.getenv("JUPITER_API_KEY"):
        print("  !! JUPITER_API_KEY missing — Jupiter swap + price API will return 401.\n")

    # ── Summary ───────────────────────────────────────────────────────────

    print(f"{'=' * 70}")
    print("  Summary")
    print(f"{'=' * 70}\n")
    total = len(ENV_VARS)
    print(f"  Total variables:    {total}")
    print(f"  Present:            {present}")
    print(f"  Missing (required): {len(missing_required)}")
    print(f"  Missing (optional): {len(missing_optional)}")
    print(f"  Format warnings:    {len(warnings)}")

    if missing_required:
        print(f"\n  REQUIRED BUT MISSING:")
        for name in missing_required:
            print(f"    !! {name}")

    # ── Railway raw env copy-paste block ──────────────────────────────────

    print(f"\n{'=' * 70}")
    print("  Railway Raw Env (copy-paste — fill REPLACE_ME values)")
    print(f"{'=' * 70}\n")

    for name in sorted(ENV_VARS.keys()):
        value = os.getenv(name, "")
        if value:
            # Mask secrets for display
            if any(s in name.upper() for s in ("KEY", "SECRET", "TOKEN", "PRIVATE", "PASSWORD")):
                display = _mask(value)
            else:
                display = value
            print(f"  {name}={display}")
        else:
            print(f"  {name}=REPLACE_ME")

    print()


if __name__ == "__main__":
    main()
