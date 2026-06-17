"""PostgreSQL implementation of IPreferenceRepo."""
from sqlalchemy import select

from core.identifier import generate_id
from db.base import get_db_session
from db.models.preference import UserPreference


class PgPreferenceRepo:
    async def get(self, user_id: str) -> dict | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(UserPreference).where(UserPreference.user_id == user_id)
            )
            row = result.scalar_one_or_none()
            return _to_dict(row) if row else None

    async def upsert(self, user_id: str, **fields) -> dict:
        async with get_db_session() as session:
            result = await session.execute(
                select(UserPreference).where(UserPreference.user_id == user_id)
            )
            row = result.scalar_one_or_none()
            if row:
                for k, v in fields.items():
                    setattr(row, k, v)
            else:
                row = UserPreference(id=generate_id(), user_id=user_id, **fields)
                session.add(row)
            return _to_dict(row)


def _to_dict(row: UserPreference) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
