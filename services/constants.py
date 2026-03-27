"""
ZMN Bot Shared Constants
=========================
Module-level constants imported by signal_listener.py, dashboard_api.py,
and signal_aggregator.py to avoid duplication.
"""

# Known CEX deposit addresses for exit signal detection.
# Extend this list as new exchange deposit addresses are identified.
CEX_ADDRESSES = {
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9",  # Binance hot wallet
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",  # FTX (legacy)
    "ASTyfSima4LLAdDgoFGkgqoKowG1LZFDr9fAQrg7iaJZ",  # Bybit
}

# Native SOL mint address — filter this out of token transfer signals
SOL_MINT = "So11111111111111111111111111111111111111112"

# Helius webhook transaction types to subscribe to
HELIUS_WEBHOOK_TX_TYPES = [
    "SWAP",               # Core whale trade detection
    "TRANSFER",           # CEX transfers and accumulation moves
    "TOKEN_MINT",         # New token launches from tracked wallets
    "ADD_LIQUIDITY",      # Whale adding LP = accumulation signal
    "WITHDRAW_LIQUIDITY", # Whale removing LP = exit signal
    "CREATE_POOL",        # Whale creating new pool = strong insider signal
    "BURN",               # LP burn / exit confirmation
    "CLOSE_ACCOUNT",      # Whale fully exited a token position
]
