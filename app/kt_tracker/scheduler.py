"""Background scheduler that periodically runs the Microsoft 365 meeting sync.

Started/stopped from the FastAPI ``lifespan`` in ``app.api.main`` so KT
activities stay current without anyone calling an API by hand. Controlled via
environment variables so it can be safely disabled (default) until a tenant
app registration and mailbox are configured.
"""

from __future__ import annotations

import asyncio
import logging
import os

from app.kt_tracker.meeting_sync_service import sync_all

logger = logging.getLogger("kt_tracker.scheduler")

SYNC_ENABLED = os.getenv("KT_GRAPH_SYNC_ENABLED", "false").lower() in ("1", "true", "yes")
SYNC_INTERVAL_SECONDS = int(os.getenv("KT_GRAPH_SYNC_INTERVAL_SECONDS", "900"))
MAILBOXES = [m.strip() for m in os.getenv("KT_GRAPH_MAILBOXES", "").split(",") if m.strip()]


class KtGraphScheduler:
    """Runs ``meeting_sync_service.sync_all`` on a fixed interval for each mailbox."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    async def _loop(self) -> None:
        while True:
            for mailbox in MAILBOXES:
                try:
                    result = await asyncio.to_thread(sync_all, mailbox)
                    logger.info("KT Graph sync for %s: %s", mailbox, result.message)
                except Exception:  # pragma: no cover - keep the loop alive
                    logger.exception("KT Graph sync failed for mailbox %s", mailbox)
            await asyncio.sleep(SYNC_INTERVAL_SECONDS)

    def start(self) -> None:
        if not SYNC_ENABLED:
            logger.info(
                "KT Graph scheduler disabled (set KT_GRAPH_SYNC_ENABLED=true to enable)."
            )
            return
        if not MAILBOXES:
            logger.warning(
                "KT Graph scheduler enabled but KT_GRAPH_MAILBOXES is empty; nothing to sync."
            )
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info(
                "KT Graph scheduler started: interval=%ss mailboxes=%s",
                SYNC_INTERVAL_SECONDS,
                MAILBOXES,
            )

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("KT Graph scheduler stopped.")


scheduler = KtGraphScheduler()
