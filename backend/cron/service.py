"""CronService — the main facade for cron job management.

Provides CRUD operations + scheduler start/stop.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from core.log import create_logger
from core.identifier import ascending
from cron.timer import TimerState, arm_timer, stop_timer
from cron.types import CronJobCreate, CronJobUpdate, CronJobStatus

log = create_logger("cron.service")


class CronService:
    """Session-level cron job scheduler."""

    def __init__(self):
        self._state = TimerState()
        self._started = False

    async def start(self) -> None:
        """Start the cron scheduler. Call during app lifespan startup."""
        if self._started:
            return
        self._started = True
        log.info("Cron scheduler starting...")

        # Recovery: clean stuck markers + replay missed jobs
        from cron.recovery import recover_on_startup
        await recover_on_startup()

        # Recompute next_run_at for all enabled jobs
        await self._recompute_all()

        # Arm the timer
        arm_timer(self._state)
        log.info("Cron scheduler started")

    async def stop(self) -> None:
        """Stop the cron scheduler. Call during app lifespan shutdown."""
        if not self._started:
            return
        stop_timer(self._state)
        self._started = False
        log.info("Cron scheduler stopped")

    def set_executor(self, executor) -> None:
        """Inject the job executor callback (set by executor.py)."""
        self._state.execute_job = executor

    def set_result_handler(self, handler) -> None:
        """Inject the result handler callback."""
        self._state.on_job_result = handler

    # ── CRUD ──

    async def add(self, user_id: str, create: CronJobCreate) -> dict:
        """Create a new cron job."""
        from db.base import get_db_session
        from db.models.cron import CronJob
        from cron.schedule import compute_next_run_at

        now = datetime.now(timezone.utc)
        job_id = ascending("cron")

        # Determine delete_after_run default
        delete_after_run = create.delete_after_run
        if delete_after_run is None:
            delete_after_run = create.schedule.kind == "at"

        # Compute initial next_run_at
        schedule_dict = create.schedule.model_dump()
        schedule_obj = create.schedule

        # For "every" schedule, set anchor to now if not provided
        if schedule_obj.kind == "every" and not schedule_obj.anchor_ms:
            schedule_dict["anchor_ms"] = int(now.timestamp() * 1000)

        next_run = compute_next_run_at(schedule_obj, now) if create.enabled else None

        delivery_dict = create.delivery.model_dump() if create.delivery else {}

        async with get_db_session() as db:
            row = CronJob(
                id=job_id,
                user_id=user_id,
                session_id=create.session_id,
                name=create.name,
                description=create.description,
                enabled=create.enabled,
                schedule=schedule_dict,
                task_prompt=create.task_prompt,
                agent=create.agent,
                model=create.model,
                timeout_seconds=create.timeout_seconds,
                delivery=delivery_dict,
                delete_after_run=delete_after_run,
                max_retries=create.max_retries,
                next_run_at=next_run,
                created_at=now,
                updated_at=now,
            )
            db.add(row)

        # Re-arm timer
        arm_timer(self._state)

        log.info(f"Created cron job {job_id} ({create.name}) for session {create.session_id}")

        # Publish event
        from bus import bus
        from bus.events import CRON_JOB_CREATED
        bus.publish(CRON_JOB_CREATED, {
            "userId": user_id,
            "jobId": job_id,
            "sessionId": create.session_id,
            "name": create.name,
        })

        return {"id": job_id, "next_run_at": next_run.isoformat() if next_run else None}

    async def update(self, job_id: str, user_id: str, patch: CronJobUpdate) -> dict:
        """Update an existing cron job."""
        from db.base import get_db_session
        from db.models.cron import CronJob
        from sqlalchemy import select, update

        now = datetime.now(timezone.utc)

        async with get_db_session() as db:
            result = await db.execute(
                select(CronJob).where(
                    CronJob.id == job_id,
                    CronJob.user_id == user_id,
                    CronJob.is_deleted == False,
                )
            )
            job = result.scalar_one_or_none()
            if not job:
                raise ValueError(f"Cron job {job_id} not found")

            values: dict = {"updated_at": now}

            if patch.name is not None:
                values["name"] = patch.name
            if patch.description is not None:
                values["description"] = patch.description
            if patch.task_prompt is not None:
                values["task_prompt"] = patch.task_prompt
            if patch.agent is not None:
                values["agent"] = patch.agent
            if patch.model is not None:
                values["model"] = patch.model
            if patch.timeout_seconds is not None:
                values["timeout_seconds"] = patch.timeout_seconds
            if patch.delivery is not None:
                values["delivery"] = patch.delivery.model_dump()
            if patch.enabled is not None:
                values["enabled"] = patch.enabled

            # If schedule changed, recompute next_run_at
            if patch.schedule is not None:
                values["schedule"] = patch.schedule.model_dump()
                if patch.enabled is not False and (patch.enabled or job.enabled):
                    from cron.schedule import compute_next_run_at
                    values["next_run_at"] = compute_next_run_at(patch.schedule, now)
                else:
                    values["next_run_at"] = None

            # If enabled changed, recompute
            if patch.enabled is not None and patch.schedule is None:
                if patch.enabled:
                    from cron.schedule import compute_next_run_at
                    from cron.types import CronScheduleCron, CronScheduleEvery, CronScheduleAt
                    sched = job.schedule
                    kind = sched.get("kind") if isinstance(sched, dict) else None
                    if kind == "cron":
                        sobj = CronScheduleCron(expr=sched["expr"], tz=sched.get("tz", "UTC"))
                    elif kind == "every":
                        sobj = CronScheduleEvery(every_ms=sched["every_ms"], anchor_ms=sched.get("anchor_ms"))
                    elif kind == "at":
                        sobj = CronScheduleAt(at=sched["at"])
                    else:
                        sobj = None
                    if sobj:
                        values["next_run_at"] = compute_next_run_at(sobj, now)
                else:
                    values["next_run_at"] = None

            await db.execute(
                update(CronJob).where(CronJob.id == job_id).values(**values)
            )

        arm_timer(self._state)

        from bus import bus
        from bus.events import CRON_JOB_UPDATED
        bus.publish(CRON_JOB_UPDATED, {
            "userId": user_id,
            "jobId": job_id,
        })

        return {"ok": True}

    async def remove(self, job_id: str, user_id: str) -> dict:
        """Soft-delete a cron job."""
        from db.base import get_db_session
        from db.models.cron import CronJob
        from sqlalchemy import update

        now = datetime.now(timezone.utc)

        async with get_db_session() as db:
            result = await db.execute(
                update(CronJob)
                .where(
                    CronJob.id == job_id,
                    CronJob.user_id == user_id,
                    CronJob.is_deleted == False,
                )
                .values(is_deleted=True, enabled=False, updated_at=now)
            )
            if result.rowcount == 0:
                raise ValueError(f"Cron job {job_id} not found")

        arm_timer(self._state)
        return {"ok": True}

    async def run(self, job_id: str, user_id: str) -> dict:
        """Manually trigger a cron job."""
        from db.base import get_db_session
        from db.models.cron import CronJob
        from sqlalchemy import select

        async with get_db_session() as db:
            result = await db.execute(
                select(CronJob).where(
                    CronJob.id == job_id,
                    CronJob.user_id == user_id,
                    CronJob.is_deleted == False,
                )
            )
            job = result.scalar_one_or_none()
            if not job:
                raise ValueError(f"Cron job {job_id} not found")

            if job.running_at is not None:
                return {"ok": False, "reason": "already-running"}

        # Build job dict and execute
        job_dict = {
            "id": job.id,
            "user_id": job.user_id,
            "session_id": job.session_id,
            "name": job.name,
            "schedule": job.schedule,
            "task_prompt": job.task_prompt,
            "agent": job.agent,
            "model": job.model,
            "timeout_seconds": job.timeout_seconds,
            "delivery": job.delivery,
            "delete_after_run": job.delete_after_run,
            "max_retries": job.max_retries,
            "consecutive_errors": job.consecutive_errors,
            "summary_cache": job.summary_cache,
            "summary_cache_msg_id": job.summary_cache_msg_id,
        }

        if self._state.execute_job:
            asyncio.create_task(self._run_manual(job_dict))
            return {"ok": True, "status": "triggered"}
        else:
            return {"ok": False, "reason": "no-executor"}

    async def _run_manual(self, job_dict: dict) -> None:
        """Execute a manual job run (background task)."""
        import time as _time
        from cron.timer import _apply_job_result

        job_id = job_dict["id"]

        # Mark running
        from db.base import get_db_session
        from db.models.cron import CronJob
        from sqlalchemy import update
        now = datetime.now(timezone.utc)
        async with get_db_session() as db:
            await db.execute(
                update(CronJob).where(CronJob.id == job_id).values(running_at=now)
            )

        start = _time.time()
        try:
            result = await asyncio.wait_for(
                self._state.execute_job(job_dict),
                timeout=job_dict.get("timeout_seconds", 1800),
            )
        except asyncio.TimeoutError:
            result = {"status": "error", "error": "Job execution timed out"}
        except Exception as e:
            result = {"status": "error", "error": str(e)}

        result["duration_ms"] = int((_time.time() - start) * 1000)

        # Apply result (don't advance schedule for manual runs)
        async with self._state.lock:
            await _apply_job_result(self._state, job_id, result)

    async def list_jobs(self, user_id: str, session_id: str | None = None) -> list[dict]:
        """List cron jobs, optionally filtered by session."""
        from db.base import get_db_session
        from db.models.cron import CronJob
        from sqlalchemy import select

        async with get_db_session() as db:
            query = select(CronJob).where(
                CronJob.user_id == user_id,
                CronJob.is_deleted == False,
            )
            if session_id:
                query = query.where(CronJob.session_id == session_id)
            query = query.order_by(CronJob.created_at.desc())

            result = await db.execute(query)
            rows = result.scalars().all()

        jobs = [_job_to_dict(row) for row in rows]

        # Which project each job runs in. Shown in the UI because a scheduled
        # task acts on files, and "where" is the part you cannot infer from the
        # prompt. Resolved through the cached slug lookup, so this is not a
        # query per job.
        from project.workspace import project_directory, slug_for
        from session.session import project_id_for
        for job in jobs:
            try:
                pid = await project_id_for(job["session_id"])
                slug = await slug_for(pid)
                job["project_id"] = pid
                job["project_directory"] = project_directory(slug)
            except Exception:
                job["project_id"] = None
                job["project_directory"] = None
        return jobs

    async def get_job(self, job_id: str, user_id: str) -> dict | None:
        """Get a single cron job."""
        from db.base import get_db_session
        from db.models.cron import CronJob
        from sqlalchemy import select

        async with get_db_session() as db:
            result = await db.execute(
                select(CronJob).where(
                    CronJob.id == job_id,
                    CronJob.user_id == user_id,
                    CronJob.is_deleted == False,
                )
            )
            job = result.scalar_one_or_none()

        return _job_to_dict(job) if job else None

    async def list_runs(self, job_id: str, user_id: str, limit: int = 20) -> list[dict]:
        """Get execution history for a cron job."""
        from db.base import get_db_session
        from db.models.cron import CronRun
        from sqlalchemy import select

        async with get_db_session() as db:
            result = await db.execute(
                select(CronRun)
                .where(
                    CronRun.job_id == job_id,
                    CronRun.user_id == user_id,
                )
                .order_by(CronRun.started_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()

        return [_run_to_dict(row) for row in rows]

    async def status(self) -> dict:
        """Get scheduler status."""
        from db.base import get_db_session
        from db.models.cron import CronJob
        from sqlalchemy import select, func

        async with get_db_session() as db:
            total = await db.execute(
                select(func.count()).select_from(CronJob).where(CronJob.is_deleted == False)
            )
            enabled = await db.execute(
                select(func.count()).select_from(CronJob).where(
                    CronJob.is_deleted == False, CronJob.enabled == True
                )
            )
            running = await db.execute(
                select(func.count()).select_from(CronJob).where(
                    CronJob.running_at.isnot(None)
                )
            )

        return {
            "running": self._started,
            "total_jobs": total.scalar() or 0,
            "enabled_jobs": enabled.scalar() or 0,
            "running_jobs": running.scalar() or 0,
        }

    # ── Internal ──

    async def _recompute_all(self) -> None:
        """Recompute next_run_at for all enabled jobs."""
        from db.base import get_db_session
        from db.models.cron import CronJob
        from sqlalchemy import select, update
        from cron.schedule import compute_next_run_at
        from cron.types import CronScheduleCron, CronScheduleEvery, CronScheduleAt

        now = datetime.now(timezone.utc)

        async with get_db_session() as db:
            result = await db.execute(
                select(CronJob).where(
                    CronJob.enabled == True,
                    CronJob.is_deleted == False,
                )
            )
            jobs = result.scalars().all()

            for job in jobs:
                sched = job.schedule
                kind = sched.get("kind") if isinstance(sched, dict) else None
                sobj = None
                if kind == "cron":
                    sobj = CronScheduleCron(expr=sched["expr"], tz=sched.get("tz", "UTC"))
                elif kind == "every":
                    sobj = CronScheduleEvery(every_ms=sched["every_ms"], anchor_ms=sched.get("anchor_ms"))
                elif kind == "at":
                    sobj = CronScheduleAt(at=sched["at"])

                if sobj:
                    next_run = compute_next_run_at(sobj, now)
                    if next_run != job.next_run_at:
                        await db.execute(
                            update(CronJob)
                            .where(CronJob.id == job.id)
                            .values(next_run_at=next_run, updated_at=now)
                        )


def _job_to_dict(job) -> dict:
    """Convert CronJob ORM to dict."""
    return {
        "id": job.id,
        "user_id": job.user_id,
        "session_id": job.session_id,
        "name": job.name,
        "description": job.description,
        "enabled": job.enabled,
        "schedule": job.schedule,
        "task_prompt": job.task_prompt,
        "agent": job.agent,
        "model": job.model,
        "timeout_seconds": job.timeout_seconds,
        "delivery": job.delivery,
        "delete_after_run": job.delete_after_run,
        "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "last_status": job.last_status,
        "last_error": job.last_error,
        "last_duration_ms": job.last_duration_ms,
        "consecutive_errors": job.consecutive_errors,
        "total_runs": job.total_runs,
        "total_successes": job.total_successes,
        "total_failures": job.total_failures,
        "running": job.running_at is not None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def _run_to_dict(run) -> dict:
    """Convert CronRun ORM to dict."""
    return {
        "id": run.id,
        "job_id": run.job_id,
        "status": run.status,
        "error_message": run.error_message,
        "task_prompt": run.task_prompt,
        "summary_text": run.summary_text,
        "injected": run.injected,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "total_tokens": run.total_tokens,
        "duration_ms": run.duration_ms,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
    }


# Singleton
cron_service = CronService()
