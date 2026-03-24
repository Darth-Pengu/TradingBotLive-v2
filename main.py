"""
ToxiBot v3.0 — Main Launcher
==============================
Starts all services concurrently in a single process.
Used by Railway as the single entrypoint.

Each service runs as an asyncio task. If any critical service crashes,
it is restarted automatically. The dashboard_api (web server) runs
on the PORT assigned by Railway.
"""

import asyncio
import importlib
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("main")

# Ensure the project root is on the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def run_service(name: str, module_path: str, critical: bool = False):
    """Run a service's main() with automatic restart on failure."""
    while True:
        try:
            logger.info("Starting service: %s", name)
            mod = importlib.import_module(module_path)
            await mod.main()
        except asyncio.CancelledError:
            logger.info("Service %s cancelled", name)
            break
        except Exception as e:
            logger.error("Service %s crashed: %s", name, e)
            if critical:
                logger.critical("Critical service %s failed — restarting in 5s", name)
            else:
                logger.warning("Service %s failed — restarting in 10s", name)
            await asyncio.sleep(5 if critical else 10)


async def run_dashboard():
    """Run the dashboard web server (uses aiohttp.web.run_app internally)."""
    from aiohttp import web
    from services.dashboard_api import create_app

    port = int(os.getenv("PORT", "8080"))
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Dashboard running on port %d", port)

    # Keep alive
    while True:
        await asyncio.sleep(3600)


async def main():
    test_mode = os.getenv("TEST_MODE", "true").lower() == "true"
    logger.info("=" * 60)
    logger.info("ToxiBot v3.0 starting")
    logger.info("TEST_MODE=%s", test_mode)
    logger.info("=" * 60)

    if test_mode:
        logger.info("TEST MODE — no real trades will be executed")

    tasks = [
        # Web dashboard (must bind PORT for Railway health check)
        asyncio.create_task(run_dashboard()),

        # Core infrastructure
        asyncio.create_task(run_service("market_health", "services.market_health", critical=True)),
        asyncio.create_task(run_service("signal_listener", "services.signal_listener", critical=True)),
        asyncio.create_task(run_service("treasury", "services.treasury", critical=True)),

        # Processing pipeline
        asyncio.create_task(run_service("ml_engine", "services.ml_engine")),
        asyncio.create_task(run_service("signal_aggregator", "services.signal_aggregator")),
        asyncio.create_task(run_service("bot_core", "services.bot_core")),

        # Governance (lowest priority)
        asyncio.create_task(run_service("governance", "services.governance")),
    ]

    # Wait for all — if one crashes the run_service wrapper restarts it
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
