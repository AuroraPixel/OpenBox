"""Session CRUD operations — backed by SQLAlchemy ORM tables."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy import select, update

from bus import bus
from bus.events import SESSION_STATUS, SESSION_TITLE
from db.base import get_db_session
from db.models.session import Session as SessionORM
from db.models.message import Message as MessageORM
from db.models.part import Part as PartORM
from models.message import SessionStatus, TokenUsage, MessageWithParts, MessageInfo, MessagePart
from core.identifier import descending, ascending
from core.log import create_logger

log = create_logger("session")


class Session(BaseModel):
    """Session model matching frontend types/session.ts."""
    id: str
    title: str = ""
    agent: str = "build"
    model: str = ""
    status: SessionStatus = SessionStatus.IDLE
    created_at: str = ""
    updated_at: str = ""
    sandbox_id: str | None = None
    additions: int = 0
    deletions: int = 0
    files_changed: int = 0
    token_usage: TokenUsage | None = None
    slug: str = ""
    # Internal fields
    project_id: str = "default"
    parent_id: str | None = None  # Links child (subtask) sessions to their parent


def _orm_to_session(row: SessionORM) -> Session:
    """Convert a SessionORM row to a Pydantic Session model."""
    return Session(
        id=row.id,
        title=row.title or "",
        agent=row.agent or "build",
        model=row.model or "",
        status=SessionStatus(row.status) if row.status else SessionStatus.IDLE,
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
        sandbox_id=row.sandbox_id,
        additions=row.additions or 0,
        deletions=row.deletions or 0,
        files_changed=row.files_changed or 0,
        token_usage=TokenUsage(**row.token_usage) if row.token_usage and isinstance(row.token_usage, dict) and any(row.token_usage.values()) else None,
        slug=row.slug or "",
        project_id=row.project_id or "default",
        parent_id=row.parent_id,
    )


def plan_path(session: Session) -> str:
    """Return plan file path inside the sandbox workspace."""
    ts = int(datetime.fromisoformat(session.created_at).timestamp() * 1000)
    return f"/workspace/.openbox/plans/{ts}-{session.slug}.md"


async def create_session(
    model: str = "",
    agent: str = "build",
    title: str | None = None,
    parent_id: str | None = None,
    user_id: str = "default",
    project_id: str = "default",
) -> Session:
    """Create a new session."""
    from core.slug import create as create_slug

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    session_id = descending("session")
    slug = create_slug()
    final_title = title or f"New session - {now_iso}"

    # Resolve project_id: if "default", look up user's default project
    if project_id == "default" and user_id != "default":
        from db.models.project import Project as ProjectORM
        async with get_db_session() as db:
            result = await db.execute(
                select(ProjectORM).where(
                    ProjectORM.user_id == user_id,
                    ProjectORM.slug == "default",
                    ProjectORM.is_deleted == False,
                )
            )
            proj = result.scalar_one_or_none()
            if proj:
                project_id = proj.id

    async with get_db_session() as db:
        row = SessionORM(
            id=session_id,
            user_id=user_id,
            project_id=project_id,
            title=final_title,
            agent=agent,
            model=model,
            status="idle",
            slug=slug,
            parent_id=parent_id,
            token_usage={},
            created_at=now,
            updated_at=now,
        )
        db.add(row)

    session = Session(
        id=session_id,
        title=final_title,
        agent=agent,
        model=model,
        status=SessionStatus.IDLE,
        created_at=now_iso,
        updated_at=now_iso,
        slug=slug,
        project_id=project_id,
        parent_id=parent_id,
    )

    bus.publish(SESSION_STATUS, {
        "userId": user_id,
        "sessionId": session.id,
        "status": session.status.value,
    })

    log.info(f"Created session {session.id}")
    return session


async def get_session(session_id: str, project_id: str = "default", user_id: str = "default") -> Session | None:
    """Get a session by ID (user_id required for ownership check)."""
    async with get_db_session() as db:
        result = await db.execute(
            select(SessionORM).where(
                SessionORM.id == session_id,
                SessionORM.user_id == user_id,
                SessionORM.is_deleted == False,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return _orm_to_session(row)


async def list_sessions(project_id: str = "default", user_id: str = "default") -> list[Session]:
    """List all top-level sessions for a user (excludes child/subtask sessions)."""
    async with get_db_session() as db:
        # List all user's sessions (don't filter by project_id for now)
        result = await db.execute(
            select(SessionORM).where(
                SessionORM.user_id == user_id,
                SessionORM.is_deleted == False,
                SessionORM.parent_id == None,
            ).order_by(SessionORM.created_at.desc())
        )
        return [_orm_to_session(r) for r in result.scalars().all()]


async def delete_session(session_id: str, user_id: str = "default") -> None:
    """Soft-delete a session (messages/parts are kept for history).

    Also cascade-disables associated cron jobs.
    """
    now = datetime.now(timezone.utc)

    # Cascade: soft-delete associated cron jobs
    try:
        from db.models.cron import CronJob
        async with get_db_session() as db:
            await db.execute(
                update(CronJob)
                .where(
                    CronJob.session_id == session_id,
                    CronJob.is_deleted == False,
                )
                .values(enabled=False, is_deleted=True, updated_at=now)
            )
    except Exception as e:
        log.debug(f"Cron cascade cleanup: {e}")

    async with get_db_session() as db:
        await db.execute(
            update(SessionORM).where(
                SessionORM.id == session_id,
                SessionORM.user_id == user_id,
            ).values(is_deleted=True, deleted_at=now)
        )

    # Release sandbox
    from sandbox import sandbox_manager
    await sandbox_manager.release(session_id)

    log.info(f"Deleted session {session_id}")


async def update_session(session_id: str, user_id: str = "default", **kwargs) -> Session | None:
    """Update session fields."""
    # Serialize TokenUsage to dict for JSON column
    if "token_usage" in kwargs and kwargs["token_usage"] is not None:
        tu = kwargs["token_usage"]
        if hasattr(tu, "model_dump"):
            kwargs["token_usage"] = tu.model_dump()

    # Serialize status enum to string
    if "status" in kwargs and kwargs["status"] is not None:
        s = kwargs["status"]
        if hasattr(s, "value"):
            kwargs["status"] = s.value

    kwargs["updated_at"] = datetime.now(timezone.utc)

    async with get_db_session() as db:
        await db.execute(
            update(SessionORM).where(
                SessionORM.id == session_id,
                SessionORM.user_id == user_id,
            ).values(**kwargs)
        )

    # Re-fetch to return the updated session
    return await get_session(session_id, user_id=user_id)


async def set_session_status(session_id: str, status: SessionStatus, user_id: str = "default") -> None:
    """Update session status and broadcast SSE event."""
    await update_session(session_id, user_id=user_id, status=status)
    bus.publish(SESSION_STATUS, {
        "userId": user_id,
        "sessionId": session_id,
        "status": status.value,
    })


async def set_session_title(session_id: str, title: str, user_id: str = "default") -> None:
    """Update session title and broadcast SSE event."""
    await update_session(session_id, user_id=user_id, title=title)
    bus.publish(SESSION_TITLE, {
        "userId": user_id,
        "sessionId": session_id,
        "title": title,
    })


async def update_session_tokens(session_id: str, step_tokens: TokenUsage, user_id: str = "default") -> None:
    """Accumulate step-level tokens into session-level token_usage and broadcast."""
    session = await get_session(session_id, user_id=user_id)
    if not session:
        return

    # Get or initialize cumulative usage
    cu = session.token_usage or TokenUsage()
    cu.input += step_tokens.input
    cu.output += step_tokens.output
    cu.cache += step_tokens.cache
    cu.total += step_tokens.total or (step_tokens.input + step_tokens.output)
    cu.cost += step_tokens.cost

    # Context window = last step's total tokens (input + output), matching opencode's isOverflow
    cu.context = step_tokens.total or (step_tokens.input + step_tokens.output)

    # Always update limit based on current model (supports model switching)
    from agent.compaction import get_model_context_limit
    cu.limit = get_model_context_limit(session.model) if session.model else 200_000

    await update_session(session_id, user_id=user_id, token_usage=cu)

    from bus.events import SESSION_UPDATED
    bus.publish(SESSION_UPDATED, {
        "userId": user_id,
        "sessionId": session_id,
        "token_usage": cu.model_dump(),
    })


# --- Message Operations ---

async def create_user_message(
    session_id: str,
    text: str,
    agent: str = "build",
    model: str | None = None,
    synthetic: bool = False,
    variant: str | None = None,
    client_message_id: str | None = None,
    output_format: dict | None = None,
    user_id: str = "default",
) -> MessageWithParts:
    """Create a user message with a text part.

    Args:
        synthetic: If True, marks the text part as synthetic (system-generated).
            Synthetic messages are not wrapped with "The user sent the following
            message..." in _insert_reminders, matching opencode's behavior.
    """
    msg_id = ascending("message")
    text_part_id = ascending("part")
    now = datetime.now(timezone.utc)

    from models.message import TextPart
    text_part = TextPart(
        id=text_part_id,
        text=text,
        session_id=session_id,
        message_id=msg_id,
        synthetic=synthetic,
    )

    async with get_db_session() as db:
        msg_row = MessageORM(
            id=msg_id,
            session_id=session_id,
            user_id=user_id,
            role="user",
            client_message_id=client_message_id,
            agent=agent,
            model=model,
            variant=variant,
            format=output_format,
            created_at=now,
        )
        db.add(msg_row)

        part_row = PartORM(
            id=text_part_id,
            message_id=msg_id,
            session_id=session_id,
            user_id=user_id,
            type="text",
            data=text_part.model_dump(),
            created_at=now,
        )
        db.add(part_row)

    from bus.events import MESSAGE_CREATED
    from models.message import id_to_iso
    msg = MessageWithParts(
        id=msg_id,
        session_id=session_id,
        role="user",
        parts=[text_part],
        created_at=id_to_iso(msg_id),
        client_message_id=client_message_id,
        agent=agent,
        model=model,
    )
    log.info(f"PUBLISHING MESSAGE_CREATED for {msg_id} userId={user_id}")
    bus.publish(MESSAGE_CREATED, {
        "userId": user_id,
        "sessionId": session_id,
        "message": msg.model_dump(),
    })

    return msg


async def create_assistant_message(
    session_id: str,
    parent_id: str,
    model_id: str | None = None,
    agent: str | None = None,
    user_id: str = "default",
) -> MessageInfo:
    """Create an assistant message."""
    msg_id = ascending("message")
    now = datetime.now(timezone.utc)

    info = MessageInfo(
        id=msg_id,
        session_id=session_id,
        role="assistant",
        parent_id=parent_id,
        model_id=model_id,
        agent=agent,
    )

    async with get_db_session() as db:
        msg_row = MessageORM(
            id=msg_id,
            session_id=session_id,
            user_id=user_id,
            role="assistant",
            parent_id=parent_id,
            model_id=model_id,
            agent=agent,
            created_at=now,
        )
        db.add(msg_row)

    # Publish MESSAGE_CREATED so frontend creates the message entry
    # before subsequent part.created / text_delta events arrive
    from bus.events import MESSAGE_CREATED
    from models.message import id_to_iso
    msg = MessageWithParts(
        id=msg_id,
        session_id=session_id,
        role="assistant",
        parts=[],
        created_at=id_to_iso(msg_id),
        parent_id=parent_id,
        model=model_id,
        agent=agent,
    )
    bus.publish(MESSAGE_CREATED, {
        "userId": user_id,
        "sessionId": session_id,
        "message": msg.model_dump(),
    })

    return info


async def update_message_info(info: MessageInfo, user_id: str = "default") -> None:
    """Update a message's info in the database."""
    values: dict = {}
    if info.tokens:
        values["tokens"] = info.tokens.model_dump()
    if info.finish is not None:
        values["finish"] = info.finish
    if info.error is not None:
        values["error"] = info.error
    if info.model_id is not None:
        values["model_id"] = info.model_id
    if info.summary is not None:
        values["summary"] = info.summary
    if info.structured is not None:
        values["structured"] = info.structured

    if values:
        async with get_db_session() as db:
            await db.execute(
                update(MessageORM).where(MessageORM.id == info.id).values(**values)
            )

    from bus.events import MESSAGE_UPDATED
    # Send key fields so frontend can merge without losing parts
    msg_update: dict = {"id": info.id, "role": info.role.value}
    if info.tokens:
        msg_update["tokens"] = info.tokens.model_dump()
    if info.finish is not None:
        msg_update["finish"] = info.finish
    if info.error is not None:
        msg_update["error"] = info.error
    if info.model_id is not None:
        msg_update["model"] = info.model_id
    bus.publish(MESSAGE_UPDATED, {
        "userId": user_id,
        "sessionId": info.session_id,
        "message": msg_update,
    })


async def save_part(part: MessagePart, is_new: bool = False, user_id: str = "default") -> None:
    """Save a part to the database and publish event.

    Args:
        part: The message part to save.
        is_new: If True, publish PART_CREATED instead of PART_UPDATED.
        user_id: The user ID for bus events.
    """
    part_dict = part.model_dump()
    msg_id = part_dict.get("message_id", "")
    session_id = part_dict.get("session_id", "")

    # PostgreSQL JSONB cannot store \u0000 (null bytes). Strip them to avoid
    # "unsupported Unicode escape sequence" errors from asyncpg.
    import json as _json
    part_dict = _json.loads(_json.dumps(part_dict).replace("\\u0000", ""))

    async with get_db_session() as db:
        if is_new:
            row = PartORM(
                id=part.id,
                message_id=msg_id,
                session_id=session_id,
                user_id=user_id,
                type=part_dict.get("type", "text"),
                data=part_dict,
                created_at=datetime.now(timezone.utc),
            )
            db.add(row)
        else:
            await db.execute(
                update(PartORM).where(PartORM.id == part.id).values(data=part_dict)
            )

    # Exclude internal fields from SSE event (frontend doesn't need them)
    sse_dict = part.model_dump(exclude={"session_id", "message_id", "state"})

    from bus.events import PART_CREATED, PART_UPDATED
    event_type = PART_CREATED if is_new else PART_UPDATED
    bus.publish(event_type, {
        "userId": user_id,
        "sessionId": session_id,
        "messageId": msg_id,
        "part": sse_dict,
    })


async def get_messages(session_id: str, offset: int = 0, limit: int = 200, user_id: str | None = None) -> list[MessageWithParts]:
    """Get messages for a session with their parts in a single query.

    Args:
        user_id: If provided, verifies session belongs to this user (defense-in-depth).
    """
    async with get_db_session() as db:
        # Defense-in-depth: verify session ownership when user_id is provided
        if user_id:
            ownership = await db.execute(
                select(SessionORM.id).where(
                    SessionORM.id == session_id,
                    SessionORM.user_id == user_id,
                    SessionORM.is_deleted == False,
                )
            )
            if not ownership.scalar_one_or_none():
                return []

        # Get messages with pagination
        msg_result = await db.execute(
            select(MessageORM).where(MessageORM.session_id == session_id)
            .order_by(MessageORM.created_at)
            .offset(offset).limit(limit)
        )
        messages = msg_result.scalars().all()

        if not messages:
            return []

        msg_ids = [m.id for m in messages]

        # Get all parts for these messages in one query
        parts_result = await db.execute(
            select(PartORM).where(PartORM.message_id.in_(msg_ids))
            .order_by(PartORM.created_at)
        )
        all_parts = parts_result.scalars().all()

    # Group parts by message_id
    parts_by_msg: dict[str, list[dict]] = {}
    for p in all_parts:
        parts_by_msg.setdefault(p.message_id, []).append(p.data)

    # Build result
    from models.message import id_to_iso
    result = []
    for m in messages:
        tokens_obj = None
        if m.tokens and isinstance(m.tokens, dict):
            tokens_obj = TokenUsage(**m.tokens)

        result.append(MessageWithParts(
            id=m.id,
            session_id=session_id,
            role=m.role,
            parts=parts_by_msg.get(m.id, []),
            created_at=id_to_iso(m.id),
            client_message_id=m.client_message_id,
            agent=m.agent,
            model=m.model,
            variant=m.variant,
            parent_id=m.parent_id,
            finish=m.finish,
            summary=m.summary,
            tokens=tokens_obj,
            format=m.format,
            structured=m.structured,
        ))

    return result


async def get_parts_for_message(message_id: str) -> list[dict]:
    """Get all parts for a specific message, ordered by creation time."""
    async with get_db_session() as db:
        result = await db.execute(
            select(PartORM).where(PartORM.message_id == message_id)
            .order_by(PartORM.created_at)
        )
        return [p.data for p in result.scalars().all()]


async def update_part_data(part_id: str, data: dict) -> None:
    """Update a part's data directly by ID."""
    async with get_db_session() as db:
        await db.execute(
            update(PartORM).where(PartORM.id == part_id).values(data=data)
        )


async def check_message_has_synthetic_text(message_id: str) -> bool:
    """Check if a message already has a synthetic text part."""
    async with get_db_session() as db:
        result = await db.execute(
            select(PartORM).where(
                PartORM.message_id == message_id,
                PartORM.type == "text",
            )
        )
        for p in result.scalars().all():
            if isinstance(p.data, dict) and p.data.get("synthetic"):
                return True
        return False
