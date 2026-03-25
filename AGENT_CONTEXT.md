# ZMN Bot — Agent Context Document
**Version:** 3.0  
**Last Updated:** March 2026  
**Changes from v2.0:**
- Execution layer completely replaced: ToxiBot/Telethon → PumpPortal Local API + Jupiter Ultra API
- Agent governance layer added (Section 10) — separate scheduled process running Claude API
- Treasury sweep service added (Section 11) — auto-transfers excess SOL to holding wallet
- Env vars, Procfile, requirements updated throughout

**Purpose:** Complete context for an autonomous coding agent. Read this entire file before writing a single line of code. Do not rely on memory of previous versions — this document supersedes all prior versions.

---

## 1. Project Overview

ZMN Bot is a **Solana memecoin trading bot** with three concurrent AI personalities, ML scoring, real-time market health detection, an agent governance layer, and a web dashboard. It executes trades directly on-chain via two clean REST APIs (no Telegram dependency), validates tokens through Rugcheck, and monitors the market via multiple on-chain and off-chain data feeds.

**Deployment:** Railway.app  
**Language:** Python 3.11+ (async/await throughout — no sync/blocking calls anywhere)  
**DB:** SQLite (`toxibot.db`) via `aiosqlite`  
**Queue:** Redis for inter-service communication  
**Dashboard:** HTML/CSS/JS (Satoshi template — needs repurposing per Section 13)  
**Starting capital:** 20+ SOL  
**Holding wallet:** Separate Phantom wallet — receives swept profits above 30 SOL threshold

---

## 2. Repository Structure

```
/
├── AGENT_CONTEXT.md              ← this file (always read first)
├── requirements.txt              ← see Section 20 for full list
├── .gitignore
├── Procfile                      ← Railway process definitions
├── railway.toml                  ← Railway service config
├── .env.example                  ← all required env vars, no values
│
├── services/
│   ├── signal_listener.py        ← PumpPortal WS + GeckoTerminal + DexPaprika
│   ├── signal_aggregator.py      ← dedup, score, ML gate, route to personalities
│   ├── market_health.py          ← daily/intraday market condition detector
│   ├── bot_core.py               ← trading engine, personality coordinator
│   ├── ml_engine.py              ← CatBoost + LightGBM ensemble
│   ├── risk_manager.py           ← quarter-Kelly, drawdown scaling, position sizing
│   ├── execution.py              ← PumpPortal Local + Jupiter Ultra + Jito + retry
│   ├── treasury.py               ← SOL sweep: trading wallet → holding wallet
│   ├── governance.py             ← Claude API governance agent (scheduled)
│   └── dashboard_api.py          ← WebSocket server feeding live data to dashboard
│
├── data/
│   ├── whale_wallets.json        ← curated wallet list with scores
│   ├── market_baselines.json     ← rolling 7-day baseline cache
│   └── governance_notes.md       ← agent writes recommendations here for review
│
├── db/
│   └── migrations/               ← numbered SQL migration files
│
└── dashboard/
    ├── dashboard.html            ← Bot Overview
    ├── dashboard-analytics.html  ← Performance & ML
    └── dashboard-wallet.html     ← Live Trade Feed
```

**Files that do NOT yet exist and must be built:**
All files under `services/`, `data/`, `db/migrations/`, Procfile, railway.toml, .env.example.

---

## 3. The Three Bot Personalities

All three run **concurrently** and share a single ML learning pipeline. Never disable one to run another. If two personalities would enter the same token simultaneously, reduce the second entry's position by 50%. Never allow more than 2 personalities in the same token at once.

---

### Speed Demon ⚡ (Ultra-Early Hunter)

**Mission:** First-mover on brand new pump.fun bonding curve tokens using tiered entries.

**Execution method:** PumpPortal Local API (`/api/trade-local`) — bonding curve only.

**Signal sources:**
- PumpPortal `subscribeNewToken` WebSocket (primary — sub-100ms)
- GeckoTerminal `/networks/solana/new_pools` (backup — poll 60s)
- DexPaprika SSE stream (tertiary)

**Tiered entry system:**

| Tier | Window | ML threshold | Position size | Key conditions |
|------|--------|-------------|--------------|----------------|
| Alpha Snipe | 0–30 sec | ≥ 80% | 0.5–1 SOL | No bundle, diverse wallets, high liq velocity |
| Confirmation | 30 sec–3 min | ≥ 65% | 0.3–0.5 SOL | Positive dev signals, healthy holders |
| Post-Grad Dip | 5–15 min post-migration | ≥ 70% | 0.5–1 SOL DCA × 2 | Token graduated, mcap $30–50K, dip confirmed |

**Entry hard filters (reject if ANY fail):**
- `liquidity_sol > 5`
- Bonding curve progress NOT in 30–55% range (KOTH dump zone) — unless ML ≥ 85%
- `bundle_detected == False`
- `bundled_supply_pct < 10%`
- Dev sold <20% of holdings in first 2 minutes
- Creator has <3 dead tokens in last 30 days
- `bot_transaction_ratio < 0.60`
- `fresh_wallet_ratio < 0.40`

**Exit strategy (staged — not a single TP):**
- Sell **40%** at 2× — recover investment
- Sell **30%** at 3× — lock profit
- Keep **30%** as moon bag with 30% trailing stop
- Time-based exit: if no positive movement in 5 minutes from entry, close entire position
- Signal-based hard exits (immediate): dev wallet sells >20%, bundle dump detected, buyer diversity collapses, Rugcheck risk score spikes

**Stop loss:** 50% absolute floor for alpha snipe. Once in profit >30%, switch to 30% trailing stop.

---

### Analyst 🔍 (Data-Driven Researcher)

**Mission:** Medium-term positions (5 min – 2 hours) on confirmed tokens using multi-source signals.

**Execution method:** Jupiter Ultra API for post-graduation tokens (`/swap/v1/`). PumpPortal Local API for tokens still on the bonding curve (when Analyst enters pre-graduation).

**Signal sources:**
- BitQuery GraphQL streams
- GeckoTerminal trending pools
- Vybe Network token analytics
- Nansen Smart Money flows (if subscribed)

**Signal stack (by predictive weight):**
1. Liquidity velocity (2× weight in ML) — SOL per trade in first 30 sec
2. Holder concentration — top 10 wallets combined <25%
3. Volume acceleration — 3×+ increase in any 15-min window
4. Unique buyer growth — >20 new holders in first 30 min
5. Buy/sell ratio — >1.2× = healthy, <1.0 = reject

**Entry criteria:**
- `liquidity_sol > 10`
- 2+ independent sources agree on signal
- ML score ≥ 70%
- Token NOT already held by Speed Demon (if yes, wait 5 min and halve position)
- Bonding curve progress in 20–30% OR >60% (avoid 30–60% KOTH zone)

**Exit strategy:**
- Sell **30%** at 1.5×
- Sell **30%** at 2.5×
- Sell **25%** via 25% trailing stop from peak
- Keep **15%** as moon bag — 40% trailing stop, 2-hour maximum hold

**Stop loss:** 30% from entry. Time-based: exit if no movement in 30 minutes.

---

### Whale Tracker 🐋 (Smart Money Follower)

**Mission:** Copy-trade systematically identified profitable wallets.

**Execution method:** Jupiter Ultra API for graduated tokens. PumpPortal Local API for bonding curve tokens that whales are buying.

**Signal sources:**
- PumpPortal `subscribeAccountTrade` (tracked wallets list)
- Helius webhooks on tracked wallet addresses
- Vybe Network labeled wallets
- Nansen Smart Money Dashboard (weekly refresh)

**Wallet scoring pipeline (maintain 50–100 wallets, score weekly):**

| Dimension | Weight | Minimum threshold |
|-----------|--------|-------------------|
| Win rate | 25% | >55% |
| Avg ROI per trade | 20% | >50% |
| Trade frequency (per week) | 15% | 5–50 |
| Realized PnL (SOL/month) | 15% | >10 SOL |
| Consistency (low std dev) | 15% | — |
| Hold period alignment | 10% | 5 min – 4 hr |

**Auto-disqualify wallets with ANY of:** win rate >90%, hold time <30s, all profit from one token, wallet age <7 days, >200 trades/day.

**Entry criteria:**
- Wallet score ≥ 70/100
- `holders > 100`
- ML score ≥ 70%
- 3+ tracked whales in same token within 1 hour → treat as maximum confidence, enter immediately

**Copy-trade delay by tier:** Top 10 wallets (score ≥ 85) → 0–5 seconds. Mid-tier (70–85) → 15–30 seconds.

**Accumulation vs. distribution:** If tracked whale sends >10% of token position to a CEX address → immediately exit or reduce copy position by 50%.

**Exit strategy:**
- Sell **30%** at 2×
- Sell **40%** at 5×
- Keep **30%** as runner — 25% trailing stop, 4-hour maximum hold
- Immediate exit if whale starts selling (detected via subscribeAccountTrade)

---

## 4. Risk Management (Hard Rules — Never Override in Code)

### Quarter-Kelly position sizing

```python
# Kelly: f* = (b * p - q) / b   Quarter Kelly: f = f* * 0.25
KELLY_PARAMS = {
    "speed_demon":   {"win_rate": 0.35, "avg_win": 2.00, "avg_loss": 0.50},  # ~4.7% quarter Kelly
    "analyst":       {"win_rate": 0.45, "avg_win": 1.00, "avg_loss": 0.30},  # ~7.1% quarter Kelly
    "whale_tracker": {"win_rate": 0.40, "avg_win": 1.50, "avg_loss": 0.40},  # ~6.0% quarter Kelly
}

# Final position = quarterKelly × volatilityRatio × drawdownMultiplier × streakMultiplier × timeOfDayMultiplier
# Cap at per-personality max AND portfolio limits below. Never skip a multiplier.
```

### Hard position limits

```python
MAX_POSITION_PCT = {
    "speed_demon":   0.03,   # 3% of portfolio (~0.6 SOL on 20 SOL)
    "analyst":       0.05,   # 5% (~1.0 SOL)
    "whale_tracker": 0.04,   # 4% (~0.8 SOL)
}
MIN_POSITION_SOL            = 0.10   # Below this, fees destroy edge
MAX_CONCURRENT_PER_PERSONALITY = 3
MAX_CONCURRENT_WHALE        = 2
PORTFOLIO_MAX_EXPOSURE      = 0.25   # 25% total — never exceed
RESERVE_FLOOR_PCT           = 0.60   # Always keep 60% in reserve
DAILY_LOSS_LIMIT_SOL        = 1.0    # 5% of 20 SOL — triggers EMERGENCY_STOP
CORRELATION_HAIRCUT         = 0.70   # pump.fun tokens ~70% correlated
```

### Drawdown-based position scaling

```python
DRAWDOWN_MULTIPLIERS = {
    (0.00, 0.05):  1.00,
    (0.05, 0.10):  0.75,
    (0.10, 0.15):  0.50,
    (0.15, 0.20):  0.25,
    (0.20, 1.00):  0.00,   # >20% drawdown: STOP ALL TRADING
}
CONSECUTIVE_LOSS_MULTIPLIERS = {0: 1.0, 1: 1.0, 2: 0.85, 3: 0.65, 4: 0.50, 5: 0.25}
```

### Time-of-day multipliers

```python
TIME_OF_DAY_MULTIPLIERS = {
    (0,  4):  0.70,   # Asia
    (4,  8):  0.55,   # Dead zone
    (8,  12): 0.90,   # EU opens
    (12, 17): 1.00,   # Peak: EU+US overlap
    (17, 21): 0.90,   # US afternoon
    (21, 24): 0.70,   # Declining
}
WEEKEND_MULTIPLIER = 0.70   # Fri eve–Sun: lower volume + concentrated rug risk
```

### EMERGENCY_STOP triggers

When ANY of these fire → halt all three personalities simultaneously, cancel pending orders, send Discord alert, log reason, require manual restart:
- `daily_pl_sol <= -1.0`
- `portfolio_drawdown_pct >= 0.20`
- Network: veryHigh priority fees >50M microlamports for >10 consecutive minutes
- RUG CASCADE: >10 tokens dropped >80% in same 5-minute window
- SOL price drops >10% in 24h
- Treasury sweep fails 3× in a row (possible wallet compromise — halt and alert)

---

## 5. Execution Layer (v3.0 — PumpPortal Local + Jupiter Ultra)

**The Telethon/ToxiBot approach is completely removed. All execution goes through two official REST APIs. No Telegram dependency anywhere in the execution path.**

---

### Primary: PumpPortal Local API (bonding curve tokens)

Used by: Speed Demon (all tiers), Analyst/Whale Tracker (pre-graduation tokens only).

```
Endpoint: POST https://pumpportal.fun/api/trade-local
Fee: 0.5% per trade (calculated before slippage)
Custody: Full — API builds the transaction, YOU sign and send it
Key feature: Supports pump, raydium, pump-amm, launchlab, raydium-cpmm, bonk, auto
```

**Implementation pattern:**
```python
import aiohttp
from solders.transaction import VersionedTransaction
from solders.keypair import Keypair

async def execute_pumpportal(
    action: str,          # "buy" or "sell"
    mint: str,            # token contract address
    amount_sol: float,
    slippage_pct: int,
    priority_fee_sol: float,
    pool: str = "auto"
) -> str:
    payload = {
        "publicKey": TRADING_WALLET_PUBLIC_KEY,
        "action": action,
        "mint": mint,
        "amount": amount_sol,
        "denominatedInSol": "true",
        "slippage": slippage_pct,
        "priorityFee": priority_fee_sol,
        "pool": pool
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://pumpportal.fun/api/trade-local",
            json=payload
        ) as resp:
            if resp.status != 200:
                raise ExecutionError(f"PumpPortal error: {resp.status}")
            tx_bytes = await resp.read()

    # Sign with trading wallet keypair (key loaded from env, never hardcoded)
    keypair = Keypair.from_base58_string(TRADING_WALLET_PRIVATE_KEY)
    tx = VersionedTransaction.deserialize(tx_bytes)
    tx.sign([keypair])

    # Send via Helius staked RPC (better landing rate than public RPC)
    signature = await helius_rpc.send_transaction(tx)
    return signature
```

**Slippage config for PumpPortal:**
```python
PUMPPORTAL_SLIPPAGE = {
    "alpha_snipe":   25,   # 0–30 sec entries, high volatility
    "confirmation":  15,   # 30 sec–3 min entries
    "post_grad_dip": 10,   # post-graduation dip entries
    "sell":          10,   # sells
}
```

---

### Secondary: Jupiter Ultra API (graduated/AMM tokens)

Used by: Analyst (primarily), Whale Tracker (primarily), Speed Demon (post-graduation Tier 3 entries when pool is deep enough).

```
Endpoint: https://lite-api.jup.ag/swap/v1/
Fee: 0% protocol fee — only Solana network fees
Custody: Full non-custodial — you sign all transactions
MEV protection: ShadowLane private transaction routing built in
Key advantage: Best routing across all Raydium/Orca/PumpSwap/Meteora pools
Does NOT handle: pump.fun bonding curve tokens — use PumpPortal for those
```

**Implementation pattern:**
```python
import aiohttp

async def execute_jupiter_ultra(
    input_mint: str,      # "So11111111111111111111111111111111111111112" for SOL
    output_mint: str,     # token mint address
    amount_lamports: int,
    slippage_bps: int
) -> str:
    # Step 1: Get quote
    async with aiohttp.ClientSession() as session:
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount_lamports,
            "slippageBps": slippage_bps,
            "onlyDirectRoutes": False,
        }
        async with session.get(
            "https://lite-api.jup.ag/swap/v1/quote", params=params
        ) as resp:
            quote = await resp.json()

        # Step 2: Get swap transaction
        swap_payload = {
            "quoteResponse": quote,
            "userPublicKey": TRADING_WALLET_PUBLIC_KEY,
            "wrapAndUnwrapSol": True,
            "computeUnitPriceMicroLamports": await get_dynamic_priority_fee(),
        }
        async with session.post(
            "https://lite-api.jup.ag/swap/v1/swap",
            json=swap_payload
        ) as resp:
            swap_data = await resp.json()

    # Step 3: Sign and send
    import base64
    from solders.transaction import VersionedTransaction
    tx_bytes = base64.b64decode(swap_data["swapTransaction"])
    tx = VersionedTransaction.deserialize(tx_bytes)
    keypair = Keypair.from_base58_string(TRADING_WALLET_PRIVATE_KEY)
    tx.sign([keypair])
    signature = await helius_rpc.send_transaction(tx)
    return signature
```

**Slippage config for Jupiter Ultra:**
```python
JUPITER_SLIPPAGE_BPS = {
    "graduated_deep":    50,    # 0.5% — pools >$1M liquidity
    "graduated_medium":  150,   # 1.5% — pools $100K–$1M
    "graduated_shallow": 350,   # 3.5% — pools <$100K
}
```

---

### Routing decision: which API to use

```python
def choose_execution_api(token: Token) -> str:
    if token.pool in ("pump", "pump-amm") and token.bonding_curve_progress < 1.0:
        return "pumpportal"   # Still on bonding curve — must use PumpPortal
    elif token.pool in ("raydium", "raydium-cpmm", "orca", "meteora", "pumpswap"):
        return "jupiter"      # Graduated to AMM pool — use Jupiter Ultra
    else:
        return "pumpportal"   # Default to PumpPortal with pool="auto"
```

---

### Jito MEV protection (wrap all PumpPortal transactions)

```python
JITO_ENDPOINT = "https://mainnet.block-engine.jito.wtf/api/v1/bundles"
JITO_DONTFRONT_PUBKEY = "jitodontfront111111111111111111111111111111"

JITO_TIPS_LAMPORTS = {
    "normal":       1_000_000,    # 0.001 SOL
    "competitive":  10_000_000,   # 0.01 SOL
    "frenzy_snipe": 100_000_000,  # 0.1 SOL — hard maximum, never exceed
}
# Add JITO_DONTFRONT_PUBKEY as read-only account on every swap instruction
# Jupiter Ultra has MEV protection built in — no Jito wrap needed for Jupiter trades
```

---

### Transaction retry config

```python
RETRY_CONFIG = {
    "max_retries":      5,
    "initial_delay_ms": 500,
    "backoff_factor":   1.5,
    "escalate_fee":     True,    # bump priority fee tier on each retry
    "preflight":        True,    # enable on attempt 1, skip on retries 2+
    "commitment":       "confirmed",
    "encoding":         "base64",
}
```

---

## 6. Treasury Sweep Service (`services/treasury.py`)

**Purpose:** Automatically transfer excess SOL from the trading wallet to the holding wallet, preventing catastrophic loss of all capital if a trade goes catastrophically wrong or the bot is compromised.

### Rules (hard-coded — never make these configurable at runtime)

```python
TREASURY_RULES = {
    "trigger_threshold_sol": 30.0,   # Only sweep when trading wallet exceeds this
    "target_balance_sol":    25.0,   # Leave this much in trading wallet after sweep
    "min_transfer_sol":       1.0,   # Never transfer less than this (prevents dust sweeps)
    "holding_wallet":        HOLDING_WALLET_ADDRESS,  # From env — never hardcoded
    "check_interval_seconds": 300,   # Poll every 5 minutes
    "max_retries":            3,     # Retry failed sweeps up to 3 times
    "sweep_priority_fee":     0.000005,  # Low priority — this is not time-sensitive
}
```

### Sweep logic

```python
async def run_treasury_sweep():
    """
    Run continuously. Every 5 minutes:
    1. Check trading wallet SOL balance (use Helius RPC getBalance)
    2. If balance > 30 SOL:
       a. Calculate transfer amount = balance - 25.0 SOL
       b. If transfer_amount < 1.0 SOL: skip (below minimum transfer threshold)
       c. Build SOL transfer transaction (SystemProgram.transfer)
       d. Sign with trading wallet keypair
       e. Send via Helius RPC (NOT Jito — this is a simple SOL transfer, low priority)
       f. Log to SQLite: timestamp, amount_swept, trading_balance_before, trading_balance_after
       g. Send Discord notification: "Treasury sweep: {amount} SOL → holding wallet. Trading balance: {after} SOL"
    3. If sweep fails: log error, increment failure counter
    4. If 3 consecutive failures: trigger EMERGENCY_STOP and alert Discord
       (consecutive failures may indicate wallet compromise or RPC issue)
    """
    pass  # Agent implements this
```

### Sweep transaction implementation

```python
from solders.system_program import transfer, TransferParams
from solders.transaction import Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey

async def execute_treasury_sweep(amount_sol: float) -> str:
    amount_lamports = int(amount_sol * 1_000_000_000)
    trading_keypair = Keypair.from_base58_string(TRADING_WALLET_PRIVATE_KEY)
    holding_pubkey = Pubkey.from_string(HOLDING_WALLET_ADDRESS)

    ix = transfer(TransferParams(
        from_pubkey=trading_keypair.pubkey(),
        to_pubkey=holding_pubkey,
        lamports=amount_lamports
    ))

    blockhash = await helius_rpc.get_latest_blockhash()
    tx = Transaction(
        recent_blockhash=blockhash.value.blockhash,
        fee_payer=trading_keypair.pubkey(),
        instructions=[ix]
    )
    tx.sign([trading_keypair])
    signature = await helius_rpc.send_transaction(tx)
    return str(signature)
```

### Sweep dashboard display

The dashboard must show a **Treasury panel** on `dashboard.html`:
- Trading wallet current balance (SOL)
- Holding wallet current balance (SOL — read-only query, no private key needed)
- Sweep threshold indicator (progress bar: current balance vs 30 SOL trigger)
- Last sweep: timestamp + amount
- Total swept to date (SOL)
- Sweep history (last 10 sweeps)

### Security notes

- `HOLDING_WALLET_ADDRESS` is a **public key only** — never put the holding wallet's private key anywhere in the system
- The bot can only transfer TO the holding wallet, never from it
- Holding wallet private key stays in Phantom, accessed manually by the owner only
- The sweep is one-directional by design — even if the trading bot is fully compromised, the attacker can only drain 25 SOL (trading balance floor), not the accumulated holdings

---

## 7. Agent Governance Layer (`services/governance.py`)

**Purpose:** A separate scheduled process that calls the Anthropic Claude API to perform reasoning-level oversight that deterministic rules cannot handle — wallet scoring, anomaly diagnosis, strategy parameter recommendations. It never touches trade execution.

### What the governance agent does (and does not do)

**Does:**
- Weekly: Re-score whale wallet list using Vybe/Nansen data, write updated `whale_wallets.json`
- Daily: Interpret composite market health score and write a plain-English daily briefing to `governance_notes.md`
- On drawdown event: Diagnose what went wrong (bad signal? bad market? parameter issue?) and write recommendations
- On 3+ consecutive losses per personality: Suggest specific parameter adjustments (tighter stops, higher ML threshold, etc.)
- On anomalous token patterns: Flag unusual activity for human review
- Monthly: Write a performance report summarising what's working and what isn't

**Does NOT:**
- Make live trade decisions
- Write directly to any config that affects live execution without human review
- Override EMERGENCY_STOP
- Modify `MAX_WALLET_EXPOSURE`, `DAILY_LOSS_LIMIT_SOL`, or position sizing hard caps
- Automatically deploy any code changes

### Implementation

```python
import anthropic
import json
from datetime import datetime

GOVERNANCE_SCHEDULE = {
    "wallet_rescore":     "weekly",    # Every Monday 02:00 UTC
    "daily_briefing":     "daily",     # Every day 06:00 UTC
    "drawdown_diagnosis": "triggered", # On drawdown event from Redis pub/sub
    "loss_streak_review": "triggered", # On 3+ consecutive losses
    "monthly_report":     "monthly",   # First of month 06:00 UTC
}

async def run_governance_task(task_type: str, context_data: dict):
    """
    Calls Claude API (claude-sonnet-4-6) with relevant data.
    Writes output to governance_notes.md and/or whale_wallets.json.
    Never writes to execution config directly.
    """
    client = anthropic.AsyncAnthropic()

    system_prompt = """You are the governance agent for ToxiBot, a Solana memecoin trading bot.
    Your role is strategic oversight — you analyse performance data, score whale wallets,
    and make recommendations. You never make live trading decisions.
    Write clearly and concisely. All output will be reviewed by the bot owner before any
    parameter changes are applied. Flag anything unusual. Be direct about problems."""

    user_prompt = build_governance_prompt(task_type, context_data)

    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": user_prompt}]
    )

    output = message.content[0].text
    await write_governance_output(task_type, output, context_data)
    await notify_discord(f"Governance: {task_type} complete — check governance_notes.md")
```

### Governance prompts by task type

```python
def build_governance_prompt(task_type: str, context: dict) -> str:
    if task_type == "wallet_rescore":
        return f"""
Review the following whale wallet performance data from the past 7 days and provide
an updated score (0–100) for each wallet. Remove wallets that no longer meet minimum
thresholds. Suggest any new wallets from the top trader lists that should be added.

Current wallet list: {json.dumps(context['current_wallets'], indent=2)}
Performance data (7 days): {json.dumps(context['performance_data'], indent=2)}
Vybe top trader data: {json.dumps(context['vybe_data'], indent=2)}

Output: Valid JSON array matching the whale_wallets.json schema. Nothing else.
"""

    elif task_type == "daily_briefing":
        return f"""
Write a concise daily briefing for the ToxiBot owner. Cover:
1. Yesterday's performance (P/L, win rate, best/worst trade per personality)
2. Current market condition and whether the HIBERNATE/DEFENSIVE/NORMAL/AGGRESSIVE/FRENZY
   mode seems correct given what you see in the data
3. Any anomalies or concerns worth flagging
4. One specific recommendation if something looks off

Data: {json.dumps(context, indent=2)}

Be direct. No fluff. Max 300 words.
"""

    elif task_type == "drawdown_diagnosis":
        return f"""
ToxiBot has hit a significant drawdown. Analyse the recent trade history and diagnose
the root cause. Was this a market condition problem, a signal quality problem, a position
sizing problem, or something else? Be specific about which trades caused the most damage
and why.

Drawdown details: {json.dumps(context['drawdown_info'], indent=2)}
Recent trades (last 48h): {json.dumps(context['recent_trades'], indent=2)}
Market conditions during drawdown: {json.dumps(context['market_conditions'], indent=2)}
Signal sources that triggered losing trades: {json.dumps(context['signal_sources'], indent=2)}

Provide: (1) root cause diagnosis, (2) specific parameter changes to consider,
(3) whether trading should resume or stay paused. Be direct.
"""

    elif task_type == "loss_streak_review":
        return f"""
{context['personality']} has had {context['consecutive_losses']} consecutive losses.
Review the losing trades and determine whether this is:
a) Bad luck in a volatile market (no action needed — resume at reduced sizing)
b) A signal quality issue (specific signal sources to stop trusting temporarily)
c) A parameter issue (specific thresholds to adjust)
d) A market regime change (the personality's strategy isn't suited to current conditions)

Losing trades: {json.dumps(context['losing_trades'], indent=2)}
Current parameters: {json.dumps(context['parameters'], indent=2)}

Provide: diagnosis + specific recommendation. One paragraph max.
"""

    elif task_type == "monthly_report":
        return f"""
Write a monthly performance report for ToxiBot. Include:
1. Overall P/L and Sharpe ratio
2. Per-personality breakdown (Speed Demon, Analyst, Whale Tracker)
3. ML model accuracy trend
4. Best performing signal sources
5. Worst performing signal sources (consider dropping)
6. Treasury sweep summary (total swept to holding wallet)
7. Top 3 recommendations for next month

Data: {json.dumps(context, indent=2)}
"""
    return ""
```

### Governance output handling

```python
async def write_governance_output(task_type: str, output: str, context: dict):
    timestamp = datetime.utcnow().isoformat()

    if task_type == "wallet_rescore":
        # Parse JSON output and write to whale_wallets.json
        # IMPORTANT: Write to whale_wallets_pending.json first
        # Bot owner must manually rename to whale_wallets.json to activate
        # This prevents auto-activation of AI-generated wallet changes
        updated_wallets = json.loads(output)
        with open("data/whale_wallets_pending.json", "w") as f:
            json.dump(updated_wallets, f, indent=2)
        # Notify owner to review and approve
        await notify_discord(
            "Whale wallet rescore complete. Review data/whale_wallets_pending.json "
            "and rename to whale_wallets.json to activate. Changes NOT yet live."
        )
    else:
        # All other outputs → append to governance_notes.md
        with open("data/governance_notes.md", "a") as f:
            f.write(f"\n\n---\n## {task_type} — {timestamp}\n\n{output}\n")
```

### Governance triggers via Redis

```python
# Bot core publishes these events to Redis when thresholds are hit
GOVERNANCE_TRIGGERS = {
    "drawdown:significant":    "drawdown_diagnosis",  # drawdown > 10%
    "streak:loss":             "loss_streak_review",   # 3+ consecutive losses/personality
}
# Governance service subscribes to these channels and fires the appropriate Claude API call
```

---

## 8. Market Health Detection (`services/market_health.py`)

### Market modes and thresholds

| Mode | Pump.fun 24h vol | Graduation rate | Solana DEX vol | Effect |
|------|-----------------|----------------|---------------|--------|
| HIBERNATE | <$50M | <0.5% | <$1.5B | No new positions |
| DEFENSIVE | $50M–$100M | 0.5–0.8% | $1.5B–$2.5B | 0.5× sizing, tighter stops |
| NORMAL | $100M–$500M | 0.8–1.0% | $2B–$4B | Full operation |
| AGGRESSIVE | $200M–$500M | >1.0% | >$4B | 1.25× sizing |
| FRENZY | >$500M | >1.5% | >$6B | 1.5× sizing (watch for reversal) |

Publish current mode to Redis pub/sub channel `market:mode` — all services subscribe and immediately apply multipliers on mode change.

### Daily composite sentiment score (0–100)

```python
sentiment_score = (
    cfgi_fear_greed_index          * 0.30 +
    graduation_rate_z_score_scaled * 0.25 +
    sol_24h_change_scaled          * 0.20 +
    dex_volume_z_score_scaled      * 0.15 +
    launch_rate_z_score_scaled     * 0.10
)
```

### Intraday real-time checks (every 5 minutes)

```python
# Rug cascade
rugged = count_tokens_dropped(pct=0.80, window_minutes=5)
if rugged > 5:  trigger_rug_alert()     # halt new entries
if rugged > 10: trigger_emergency_halt() # exit all positions

# SOL price shock (check every 60 seconds)
if sol_change_1h < -0.05:  halt_new_entries()
if sol_change_24h < -0.10: trigger_emergency_stop()

# Network congestion (check every 30 seconds)
if helius_priority_fee["veryHigh"] > 50_000_000:  # 50M microlamports
    halt_trading("network_congested")
```

### Market health data sources

- DefiLlama: `GET https://api.llama.fi/overview/dexs?chain=solana`
- CFGI: `GET https://cfgi.io/api/solana-fear-greed-index/1d`
- SOL price: Jupiter Price API (free)
- Network fees: Helius `getPriorityFeeEstimate`
- Token launch rate: Count PumpPortal `subscribeNewToken` events per window

---

## 9. Data API Stack

### Existing APIs (keep)
| API | Cost | Primary use |
|-----|------|-------------|
| Helius | $49/mo | RPC, webhooks, priority fee estimation, staked tx landing |
| BitQuery | Free tier | DEX analytics, volume, holder data, creator history |
| PumpPortal | Free data / 0.5% trades | WebSocket signals + trade execution |
| Jupiter | Free | Ultra swap API + price data |
| Rugcheck | Free | Token safety scoring |
| Dexscreener | Free | Token metadata backup |

### New APIs (add)
| API | Cost | Primary use |
|-----|------|-------------|
| Vybe Network | Free (4 req/min) | Labeled wallets, whale wallet scoring |
| GeckoTerminal | Free (30 req/min) | New pool detection, trending, OHLCV |
| DexPaprika | Free (SSE) | Tertiary signal stream |
| DefiLlama | Free | Market health — Solana DEX volume |
| CFGI | Free | Solana Fear & Greed Index |
| Nansen Pro | $49/mo optional | Smart money tracking, wallet PnL leaderboards |
| Birdeye Lite | $39/mo optional | Trending tokens, holder analytics |

### Dropped completely
- **Telethon** — no longer needed for execution
- **ToxiBot (@toxi_solana_bot)** — replaced by PumpPortal Local + Jupiter Ultra
- All Telegram session management code

---

## 10. Environment Variables (Complete — v3.0)

```bash
# === BLOCKCHAIN ===
HELIUS_API_KEY=                    # helius.dev — Developer tier $49/mo
HELIUS_RPC_URL=                    # https://mainnet.helius-rpc.com/?api-key=...
JITO_ENDPOINT=https://mainnet.block-engine.jito.wtf/api/v1/bundles

# === TRADING WALLETS ===
TRADING_WALLET_PRIVATE_KEY=        # Base58 private key — NEVER commit, env only
TRADING_WALLET_ADDRESS=            # Public key of trading wallet
HOLDING_WALLET_ADDRESS=            # Public key ONLY — no private key needed/allowed

# === TREASURY ===
TREASURY_TRIGGER_SOL=30.0          # Sweep when trading wallet exceeds this
TREASURY_TARGET_SOL=25.0           # Leave this much after sweep
TREASURY_MIN_TRANSFER_SOL=1.0      # Minimum single transfer amount

# === DATA APIS ===
BITQUERY_API_KEY=                  # bitquery.io
VYBE_API_KEY=                      # vybenetwork.xyz (free tier)
NANSEN_API_KEY=                    # nansen.ai Pro $49/mo (optional)

# === GOVERNANCE ===
ANTHROPIC_API_KEY=                 # From console.anthropic.com — for governance agent
GOVERNANCE_MODEL=claude-sonnet-4-6 # Model to use for governance tasks

# === ALERTS ===
DISCORD_WEBHOOK_URL=               # Discord webhook for alerts + daily briefings
DISCORD_WEBHOOK_TREASURY=          # Separate channel for treasury sweep notifications

# === INFRASTRUCTURE ===
REDIS_URL=                         # Railway Redis plugin
DATABASE_URL=sqlite:///toxibot.db
DASHBOARD_SECRET=                  # JWT secret for dashboard auth

# === RUNTIME ===
ENVIRONMENT=development            # 'development' or 'production'
TEST_MODE=true                     # true = detect signals, never execute trades
STARTING_CAPITAL_SOL=20
LOG_LEVEL=INFO

# === NO LONGER NEEDED (removed in v3.0) ===
# TELEGRAM_API_ID — removed
# TELEGRAM_API_HASH — removed
# TELEGRAM_SESSION — removed
# TELEGRAM_SIGNAL_CHANNELS — removed
# TOXI_BOT_USERNAME — removed
```

---

## 11. Signal Stack Architecture (v3.0)

```
Layer 1 — On-chain primary (self-owned, zero Telegram dependency)
  ├── PumpPortal WebSocket: wss://pumpportal.fun/api/data
  │     subscribeNewToken        → Speed Demon primary feed
  │     subscribeAccountTrade    → Whale Tracker (tracked wallets)
  │     subscribeMigration       → graduation events
  ├── GeckoTerminal new_pools    → Speed Demon backup (poll 60s)
  ├── DexPaprika SSE stream      → tertiary signal feed
  ├── Helius webhooks            → large wallet movements
  ├── BitQuery GraphQL streams   → volume, holders, dev wallet, creator history
  ├── Vybe Network               → labeled wallets, smart money
  └── Rugcheck                   → per-token safety gate

Layer 2 — Optional external signal channels (supplementary only)
  └── GeckoTerminal trending + Vybe top traders as confirmation signals
      (Telethon/Telegram channels removed entirely in v3.0)

Layer 3 — Signal aggregator
  ├── Deduplicates by token address within 60-second window
  ├── Multi-source confidence: base 50 + 15 per additional source
  ├── Applies market mode multiplier (HIBERNATE → skip all)
  ├── Applies bonding curve filter (reject 30–55% KOTH zone for Speed Demon)
  └── Routes through ML gate before forwarding to execution
```

---

## 12. ML Scoring System (v2.0 features — unchanged from v2)

**Model:** CatBoost + LightGBM ensemble. `auto_class_weights="Balanced"`. Retrain weekly. 7-day sliding window. Min 50 samples before first train, 200 before production.

**Key features (26 total):** See v2.0 Section 7 for full feature vector. Highest-weight features: `liquidity_velocity` (2×), `bonding_curve_progress` (2×), `buy_sell_ratio_5min` (2×), `dev_wallet_hold_pct` (strong negative predictor), `bundle_detected` (strong negative predictor).

**ML thresholds:**
```python
ML_THRESHOLDS = {
    "speed_demon":   65,   # FRENZY mode: −5. DEFENSIVE mode: +10
    "analyst":       70,
    "whale_tracker": 70,
}
```

---

## 13. Dashboard Repurposing

**dashboard.html → Bot Overview**
- SOL trading balance + holding wallet balance (read-only)
- Treasury sweep panel: current balance, threshold progress bar (vs 30 SOL), last sweep, total swept
- Bot personality leaderboard (Speed Demon / Analyst / Whale Tracker)
- Market mode indicator (HIBERNATE / DEFENSIVE / NORMAL / AGGRESSIVE / FRENZY)
- EMERGENCY STOP button (red, requires confirmation)
- CFGI Fear & Greed gauge

**dashboard-analytics.html → Performance & ML + Governance**
- Sharpe ratio per bot, max drawdown chart, ML confidence distribution
- Governance notes panel: latest entry from `governance_notes.md`
- Whale wallet pending review notification (when `whale_wallets_pending.json` exists)
- Monthly report when available

**dashboard-wallet.html → Live Trade Feed**
- Incoming signal feed (pre-ML gate)
- Active positions with unrealised P/L
- Recent closed trades log (last 50)
- Whale wallet activity panel

**All pages:** Remove ADA/ETH/BTC/MetaMask/Coinbase/Avalanche. Phantom and Glow only. Apply TRON glassmorphism CSS.

---

## 14. Railway Deployment

**Procfile:**
```
web: python services/dashboard_api.py
signal_listener: python services/signal_listener.py
market_health: python services/market_health.py
signal_aggregator: python services/signal_aggregator.py
bot_core: python services/bot_core.py
ml_engine: python services/ml_engine.py
treasury: python services/treasury.py
governance: python services/governance.py
```

**Startup order:** `market_health` must publish to Redis before `bot_core` processes any signals. `bot_core` waits up to 60 seconds for `market:mode` key in Redis before starting.

**Resource notes:**
- `governance.py` makes Anthropic API calls — costs money per call. Guard all calls with try/except and log token usage.
- `treasury.py` is the most critical safety service — give it `restart: always` and monitor its logs closely.
- `ml_engine.py` retrains weekly — watch for Railway memory spikes during retraining.

---

## 15. Build Priority Order

**Phase 1 — Core infrastructure**
1. `services/signal_listener.py` — PumpPortal + GeckoTerminal + DexPaprika (no Telethon)
2. `services/market_health.py` — health check + Redis broadcast
3. `.env.example`, `Procfile`, `railway.toml`

**Phase 2 — Execution (replaces ToxiBot/Telethon entirely)**
4. `services/execution.py` — PumpPortal Local API + Jupiter Ultra API + Jito wrap + retry
5. `services/risk_manager.py` — quarter-Kelly + drawdown scaling + time-of-day

**Phase 3 — Safety and intelligence**
6. `services/treasury.py` — SOL sweep to holding wallet
7. `services/ml_engine.py` — CatBoost + LightGBM ensemble
8. `services/signal_aggregator.py` — dedup + score + ML gate + route
9. `data/whale_wallets.json` — initial list (empty schema)

**Phase 4 — Bot core and governance**
10. `services/bot_core.py` — personality coordinator + EMERGENCY_STOP
11. `services/governance.py` — Claude API governance agent
12. `services/dashboard_api.py` — WebSocket server

**Phase 5 — Dashboard**
13. All three HTML dashboard pages

---

## 16. Testing Approach

- `ENVIRONMENT=development` + `TEST_MODE=true` before any live trading
- Treasury sweep: test with 0.001 SOL transfers first, verify holding wallet receives them
- Governance: test with `max_tokens=100` first to verify API calls work before full prompts
- Paper trade minimum 48 hours before enabling live execution
- Start live with 0.1 SOL test positions, scale to full sizing after 20+ successful trades
- Verify EMERGENCY_STOP halts all three personalities simultaneously before going live

---

## 17. Key Constraints (Inviolable)

- **Never commit `.env`, `*.session`, `toxibot.db`, or any private key file**
- **Never hardcode any private key or API key**
- **TEST_MODE=true means zero trades — not reduced trades**
- **25% portfolio exposure is the absolute ceiling — no code path can exceed it**
- **EMERGENCY_STOP halts all three personalities simultaneously — never per-personality**
- **Daily loss limit: 1.0 SOL / 5% of portfolio (whichever is lower)**
- **Jito tip never exceeds 0.1 SOL**
- **Treasury sweep is one-directional: trading wallet → holding wallet only**
- **Holding wallet private key NEVER enters the system — public key only**
- **Governance agent output is advisory — no auto-deployment of parameter changes**
- **`whale_wallets_pending.json` requires manual review and rename before activation**
- **Never enter a token in the 30–55% bonding curve KOTH zone unless ML score ≥ 85%**
- **Maximum 2 personalities in any single token simultaneously**
- **No Telethon, no Telegram session files, no @toxi_solana_bot calls — anywhere**

---

## 18. First Agent Task (Copy-Paste Ready)

```
Read AGENT_CONTEXT.md in full before writing any code.

Build Phase 1 + Phase 2:

PHASE 1 — Signal infrastructure:

1. services/signal_listener.py
   - PumpPortal WebSocket (wss://pumpportal.fun/api/data):
     subscribeNewToken, subscribeAccountTrade (wallets from whale_wallets.json),
     subscribeMigration, subscribeTokenTrade
   - GeckoTerminal polling every 60s: GET /networks/solana/new_pools (backup)
   - DexPaprika SSE: /v1/solana/events/stream (tertiary)
   - All signals → Redis LPUSH "signals:raw" as JSON:
     {mint, source, timestamp, age_seconds, raw_data, signal_type}
   - Exponential backoff reconnect: 1s base, ×2 each attempt, 60s max
   - TEST_MODE=true: log signals, do NOT push to Redis
   - NO Telethon. NO Telegram. Nothing related to messaging.

2. services/market_health.py
   - Daily 00:00 UTC: query DefiLlama, CFGI, Jupiter price
   - Compute composite sentiment score and market mode
   - Publish to Redis pub/sub "market:mode"
   - Cache to Redis key "market:health" (5-min TTL)
   - Intraday every 5 minutes: rug cascade detection, SOL price shock, congestion
   - Publish EMERGENCY events to "alerts:emergency" Redis channel

3. services/treasury.py
   - Poll Helius getBalance on TRADING_WALLET_ADDRESS every 5 minutes
   - If balance > TREASURY_TRIGGER_SOL (30.0):
     transfer_amount = balance - TREASURY_TARGET_SOL (25.0)
     if transfer_amount >= TREASURY_MIN_TRANSFER_SOL (1.0): execute sweep
   - Use SystemProgram.transfer via Helius RPC (NOT Jito — low priority)
   - Log every sweep to SQLite treasury_sweeps table
   - Send Discord notification on each sweep
   - On 3 consecutive failures: publish to "alerts:emergency" and halt
   - TEST_MODE=true: log what WOULD be swept, do not execute transfer

PHASE 2 — Execution layer:

4. services/execution.py
   - PumpPortal Local API: POST https://pumpportal.fun/api/trade-local
     - Build payload, receive serialized tx, sign with trading keypair, send via Helius RPC
     - Wrap in Jito bundle with dontfront pubkey for MEV protection
     - Slippage config from Section 5 of AGENT_CONTEXT.md
   - Jupiter Ultra API: GET quote + POST swap from https://lite-api.jup.ag/swap/v1/
     - MEV protection built in — no Jito wrap needed
     - Slippage config from Section 5 of AGENT_CONTEXT.md
   - choose_execution_api() routing function from Section 5
   - Retry logic: 5 attempts, 500ms initial, 1.5× backoff, escalate fee tier on each retry
   - TEST_MODE=true: build and log transaction details, do NOT sign or send

5. .env.example — all vars from Section 10, descriptions, no values
6. Procfile — all 8 services from Section 14
7. data/whale_wallets.json — empty array [] with schema comment
8. data/governance_notes.md — empty file with header comment

Do NOT build signal_aggregator.py, ml_engine.py, bot_core.py, or governance.py yet.
When done: commit "feat: phase-1-2 signal infra, execution layer, treasury sweep"
```

---

## 19. Useful Commands

```bash
pip install -r requirements.txt

# Run services individually for testing
python services/market_health.py
python services/signal_listener.py
python services/treasury.py       # watch logs carefully — real SOL if not TEST_MODE
python services/execution.py      # only safe in TEST_MODE=true

# Deploy
git push origin main   # Railway auto-deploys

# Logs
railway logs --service treasury    # most important to monitor
railway logs --service bot_core
railway logs --service governance
```

---

## 20. Requirements (Full)

```
# Core async
aiohttp>=3.9.0
aiofiles>=23.2.0
websockets>=12.0
aiohttp-sse-client>=0.2.1    # for DexPaprika SSE stream

# Solana
solders>=0.20.0
solana>=0.34.0
base58>=2.1.1

# Database
aiosqlite>=0.20.0
redis[asyncio]>=5.0.0

# ML
catboost>=1.2.5
lightgbm>=4.3.0
scikit-learn>=1.4.0
numpy>=1.26.0
pandas>=2.2.0

# Governance agent
anthropic>=0.25.0

# Utilities
python-dotenv>=1.0.0
httpx>=0.27.0
pydantic>=2.6.0
schedule>=1.2.0
python-jose[cryptography]>=3.3.0

# REMOVED from v2.0:
# telethon — no longer needed
```
