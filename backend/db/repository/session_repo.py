"""PostgreSQL implementation of ISessionRepo. Full implementation in Phase 4."""
from datetime import datetime, timezone

from sqlalchemy import select, update, func

from db.base import get_db_session
from db.models.session import Session


class PgSessionRepo:
    async def create(self, user_id: str, **fields) -> dict:
        now = datetime.now(timezone.utc)
        row = Session(user_id=user_id, created_at=now, updated_at=now, **fields)
        async with get_db_session() as session:
            session.add(row)
        return {**fields, "user_id": user_id, "created_at": str(now)}

    async def get(self, session_id: str, user_id: str) -> dict | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(Session).where(
                    Session.id == session_id, Session.user_id == user_id, Session.is_deleted == False
                )
            )
            row = result.scalar_one_or_none()
            return _to_dict(row) if row else None

    async def list_by_user(self, user_id: str, project_id: str | None = None,
                           offset: int = 0, limit: int = 100) -> list[dict]:
        async with get_db_session() as session:
            q = select(Session).where(Session.user_id == user_id, Session.is_deleted == False)
            if project_id:
                q = q.where(Session.project_id == project_id)
            q = q.order_by(Session.created_at.desc()).offset(offset).limit(limit)
            result = await session.execute(q)
            return [_to_dict(r) for r in result.scalars().all()]

    async def update(self, session_id: str, user_id: str, **fields) -> dict | None:
        fields["updated_at"] = datetime.now(timezone.utc)
        async with get_db_session() as db:
            await db.execute(
                update(Session).where(
                    Session.id == session_id, Session.user_id == user_id
                ).values(**fields)
            )
        return await self.get(session_id, user_id)

    async def soft_delete(self, session_id: str, user_id: str) -> None:
        now = datetime.now(timezone.utc)
        async with get_db_session() as session:
            await session.execute(
                update(Session).where(
                    Session.id == session_id, Session.user_id == user_id
                ).values(is_deleted=True, deleted_at=now, updated_at=now)
            )

    async def count_by_user(self, user_id: str) -> int:
        async with get_db_session() as session:
            result = await session.execute(
                select(func.count()).select_from(Session).where(
                    Session.user_id == user_id, Session.is_deleted == False
                )
            )
            return result.scalar_one()

    async def count_busy(self, user_id: str) -> int:
        async with get_db_session() as session:
            result = await session.execute(
                select(func.count()).select_from(Session).where(
                    Session.user_id == user_id, Session.status == "busy"
                )
            )
            return result.scalar_one()


def _to_dict(row: Session) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
