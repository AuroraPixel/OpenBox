"""Cron job management API."""
from fastapi import APIRouter, Depends, HTTPException
from auth.middleware import get_current_user
from cron.types import CronJobCreate, CronJobUpdate
from cron.service import cron_service

router = APIRouter(
    prefix="/api/cron",
    tags=["cron"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/status")
async def get_cron_status():
    """Get cron scheduler status."""
    return await cron_service.status()


@router.get("/jobs")
async def list_cron_jobs(
    session_id: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """List cron jobs. Optionally filter by session_id."""
    user_id = current_user["user_id"]
    return await cron_service.list_jobs(user_id, session_id=session_id)


@router.post("/jobs")
async def create_cron_job(
    body: CronJobCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a new cron job."""
    user_id = current_user["user_id"]
    try:
        return await cron_service.add(user_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/jobs/{job_id}")
async def update_cron_job(
    job_id: str,
    body: CronJobUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update a cron job."""
    user_id = current_user["user_id"]
    try:
        return await cron_service.update(job_id, user_id, body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/jobs/{job_id}")
async def delete_cron_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a cron job."""
    user_id = current_user["user_id"]
    try:
        return await cron_service.remove(job_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/jobs/{job_id}/run")
async def run_cron_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Manually trigger a cron job."""
    user_id = current_user["user_id"]
    try:
        return await cron_service.run(job_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/jobs/pause-all")
async def pause_all_cron_jobs(
    session_id: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Pause (disable) all cron jobs. Optionally filter by session."""
    user_id = current_user["user_id"]
    from db.base import get_db_session
    from db.models.cron import CronJob as CronJobORM
    from sqlalchemy import update
    from datetime import datetime, timezone

    query = (
        update(CronJobORM)
        .where(CronJobORM.user_id == user_id, CronJobORM.is_deleted == False, CronJobORM.enabled == True)
    )
    if session_id:
        query = query.where(CronJobORM.session_id == session_id)
    query = query.values(enabled=False, updated_at=datetime.now(timezone.utc))

    async with get_db_session() as db:
        result = await db.execute(query)
    return {"ok": True, "paused": result.rowcount}


@router.post("/jobs/resume-all")
async def resume_all_cron_jobs(
    session_id: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Resume (enable) all cron jobs. Optionally filter by session."""
    user_id = current_user["user_id"]
    from db.base import get_db_session
    from db.models.cron import CronJob as CronJobORM
    from sqlalchemy import update, select
    from datetime import datetime, timezone
    from cron.schedule import compute_next_run_at
    from cron.types import CronScheduleCron, CronScheduleEvery, CronScheduleAt

    now = datetime.now(timezone.utc)

    # Enable all disabled jobs
    query = (
        update(CronJobORM)
        .where(CronJobORM.user_id == user_id, CronJobORM.is_deleted == False, CronJobORM.enabled == False)
    )
    if session_id:
        query = query.where(CronJobORM.session_id == session_id)
    query = query.values(enabled=True, updated_at=now)

    async with get_db_session() as db:
        result = await db.execute(query)

    # Recompute next_run_at for all resumed jobs
    async with get_db_session() as db:
        q = select(CronJobORM).where(
            CronJobORM.user_id == user_id, CronJobORM.is_deleted == False, CronJobORM.enabled == True,
            CronJobORM.next_run_at.is_(None),
        )
        if session_id:
            q = q.where(CronJobORM.session_id == session_id)
        rows = (await db.execute(q)).scalars().all()
        for job in rows:
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
                await db.execute(
                    update(CronJobORM).where(CronJobORM.id == job.id).values(next_run_at=next_run, updated_at=now)
                )

    from cron.timer import arm_timer
    from cron.service import cron_service
    arm_timer(cron_service._state)

    return {"ok": True, "resumed": result.rowcount}


@router.get("/jobs/{job_id}")
async def get_cron_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a specific cron job."""
    user_id = current_user["user_id"]
    job = await cron_service.get_job(job_id, user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/runs")
async def list_cron_runs(
    job_id: str,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Get execution history for a cron job."""
    user_id = current_user["user_id"]
    return await cron_service.list_runs(job_id, user_id, limit=limit)
