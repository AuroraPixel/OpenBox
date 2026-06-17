"""PostgreSQL implementation of IAuditRepo."""
from datetime import datetime, timezone

from sqlalchemy import select

from db.base import get_db_session
from db.models.audit_log import AuditLog


class PgAuditRepo:
    async def create(self, user_id: str, action: str, **fields) -> dict:
        now = datetime.now(timezone.utc)
        row = AuditLog(user_id=user_id, action=action, created_at=now, **fields)
        async with get_db_session() as session:
            session.add(row)
        return {"user_id": user_id, "action": action, **fields, "created_at": str(now)}

    async def list_by_user(self, user_id: str, offset: int = 0, limit: int = 100) -> list[dict]:
        async with get_db_session() as session:
            result = await session.execute(
                select(AuditLog).where(AuditLog.user_id == user_id)
                .order_by(AuditLog.created_at.desc())
                .offset(offset).limit(limit)
            )
            return [{c.name: getattr(r, c.name) for c in r.__table__.columns}
                    for r in result.scalars().all()]
