"""PostgreSQL implementation of IUserRepo."""
from datetime import datetime, timezone

from sqlalchemy import select, update

from db.base import get_db_session
from db.models.user import User


class PgUserRepo:
    async def create(self, *, id: str, username: str, password_hash: str | None,
                     email: str | None = None, role: str = "user",
                     oauth_provider: str | None = None, oauth_id: str | None = None,
                     avatar_url: str | None = None) -> dict:
        # password_hash is None for federated users (Logto/OIDC) — they never
        # authenticate against the local password path.
        now = datetime.now(timezone.utc)
        user = User(id=id, username=username, password_hash=password_hash,
                    email=email, role=role, oauth_provider=oauth_provider,
                    oauth_id=oauth_id, avatar_url=avatar_url,
                    created_at=now, updated_at=now)
        async with get_db_session() as session:
            session.add(user)
        return {"id": id, "username": username, "email": email, "role": role}

    async def get_by_oauth(self, provider: str, oauth_id: str) -> dict | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(User).where(
                    User.oauth_provider == provider,
                    User.oauth_id == oauth_id,
                    User.is_deleted == False,
                )
            )
            user = result.scalar_one_or_none()
            return _to_dict(user) if user else None

    async def get(self, user_id: str) -> dict | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(User).where(User.id == user_id, User.is_deleted == False)
            )
            user = result.scalar_one_or_none()
            return _to_dict(user) if user else None

    async def get_by_username(self, username: str) -> dict | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(User).where(User.username == username, User.is_deleted == False)
            )
            user = result.scalar_one_or_none()
            return _to_dict(user) if user else None

    async def update(self, user_id: str, **fields) -> dict | None:
        fields["updated_at"] = datetime.now(timezone.utc)
        async with get_db_session() as session:
            await session.execute(
                update(User).where(User.id == user_id).values(**fields)
            )
        return await self.get(user_id)

    async def soft_delete(self, user_id: str) -> None:
        now = datetime.now(timezone.utc)
        async with get_db_session() as session:
            await session.execute(
                update(User).where(User.id == user_id).values(
                    is_deleted=True, deleted_at=now, updated_at=now
                )
            )

    async def increment_failed_login(self, user_id: str) -> int:
        async with get_db_session() as session:
            result = await session.execute(
                select(User.failed_login_count).where(User.id == user_id)
            )
            count = (result.scalar_one_or_none() or 0) + 1
            await session.execute(
                update(User).where(User.id == user_id).values(failed_login_count=count)
            )
            return count

    async def reset_failed_login(self, user_id: str) -> None:
        async with get_db_session() as session:
            await session.execute(
                update(User).where(User.id == user_id).values(failed_login_count=0, locked_until=None)
            )

    async def lock_until(self, user_id: str, until: str) -> None:
        async with get_db_session() as session:
            await session.execute(
                update(User).where(User.id == user_id).values(locked_until=until)
            )


def _to_dict(user: User) -> dict:
    return {
        "id": user.id, "username": user.username, "email": user.email,
        "role": user.role, "is_active": user.is_active, "avatar_url": user.avatar_url,
        "oauth_provider": user.oauth_provider, "failed_login_count": user.failed_login_count,
        "locked_until": str(user.locked_until) if user.locked_until else None,
        "monthly_cost_limit": float(user.monthly_cost_limit) if user.monthly_cost_limit else None,
        "password_hash": user.password_hash,
        "created_at": str(user.created_at), "updated_at": str(user.updated_at),
    }
