"""Timer-based job scheduler — translated from OpenClaw's timer.ts.

Core loop: arm_timer → on_timer → collect_runnable → execute → apply_result → re-arm.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any

from core.log import create_logger
from cron.types import (
    BACKOFF_SCHEDULE_MS, MAX_TIMER_DELAY_MS, MIN_REFIRE_GAP_MS,
    STUCK_RUN_MS, TRANSIENT_PATTERNS, CronJobStatus,
)
from cron.schedule import compute_next_run_at

log = create_logger("cron.timer")


class TimerState:
    """Mutable state for the timer loop."""

    def __init__(self):
        self.running = False
        self.timer_handle: asyncio.TimerHandle | None = None
        self.watchdog_handle: asyncio.TimerHandle | None = None
        self.lock = asyncio.Lock()
        self.max_concurrent_jobs = 2

        # Callbacks (injected by CronService)
        self.execute_job: Any = None  # async (job_row) -> dict
        self.on_job_result: Any = None  # async (job_id, result) -> None


def arm_timer(state: TimerState) -> None:
    """Schedule the next timer tick based on earliest due job."""
    _cancel_timer(state)

    loop = asyncio.get_event_loop()
    if loop.is_closed():
        return

    # Find next wake time
    next_wake_coro = _find_next_wake_ms(state)
    loop.create_task(_arm_timer_async(state, next_wake_coro))


async def _arm_timer_async(state: TimerState, next_wake_coro) -> None:
    """Async helper for arm_timer — needs DB access."""
    try:
        next_wake_at = await next_wake_coro
        now_ms = _now_ms()

        if next_wake_at is None:
            # No jobs scheduled, wake in MAX_TIMER_DELAY to check again
            delay_s = MAX_TIMER_DELAY_MS / 1000
        else:
            delay_ms = max(0, next_wake_at - now_ms)
            # Floor: prevent tight loops
            if delay_ms == 0:
                delay_ms = MIN_REFIRE_GAP_MS
            # Ceiling: wake at least once per minute
            delay_ms = min(delay_ms, MAX_TIMER_DELAY_MS)
            delay_s = delay_ms / 1000

        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            state.timer_handle = loop.call_later(delay_s, lambda: loop.create_task(on_timer(state)))

    except Exception as e:
        log.error(f"arm_timer error: {e}")
        # Fallback: retry in 60s
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            state.timer_handle = loop.call_later(60, lambda: loop.create_task(on_timer(state)))


async def on_timer(state: TimerState) -> None:
    """Main timer tick — collect and execute due jobs."""
    if state.running:
        _arm_watchdog(state)
        return

    state.running = True
    _arm_watchdog(state)

    try:
        async with state.lock:
            due_jobs = await _collect_runnable_jobs(state)

        if not due_jobs:
            return

        # Mark jobs as running in DB
        async with state.lock:
            await _mark_jobs_running(due_jobs)

        # Execute with concurrency control
        results = await _execute_jobs_concurrent(state, due_jobs)

        # Apply results
        async with state.lock:
            for job_id, result in results:
                try:
                    await _apply_job_result(state, job_id, result)
                except Exception as e:
                    log.error(f"Failed to apply result for job {job_id}: {e}")

    except Exception as e:
        log.error(f"on_timer error: {e}")
    finally:
        # Piggyback maintenance tasks on timer tick
        try:
            from cron.reaper import sweep_if_due
            await sweep_if_due()
        except Exception as e:
            log.debug(f"Reaper sweep error: {e}")

        try:
            from cron.warmup import check_warmup, update_keepalive_users
            await check_warmup()
            await update_keepalive_users()
        except Exception as e:
            log.debug(f"Warmup check error: {e}")

        state.running = False
        arm_timer(state)


def stop_timer(state: TimerState) -> None:
    """Stop the timer and watchdog."""
    _cancel_timer(state)
    _cancel_watchdog(state)
    state.running = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_ms() -> int:
    return int(time.time() * 1000)


def _cancel_timer(state: TimerState) -> None:
    if state.timer_handle is not None:
        state.timer_handle.cancel()
        state.timer_handle = None


def _cancel_watchdog(state: TimerState) -> None:
    if state.watchdog_handle is not None:
        state.watchdog_handle.cancel()
        state.watchdog_handle = None


def _arm_watchdog(state: TimerState) -> None:
    """Re-arm watchdog to re-check timer in 60s (prevents scheduler death)."""
    _cancel_watchdog(state)
    loop = asyncio.get_event_loop()
    if not loop.is_closed():
        state.watchdog_handle = loop.call_later(
            60, lambda: loop.create_task(on_timer(state))
        )


async def _find_next_wake_ms(state: TimerState) -> int | None:
    """Find the earliest next_run_at across all enabled jobs."""
    from db.base import get_db_session
    from db.models.cron import CronJob
    from sqlalchemy import select

    async with get_db_session() as db:
        result = await db.execute(
            select(CronJob.next_run_at)
            .where(
                CronJob.enabled == True,
                CronJob.is_deleted == False,
                CronJob.next_run_at.isnot(None),
            )
            .order_by(CronJob.next_run_at.asc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return int(row.timestamp() * 1000)


async def _collect_runnable_jobs(state: TimerState) -> list[dict]:
    """Query DB for due jobs that should be executed."""
    from db.base import get_db_session
    from db.models.cron import CronJob
    from sqlalchemy import select

    now = datetime.now(timezone.utc)

    async with get_db_session() as db:
        result = await db.execute(
            select(CronJob)
            .where(
                CronJob.enabled == True,
                CronJob.is_deleted == False,
                CronJob.next_run_at <= now,
                CronJob.running_at.is_(None),
            )
            .order_by(CronJob.next_run_at.asc())
        )
        rows = result.scalars().all()

    # Per-user concurrency limit: max 2 concurrent cron jobs per user
    MAX_CONCURRENT_PER_USER = 2
    user_running_count: dict[str, int] = {}

    # Count already-running jobs per user
    async with get_db_session() as db:
        running_result = await db.execute(
            select(CronJob.user_id)
            .where(CronJob.running_at.isnot(None))
        )
        for r in running_result.all():
            user_running_count[r[0]] = user_running_count.get(r[0], 0) + 1

    due = []
    for row in rows:
        # Check backoff window
        if _is_in_backoff(row):
            continue
        # Per-user concurrency check
        user_running = user_running_count.get(row.user_id, 0)
        if user_running >= MAX_CONCURRENT_PER_USER:
            continue
        user_running_count[row.user_id] = user_running + 1
        due.append({
            "id": row.id,
            "user_id": row.user_id,
            "session_id": row.session_id,
            "name": row.name,
            "schedule": row.schedule,
            "task_prompt": row.task_prompt,
            "agent": row.agent,
            "model": row.model,
            "timeout_seconds": row.timeout_seconds,
            "delivery": row.delivery,
            "delete_after_run": row.delete_after_run,
            "max_retries": row.max_retries,
            "consecutive_errors": row.consecutive_errors,
            "summary_cache": row.summary_cache,
            "summary_cache_msg_id": row.summary_cache_msg_id,
        })

    return due


def _is_in_backoff(job) -> bool:
    """Check if job is in error backoff window."""
    errors = job.consecutive_errors or 0
    if errors == 0:
        return False
    last_run = job.last_run_at
    if last_run is None:
        return False
    backoff_ms = error_backoff_ms(errors)
    backoff_until = last_run + timedelta(milliseconds=backoff_ms)
    return datetime.now(timezone.utc) < backoff_until


async def _mark_jobs_running(jobs: list[dict]) -> None:
    """Mark jobs as running in DB (persist before execution)."""
    from db.base import get_db_session
    from db.models.cron import CronJob
    from sqlalchemy import update

    now = datetime.now(timezone.utc)
    job_ids = [j["id"] for j in jobs]

    async with get_db_session() as db:
        await db.execute(
            update(CronJob)
            .where(CronJob.id.in_(job_ids))
            .values(running_at=now)
        )


async def _execute_jobs_concurrent(
    state: TimerState, jobs: list[dict]
) -> list[tuple[str, dict]]:
    """Execute jobs with concurrency control (worker pool pattern)."""
    results: list[tuple[str, dict]] = []
    cursor = 0
    cursor_lock = asyncio.Lock()

    async def worker():
        nonlocal cursor
        while True:
            async with cursor_lock:
                if cursor >= len(jobs):
                    return
                idx = cursor
                cursor += 1

            job = jobs[idx]
            start = time.time()
            try:
                if state.execute_job:
                    result = await asyncio.wait_for(
                        state.execute_job(job),
                        timeout=job.get("timeout_seconds", 1800),
                    )
                else:
                    result = {"status": "error", "error": "No executor configured"}
            except asyncio.TimeoutError:
                result = {"status": "error", "error": "Job execution timed out"}
            except Exception as e:
                result = {"status": "error", "error": str(e)}

            result["duration_ms"] = int((time.time() - start) * 1000)
            results.append((job["id"], result))

    concurrency = min(state.max_concurrent_jobs, len(jobs))
    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
    await asyncio.gather(*workers, return_exceptions=True)

    return results


async def _apply_job_result(state: TimerState, job_id: str, result: dict) -> None:
    """Apply execution result to job state in DB."""
    from db.base import get_db_session
    from db.models.cron import CronJob
    from sqlalchemy import select, update

    now = datetime.now(timezone.utc)
    status = result.get("status", "error")
    error = result.get("error")
    duration_ms = result.get("duration_ms", 0)

    async with get_db_session() as db:
        row = await db.execute(
            select(CronJob).where(CronJob.id == job_id)
        )
        job = row.scalar_one_or_none()
        if not job:
            return

        values: dict = {
            "running_at": None,
            "last_run_at": now,
            "last_status": status,
            "last_duration_ms": duration_ms,
            "updated_at": now,
            "total_runs": job.total_runs + 1,
        }

        if status == "ok":
            values["consecutive_errors"] = 0
            values["last_error"] = None
            values["total_successes"] = job.total_successes + 1
        elif status == "error":
            values["consecutive_errors"] = job.consecutive_errors + 1
            values["last_error"] = error
            values["total_failures"] = job.total_failures + 1

        # Compute next_run_at
        schedule = job.schedule
        schedule_kind = schedule.get("kind") if isinstance(schedule, dict) else None

        if schedule_kind == "at":
            # One-shot job
            if status == "ok" or status == "skipped":
                values["enabled"] = False
                values["next_run_at"] = None
            elif status == "error":
                consecutive = values.get("consecutive_errors", job.consecutive_errors + 1)
                if _is_transient_error(error) and consecutive <= job.max_retries:
                    backoff = error_backoff_ms(consecutive)
                    values["next_run_at"] = now + timedelta(milliseconds=backoff)
                else:
                    values["enabled"] = False
                    values["next_run_at"] = None
        else:
            # Recurring job
            from cron.schedule import compute_next_run_at as _compute
            from cron.types import CronScheduleCron, CronScheduleEvery

            # Reconstruct schedule object
            if schedule_kind == "cron":
                sched = CronScheduleCron(expr=schedule["expr"], tz=schedule.get("tz", "UTC"))
            elif schedule_kind == "every":
                sched = CronScheduleEvery(every_ms=schedule["every_ms"], anchor_ms=schedule.get("anchor_ms"))
            else:
                sched = None

            if sched:
                natural_next = _compute(sched, now)
                if status == "error" and job.enabled:
                    backoff = error_backoff_ms(values.get("consecutive_errors", 1))
                    backoff_next = now + timedelta(milliseconds=backoff)
                    if natural_next:
                        values["next_run_at"] = max(natural_next, backoff_next)
                    else:
                        values["next_run_at"] = backoff_next
                elif natural_next:
                    # Ensure MIN_REFIRE_GAP
                    min_next = now + timedelta(milliseconds=MIN_REFIRE_GAP_MS)
                    values["next_run_at"] = max(natural_next, min_next)
                else:
                    values["next_run_at"] = None

        # Handle delete_after_run
        if schedule_kind == "at" and job.delete_after_run and status == "ok":
            values["is_deleted"] = True

        await db.execute(
            update(CronJob).where(CronJob.id == job_id).values(**values)
        )

    # Notify via callback
    if state.on_job_result:
        try:
            await state.on_job_result(job_id, result)
        except Exception as e:
            log.error(f"on_job_result callback error: {e}")


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def error_backoff_ms(consecutive_errors: int) -> int:
    """Compute backoff delay based on consecutive error count."""
    idx = min(consecutive_errors - 1, len(BACKOFF_SCHEDULE_MS) - 1)
    return BACKOFF_SCHEDULE_MS[max(0, idx)]


def _is_transient_error(error: str | None) -> bool:
    """Check if an error is transient (retryable)."""
    if not error:
        return False
    return any(
        re.search(pattern, error)
        for pattern in TRANSIENT_PATTERNS.values()
    )
