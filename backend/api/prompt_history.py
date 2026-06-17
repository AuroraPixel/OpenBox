"""Prompt history API routes: CRUD for user input history."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from auth.middleware import get_current_user
from core.identifier import generate_id
from core.log import create_logger

log = create_logger("api.prompt_history")

router = APIRouter(tags=["PromptHistory"])


def _use_db() -> bool:
    try:
        from db.base import _engine
        return _engine is not None
    except ImportError:
        return False


@router.get("/prompt-history")
async def list_prompt_history(
    limit: int = Query(default=100, le=500),
    current_user: dict = Depends(get_current_user),
):
    """List recent prompt history for the current user."""
    user_id = current_user["user_id"]

    if _use_db():
        from db.base import get_db_session
        from db.models.prompt_history import PromptHistory
        from sqlalchemy import select

        async with get_db_session() as db:
            result = await db.execute(
                select(PromptHistory)
                .where(PromptHistory.user_id == user_id)
                .order_by(PromptHistory.created_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
        return [
            {"id": r.id, "content": r.content, "created_at": str(r.created_at)}
            for r in rows
        ]
    else:
        from storage import storage
        data = await storage.read(["prompt_history", user_id]) or []
        return data[-limit:]


@router.post("/prompt-history")
async def add_prompt_history(
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    """Save a prompt to history."""
    user_id = current_user["user_id"]
    content = body.get("content", "").strip()
    if not content:
        return {"ok": False}

    if _use_db():
        from db.base import get_db_session
        from db.models.prompt_history import PromptHistory

        async with get_db_session() as db:
            row = PromptHistory(
                id=generate_id(),
                user_id=user_id,
                content=content,
                created_at=datetime.now(timezone.utc),
            )
            db.add(row)
        return {"ok": True}
    else:
        from storage import storage
        data = await storage.read(["prompt_history", user_id]) or []
        data.append({
            "id": generate_id(),
            "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        # Keep only last 500
        if len(data) > 500:
            data = data[-500:]
        await storage.write(["prompt_history", user_id], data)
        return {"ok": True}


async def save_prompt_history_async(user_id: str, content: str) -> None:
    """Fire-and-forget helper to save prompt history from send_message."""
    content = content.strip()
    if not content:
        return
    try:
        if _use_db():
            from db.base import get_db_session
            from db.models.prompt_history import PromptHistory

            async with get_db_session() as db:
                row = PromptHistory(
                    id=generate_id(),
                    user_id=user_id,
                    content=content,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(row)
        else:
            from storage import storage
            data = await storage.read(["prompt_history", user_id]) or []
            data.append({
                "id": generate_id(),
                "content": content,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            if len(data) > 500:
                data = data[-500:]
            await storage.write(["prompt_history", user_id], data)
    except Exception as e:
        log.debug(f"Failed to save prompt history: {e}")
