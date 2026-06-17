"""PostgreSQL implementation of IPermissionRepo."""
from datetime import datetime, timezone

from sqlalchemy import select, delete

from db.base import get_db_session
from db.models.permission import PermissionRule


class PgPermissionRepo:
    async def create_rule(self, user_id: str, **fields) -> dict:
        now = datetime.now(timezone.utc)
        row = PermissionRule(user_id=user_id, created_at=now, **fields)
        async with get_db_session() as session:
            session.add(row)
        return {**fields, "user_id": user_id, "created_at": str(now)}

    async def list_rules(self, user_id: str, project_id: str | None = None) -> list[dict]:
        async with get_db_session() as session:
            q = select(PermissionRule).where(PermissionRule.user_id == user_id)
            if project_id:
                q = q.where(
                    (PermissionRule.project_id == project_id) | (PermissionRule.project_id.is_(None))
                )
            result = await session.execute(q)
            return [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in result.scalars().all()]

    async def delete_rule(self, rule_id: str, user_id: str) -> None:
        async with get_db_session() as session:
            await session.execute(
                delete(PermissionRule).where(
                    PermissionRule.id == rule_id, PermissionRule.user_id == user_id
                )
            )
