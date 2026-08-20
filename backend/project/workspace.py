"""Projects as the unit a workspace is organised around.

A project is a named directory under /workspace that sessions run inside. Two
sessions in the same project share the directory and see each other's edits —
the same thing that happens when you open two terminals in one repository.

This mirrors how opencode, Codex and Claude Code all scope work: a project is a
directory, a session is a conversation bound to it. Where opencode *derives* the
project from a git remote, OpenBox lets the user name it, because the sandbox
starts empty and there is no repository to derive an identity from until the
agent puts one there.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update

from core.identifier import generate_id
from core.log import create_logger
from db.base import get_db_session
from db.models.project import Project as ProjectORM

log = create_logger("project.workspace")

WORKSPACE_ROOT = "/workspace"
#: Everything OpenBox keeps for itself lives here, so a project directory
#: contains only the user's files. Snapshots in particular must stay outside
#: the tree they are snapshotting.
INTERNAL_ROOT = f"{WORKSPACE_ROOT}/.openbox"
TRASH_ROOT = f"{INTERNAL_ROOT}/trash"
SNAPSHOT_ROOT = f"{INTERNAL_ROOT}/snapshots"

DEFAULT_SLUG = "default"
DEFAULT_NAME = "Default"

#: A slug becomes a directory name, so it has to be safe as a path segment and
#: as a shell word. Leading dots are excluded to keep projects out of the same
#: namespace as .openbox.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
RESERVED_SLUGS = {"", ".", "..", ".openbox", "sessions", "skills", "trash", "snapshots"}


class ProjectError(Exception):
    """Something the user can fix — surfaced as a 4xx, not a 500."""


@dataclass
class ProjectInfo:
    id: str
    name: str
    slug: str
    description: str | None = None
    created_at: str = ""
    updated_at: str = ""
    #: Filled in by the API layer; not stored.
    session_count: int = 0

    @property
    def directory(self) -> str:
        return project_directory(self.slug)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "directory": self.directory,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "session_count": self.session_count,
        }


def project_directory(slug: str) -> str:
    """Where a project's files live inside the sandbox."""
    return f"{WORKSPACE_ROOT}/{slug}"


def slugify(name: str) -> str:
    """Turn a display name into a directory-safe slug.

    Non-ASCII names (Chinese, for instance) can slugify to nothing; the caller
    is expected to fall back to a generated slug rather than write an empty
    path segment.
    """
    slug = (name or "").strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9._-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-.")
    return slug[:64]


def validate_slug(slug: str) -> str:
    if slug in RESERVED_SLUGS:
        raise ProjectError(f"'{slug}' is reserved and cannot be used as a project name")
    if not SLUG_RE.match(slug):
        raise ProjectError(
            "Project id must start with a letter or digit and contain only "
            "lowercase letters, digits, dot, dash or underscore"
        )
    return slug


def _row_to_info(row: ProjectORM) -> ProjectInfo:
    return ProjectInfo(
        id=row.id,
        name=row.name,
        slug=row.slug or row.id,
        description=row.description,
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


# ---------------------------------------------------------------------------
# Slug cache
#
# The agent loop resolves a session's working directory on every step. That is
# one lookup per step per session, for a value that changes only when a project
# is renamed or deleted — both of which invalidate here.
# ---------------------------------------------------------------------------

_slug_cache: dict[str, str] = {}


def _cache_put(project_id: str, slug: str) -> None:
    _slug_cache[project_id] = slug


def invalidate_slug(project_id: str) -> None:
    _slug_cache.pop(project_id, None)


async def slug_for(project_id: str) -> str:
    """The directory name for a project id, defaulting to `default`.

    Never raises: a session pointing at a project that has gone away still has
    to run somewhere, and failing the whole turn over a missing directory name
    would be worse than putting it in the default project.
    """
    if not project_id:
        return DEFAULT_SLUG
    cached = _slug_cache.get(project_id)
    if cached:
        return cached
    try:
        async with get_db_session() as db:
            row = (await db.execute(
                select(ProjectORM).where(ProjectORM.id == project_id)
            )).scalar_one_or_none()
    except Exception as e:
        log.warning(f"Could not resolve project {project_id}: {e}")
        return DEFAULT_SLUG
    if not row or not row.slug:
        return DEFAULT_SLUG
    _cache_put(project_id, row.slug)
    return row.slug


async def workdir_for_session(session) -> str:
    """The directory a session's tools run in."""
    return project_directory(await slug_for(getattr(session, "project_id", "") or ""))


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def list_projects(user_id: str) -> list[ProjectInfo]:
    async with get_db_session() as db:
        rows = (await db.execute(
            select(ProjectORM).where(
                ProjectORM.user_id == user_id,
                ProjectORM.is_deleted == False,  # noqa: E712
            ).order_by(ProjectORM.created_at.asc())
        )).scalars().all()
    out = []
    for r in rows:
        info = _row_to_info(r)
        _cache_put(info.id, info.slug)
        out.append(info)
    return out


async def get_project(project_id: str, user_id: str) -> ProjectInfo | None:
    async with get_db_session() as db:
        row = (await db.execute(
            select(ProjectORM).where(
                ProjectORM.id == project_id,
                ProjectORM.user_id == user_id,
                ProjectORM.is_deleted == False,  # noqa: E712
            )
        )).scalar_one_or_none()
    return _row_to_info(row) if row else None


async def get_by_slug(slug: str, user_id: str) -> ProjectInfo | None:
    async with get_db_session() as db:
        row = (await db.execute(
            select(ProjectORM).where(
                ProjectORM.user_id == user_id,
                ProjectORM.slug == slug,
                ProjectORM.is_deleted == False,  # noqa: E712
            )
        )).scalar_one_or_none()
    return _row_to_info(row) if row else None


async def create_project(
    user_id: str,
    name: str,
    slug: str | None = None,
    description: str | None = None,
) -> ProjectInfo:
    """Register a project and make sure its directory exists.

    The row is written first: a directory without a row is invisible, while a
    row without a directory is repaired on first use by ensure_directory().
    """
    name = (name or "").strip()
    if not name:
        raise ProjectError("Project name is required")
    if len(name) > 128:
        raise ProjectError("Project name is too long (max 128 characters)")

    candidate = slug.strip().lower() if slug else slugify(name)
    if not candidate:
        # A name with no ASCII letters at all — Chinese, emoji — still deserves
        # a working directory, just not one derived from its characters.
        candidate = f"project-{generate_id()[:8].lower()}"
    validate_slug(candidate)

    if await get_by_slug(candidate, user_id):
        raise ProjectError(f"A project with id '{candidate}' already exists")

    now = datetime.now(timezone.utc)
    project_id = generate_id()
    async with get_db_session() as db:
        db.add(ProjectORM(
            id=project_id,
            user_id=user_id,
            name=name,
            slug=candidate,
            description=(description or None),
            created_at=now,
            updated_at=now,
        ))

    _cache_put(project_id, candidate)
    info = ProjectInfo(
        id=project_id, name=name, slug=candidate, description=description,
        created_at=now.isoformat(), updated_at=now.isoformat(),
    )
    log.info(f"Created project {candidate} ({project_id}) for user {user_id}")
    return info


async def rename_project(project_id: str, user_id: str, name: str) -> ProjectInfo:
    """Change the display name. The slug — and so the directory — is fixed.

    Moving a live directory would invalidate every path the agent has already
    seen in its own transcript, so the name is presentation only.
    """
    name = (name or "").strip()
    if not name:
        raise ProjectError("Project name is required")
    existing = await get_project(project_id, user_id)
    if not existing:
        raise ProjectError("Project not found")
    async with get_db_session() as db:
        await db.execute(
            update(ProjectORM)
            .where(ProjectORM.id == project_id, ProjectORM.user_id == user_id)
            .values(name=name, updated_at=datetime.now(timezone.utc))
        )
    existing.name = name
    return existing


async def delete_project(project_id: str, user_id: str, sandbox=None) -> None:
    """Soft-delete a project and move its directory out of the way.

    The directory goes to .openbox/trash rather than being removed: an agent
    can put hours of work in there, and a mis-click should not be the end of it.
    """
    info = await get_project(project_id, user_id)
    if not info:
        raise ProjectError("Project not found")
    if info.slug == DEFAULT_SLUG:
        raise ProjectError("The default project cannot be deleted")

    active = await active_session_count(project_id, user_id)
    if active:
        raise ProjectError(
            f"{active} session(s) are still running in this project. "
            "Stop them before deleting it."
        )

    now = datetime.now(timezone.utc)
    async with get_db_session() as db:
        await db.execute(
            update(ProjectORM)
            .where(ProjectORM.id == project_id, ProjectORM.user_id == user_id)
            .values(is_deleted=True, deleted_at=now, updated_at=now)
        )
    invalidate_slug(project_id)

    if sandbox is not None:
        stamp = now.strftime("%Y%m%d-%H%M%S")
        target = f"{TRASH_ROOT}/{info.slug}-{stamp}"
        try:
            await sandbox.execute(
                f"mkdir -p {TRASH_ROOT} && "
                f"[ -d {info.directory} ] && mv {info.directory} {target} || true",
                timeout=60,
            )
            log.info(f"Moved {info.directory} to {target}")
        except Exception as e:
            # The row is already gone; a directory left behind is clutter, not
            # a failure the user needs to act on.
            log.warning(f"Could not move {info.directory} to trash: {e}")


async def active_session_count(project_id: str, user_id: str) -> int:
    from db.models.session import Session as SessionORM
    from sqlalchemy import func
    async with get_db_session() as db:
        return (await db.execute(
            select(func.count()).select_from(SessionORM).where(
                SessionORM.project_id == project_id,
                SessionORM.user_id == user_id,
                SessionORM.is_deleted == False,  # noqa: E712
                SessionORM.status != "idle",
            )
        )).scalar_one()


async def session_counts(user_id: str) -> dict[str, int]:
    """Live session count per project, for the picker."""
    from db.models.session import Session as SessionORM
    from sqlalchemy import func
    async with get_db_session() as db:
        rows = (await db.execute(
            select(SessionORM.project_id, func.count())
            .where(
                SessionORM.user_id == user_id,
                SessionORM.is_deleted == False,  # noqa: E712
                SessionORM.parent_id == None,  # noqa: E711
            )
            .group_by(SessionORM.project_id)
        )).all()
    return {pid: count for pid, count in rows}


async def ensure_default_project(user_id: str) -> ProjectInfo:
    """The project a session lands in when the user did not pick one."""
    existing = await get_by_slug(DEFAULT_SLUG, user_id)
    if existing:
        _cache_put(existing.id, existing.slug)
        return existing
    return await create_project(user_id, DEFAULT_NAME, slug=DEFAULT_SLUG)


async def resolve_for_session(project_id: str | None, user_id: str) -> str:
    """The project id a new session should be filed under.

    Accepts a real id, a slug, or nothing at all, so callers that only know the
    directory name do not have to look the id up first.
    """
    if project_id and project_id != DEFAULT_SLUG:
        if await get_project(project_id, user_id):
            return project_id
        by_slug = await get_by_slug(project_id, user_id)
        if by_slug:
            return by_slug.id
        log.warning(f"Unknown project {project_id!r}, filing session under default")
    return (await ensure_default_project(user_id)).id


# ---------------------------------------------------------------------------
# Sandbox side
# ---------------------------------------------------------------------------

async def ensure_directory(sandbox, slug: str) -> str:
    """Create the project directory if it is not there yet.

    Called on the path that starts a run, so a project created while the
    sandbox was down still works the first time it is used.
    """
    directory = project_directory(slug)
    if sandbox is None:
        return directory
    try:
        await sandbox.execute(f"mkdir -p {directory}", timeout=30)
    except Exception as e:
        log.warning(f"Could not create {directory}: {e}")
    return directory
