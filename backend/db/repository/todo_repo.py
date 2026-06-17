"""PostgreSQL implementation for todos."""
from datetime import datetime, timezone

from sqlalchemy import select

from core.identifier import generate_id
from db.base import get_db_session
from db.models.todo import Todo


class PgTodoRepo:
    async def get(self, session_id: str, user_id: str) -> dict | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(Todo).where(Todo.session_id == session_id)
            )
            row = result.scalar_one_or_none()
            return _to_dict(row) if row else None

    async def upsert(self, session_id: str, user_id: str, items: list) -> dict:
        now = datetime.now(timezone.utc)
        async with get_db_session() as session:
            result = await session.execute(
                select(Todo).where(Todo.session_id == session_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.items = items
                row.updated_at = now
            else:
                row = Todo(
                    id=generate_id(), session_id=session_id,
                    user_id=user_id, items=items, updated_at=now
                )
                session.add(row)
            return _to_dict(row)


def _to_dict(row: Todo) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
