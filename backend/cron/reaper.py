"""Temporary session cleaner — removes expired cron execution sessions.

Runs periodically (piggybacked on timer tick), cleaning up temp sessions
older than RETENTION_HOURS and cron_runs older than RETENTION_DAYS.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

from core.log import create_logger

log = create_logger("cron.reaper")

REAPER_INTERVAL_MS = 5 * 60 * 1000   # 5 minutes between sweeps
RETENTION_HOURS = 24                   # Keep temp sessions for 24 hours
RETENTION_DAYS = 30                    # Keep cron_runs for 30 days

_last_sweep_at_ms: int = 0


async def sweep_if_due() -> None:
    """Run sweep if enough time has passed since the last one.

    Call this from the timer tick's finally block.
    """
    global _last_sweep_at_ms
    now_ms = int(time.time() * 1000)

    if now_ms - _last_sweep_at_ms < REAPER_INTERVAL_MS:
        return

    _last_sweep_at_ms = now_ms

    try:
        await _sweep_temp_sessions()
        await _sweep_old_runs()
    except Exception as e:
        log.error(f"Reaper sweep error: {e}")


async def _sweep_temp_sessions() -> None:
    """Delete expired temporary cron sessions."""
    from db.base import get_db_session
    from db.models.cron import CronRun
    from sqlalchemy import select

    cutoff = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)

    async with get_db_session() as db:
        result = await db.execute(
            select(CronRun.temp_session_id)
            .where(
                CronRun.temp_session_id.isnot(None),
                CronRun.status != "running",
                CronRun.started_at < cutoff,
            )
            .distinct()
        )
        expired_session_ids = [row[0] for row in result.all() if row[0]]

    if not expired_session_ids:
        return

    # Delete the temp sessions (cascade deletes messages + parts)
    from session.session import delete_session
    deleted = 0
    for sid in expired_session_ids:
        try:
            await delete_session(sid, user_id="default")
            deleted += 1
        except Exception:
            pass  # Session may already be deleted

    if deleted:
        log.info(f"Reaped {deleted} expired cron temp session(s)")


async def _sweep_old_runs() -> None:
    """Delete cron_runs older than RETENTION_DAYS."""
    from db.base import get_db_session
    from db.models.cron import CronRun
    from sqlalchemy import delete

    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)

    async with get_db_session() as db:
        result = await db.execute(
            delete(CronRun).where(CronRun.started_at < cutoff)
        )
        if result.rowcount > 0:
            log.info(f"Cleaned up {result.rowcount} old cron run(s)")
