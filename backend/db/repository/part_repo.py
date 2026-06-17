"""PostgreSQL implementation of IPartRepo."""
from datetime import datetime, timezone

from sqlalchemy import select, update

from db.base import get_db_session
from db.models.part import Part


class PgPartRepo:
    async def create(self, user_id: str, **fields) -> dict:
        now = datetime.now(timezone.utc)
        row = Part(user_id=user_id, created_at=now, **fields)
        async with get_db_session() as session:
            session.add(row)
        return {**fields, "user_id": user_id, "created_at": str(now)}

    async def upsert(self, user_id: str, **fields) -> dict:
        part_id = fields.get("id")
        async with get_db_session() as session:
            result = await session.execute(select(Part).where(Part.id == part_id))
            existing = result.scalar_one_or_none()
            if existing:
                for k, v in fields.items():
                    if k != "id":
                        setattr(existing, k, v)
                return {**fields}
            else:
                now = datetime.now(timezone.utc)
                row = Part(user_id=user_id, created_at=now, **fields)
                session.add(row)
                return {**fields, "user_id": user_id, "created_at": str(now)}

    async def get(self, part_id: str) -> dict | None:
        async with get_db_session() as session:
            result = await session.execute(select(Part).where(Part.id == part_id))
            row = result.scalar_one_or_none()
            return _to_dict(row) if row else None

    async def list_by_message(self, message_id: str) -> list[dict]:
        async with get_db_session() as session:
            result = await session.execute(
                select(Part).where(Part.message_id == message_id)
                .order_by(Part.created_at)
            )
            return [_to_dict(r) for r in result.scalars().all()]

    async def update(self, part_id: str, **fields) -> dict | None:
        async with get_db_session() as session:
            await session.execute(
                update(Part).where(Part.id == part_id).values(**fields)
            )
        return await self.get(part_id)


def _to_dict(row: Part) -> dict:
    d = {}
    for c in row.__table__.columns:
        v = getattr(row, c.name)
        if c.name == "data" and isinstance(v, dict):
            # Merge data fields into top level for compatibility with existing code
            d.update(v)
        d[c.name] = v
    return d
