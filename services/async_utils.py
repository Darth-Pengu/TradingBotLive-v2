"""
ZMN Bot — shared async resilience helpers.

FIX-PUBSUB-ISOLATION (2026-06-03, FULL-CODE-AUDIT-001 §B Phase-0 #1):
`supervise()` is a supervised-restart wrapper for long-lived service
coroutines. Each service launches its background tasks via a single top-level
`asyncio.gather(...)`. Those gathers had no `return_exceptions=True` and no
per-task supervision, so a transient exception escaping ANY task — most often a
redis pubsub `TimeoutError` raised by an unguarded `async for pubsub.listen()`
— propagated through the gather, cancelled every sibling, and tore down the
whole container. Railway then restart-looped the service (~6.7s), which is the
2026-05-28 dual-service outage root cause (signal_listener + bot_core CRASHED).

Wrapping each gather member in `supervise(lambda: coro(...), "name")` isolates a
crashing coroutine from its siblings: the failed task is restarted with capped
exponential backoff while the others keep running. Because restarting a pubsub
listener re-runs its `subscribe(...)` + `listen()` setup, this delivers BOTH
crash-isolation AND self-healing reconnection without editing the listener
bodies — the minimal, uniform, reversible fix the audit called for.

Semantics:
  * Exception      -> log (with traceback) + sleep(backoff) + restart;
                      backoff doubles each crash up to ``max_delay``.
  * clean return   -> log + STOP (a coroutine that returns on purpose — e.g. a
                      disabled monitor that early-returns — is never hot-looped).
  * CancelledError -> propagate (cooperative shutdown is honoured, so
                      ``task.cancel()`` / event-loop teardown still works).

Pass a zero-arg FACTORY, not a coroutine: ``supervise(lambda: foo(x), "foo")``,
never ``supervise(foo(x), "foo")`` — the factory is re-invoked on each restart
to produce a fresh awaitable.
"""

import asyncio
import logging

logger = logging.getLogger("async_utils")


async def supervise(coro_factory, name, *, base_delay: float = 2.0, max_delay: float = 60.0):
    """Run ``coro_factory()`` in a restart-on-crash loop.

    Args:
        coro_factory: zero-arg callable returning a fresh awaitable each call.
        name: label used in log lines.
        base_delay: initial restart delay in seconds after a crash.
        max_delay: cap on the (doubling) restart delay.
    """
    delay = base_delay
    while True:
        try:
            await coro_factory()
        except asyncio.CancelledError:
            logger.info("[supervise] %s cancelled — exiting", name)
            raise
        except Exception:  # noqa: BLE001 — backstop: isolate this task's crash from siblings
            logger.error(
                "[supervise] %s crashed — restarting in %.1fs", name, delay, exc_info=True,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
            continue
        # Clean return is not a failure — do not restart (avoids hot-looping a
        # coroutine that intentionally returns, e.g. a disabled feature monitor).
        logger.info("[supervise] %s returned cleanly — not restarting", name)
        return
