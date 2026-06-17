"""Session forking: duplicate a session up to a given message.

Creates a new session with copies of all messages and parts up to
a specified message_id, allowing the user to branch the conversation.
"""
from datetime import datetime, timezone

from core.identifier import ascending
from core.log import create_logger

log = create_logger("session.fork")


async def fork_session(
    source_session_id: str,
    up_to_message_id: str | None = None,
    user_id: str = "default",
) -> dict:
    """Fork a session, copying messages up to the specified message.

    Args:
        source_session_id: The session to fork from.
        up_to_message_id: Copy messages up to (and including) this message.
                          If None, copies all messages.
        user_id: The user performing the fork.

    Returns:
        The newly created session dict.
    """
    from session.session import get_session, create_session, get_messages

    source = await get_session(source_session_id, user_id=user_id)
    if not source:
        raise ValueError(f"Session {source_session_id} not found")

    # Get messages from source
    messages = await get_messages(source_session_id)

    # Truncate at the specified message
    if up_to_message_id:
        truncated = []
        for msg in messages:
            truncated.append(msg)
            if msg.id == up_to_message_id:
                break
        messages = truncated

    # Create new session with same model/agent
    new_session = await create_session(
        model=source.model,
        agent=source.agent or "build",
        title=f"Fork: {source.title or 'Untitled'}",
        user_id=user_id,
        project_id=getattr(source, "project_id", None),
    )

    # Deep copy messages and parts to new session
    now = datetime.now(timezone.utc)

    def _use_db() -> bool:
        try:
            from db.base import _engine
            return _engine is not None
        except ImportError:
            return False

    if _use_db():
        from db.base import get_db_session
        from db.models.message import Message as MessageORM
        from db.models.part import Part as PartORM

        async with get_db_session() as db:
            for msg in messages:
                new_msg_id = ascending("message")
                role = msg.role if isinstance(msg.role, str) else msg.role.value

                msg_row = MessageORM(
                    id=new_msg_id,
                    session_id=new_session.id,
                    user_id=user_id,
                    role=role,
                    agent=getattr(msg, "agent", None),
                    model=getattr(msg, "model", None),
                    model_id=getattr(msg, "model_id", None),
                    finish=getattr(msg, "finish", None),
                    created_at=now,
                )
                db.add(msg_row)

                # Copy parts
                parts = msg.parts or []
                for part in parts:
                    p = part if isinstance(part, dict) else (
                        part.model_dump() if hasattr(part, "model_dump") else {}
                    )
                    if not isinstance(p, dict):
                        continue

                    new_part_id = ascending("part")
                    p_copy = {
                        **p,
                        "id": new_part_id,
                        "message_id": new_msg_id,
                        "session_id": new_session.id,
                    }

                    part_row = PartORM(
                        id=new_part_id,
                        message_id=new_msg_id,
                        session_id=new_session.id,
                        user_id=user_id,
                        type=p.get("type", "text"),
                        data=p_copy,
                        created_at=now,
                    )
                    db.add(part_row)
    else:
        # File-based storage: copy via storage module
        from storage import storage
        for msg in messages:
            new_msg_id = ascending("message")
            role = msg.role if isinstance(msg.role, str) else msg.role.value

            msg_data = {
                "id": new_msg_id,
                "session_id": new_session.id,
                "role": role,
                "agent": getattr(msg, "agent", None),
                "model": getattr(msg, "model", None),
                "finish": getattr(msg, "finish", None),
                "created_at": now.isoformat(),
            }
            # Read existing messages list and append
            existing = await storage.read(["messages", new_session.id]) or []
            existing.append(msg_data)
            await storage.write(["messages", new_session.id], existing)

            # Copy parts
            parts = msg.parts or []
            for part in parts:
                p = part if isinstance(part, dict) else (
                    part.model_dump() if hasattr(part, "model_dump") else {}
                )
                if not isinstance(p, dict):
                    continue
                new_part_id = ascending("part")
                p_copy = {**p, "id": new_part_id, "message_id": new_msg_id, "session_id": new_session.id}
                existing_parts = await storage.read(["parts", new_session.id]) or []
                existing_parts.append(p_copy)
                await storage.write(["parts", new_session.id], existing_parts)

    log.info(f"Forked session {source_session_id} -> {new_session.id} ({len(messages)} messages)")
    return new_session
