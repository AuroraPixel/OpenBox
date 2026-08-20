"""Reclaiming project directories whose sessions are gone.

Directories used to accumulate forever: nothing removed them when a session was
deleted, and the WUYING provider's delete_container is a no-op, so the usual
"the container goes away eventually" safety net does not exist either.

Deleted material goes to .openbox/trash first and is removed from there on a
later pass. An agent can put hours of work in a project directory, and a
reclaim job that deletes outright turns one wrong retention setting into
permanent loss.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from core.log import create_logger
from db.base import get_db_session
from db.models.project import Project as ProjectORM
from project.workspace import TRASH_ROOT, WORKSPACE_ROOT

log = create_logger("project.reclaim")

#: How long a soft-deleted project keeps its directory before it is binned.
DELETED_GRACE_DAYS = 7
#: How long binned material stays recoverable.
TRASH_GRACE_DAYS = 14


async def _live_slugs(user_id: str | None = None) -> set[str]:
    """Slugs that must not be touched — every project still on the books."""
    conditions = [ProjectORM.is_deleted == False]  # noqa: E712
    if user_id:
        conditions.append(ProjectORM.user_id == user_id)
    async with get_db_session() as db:
        rows = (await db.execute(
            select(ProjectORM.slug).where(*conditions)
        )).scalars().all()
    return {s for s in rows if s}


async def _expired_slugs(user_id: str | None = None) -> set[str]:
    """Slugs of projects deleted long enough ago to reclaim."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=DELETED_GRACE_DAYS)
    conditions = [
        ProjectORM.is_deleted == True,  # noqa: E712
        ProjectORM.deleted_at != None,  # noqa: E711
        ProjectORM.deleted_at < cutoff,
    ]
    if user_id:
        conditions.append(ProjectORM.user_id == user_id)
    async with get_db_session() as db:
        rows = (await db.execute(
            select(ProjectORM.slug).where(*conditions)
        )).scalars().all()
    return {s for s in rows if s}


async def reclaim(sandbox, user_id: str | None = None, dry_run: bool = False) -> dict:
    """Bin directories for deleted projects and empty the old trash.

    Only directories whose slug maps to a *deleted* project are touched.
    Anything unrecognised is left alone and reported: a directory the database
    has never heard of is more likely to be something worth keeping than
    something worth deleting.
    """
    if sandbox is None:
        return {"binned": [], "purged": [], "unknown": [], "skipped": "no sandbox"}

    live = await _live_slugs(user_id)
    expired = await _expired_slugs(user_id)

    try:
        result = await sandbox.execute(
            f"ls -1 {WORKSPACE_ROOT} 2>/dev/null || true", timeout=30)
        present = [d.strip() for d in (result.stdout or "").splitlines() if d.strip()]
    except Exception as e:
        log.warning(f"Could not list {WORKSPACE_ROOT}: {e}")
        return {"binned": [], "purged": [], "unknown": [], "error": str(e)}

    binned, unknown = [], []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    for name in present:
        if name.startswith("."):
            continue  # .openbox and friends are ours
        if name in live:
            continue
        if name in expired:
            if not dry_run:
                await sandbox.execute(
                    f"mkdir -p {TRASH_ROOT} && "
                    f"mv {WORKSPACE_ROOT}/{name} {TRASH_ROOT}/{name}-{stamp} || true",
                    timeout=60)
            binned.append(name)
        else:
            unknown.append(name)

    purged = await _purge_trash(sandbox, dry_run=dry_run)

    if binned or purged:
        log.info(f"Reclaim: binned {len(binned)}, purged {len(purged)}")
    if unknown:
        log.info(f"Reclaim: left {len(unknown)} unrecognised directories alone: {unknown}")
    return {"binned": binned, "purged": purged, "unknown": unknown}


async def _purge_trash(sandbox, dry_run: bool = False) -> list[str]:
    """Delete trash older than the recovery window."""
    try:
        result = await sandbox.execute(
            f"find {TRASH_ROOT} -maxdepth 1 -mindepth 1 -type d "
            f"-mtime +{TRASH_GRACE_DAYS} 2>/dev/null || true",
            timeout=30)
        stale = [d.strip() for d in (result.stdout or "").splitlines() if d.strip()]
    except Exception as e:
        log.warning(f"Could not scan trash: {e}")
        return []

    for path in stale:
        # Belt and braces: a bug that produced an empty path here would
        # otherwise expand to `rm -rf /`.
        if not path.startswith(TRASH_ROOT + "/"):
            log.warning(f"Refusing to purge path outside trash: {path}")
            continue
        if not dry_run:
            await sandbox.execute(f"rm -rf {path}", timeout=120)
    return stale
