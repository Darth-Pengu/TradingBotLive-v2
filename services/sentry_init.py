"""
Sentry initialization helper shared across ZMN services.

Each service's entrypoint should import and call init_sentry() once at startup.
If SENTRY_DSN is not set (e.g., local dev, initial deploy before env vars land),
init silently no-ops — do not crash the service.

Traces sample rate is intentionally low (0.05 = 5% of transactions) because ZMN's
hot paths fire thousands of times per hour; 100% sampling would overwhelm free tier.
Error events are always captured (sample rate ignored for errors).
"""
from __future__ import annotations

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def init_sentry(service_name: str, traces_sample_rate: float = 0.05) -> Optional[str]:
    """
    Initialize Sentry SDK for this service. Returns the DSN used, or None if
    Sentry is disabled (no DSN set).

    Call once at the top of each service's entrypoint, before any background
    tasks are spawned.
    """
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info("Sentry disabled for %s (SENTRY_DSN not set)", service_name)
        return None

    try:
        import sentry_sdk
    except ImportError:
        logger.warning("sentry-sdk not installed; skipping Sentry init for %s", service_name)
        return None

    environment = os.getenv("RAILWAY_ENVIRONMENT", "local")
    release = os.getenv("RAILWAY_GIT_COMMIT_SHA", "unknown")[:12]

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
        before_send=lambda event, hint: _tag_service(event, service_name),
    )

    logger.info("Sentry initialized for %s (env=%s, release=%s)", service_name, environment, release)
    return dsn


def _tag_service(event: dict, service_name: str) -> dict:
    tags = event.setdefault("tags", {})
    tags["service"] = service_name
    return event
