"""
ZMN Bot Agent Governance Layer v2
====================================
Features:
- Rolling memory (data/governance_memory.json)
- Anomaly detection (every 30 min)
- Parameter approval system (pending_parameters.json -> active_parameters.json)
- Personality weighting by market regime (personality_weights.json)
- Weekly meta report (GeckoTerminal trending + Nansen + Claude analysis)
- Self-improving prompts (memory-informed context)
- Discord two-way commands (via signal_listener.py)

Schedule (all Sydney time):
- daily_briefing: 7:00 AM Sydney
- wallet_rescore + personality_weights + meta_report: Monday 6:00-7:00 AM Sydney
- anomaly_detection: every 30 minutes
- monthly_report: 1st of month 7:00 AM Sydney
- drawdown_diagnosis / loss_streak_review: triggered via Redis
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import pytz
import redis.asyncio as aioredis
from dotenv import load_dotenv

from services.db import get_pool

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("governance")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
NANSEN_API_KEY = os.getenv("NANSEN_API_KEY", "").strip()
GOVERNANCE_MODEL = os.getenv("GOVERNANCE_MODEL", "claude-haiku-4-5-20251001")
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"

NANSEN_MCP_SERVER = {
    "type": "url",
    "url": "https://mcp.nansen.ai/ra/mcp/",
    "name": "nansen-mcp",
    "headers": {"NANSEN-API-KEY": NANSEN_API_KEY},
} if NANSEN_API_KEY else None

SYDNEY_TZ = pytz.timezone("Australia/Sydney")

# Data file paths
DATA_DIR = Path("data")
MEMORY_FILE = DATA_DIR / "governance_memory.json"
PENDING_PARAMS_FILE = DATA_DIR / "pending_parameters.json"
ACTIVE_PARAMS_FILE = DATA_DIR / "active_parameters.json"
PERSONALITY_WEIGHTS_FILE = DATA_DIR / "personality_weights.json"
GOVERNANCE_NOTES_FILE = DATA_DIR / "governance_notes.md"


def get_sydney_time():
    return datetime.now(pytz.utc).astimezone(SYDNEY_TZ)


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 1 — ROLLING MEMORY
# ═══════════════════════════════════════════════════════════════════════════════

def _load_memory() -> dict:
    """Load governance memory or create default."""
    default = {
        "recommendations": [],
        "confirmed_strengths": [],
        "known_weaknesses": [],
        "prompt_effectiveness": [],
    }
    try:
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE) as f:
                data = json.load(f)
            # Ensure all keys
            for k, v in default.items():
                data.setdefault(k, v)
            return data
    except Exception as e:
        logger.warning("Memory load failed: %s", e)
    return default


def _save_memory(memory: dict):
    """Save governance memory, keeping last 10 recommendations."""
    memory["recommendations"] = memory.get("recommendations", [])[-10:]
    try:
        DATA_DIR.mkdir(exist_ok=True)
        with open(MEMORY_FILE, "w") as f:
            json.dump(memory, f, indent=2)
    except Exception as e:
        logger.warning("Memory save failed: %s", e)


def _record_recommendation(memory: dict, task_type: str, summary: str):
    """Add a recommendation to memory."""
    memory["recommendations"].append({
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "task": task_type,
        "summary": summary[:200],
        "status": "pending",
        "performance_impact": None,
    })
    _save_memory(memory)


def _build_memory_context(memory: dict) -> str:
    """Build memory context string for Claude prompts (Feature 6 — self-improving)."""
    recent = memory.get("recommendations", [])[-5:]
    strengths = memory.get("confirmed_strengths", [])[-5:]
    weaknesses = memory.get("known_weaknesses", [])[-5:]
    parts = []
    if strengths:
        parts.append(f"Confirmed working strategies: {json.dumps(strengths)}")
    if weaknesses:
        parts.append(f"Known current weaknesses: {json.dumps(weaknesses)}")
    if recent:
        parts.append(f"Recent recommendations: {json.dumps(recent)}")
    return "\n".join(parts) if parts else "No prior context available."


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 3 — PARAMETER APPROVAL SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

def _load_json_file(path: Path, default=None):
    if default is None:
        default = []
    try:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _save_json_file(path: Path, data):
    DATA_DIR.mkdir(exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def propose_parameter_change(param_name: str, current_val, proposed_val, reason: str):
    """Write a parameter change proposal to PostgreSQL bot_state."""
    new_entry = {
        "parameter": param_name,
        "current_value": current_val,
        "proposed_value": proposed_val,
        "reason": reason,
        "proposed_by": "governance",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "status": "pending",
    }
    async def _write():
        pool = await get_pool()
        raw = await pool.fetchval("SELECT value_text FROM bot_state WHERE key = 'pending_parameters'")
        pending = json.loads(raw) if raw else []
        pending.append(new_entry)
        await pool.execute(
            """INSERT INTO bot_state (key, value_text, updated_at) VALUES ($1, $2, NOW())
               ON CONFLICT (key) DO UPDATE SET value_text = $2, updated_at = NOW()""",
            "pending_parameters", json.dumps(pending),
        )
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_write())
        else:
            loop.run_until_complete(_write())
    except Exception as e:
        logger.warning("Parameter proposal write failed: %s — falling back to file", e)
        # File fallback
        pending = _load_json_file(PENDING_PARAMS_FILE, [])
        pending.append(new_entry)
        _save_json_file(PENDING_PARAMS_FILE, pending)
    logger.info("Parameter proposal: %s %s -> %s", param_name, current_val, proposed_val)


# ═══════════════════════════════════════════════════════════════════════════════
# CORE — SYSTEM PROMPT + PROMPT BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def _build_system_prompt(memory: dict) -> str:
    """Build system prompt with self-improving context (Feature 6)."""
    base = """You are the ZMN Bot governance agent, a Solana memecoin trading bot.
Your role is strategic oversight -- analyse performance, score wallets, detect anomalies,
and make recommendations. You never make live trading decisions.
Write clearly and concisely. Flag anything unusual. Be direct about problems."""
    ctx = _build_memory_context(memory)
    return f"{base}\n\nHistorical context:\n{ctx}"


def build_governance_prompt(task_type: str, context: dict) -> str:
    if task_type == "wallet_rescore":
        wallet_addrs = context.get("wallet_addresses", [])[:20]
        return f"""
Review whale wallet list and provide updated scores (0-100).
Remove wallets below thresholds. Suggest new wallets to add.

Current wallets: {json.dumps(context.get('current_wallets', [])[:20], indent=2)}
Wallet addresses for lookup: {json.dumps(wallet_addrs, indent=2)}

Use the Nansen MCP server to look up current PnL and activity for each wallet.
Query Nansen for Solana smart money activity in the last 48 hours and identify
any wallets we should add or remove from our watchlist.
Scoring: win_rate (25%), avg_roi (20%), trade_frequency (15%), realized_pnl (15%), consistency (15%), hold_period (10%).

Output: Valid JSON array with schema:
[{{"address":"...","score":75,"label":"...","source":"nansen","win_rate":null,"realized_pnl_30d":null,"last_scored":"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}","active":true}}]
"""

    elif task_type == "daily_briefing":
        syd = get_sydney_time()
        try:
            from services.market_health import get_current_session_sydney
            session_name, session_quality = get_current_session_sydney()
        except Exception:
            session_name, session_quality = "UNKNOWN", "unknown"
        return f"""
Write daily briefing for ZMN Bot.
Sydney time: {syd.strftime('%A %d %B %Y %H:%M %Z')}
Trading session: {session_name} ({session_quality})
Mode: {'PAPER TRADING' if context.get('test_mode') else 'LIVE'}

Include:
1. Good morning Jay -- {syd.strftime('%A %d %B %Y')}
2. Yesterday's performance (P/L, win rate, best/worst per personality)
3. Market mode and reasoning
4. Trading windows in Sydney time
5. Network conditions
6. Governance actions needed
7. One specific recommendation
8. Smart money snapshot (use Nansen MCP tools)
9. Nansen credit usage: {json.dumps(context.get('nansen_credits', {}))}

Data: {json.dumps(context, indent=2, default=str)[:3000]}

Sign off: 'Good luck today, Jay. -- ZMN Bot Governance'
Max 500 words.
"""

    elif task_type == "drawdown_diagnosis":
        return f"""
ZMN Bot hit a significant drawdown. Diagnose root cause.
Drawdown: {json.dumps(context.get('drawdown_info', {}), indent=2)}
Recent trades: {json.dumps(context.get('recent_trades', [])[:20], indent=2, default=str)}
Provide: (1) root cause, (2) parameter changes, (3) resume or pause. Be direct.
"""

    elif task_type == "loss_streak_review":
        return f"""
{context.get('personality','Unknown')} has {context.get('consecutive_losses',0)} consecutive losses.
Losing trades: {json.dumps(context.get('losing_trades', [])[:10], indent=2, default=str)}
Diagnose: bad luck, signal quality issue, parameter issue, or regime change?
One paragraph max with specific recommendation.
"""

    elif task_type == "monthly_report":
        return f"""
Monthly performance report for ZMN Bot:
1. Overall P/L 2. Per-personality breakdown 3. ML accuracy
4. Best signal sources 5. Worst signal sources 6. Treasury sweeps
7. Top 3 recommendations for next month
Data: {json.dumps(context, indent=2, default=str)[:3000]}
"""

    elif task_type == "smart_money_analysis":
        return f"""
Analyse smart money on Solana this week using Nansen MCP tools.
1. Top holdings 2. Changes in positioning 3. Emerging narratives
4. Tokens with unusual smart money concentration
Max 300 words.
"""

    elif task_type == "anomaly_diagnosis":
        return f"""
Anomaly detected: {context.get('anomaly_description', 'Unknown anomaly')}
Recent trade data: {json.dumps(context.get('recent_data', [])[:15], indent=2, default=str)}
Diagnose the likely cause in 2 sentences and suggest one immediate action.
"""

    elif task_type == "weekly_meta":
        return f"""
Here are the top performing Solana tokens this week and what smart money bought:
Trending pools: {json.dumps(context.get('trending', [])[:10], indent=2, default=str)}
Nansen data: {json.dumps(context.get('nansen_data', [])[:10], indent=2, default=str)}

What patterns do you see? What signal types preceded the best performers?
Are there emerging narrative themes? What should ZMN Bot emphasise next week?
Max 300 words.
"""

    elif task_type == "personality_weights":
        return f"""
Analyse last 30 days of ZMN Bot trades by market condition.
Trades: {json.dumps(context.get('trades_30d', [])[:50], indent=2, default=str)}

Calculate which personality performs best in each regime:
- bull_trend, high_volatility, choppy, defensive

Output valid JSON:
{{"bull_trend":{{"speed_demon":1.0,"analyst":1.0,"whale_tracker":1.0}},"high_volatility":{{"speed_demon":1.0,"analyst":1.0,"whale_tracker":1.0}},"choppy":{{"speed_demon":1.0,"analyst":1.0,"whale_tracker":1.0}},"defensive":{{"speed_demon":1.0,"analyst":1.0,"whale_tracker":1.0}}}}
Values 0.5-1.5. Nothing else -- just the JSON.
"""

    return "No valid task type."


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 8 — STRUCTURED GOVERNANCE CLASSIFICATION (every 4h)
# ═══════════════════════════════════════════════════════════════════════════════

GOVERNANCE_DEFAULTS = {
    "mode": "NORMAL",
    "speed_demon_enabled": True,
    "analyst_enabled": True,
    "whale_tracker_enabled": True,
    "size_multiplier": 1.0,
    "max_concurrent_positions": 10,
    "reasoning": "default — no governance decision yet",
    "next_review_hours": 4,
}


async def _run_governance_classification(pool, redis_conn, session):
    """Call Haiku to classify market mode and store JSON decision in Redis."""
    if not ANTHROPIC_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY — using default governance")
        if redis_conn:
            await redis_conn.set("governance:latest_decision", json.dumps(GOVERNANCE_DEFAULTS), ex=28800)
        return GOVERNANCE_DEFAULTS

    # Gather metrics
    cfgi = 50
    if redis_conn:
        try:
            raw = await redis_conn.get("market:cfgi")
            if raw:
                cfgi = int(float(raw))
        except Exception:
            pass

    wr25 = 0
    pnl_24h = 0
    positions = 0
    top_exit = "unknown"
    trades_today = 0
    try:
        row = await pool.fetchrow(
            "SELECT COUNT(*) as t, COUNT(CASE WHEN realised_pnl_sol > 0 THEN 1 END) as w "
            "FROM (SELECT realised_pnl_sol FROM paper_trades WHERE exit_time IS NOT NULL "
            "ORDER BY exit_time DESC LIMIT 25) x"
        )
        if row and row["t"] > 0:
            wr25 = round(row["w"] / row["t"] * 100, 1)

        row2 = await pool.fetchrow(
            "SELECT COALESCE(SUM(realised_pnl_sol), 0) as pnl, COUNT(*) as trades "
            "FROM paper_trades WHERE exit_time > EXTRACT(EPOCH FROM NOW()) - 86400"
        )
        if row2:
            pnl_24h = round(float(row2["pnl"]), 4)
            trades_today = row2["trades"]

        row3 = await pool.fetchval(
            "SELECT COUNT(*) FROM paper_trades WHERE exit_time IS NULL"
        )
        positions = row3 or 0

        row4 = await pool.fetchrow(
            "SELECT exit_reason, COUNT(*) as c FROM paper_trades "
            "WHERE exit_time > NOW() - INTERVAL '24 hours' AND exit_reason IS NOT NULL "
            "GROUP BY exit_reason ORDER BY c DESC LIMIT 1"
        )
        if row4:
            top_exit = row4["exit_reason"]
    except Exception as e:
        logger.warning("Governance metrics query failed: %s", e)

    cfgi_label = "extreme_fear" if cfgi < 15 else "fear" if cfgi < 30 else "neutral" if cfgi < 60 else "greed"
    sol_change = 0  # Could fetch from Jupiter but keeping simple

    prompt = f"""You are a memecoin market analyst for an automated Solana trading bot.
Given current market conditions, output EXACTLY one JSON object. No prose, no markdown, no explanation.

Current conditions:
  CFGI: {cfgi} ({cfgi_label})
  Bot win rate (last 25): {wr25}%
  Bot PnL (last 24h): {pnl_24h} SOL
  Active positions: {positions}
  Top exit reason (24h): {top_exit}
  Total trades today: {trades_today}

Respond with ONLY this JSON:
{{"mode": "AGGRESSIVE|NORMAL|CONSERVATIVE|PAUSE|HIBERNATE", "speed_demon_enabled": true, "analyst_enabled": true, "whale_tracker_enabled": true, "size_multiplier": 1.0, "max_concurrent_positions": 10, "reasoning": "one sentence", "next_review_hours": 4}}

Rules:
- CFGI < 15 and WR < 5% -> CONSERVATIVE or PAUSE
- CFGI < 25 -> CONSERVATIVE at most
- CFGI 25-50 -> NORMAL
- CFGI > 50 and WR > 10% -> can be AGGRESSIVE
- If PnL last 24h < -2 SOL -> reduce size_multiplier to 0.5
- If 0 take-profits in exits -> keep CONSERVATIVE
- speed_demon_enabled=false if overall WR < 3%"""

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model=GOVERNANCE_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = msg.content[0].text.strip()
        logger.info("Governance classification raw: %s", raw_text[:200])

        # Parse JSON — try to extract from possible markdown wrapping
        if "```" in raw_text:
            raw_text = raw_text.split("```")[1].strip()
            if raw_text.startswith("json"):
                raw_text = raw_text[4:].strip()
        decision = json.loads(raw_text)

        # Validate required fields
        for key in ("mode", "size_multiplier"):
            if key not in decision:
                decision[key] = GOVERNANCE_DEFAULTS[key]

        logger.info("GOVERNANCE DECISION: mode=%s size=%.2f reasoning=%s",
                    decision["mode"], decision.get("size_multiplier", 1.0),
                    decision.get("reasoning", "none"))

    except Exception as e:
        logger.error("Governance classification failed: %s — using CONSERVATIVE defaults", e)
        decision = {**GOVERNANCE_DEFAULTS, "mode": "CONSERVATIVE", "size_multiplier": 0.8,
                    "reasoning": f"classification failed: {str(e)[:100]}"}

    # Store in PostgreSQL FIRST (permanent), then Redis (cache)
    if pool:
        try:
            await pool.execute(
                "INSERT INTO bot_state (key, value_text, updated_at) "
                "VALUES ('governance_latest', $1, NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value_text=$1, updated_at=NOW()",
                json.dumps(decision),
            )
        except Exception as e:
            logger.warning("Governance PostgreSQL persist failed: %s", e)

    if redis_conn:
        await redis_conn.set("governance:latest_decision", json.dumps(decision), ex=28800)
        await redis_conn.set("governance:mode", decision["mode"], ex=28800)
        await redis_conn.set("governance:last_run", datetime.now(timezone.utc).isoformat(), ex=28800)

    return decision


async def _governance_classification_loop(pool, redis_conn):
    """Run governance classification every N hours."""
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                decision = await _run_governance_classification(pool, redis_conn, session)
                wait_hours = decision.get("next_review_hours", 4)
                logger.info("Governance classification done — next in %dh", wait_hours)
                await asyncio.sleep(wait_hours * 3600)
            except Exception as e:
                logger.error("Governance classification loop error: %s", e)
                await asyncio.sleep(3600)


# ═══════════════════════════════════════════════════════════════════════════════
# CORE — OUTPUT + DISCORD + RUN TASK
# ═══════════════════════════════════════════════════════════════════════════════

async def write_governance_output(task_type: str, output: str, context: dict):
    timestamp = datetime.now(timezone.utc).isoformat()
    DATA_DIR.mkdir(exist_ok=True)

    # Write to PostgreSQL (source of truth — survives Railway redeploys)
    try:
        pool = await get_pool()
        content = f"## {task_type} -- {timestamp}\n\n{output}"
        await pool.execute(
            "INSERT INTO governance_notes_log (content) VALUES ($1)", content
        )
        # Insert decision for structured queries
        decision = "TRADE" if task_type in ("daily_briefing", "weekly_meta") else task_type.upper()
        await pool.execute(
            """INSERT INTO governance_state (decision, reason, notes, triggered_by)
               VALUES ($1, $2, $3, $4)""",
            decision, task_type, output[:500], "scheduled",
        )
    except Exception as e:
        logger.warning("Governance DB write failed: %s", e)

    # Also write to file as backup (best-effort)
    if task_type == "wallet_rescore":
        try:
            updated_wallets = json.loads(output)
            _save_json_file(DATA_DIR / "whale_wallets_pending.json", updated_wallets)
            logger.info("Wallet rescore -> whale_wallets_pending.json")
        except json.JSONDecodeError:
            with open(GOVERNANCE_NOTES_FILE, "a") as f:
                f.write(f"\n\n---\n## {task_type} -- {timestamp}\n\nWARNING: not valid JSON.\n\n{output}\n")
    elif task_type == "personality_weights":
        try:
            weights = json.loads(output)
            _save_json_file(PERSONALITY_WEIGHTS_FILE, weights)
            logger.info("Personality weights updated")
        except json.JSONDecodeError:
            with open(GOVERNANCE_NOTES_FILE, "a") as f:
                f.write(f"\n\n---\n## {task_type} -- {timestamp}\n\n{output}\n")
    else:
        with open(GOVERNANCE_NOTES_FILE, "a") as f:
            f.write(f"\n\n---\n## {task_type} -- {timestamp}\n\n{output}\n")

    logger.info("Governance output written: %s", task_type)


async def send_discord(session: aiohttp.ClientSession, message: str):
    if TEST_MODE:
        logger.info("Discord [TEST]: %s", message[:200])
        return
    if not DISCORD_WEBHOOK_URL:
        logger.info("Discord (no webhook): %s", message[:200])
        return
    try:
        await session.post(DISCORD_WEBHOOK_URL, json={"content": message[:2000]},
                           timeout=aiohttp.ClientTimeout(total=10))
    except Exception as e:
        logger.warning("Discord send failed: %s", e)


async def run_governance_task(task_type: str, context_data: dict, session: aiohttp.ClientSession,
                             use_nansen_mcp: bool = False):
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set -- skipping: %s", task_type)
        return None

    memory = _load_memory()
    logger.info("Running governance: %s", task_type)

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

        user_prompt = build_governance_prompt(task_type, context_data)
        system_prompt = _build_system_prompt(memory)

        api_kwargs = {
            "model": GOVERNANCE_MODEL,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        if use_nansen_mcp and NANSEN_MCP_SERVER:
            api_kwargs["mcp_servers"] = [NANSEN_MCP_SERVER]

        message = await client.messages.create(**api_kwargs)
        text_parts = [block.text for block in message.content if hasattr(block, "text")]
        output = "\n".join(text_parts)

        logger.info("Governance %s done -- tokens: in=%d out=%d",
                     task_type, message.usage.input_tokens, message.usage.output_tokens)

        await write_governance_output(task_type, output, context_data)
        _record_recommendation(memory, task_type, output[:200])

        # Discord notifications
        if task_type == "wallet_rescore":
            await send_discord(session, "[ZMN Bot] Wallet rescore complete. Review whale_wallets_pending.json.")
        elif task_type == "anomaly_diagnosis":
            await send_discord(session, f"[ZMN Bot] ANOMALY: {output[:1800]}")
        elif task_type == "weekly_meta":
            syd = get_sydney_time()
            await send_discord(session, f"[ZMN Bot] Weekly Meta -- {syd.strftime('%d %b %Y')}\n{output[:1800]}")
        else:
            await send_discord(session, f"[ZMN Bot] {task_type}: check governance_notes.md")

        return output

    except Exception as e:
        logger.error("Governance %s failed: %s", task_type, e)
        await send_discord(session, f"[ZMN Bot] ERROR: {task_type} failed -- {str(e)[:200]}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 2 — ANOMALY DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

async def _anomaly_loop(pool, redis_conn: aioredis.Redis | None):
    """Run anomaly checks every 30 minutes."""
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await _check_anomalies(pool, redis_conn, session)
            except Exception as e:
                logger.error("Anomaly check error: %s", e)
            await asyncio.sleep(1800)  # 30 minutes


async def _check_anomalies(pool, redis_conn, session):
    now = time.time()
    anomalies = []

    try:
        # 1. Win rate drop >10% in 24h window
        row = await pool.fetchrow(
            "SELECT COUNT(*) as total, SUM(CASE WHEN outcome='profit' THEN 1 ELSE 0 END) as wins "
            "FROM trades WHERE closed_at > $1 AND outcome IS NOT NULL", now - 86400)
        if row and row["total"] >= 5:
            wr_24h = (row["wins"] or 0) / row["total"] * 100
            row2 = await pool.fetchrow(
                "SELECT COUNT(*) as total, SUM(CASE WHEN outcome='profit' THEN 1 ELSE 0 END) as wins "
                "FROM trades WHERE closed_at > $1 AND closed_at <= $2 AND outcome IS NOT NULL",
                now - 7 * 86400, now - 86400)
            if row2 and row2["total"] >= 10:
                wr_7d = (row2["wins"] or 0) / row2["total"] * 100
                if wr_7d - wr_24h > 10:
                    anomalies.append(f"Win rate dropped from {wr_7d:.1f}% (7d avg) to {wr_24h:.1f}% (24h)")

        # 2. Exit reason spike >3x
        for reason in ["stop_loss", "emergency_stop", "smart_money_exit_alert"]:
            # Query paper_trades which has exit_reason column
            row = await pool.fetchval(
                "SELECT COUNT(*) FROM paper_trades WHERE exit_time > $1 AND realised_pnl_sol < 0 AND "
                "exit_reason LIKE $2", now - 86400, f"%{reason}%")
            count_24h = row or 0
            row2 = await pool.fetchval(
                "SELECT COUNT(*) FROM paper_trades WHERE exit_time > $1 AND exit_time <= $2 AND "
                "realised_pnl_sol < 0 AND exit_reason LIKE $3",
                now - 7 * 86400, now - 86400, f"%{reason}%")
            avg_daily = ((row2 or 0) / 6)
            if avg_daily > 0 and count_24h > avg_daily * 3:
                anomalies.append(f"Exit reason '{reason}' spiked: {count_24h} today vs {avg_daily:.1f}/day avg")

    except Exception as e:
        logger.debug("Anomaly SQL error: %s", e)

    # Fire Claude diagnosis for each anomaly
    for anomaly in anomalies:
        logger.warning("ANOMALY: %s", anomaly)
        try:
            rows = await pool.fetch(
                "SELECT * FROM trades WHERE closed_at > $1 ORDER BY closed_at DESC LIMIT 15",
                now - 86400)
            recent_trades = [dict(r) for r in rows]

            context = {"anomaly_description": anomaly, "recent_data": recent_trades}
            await run_governance_task("anomaly_diagnosis", context, session)
        except Exception as e:
            logger.error("Anomaly diagnosis failed: %s", e)


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 4 — PERSONALITY WEIGHTING
# ═══════════════════════════════════════════════════════════════════════════════

async def _calculate_personality_weights(pool, session: aiohttp.ClientSession):
    """Analyse trades by market condition, ask Claude for optimal weights."""
    now = time.time()
    try:
        rows = await pool.fetch(
            "SELECT * FROM trades WHERE created_at > $1 AND outcome IS NOT NULL ORDER BY created_at DESC LIMIT 200",
            now - 30 * 86400)
        trades = [dict(r) for r in rows]

        if len(trades) < 10:
            logger.info("Not enough trades for personality weighting (%d)", len(trades))
            return

        context = {"trades_30d": trades}
        output = await run_governance_task("personality_weights", context, session)

        if output:
            try:
                weights = json.loads(output)
                _save_json_file(PERSONALITY_WEIGHTS_FILE, weights)
                logger.info("Personality weights saved")
            except json.JSONDecodeError:
                logger.warning("Personality weights output not valid JSON")

    except Exception as e:
        logger.error("Personality weighting failed: %s", e)


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 5 — WEEKLY META REPORT
# ═══════════════════════════════════════════════════════════════════════════════

async def _weekly_meta_report(session: aiohttp.ClientSession):
    """Pull trending pools + Nansen data, ask Claude for pattern analysis."""
    try:
        # GeckoTerminal trending pools
        trending = []
        try:
            async with session.get(
                "https://api.geckoterminal.com/api/v2/networks/solana/trending_pools",
                params={"duration": "24h", "page": 1},
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for pool in data.get("data", [])[:20]:
                        attrs = pool.get("attributes", {})
                        trending.append({
                            "name": attrs.get("name", ""),
                            "price_change_24h": attrs.get("price_change_percentage", {}).get("h24"),
                            "volume_24h": attrs.get("volume_usd", {}).get("h24"),
                            "reserve_usd": attrs.get("reserve_in_usd"),
                        })
        except Exception as e:
            logger.warning("GeckoTerminal trending fetch failed: %s", e)

        # P2: Nansen Score Top Tokens (replaces generic Nansen MCP call)
        nansen_top = []
        if NANSEN_API_KEY:
            try:
                from services.nansen_client import get_nansen_top_tokens
                for mcap_group in ("lowcap", "midcap"):
                    tokens = await get_nansen_top_tokens(session, market_cap_group=mcap_group)
                    nansen_top.extend(tokens[:10])
                logger.info("Nansen top tokens: %d results for weekly meta", len(nansen_top))
            except Exception as e:
                logger.warning("Nansen top tokens fetch failed: %s", e)

        context = {"trending": trending, "nansen_data": nansen_top}
        await run_governance_task("weekly_meta", context, session, use_nansen_mcp=True)

    except Exception as e:
        logger.error("Weekly meta report failed: %s", e)


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 8 — SMART MONEY DISCOVERY SCAN (every 4 hours)
# ═══════════════════════════════════════════════════════════════════════════════

async def _smart_money_discovery_loop(redis_conn: aioredis.Redis | None):
    """
    P1: Proactive signal generation — scan what smart money is accumulating
    on Solana and inject new tokens as Analyst signals.

    Budget: 6 calls/day (every 4 hours)
    """
    if not NANSEN_API_KEY or not redis_conn:
        logger.info("Smart money discovery disabled (no Nansen API key or Redis)")
        return

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                from services.nansen_client import get_smart_money_discovery

                accumulating = await get_smart_money_discovery(session, redis_conn)

                if accumulating:
                    # Check which tokens are already known to the bot
                    for token in accumulating[:10]:  # Top 10 by default sort
                        mint = token.get("mint", "")
                        if not mint:
                            continue

                        # Check if we've seen this token recently
                        seen_key = f"seen:discovery:{mint}"
                        already_seen = await redis_conn.get(seen_key)
                        if already_seen:
                            continue

                        # Inject as Analyst signal
                        discovery_signal = {
                            "mint": mint,
                            "source": "nansen_discovery",
                            "signal_type": "token_trade",  # Routes to Analyst
                            "age_seconds": 600,  # Treat as 10-min old (post-grad tier)
                            "raw_data": {
                                "symbol": token.get("symbol", ""),
                                "balance_usd": token.get("balance_usd", 0),
                                "smart_money_change_24h": token.get("change_24h", 0),
                            },
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        await redis_conn.lpush("signals:raw", json.dumps(discovery_signal))
                        # Mark as seen for 24 hours (don't re-inject)
                        await redis_conn.set(seen_key, "1", ex=86400)
                        logger.info("DISCOVERY: injected %s (%s) — smart money accumulating",
                                     mint[:12], token.get("symbol", "?"))

            except Exception as e:
                logger.error("Smart money discovery error: %s", e)

            await asyncio.sleep(4 * 3600)  # Every 4 hours


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 9 — WHALE PORTFOLIO + PNL LEADERBOARD DISCOVERY (weekly)
# ═══════════════════════════════════════════════════════════════════════════════

async def _whale_discovery_and_portfolio(pool, session: aiohttp.ClientSession, redis_conn: aioredis.Redis | None):
    """
    P2+P3: Enhanced whale wallet rescoring with portfolio analysis
    and automated whale discovery via PnL leaderboard.

    Called during weekly wallet rescore.
    Budget: ~70 calls/week (50 portfolio + 5 leaderboard + some extras)
    """
    if not NANSEN_API_KEY:
        return

    from services.nansen_client import get_whale_portfolio, get_token_pnl_leaderboard

    # P2: Whale portfolio analysis for top 20 wallets
    try:
        try:
            from services.nansen_wallet_fetcher import get_active_wallets
            wallet_records = await get_active_wallets(personality_route="whale_tracker")
            wallets = [{"address": w["address"], "score": w.get("qualification_score", 0),
                        "label": w.get("label", "")} for w in wallet_records]
        except Exception as e:
            logger.warning("PostgreSQL wallet load failed for portfolio analysis: %s", e)
            wallets = []

        # Sort by score, analyse top 20
        sorted_wallets = sorted(wallets, key=lambda w: w.get("score", 0) if isinstance(w, dict) else 0, reverse=True)
        portfolio_insights = []

        for wallet in sorted_wallets[:20]:
            addr = wallet.get("address", "") if isinstance(wallet, dict) else str(wallet)
            if not addr:
                continue
            try:
                portfolio = await get_whale_portfolio(session, addr, redis_conn)
                if portfolio:
                    portfolio_insights.append({
                        "address": addr[:12],
                        "label": wallet.get("label", "") if isinstance(wallet, dict) else "",
                        "portfolio_summary": str(portfolio)[:300],
                    })
            except Exception as e:
                logger.debug("Portfolio fetch failed for %s: %s", addr[:12], e)

        if portfolio_insights:
            logger.info("Fetched portfolio data for %d whale wallets", len(portfolio_insights))

    except Exception as e:
        logger.error("Whale portfolio analysis failed: %s", e)

    # P3: PnL leaderboard whale discovery
    try:
        # Get top 5 performing tokens from last week
        now = time.time()
        rows = await pool.fetch(
            """SELECT mint, SUM(pnl_sol) as total_pnl FROM trades
               WHERE closed_at > $1 AND outcome = 'profit'
               GROUP BY mint ORDER BY total_pnl DESC LIMIT 5""",
            now - 7 * 86400,
        )

        discovered_wallets = []
        for row in rows:
            mint = row["mint"]
            try:
                leaderboard = await get_token_pnl_leaderboard(session, mint, days=7, redis_conn=redis_conn)
                for trader in leaderboard[:5]:
                    addr = trader.get("address", trader.get("traderAddress", ""))
                    label = trader.get("label", trader.get("fullName", ""))
                    pnl = trader.get("pnlUsdTotal", trader.get("total_pnl", 0))
                    roi = trader.get("roiPercentTotal", trader.get("total_roi", 0))

                    if addr and float(pnl or 0) > 1000:
                        discovered_wallets.append({
                            "address": addr,
                            "label": label or "Nansen PnL Leader",
                            "source_token": mint[:12],
                            "pnl_usd": float(pnl or 0),
                            "roi_pct": float(roi or 0),
                        })
            except Exception as e:
                logger.debug("PnL leaderboard failed for %s: %s", mint[:12], e)

        if discovered_wallets:
            # Deduplicate by address
            seen_addrs = set()
            unique = []
            for w in discovered_wallets:
                if w["address"] not in seen_addrs:
                    seen_addrs.add(w["address"])
                    unique.append(w)

            logger.info("Discovered %d potential whale wallets from PnL leaderboards", len(unique))

            # Save discoveries for governance review
            discovery_path = Path("data/whale_discoveries.json")
            existing = []
            if discovery_path.exists():
                try:
                    with open(discovery_path) as f:
                        existing = json.load(f)
                except Exception:
                    pass

            existing.extend(unique)
            # Keep last 100 discoveries
            existing = existing[-100:]
            Path("data").mkdir(exist_ok=True)
            with open(discovery_path, "w") as f:
                json.dump(existing, f, indent=2)

    except Exception as e:
        logger.error("PnL leaderboard whale discovery failed: %s", e)


# ═══════════════════════════════════════════════════════════════════════════════
# CONTEXT GATHERING
# ═══════════════════════════════════════════════════════════════════════════════

async def _gather_context(pool, redis_conn, task_type: str) -> dict:
    context = {}
    now = time.time()
    try:
        if task_type == "daily_briefing":
            rows = await pool.fetch(
                "SELECT * FROM trades WHERE created_at > $1 ORDER BY created_at DESC", now - 86400)
            context["trades_24h"] = [dict(r) for r in rows]

            row = await pool.fetchrow("SELECT * FROM portfolio_snapshots ORDER BY id DESC LIMIT 1")
            if row:
                context["portfolio"] = dict(row)

            if redis_conn:
                try:
                    health = await redis_conn.get("market:health")
                    if health:
                        context["market_health"] = json.loads(health)
                except Exception:
                    pass
                # Nansen credit usage for daily briefing
                try:
                    from services.nansen_client import get_credit_usage
                    context["nansen_credits"] = await get_credit_usage(redis_conn)
                except Exception:
                    context["nansen_credits"] = {}

        elif task_type == "wallet_rescore":
            try:
                with open("data/whale_wallets.json") as f:
                    context["current_wallets"] = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                context["current_wallets"] = []
            context["wallet_addresses"] = [
                w.get("address", "") if isinstance(w, dict) else str(w)
                for w in context["current_wallets"] if w
            ]

        elif task_type == "monthly_report":
            rows = await pool.fetch(
                "SELECT * FROM trades WHERE created_at > $1 ORDER BY created_at DESC",
                now - 30 * 86400)
            context["trades_30d"] = [dict(r) for r in rows]
            try:
                rows = await pool.fetch(
                    "SELECT * FROM treasury_sweeps ORDER BY id DESC LIMIT 10")
                context["treasury_sweeps"] = [dict(r) for r in rows]
            except Exception:
                context["treasury_sweeps"] = []

    except Exception as e:
        logger.error("Context gather failed for %s: %s", task_type, e)

    return context


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULED + TRIGGERED LOOPS
# ═══════════════════════════════════════════════════════════════════════════════

async def _scheduled_loop(pool, redis_conn):
    """Run scheduled tasks. All times in Sydney local time (auto DST)."""
    last_daily = 0.0
    last_weekly = 0.0
    last_weekly_meta = 0.0
    last_monthly = 0.0

    async with aiohttp.ClientSession() as session:
        while True:
            syd = get_sydney_time()
            now_ts = time.time()

            # Daily briefing: 7:00 AM Sydney
            if syd.hour == 7 and syd.minute < 2 and now_ts - last_daily > 82800:
                context = await _gather_context(pool, redis_conn, "daily_briefing")
                context["test_mode"] = TEST_MODE
                await run_governance_task("daily_briefing", context, session, use_nansen_mcp=True)
                syd_header = syd.strftime("%A %d %B %Y %H:%M %Z")
                await send_discord(session, f"[ZMN Bot] Daily Briefing -- {syd_header}")
                last_daily = now_ts

            # Monday 6:00 AM Sydney: wallet rescore + personality weights + whale discovery
            if syd.weekday() == 0 and syd.hour == 6 and syd.minute < 2 and now_ts - last_weekly > 604800:
                context = await _gather_context(pool, redis_conn, "wallet_rescore")
                await run_governance_task("wallet_rescore", context, session, use_nansen_mcp=True)
                await _calculate_personality_weights(pool, session)
                # P2+P3: Enhanced whale analysis with portfolio + PnL discovery
                await _whale_discovery_and_portfolio(pool, session, redis_conn)
                last_weekly = now_ts

            # Monday 6:30 AM Sydney: weekly meta report
            if syd.weekday() == 0 and syd.hour == 6 and 28 <= syd.minute <= 32 and now_ts - last_weekly_meta > 604800:
                await _weekly_meta_report(session)
                last_weekly_meta = now_ts

            # 1st of month, 7:00 AM Sydney
            if syd.day == 1 and syd.hour == 7 and syd.minute < 2 and now_ts - last_monthly > 2592000:
                context = await _gather_context(pool, redis_conn, "monthly_report")
                await run_governance_task("monthly_report", context, session)
                last_monthly = now_ts

            await asyncio.sleep(60)


async def _trigger_listener(pool, redis_conn: aioredis.Redis):
    """Listen for triggered governance events via Redis pub/sub."""
    pubsub = redis_conn.pubsub()
    await pubsub.subscribe("drawdown:significant", "streak:loss")
    logger.info("Listening for governance triggers")

    async with aiohttp.ClientSession() as session:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                channel = message["channel"]

                if channel == "drawdown:significant":
                    context = await _gather_context(pool, redis_conn, "drawdown_diagnosis")
                    context["drawdown_info"] = data
                    await run_governance_task("drawdown_diagnosis", context, session)

                elif channel == "streak:loss":
                    context = data
                    rows = await pool.fetch(
                        "SELECT * FROM trades WHERE personality = $1 AND outcome = 'loss' "
                        "ORDER BY created_at DESC LIMIT 10", data.get("personality", ""))
                    context["losing_trades"] = [dict(r) for r in rows]
                    context["parameters"] = {}
                    await run_governance_task("loss_streak_review", context, session)

            except Exception as e:
                logger.error("Trigger handler error: %s", e)


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 7 — DISCORD TWO-WAY COMMANDS (handler called from signal_listener)
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_discord_command(command: str) -> str:
    """Process a !zmn command from Discord. Returns response string."""
    parts = command.strip().lower().split()
    if len(parts) < 2 or parts[0] != "!zmn":
        return ""

    cmd = parts[1]

    try:
        pool = await get_pool()
        now = time.time()

        if cmd == "status":
            row = await pool.fetchrow("SELECT * FROM portfolio_snapshots ORDER BY id DESC LIMIT 1")
            if row:
                snap = dict(row)
                return (f"[ZMN Bot] Status: {snap.get('market_mode', 'NORMAL')} mode | "
                        f"Balance: {snap.get('total_balance_sol', 0):.4f} SOL | "
                        f"Daily P/L: {snap.get('daily_pnl_sol', 0):.4f} SOL | "
                        f"Open: {snap.get('open_positions', 0)} positions")
            return "[ZMN Bot] No portfolio data available."

        elif cmd == "today":
            row = await pool.fetchrow(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(pnl_sol),0) as pnl FROM trades WHERE created_at > $1",
                now - 86400)
            return f"[ZMN Bot] Today: {row['cnt']} trades | P/L: {row['pnl']:.4f} SOL"

        elif cmd in ("best", "worst"):
            direction = "DESC" if cmd == "best" else "ASC"
            label = "Best" if cmd == "best" else "Worst"
            row = await pool.fetchrow(
                f"SELECT mint, personality, pnl_sol, pnl_pct FROM trades WHERE outcome IS NOT NULL "
                f"ORDER BY pnl_sol {direction} LIMIT 1")
            if row:
                return f"[ZMN Bot] {label} trade: {row['mint'][:12]}... ({row['personality']}) | P/L: {row['pnl_sol']:.4f} SOL ({row['pnl_pct']:.1f}%)"
            return "[ZMN Bot] No trades recorded yet."

        elif cmd == "pause" and len(parts) >= 3:
            personality = parts[2]
            try:
                conn = aioredis.from_url(REDIS_URL, decode_responses=True, max_connections=5)
                await conn.publish("bot:command", json.dumps({"action": "pause", "personality": personality}))
                await conn.close()
                return f"[ZMN Bot] Pause command sent for {personality}."
            except Exception:
                return "[ZMN Bot] Redis unavailable -- cannot send pause command."

        elif cmd == "resume" and len(parts) >= 3:
            personality = parts[2]
            try:
                conn = aioredis.from_url(REDIS_URL, decode_responses=True, max_connections=5)
                await conn.publish("bot:command", json.dumps({"action": "resume", "personality": personality}))
                await conn.close()
                return f"[ZMN Bot] Resume command sent for {personality}."
            except Exception:
                return "[ZMN Bot] Redis unavailable -- cannot send resume command."

        elif cmd == "meta":
            async with aiohttp.ClientSession() as session:
                await _weekly_meta_report(session)
            return "[ZMN Bot] Meta report triggered -- check governance_notes.md."

        elif cmd == "diagnose":
            rows = await pool.fetch(
                "SELECT * FROM trades WHERE created_at > $1 ORDER BY created_at DESC LIMIT 20",
                now - 48 * 3600)
            context = {
                "recent_trades": [dict(r) for r in rows],
                "drawdown_info": {"reason": "manual_diagnose_command"},
            }
            async with aiohttp.ClientSession() as session:
                await run_governance_task("drawdown_diagnosis", context, session)
            return "[ZMN Bot] Diagnosis triggered -- check governance_notes.md."

        elif cmd == "refresh-wallets":
            try:
                from services.nansen_wallet_fetcher import fetch_and_upsert_wallets
                result = await fetch_and_upsert_wallets(trigger="manual")
                return (f"[ZMN Bot] Wallet refresh: +{result['added']} -{result['removed']} "
                        f"total={result['total']} (whale={result['whale_count']} analyst={result['analyst_count']})")
            except Exception as ex:
                return f"[ZMN Bot] Wallet refresh failed: {str(ex)[:100]}"

        else:
            return (f"[ZMN Bot] Commands: !zmn status | !zmn today | !zmn best | !zmn worst | "
                    f"!zmn pause <personality> | !zmn resume <personality> | !zmn meta | !zmn diagnose | !zmn refresh-wallets")

    except Exception as e:
        return f"[ZMN Bot] Error: {str(e)[:100]}"


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

WALLET_REFRESH_INTERVAL_HOURS = 48


async def _wallet_refresh_loop(redis_conn: aioredis.Redis | None):
    """Governance-managed wallet refresh — runs every 48 hours."""
    while True:
        try:
            pool = await get_pool()
            last_refresh = await pool.fetchval(
                "SELECT MAX(refreshed_at) FROM wallet_refresh_log"
            )
            now = datetime.now(timezone.utc)

            if last_refresh is None or (now - last_refresh).total_seconds() >= WALLET_REFRESH_INTERVAL_HOURS * 3600:
                logger.info("Governance: initiating wallet refresh")
                from services.nansen_wallet_fetcher import fetch_and_upsert_wallets
                result = await fetch_and_upsert_wallets(trigger="scheduled")

                # Signal signal_listener to re-register Helius webhook
                if redis_conn:
                    await redis_conn.publish(
                        "governance:commands",
                        json.dumps({"action": "refresh_helius_webhook", "reason": "wallet_list_updated"}),
                    )

                # Discord notification
                async with aiohttp.ClientSession() as session:
                    await send_discord(session,
                        f"🔄 Wallet list refreshed\n"
                        f"+{result['added']} added | -{result['removed']} dropped\n"
                        f"Total: {result['total']} | "
                        f"Whale: {result['whale_count']} | Smart money: {result['analyst_count']}"
                    )

                # Append to governance notes
                DATA_DIR.mkdir(exist_ok=True)
                with open(GOVERNANCE_NOTES_FILE, "a") as f:
                    f.write(
                        f"\n\n---\n## wallet_refresh -- {now.isoformat()}\n\n"
                        f"+{result['added']} -{result['removed']} total={result['total']}\n"
                    )
            else:
                hours_since = (now - last_refresh).total_seconds() / 3600
                logger.debug("Wallet refresh not due yet (%.1fh ago)", hours_since)

        except Exception as e:
            logger.error("Wallet refresh task error: %s", e)

        await asyncio.sleep(3600)  # Check every hour, act every 48h


async def main():
    from services.sentry_init import init_sentry
    init_sentry("governance")
    logger.info("Governance v2 starting (TEST_MODE=%s)", TEST_MODE)

    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set -- governance tasks will be skipped")

    # Ensure data files exist with defaults
    DATA_DIR.mkdir(exist_ok=True)
    for path, default in [
        (MEMORY_FILE, {"recommendations": [], "confirmed_strengths": [], "known_weaknesses": [], "prompt_effectiveness": []}),
        (PENDING_PARAMS_FILE, []),
        (ACTIVE_PARAMS_FILE, []),
        (PERSONALITY_WEIGHTS_FILE, {"bull_trend": {"speed_demon": 1.0, "analyst": 1.0, "whale_tracker": 1.0},
                                     "high_volatility": {"speed_demon": 1.0, "analyst": 1.0, "whale_tracker": 1.0},
                                     "choppy": {"speed_demon": 1.0, "analyst": 1.0, "whale_tracker": 1.0},
                                     "defensive": {"speed_demon": 1.0, "analyst": 1.0, "whale_tracker": 1.0}}),
    ]:
        if not path.exists():
            _save_json_file(path, default)

    pool = await get_pool()

    redis_conn = None
    try:
        redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True, max_connections=5)
        await redis_conn.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis connection failed: %s -- triggers disabled", e)

    tasks = [
        _scheduled_loop(pool, redis_conn),
        _anomaly_loop(pool, redis_conn),
        _smart_money_discovery_loop(redis_conn),  # P1: every 4h proactive scan
        _wallet_refresh_loop(redis_conn),          # Every 48h wallet refresh
        _governance_classification_loop(pool, redis_conn),  # Structured JSON mode classification
    ]
    if redis_conn:
        tasks.append(_trigger_listener(pool, redis_conn))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
