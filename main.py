"""
ZMN Bot v3.0 — Main Launcher
==============================
Routes each Railway service to its own code via SERVICE_NAME env var.
Falls back to legacy mode (all services) if SERVICE_NAME is not set.
"""

import asyncio
import logging
import os
import sys
import importlib

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

# Check both SERVICE_NAME (explicit) and RAILWAY_SERVICE_NAME (auto-set by Railway)
SERVICE_NAME = os.getenv("SERVICE_NAME", "") or os.getenv("RAILWAY_SERVICE_NAME", "")

SERVICE_MAP = {
    "signal_listener": "services.signal_listener",
    "signal_aggregator": "services.signal_aggregator",
    "bot_core": "services.bot_core",
    "ml_engine": "services.ml_engine",
    "market_health": "services.market_health",
    "governance": "services.governance",
    "treasury": "services.treasury",
    "web": None,  # Special — runs dashboard
}


async def run_service(name: str, module_path: str, critical: bool = False):
    """Run a service's main() with automatic restart on failure and exponential backoff."""
    base_delay = 5 if critical else 10
    max_delay = 300  # Cap at 5 minutes
    current_delay = base_delay
    consecutive_failures = 0

    while True:
        try:
            logger.info("Starting service: %s", name)
            mod = importlib.import_module(module_path)
            await mod.main()
            # Service exited cleanly — reset backoff
            logger.warning("Service %s exited cleanly — restarting in %ds", name, base_delay)
            current_delay = base_delay
            consecutive_failures = 0
            await asyncio.sleep(base_delay)
        except asyncio.CancelledError:
            logger.info("Service %s cancelled", name)
            break
        except Exception as e:
            consecutive_failures += 1
            logger.error("Service %s crashed (attempt %d): %s", name, consecutive_failures, e, exc_info=True)
            logger.warning("Service %s restarting in %ds", name, current_delay)
            await asyncio.sleep(current_delay)
            current_delay = min(current_delay * 2, max_delay)


async def main():
    test_mode = os.getenv("TEST_MODE", "true").lower() == "true"
    logger.info("=" * 60)
    logger.info("ZMN Bot v3.0 starting — SERVICE_NAME=%s", SERVICE_NAME or "(not set)")
    logger.info("TEST_MODE=%s", test_mode)
    logger.info("=" * 60)

    if test_mode:
        logger.info("TEST MODE — no real trades will be executed")

    # ---------------------------------------------------------------
    # SINGLE SERVICE MODE — each Railway service runs only its own code
    # ---------------------------------------------------------------
    if SERVICE_NAME == "web":
        logger.info("Starting SINGLE service: web (dashboard only)")
        from aiohttp import web
        from services.dashboard_api import create_app

        port = int(os.getenv("PORT", "8080"))
        app = create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("Dashboard running on port %d (SERVICE_NAME=web)", port)
        await asyncio.Event().wait()  # Keep alive forever

    elif SERVICE_NAME in SERVICE_MAP and SERVICE_MAP[SERVICE_NAME]:
        logger.info("Starting SINGLE service: %s", SERVICE_NAME)

        # Lightweight health endpoint so Railway healthcheck passes
        from aiohttp import web

        health_app = web.Application()

        async def _health(_request):
            return web.json_response({"status": "ok", "service": SERVICE_NAME})

        health_app.router.add_get("/api/health", _health)
        port = int(os.getenv("PORT", "8080"))
        runner = web.AppRunner(health_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("Health endpoint running on port %d for service %s", port, SERVICE_NAME)

        mod = importlib.import_module(SERVICE_MAP[SERVICE_NAME])
        await mod.main()

    elif not SERVICE_NAME:
        # ---------------------------------------------------------------
        # LEGACY MODE — no SERVICE_NAME set, run everything (backward compat)
        # ---------------------------------------------------------------
        logger.warning("No SERVICE_NAME set — running ALL services (LEGACY MODE)")
        logger.warning("Set SERVICE_NAME env var on each Railway service to fix!")

        from aiohttp import web
        from services.dashboard_api import create_app

        port = int(os.getenv("PORT", "8080"))
        app = create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("Dashboard running on port %d — health check ready", port)

        tasks = [
            asyncio.create_task(run_service("market_health", "services.market_health", critical=True)),
            asyncio.create_task(run_service("signal_listener", "services.signal_listener", critical=True)),
            asyncio.create_task(run_service("treasury", "services.treasury", critical=True)),
            asyncio.create_task(run_service("ml_engine", "services.ml_engine")),
            asyncio.create_task(run_service("signal_aggregator", "services.signal_aggregator")),
            asyncio.create_task(run_service("bot_core", "services.bot_core")),
            asyncio.create_task(run_service("governance", "services.governance")),
        ]
        logger.info("All %d services launched (LEGACY MODE)", len(tasks))
        await asyncio.gather(*tasks)

    else:
        logger.error("Unknown SERVICE_NAME: %s — valid: %s", SERVICE_NAME, list(SERVICE_MAP.keys()))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
