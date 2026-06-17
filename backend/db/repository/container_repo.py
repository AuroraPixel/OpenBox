"""PostgreSQL implementation of IContainerRepo."""
from datetime import datetime, timezone

from sqlalchemy import select, update, func

from db.base import get_db_session
from db.models.container import Container


class PgContainerRepo:
    async def create(self, user_id: str, **fields) -> dict:
        now = datetime.now(timezone.utc)
        row = Container(user_id=user_id, created_at=now, updated_at=now, **fields)
        async with get_db_session() as session:
            session.add(row)
        return {**fields, "user_id": user_id}

    async def get(self, container_id: str, user_id: str) -> dict | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(Container).where(
                    Container.id == container_id, Container.user_id == user_id,
                    Container.is_deleted == False
                )
            )
            row = result.scalar_one_or_none()
            return _to_dict(row) if row else None

    async def list_by_user(self, user_id: str, project_id: str | None = None) -> list[dict]:
        async with get_db_session() as session:
            q = select(Container).where(Container.user_id == user_id, Container.is_deleted == False)
            if project_id:
                q = q.where(Container.project_id == project_id)
            result = await session.execute(q)
            return [_to_dict(r) for r in result.scalars().all()]

    async def update(self, container_id: str, **fields) -> dict | None:
        fields["updated_at"] = datetime.now(timezone.utc)
        async with get_db_session() as session:
            await session.execute(
                update(Container).where(Container.id == container_id).values(**fields)
            )
        return None  # caller should re-fetch if needed

    async def soft_delete(self, container_id: str, user_id: str) -> None:
        now = datetime.now(timezone.utc)
        async with get_db_session() as session:
            await session.execute(
                update(Container).where(
                    Container.id == container_id, Container.user_id == user_id
                ).values(is_deleted=True, deleted_at=now, updated_at=now)
            )

    async def count_by_user(self, user_id: str) -> int:
        async with get_db_session() as session:
            result = await session.execute(
                select(func.count()).select_from(Container).where(
                    Container.user_id == user_id, Container.is_deleted == False
                )
            )
            return result.scalar_one()


def _to_dict(row: Container) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
