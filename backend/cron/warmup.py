"""Container warmup scheduler — pre-warm containers before cron job execution.

Strategy:
  - Scan all enabled jobs, group by user_id
  - If any job's next_run_at is within WARMUP_LEAD_TIME, ensure container exists
  - If user's minimum job interval < WARMUP_LEAD_TIME, mark container as keepalive
  - Runs piggy-backed on the timer tick (every 60s)
"""
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

from core.log import create_logger
from models.container import ContainerStatus

log = create_logger("cron.warmup")

WARMUP_LEAD_TIME_MS = 5 * 60 * 1000  # 5 minutes
WARMUP_COOLDOWN_MS = 60 * 1000       # Don't re-warm within 60s

# Per-user warmup state
_warmup_state: dict[str, dict] = {}  # user_id -> {"requested_at": ms, "ready": bool}

# Set of user_ids that should keep containers alive
_keepalive_users: set[str] = set()


async def check_warmup() -> None:
    """Check if any containers need pre-warming. Called from timer tick."""
    from db.base import get_db_session
    from db.models.cron import CronJob
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    warmup_horizon = now + timedelta(milliseconds=WARMUP_LEAD_TIME_MS)

    # Find jobs that will fire within the warmup horizon
    async with get_db_session() as db:
        result = await db.execute(
            select(CronJob.user_id, CronJob.session_id, CronJob.schedule)
            .where(
                CronJob.enabled == True,
                CronJob.is_deleted == False,
                CronJob.next_run_at.isnot(None),
                CronJob.next_run_at <= warmup_horizon,
            )
            .distinct()
        )
        upcoming = result.all()

    if not upcoming:
        return

    # Group by user_id
    users_to_warm: dict[str, str] = {}  # user_id -> any session_id (for sandbox acquisition)
    for row in upcoming:
        user_id, session_id = row[0], row[1]
        if user_id not in users_to_warm:
            users_to_warm[user_id] = session_id

    # Warm up each user's container
    for user_id, session_id in users_to_warm.items():
        state = _warmup_state.get(user_id, {})

        # Cooldown check
        last_req = state.get("requested_at", 0)
        if now_ms - last_req < WARMUP_COOLDOWN_MS:
            continue

        # Check if container is already running
        from sandbox import provider
        existing = provider.get_user_container(user_id)
        if existing and existing.status == ContainerStatus.RUNNING:
            _warmup_state[user_id] = {"requested_at": now_ms, "ready": True}
            continue

        # Trigger container creation
        log.info(f"Pre-warming container for user {user_id} (upcoming cron job)")
        _warmup_state[user_id] = {"requested_at": now_ms, "ready": False}

        try:
            from sandbox import sandbox_manager
            await sandbox_manager.get_client(session_id, user_id=user_id)
            _warmup_state[user_id]["ready"] = True
            log.info(f"Container pre-warmed for user {user_id}")
        except Exception as e:
            log.warning(f"Warmup failed for user {user_id}: {e}")


async def update_keepalive_users() -> None:
    """Update the set of users whose containers should not be auto-destroyed.

    A user gets keepalive if their minimum cron interval < WARMUP_LEAD_TIME.
    """
    global _keepalive_users
    from db.base import get_db_session
    from db.models.cron import CronJob
    from sqlalchemy import select
    from cron.schedule import compute_job_interval_ms

    async with get_db_session() as db:
        result = await db.execute(
            select(CronJob)
            .where(
                CronJob.enabled == True,
                CronJob.is_deleted == False,
            )
        )
        jobs = result.scalars().all()

    # Group by user_id, find minimum interval
    user_intervals: dict[str, int] = {}
    for job in jobs:
        sched = job.schedule
        if isinstance(sched, dict):
            from cron.types import CronScheduleCron, CronScheduleEvery
            if sched.get("kind") == "every":
                interval = sched.get("every_ms", 0)
            elif sched.get("kind") == "cron":
                try:
                    s = CronScheduleCron(expr=sched["expr"], tz=sched.get("tz", "UTC"))
                    interval = compute_job_interval_ms(s) or 0
                except Exception:
                    interval = 0
            else:
                continue

            if interval > 0:
                current_min = user_intervals.get(job.user_id, float("inf"))
                user_intervals[job.user_id] = min(current_min, interval)

    new_keepalive = {
        uid for uid, interval in user_intervals.items()
        if interval < WARMUP_LEAD_TIME_MS
    }

    if new_keepalive != _keepalive_users:
        added = new_keepalive - _keepalive_users
        removed = _keepalive_users - new_keepalive
        if added:
            log.info(f"Keepalive containers added for users: {added}")
        if removed:
            log.info(f"Keepalive containers removed for users: {removed}")
        _keepalive_users = new_keepalive


def is_keepalive_user(user_id: str) -> bool:
    """Check if a user's container should be kept alive (not auto-destroyed)."""
    return user_id in _keepalive_users
