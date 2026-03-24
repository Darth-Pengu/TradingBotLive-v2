"""
ToxiBot Agent Governance Layer
================================
Separate scheduled process calling the Anthropic Claude API for reasoning-level oversight.
NEVER touches trade execution. Advisory only.

Schedule:
- wallet_rescore: Weekly (Monday 02:00 UTC)
- daily_briefing: Daily (06:00 UTC)
- drawdown_diagnosis: Triggered (via Redis pub/sub on drawdown > 10%)
- loss_streak_review: Triggered (via Redis on 3+ consecutive losses/personality)
- monthly_report: Monthly (1st of month 06:00 UTC)

Outputs:
- whale_wallets_pending.json (requires manual review + rename to activate)
- governance_notes.md (appended)
- Discord notifications
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import aiosqlite
import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("governance")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DATABASE_PATH = os.getenv("DATABASE_PATH", "toxibot.db")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOVERNANCE_MODEL = os.getenv("GOVERNANCE_MODEL", "claude-sonnet-4-6")

GOVERNANCE_SCHEDULE = {
    "wallet_rescore":     "weekly",
    "daily_briefing":     "daily",
    "drawdown_diagnosis": "triggered",
    "loss_streak_review": "triggered",
    "monthly_report":     "monthly",
}

SYSTEM_PROMPT = """You are the governance agent for ToxiBot, a Solana memecoin trading bot.
Your role is strategic oversight — you analyse performance data, score whale wallets,
and make recommendations. You never make live trading decisions.
Write clearly and concisely. All output will be reviewed by the bot owner before any
parameter changes are applied. Flag anything unusual. Be direct about problems."""


def build_governance_prompt(task_type: str, context: dict) -> str:
    if task_type == "wallet_rescore":
        return f"""
Review the following whale wallet performance data from the past 7 days and provide
an updated score (0-100) for each wallet. Remove wallets that no longer meet minimum
thresholds. Suggest any new wallets from the top trader lists that should be added.

Current wallet list: {json.dumps(context.get('current_wallets', []), indent=2)}
Performance data (7 days): {json.dumps(context.get('performance_data', {}), indent=2)}
Vybe top trader data: {json.dumps(context.get('vybe_data', {}), indent=2)}

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

Drawdown details: {json.dumps(context.get('drawdown_info', {}), indent=2)}
Recent trades (last 48h): {json.dumps(context.get('recent_trades', []), indent=2)}
Market conditions during drawdown: {json.dumps(context.get('market_conditions', {}), indent=2)}
Signal sources that triggered losing trades: {json.dumps(context.get('signal_sources', []), indent=2)}

Provide: (1) root cause diagnosis, (2) specific parameter changes to consider,
(3) whether trading should resume or stay paused. Be direct.
"""

    elif task_type == "loss_streak_review":
        return f"""
{context.get('personality', 'Unknown')} has had {context.get('consecutive_losses', 0)} consecutive losses.
Review the losing trades and determine whether this is:
a) Bad luck in a volatile market (no action needed - resume at reduced sizing)
b) A signal quality issue (specific signal sources to stop trusting temporarily)
c) A parameter issue (specific thresholds to adjust)
d) A market regime change (the personality's strategy isn't suited to current conditions)

Losing trades: {json.dumps(context.get('losing_trades', []), indent=2)}
Current parameters: {json.dumps(context.get('parameters', {}), indent=2)}

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

    return "No valid task type provided."


async def write_governance_output(task_type: str, output: str, context: dict):
    timestamp = datetime.now(timezone.utc).isoformat()

    if task_type == "wallet_rescore":
        # Write to pending file — requires manual review (Section 7)
        try:
            updated_wallets = json.loads(output)
            with open("data/whale_wallets_pending.json", "w") as f:
                json.dump(updated_wallets, f, indent=2)
            logger.info("Whale wallet rescore written to whale_wallets_pending.json")
        except json.JSONDecodeError:
            # If Claude didn't return valid JSON, save raw output to notes
            with open("data/governance_notes.md", "a") as f:
                f.write(f"\n\n---\n## {task_type} — {timestamp}\n\n**WARNING: Could not parse as JSON. Raw output:**\n\n{output}\n")
            logger.warning("wallet_rescore output was not valid JSON — saved to notes")
    else:
        with open("data/governance_notes.md", "a") as f:
            f.write(f"\n\n---\n## {task_type} — {timestamp}\n\n{output}\n")

    logger.info("Governance output written for %s", task_type)


async def send_discord(session: aiohttp.ClientSession, message: str):
    if not DISCORD_WEBHOOK_URL:
        logger.info("Discord (no webhook): %s", message[:200])
        return
    try:
        await session.post(DISCORD_WEBHOOK_URL, json={"content": message[:2000]},
                           timeout=aiohttp.ClientTimeout(total=10))
    except Exception as e:
        logger.warning("Discord notification failed: %s", e)


async def run_governance_task(task_type: str, context_data: dict, session: aiohttp.ClientSession):
    """Call Claude API with relevant data. Never writes to execution config directly."""
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — skipping governance task: %s", task_type)
        return

    logger.info("Running governance task: %s", task_type)

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

        user_prompt = build_governance_prompt(task_type, context_data)

        message = await client.messages.create(
            model=GOVERNANCE_MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        output = message.content[0].text
        token_usage = message.usage

        logger.info("Governance %s complete — tokens: input=%d, output=%d",
                     task_type, token_usage.input_tokens, token_usage.output_tokens)

        await write_governance_output(task_type, output, context_data)

        if task_type == "wallet_rescore":
            await send_discord(
                session,
                "Whale wallet rescore complete. Review data/whale_wallets_pending.json "
                "and rename to whale_wallets.json to activate. Changes NOT yet live."
            )
        else:
            await send_discord(session, f"Governance: {task_type} complete — check governance_notes.md")

    except Exception as e:
        logger.error("Governance task %s failed: %s", task_type, e)
        await send_discord(session, f"Governance ERROR: {task_type} failed — {str(e)[:200]}")


async def _gather_context(db: aiosqlite.Connection, redis_conn: aioredis.Redis | None, task_type: str) -> dict:
    """Gather context data for a governance task from DB and Redis."""
    context = {}
    now = time.time()

    try:
        if task_type == "daily_briefing":
            # Last 24h trades
            cursor = await db.execute(
                "SELECT * FROM trades WHERE created_at > ? ORDER BY created_at DESC",
                (now - 86400,),
            )
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            context["trades_24h"] = [dict(zip(cols, r)) for r in rows]

            # Portfolio snapshot
            cursor = await db.execute(
                "SELECT * FROM portfolio_snapshots ORDER BY id DESC LIMIT 1"
            )
            row = await cursor.fetchone()
            if row:
                cols = [d[0] for d in cursor.description]
                context["portfolio"] = dict(zip(cols, row))

            # Market health from Redis
            if redis_conn:
                health = await redis_conn.get("market:health")
                if health:
                    context["market_health"] = json.loads(health)

        elif task_type == "wallet_rescore":
            try:
                with open("data/whale_wallets.json") as f:
                    context["current_wallets"] = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                context["current_wallets"] = []
            context["performance_data"] = {}
            context["vybe_data"] = {}

        elif task_type == "monthly_report":
            # Last 30 days of trades
            cursor = await db.execute(
                "SELECT * FROM trades WHERE created_at > ? ORDER BY created_at DESC",
                (now - 30 * 86400,),
            )
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            context["trades_30d"] = [dict(zip(cols, r)) for r in rows]

            # Treasury sweeps
            try:
                cursor = await db.execute(
                    "SELECT * FROM treasury_sweeps WHERE timestamp > ? ORDER BY timestamp DESC",
                    (datetime.fromtimestamp(now - 30 * 86400, tz=timezone.utc).isoformat(),),
                )
                rows = await cursor.fetchall()
                cols = [d[0] for d in cursor.description]
                context["treasury_sweeps"] = [dict(zip(cols, r)) for r in rows]
            except Exception:
                context["treasury_sweeps"] = []

    except Exception as e:
        logger.error("Context gathering failed for %s: %s", task_type, e)

    return context


# --- Scheduled tasks ---
async def _scheduled_loop(db: aiosqlite.Connection, redis_conn: aioredis.Redis | None):
    """Run scheduled governance tasks."""
    last_daily = 0.0
    last_weekly = 0.0
    last_monthly = 0.0

    async with aiohttp.ClientSession() as session:
        while True:
            now = datetime.now(timezone.utc)
            now_ts = time.time()

            # Daily briefing at 06:00 UTC
            if now.hour == 6 and now_ts - last_daily > 82800:
                context = await _gather_context(db, redis_conn, "daily_briefing")
                await run_governance_task("daily_briefing", context, session)
                last_daily = now_ts

            # Weekly wallet rescore on Monday at 02:00 UTC
            if now.weekday() == 0 and now.hour == 2 and now_ts - last_weekly > 604800:
                context = await _gather_context(db, redis_conn, "wallet_rescore")
                await run_governance_task("wallet_rescore", context, session)
                last_weekly = now_ts

            # Monthly report on 1st at 06:00 UTC
            if now.day == 1 and now.hour == 6 and now_ts - last_monthly > 2592000:
                context = await _gather_context(db, redis_conn, "monthly_report")
                await run_governance_task("monthly_report", context, session)
                last_monthly = now_ts

            await asyncio.sleep(60)  # Check every minute


# --- Triggered tasks via Redis ---
async def _trigger_listener(db: aiosqlite.Connection, redis_conn: aioredis.Redis):
    """Listen for triggered governance events."""
    pubsub = redis_conn.pubsub()
    await pubsub.subscribe("drawdown:significant", "streak:loss")
    logger.info("Listening for governance triggers")

    async with aiohttp.ClientSession() as session:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            channel = message["channel"]
            try:
                data = json.loads(message["data"])

                if channel == "drawdown:significant":
                    context = await _gather_context(db, redis_conn, "drawdown_diagnosis")
                    context["drawdown_info"] = data
                    await run_governance_task("drawdown_diagnosis", context, session)

                elif channel == "streak:loss":
                    context = data
                    # Fetch recent losing trades for this personality
                    cursor = await db.execute(
                        """SELECT * FROM trades WHERE personality = ? AND outcome = 'loss'
                           ORDER BY created_at DESC LIMIT 10""",
                        (data.get("personality", ""),),
                    )
                    rows = await cursor.fetchall()
                    cols = [d[0] for d in cursor.description]
                    context["losing_trades"] = [dict(zip(cols, r)) for r in rows]
                    context["parameters"] = {}
                    await run_governance_task("loss_streak_review", context, session)

            except Exception as e:
                logger.error("Trigger handler error: %s", e)


async def main():
    logger.info("Governance service starting")

    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — governance tasks will be skipped")

    db = await aiosqlite.connect(DATABASE_PATH)

    redis_conn = None
    try:
        redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_conn.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis connection failed: %s — triggers disabled", e)

    tasks = [_scheduled_loop(db, redis_conn)]
    if redis_conn:
        tasks.append(_trigger_listener(db, redis_conn))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
