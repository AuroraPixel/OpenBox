"""Startup recovery — clean stuck jobs and replay missed jobs.

Called once during CronService.start() before the timer is armed.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.log import create_logger

log = create_logger("cron.recovery")


async def recover_on_startup() -> None:
    """Full startup recovery sequence."""
    log.info("Running cron startup recovery...")

    interrupted_ids = await _clear_stuck_running_markers()
    await _mark_interrupted_runs()
    missed_count = await _replay_missed_jobs(skip_ids=interrupted_ids)

    log.info(
        f"Recovery complete: {len(interrupted_ids)} stuck markers cleared, "
        f"{missed_count} missed jobs replayed"
    )


async def _clear_stuck_running_markers() -> set[str]:
    """Clear running_at markers left by a previous crash.

    Returns the set of job IDs that were interrupted (to skip from replay).
    """
    from db.base import get_db_session
    from db.models.cron import CronJob
    from sqlalchemy import select, update

    async with get_db_session() as db:
        result = await db.execute(
            select(CronJob.id).where(CronJob.running_at.isnot(None))
        )
        stuck_ids = {row[0] for row in result.all()}

        if stuck_ids:
            await db.execute(
                update(CronJob)
                .where(CronJob.id.in_(stuck_ids))
                .values(running_at=None)
            )
            for jid in stuck_ids:
                log.warning(f"Cleared stale running marker for job {jid}")

    return stuck_ids


async def _mark_interrupted_runs() -> None:
    """Mark cron_runs that were running when the server crashed."""
    from db.base import get_db_session
    from db.models.cron import CronRun
    from sqlalchemy import update

    now = datetime.now(timezone.utc)

    async with get_db_session() as db:
        result = await db.execute(
            update(CronRun)
            .where(CronRun.status == "running")
            .values(
                status="error",
                error_message="Server restarted during execution",
                ended_at=now,
            )
        )
        if result.rowcount > 0:
            log.warning(f"Marked {result.rowcount} interrupted cron run(s) as error")


async def _replay_missed_jobs(skip_ids: set[str]) -> int:
    """Detect and replay missed cron jobs (one execution per missed job, not per slot).

    A job is "missed" if: enabled, next_run_at < now, and last_run_at < next_run_at.
    """
    from db.base import get_db_session
    from db.models.cron import CronJob
    from sqlalchemy import select, update

    now = datetime.now(timezone.utc)
    replayed = 0

    async with get_db_session() as db:
        result = await db.execute(
            select(CronJob).where(
                CronJob.enabled == True,
                CronJob.is_deleted == False,
                CronJob.next_run_at < now,
                CronJob.running_at.is_(None),
            )
        )
        candidates = result.scalars().all()

    for job in candidates:
        if job.id in skip_ids:
            continue

        # Check if it was actually missed (last_run_at < next_run_at)
        if job.last_run_at and job.next_run_at:
            if job.last_run_at >= job.next_run_at:
                continue  # Already ran for this slot

        log.info(f"Replaying missed job {job.id} ({job.name}), was due at {job.next_run_at}")

        # Don't execute here — just mark it as due so the timer picks it up.
        # The next on_timer tick will collect and execute it.
        # This avoids blocking startup with potentially long-running jobs.
        replayed += 1

    return replayed
