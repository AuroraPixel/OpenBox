"""Periodic cleanup, piggybacked on the cron timer tick.

Removes cron temp sessions older than RETENTION_HOURS, cron_runs older than
RETENTION_DAYS, and project directories left behind in the sandbox by projects
the user deleted. Nothing else reclaims the last of those: the sandbox outlives
individual sessions, and WUYING's delete_container is a no-op, so without this
sweep a deleted project's files stay on disk indefinitely.
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

    # Each step is isolated: a sandbox that is unreachable must not stop the
    # database-side cleanup, which is the part that always works.
    for step in (_sweep_temp_sessions, _sweep_old_runs, _sweep_workspace):
        try:
            await step()
        except Exception as e:
            log.error(f"Reaper step {step.__name__} failed: {e}")


async def _sweep_temp_sessions() -> None:
    """Delete expired temporary cron sessions."""
    from db.base import get_db_session
    from db.models.cron import CronRun
    from sqlalchemy import select

    cutoff = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)

    from db.models.session import Session as SessionORM

    async with get_db_session() as db:
        # The owning user comes along: delete_session scopes its update by
        # user_id, and passing "default" against a real ULID matched no rows,
        # so nothing was ever actually reaped.
        result = await db.execute(
            select(CronRun.temp_session_id, SessionORM.user_id)
            .join(SessionORM, SessionORM.id == CronRun.temp_session_id)
            .where(
                CronRun.temp_session_id.isnot(None),
                CronRun.status != "running",
                CronRun.started_at < cutoff,
                SessionORM.is_deleted == False,  # noqa: E712
            )
            .distinct()
        )
        expired = [(sid, uid) for sid, uid in result.all() if sid]

    if not expired:
        return

    # Delete the temp sessions (cascade deletes messages + parts)
    from session.session import delete_session
    deleted = 0
    for sid, uid in expired:
        try:
            await delete_session(sid, user_id=uid)
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


async def _sweep_workspace() -> None:
    """Bin directories for deleted projects, and empty stale trash.

    Runs against whichever sandbox is up. Directories the database has never
    heard of are left alone and only logged — an unrecognised directory is far
    more likely to be something worth keeping than something worth deleting.
    """
    from project.reclaim import reclaim

    try:
        from sandbox import sandbox_manager
        client = await sandbox_manager.get_only_client()
    except Exception as e:
        log.debug(f"No sandbox for workspace sweep: {e}")
        return
    if client is None:
        return

    result = await reclaim(client)
    if result.get("binned") or result.get("purged"):
        log.info(
            f"Workspace sweep: binned {len(result['binned'])}, "
            f"purged {len(result['purged'])}"
        )
