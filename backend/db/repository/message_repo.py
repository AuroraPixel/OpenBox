"""PostgreSQL implementation of IMessageRepo. Full implementation in Phase 4."""
from datetime import datetime, timezone

from sqlalchemy import select, update, func, extract

from db.base import get_db_session
from db.models.message import Message


class PgMessageRepo:
    async def create(self, user_id: str, **fields) -> dict:
        now = datetime.now(timezone.utc)
        row = Message(user_id=user_id, created_at=now, **fields)
        async with get_db_session() as session:
            session.add(row)
        return {**fields, "user_id": user_id, "created_at": str(now)}

    async def get(self, message_id: str) -> dict | None:
        async with get_db_session() as session:
            result = await session.execute(select(Message).where(Message.id == message_id))
            row = result.scalar_one_or_none()
            return _to_dict(row) if row else None

    async def list_by_session(self, session_id: str) -> list[dict]:
        async with get_db_session() as session:
            result = await session.execute(
                select(Message).where(Message.session_id == session_id)
                .order_by(Message.created_at)
            )
            return [_to_dict(r) for r in result.scalars().all()]

    async def update(self, message_id: str, **fields) -> dict | None:
        async with get_db_session() as session:
            await session.execute(update(Message).where(Message.id == message_id).values(**fields))
        return await self.get(message_id)

    async def sum_cost_this_month(self, user_id: str) -> float:
        now = datetime.now(timezone.utc)
        async with get_db_session() as session:
            result = await session.execute(
                select(func.coalesce(func.sum(Message.cost), 0)).where(
                    Message.user_id == user_id,
                    extract("year", Message.created_at) == now.year,
                    extract("month", Message.created_at) == now.month,
                )
            )
            return float(result.scalar_one())


def _to_dict(row: Message) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
