"""Users table ORM model."""
from datetime import datetime

from sqlalchemy import String, Boolean, Integer, Index, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String(16), server_default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    oauth_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    oauth_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)
    monthly_cost_limit: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        Index("ix_users_username_active", "username", unique=True, postgresql_where=text("is_deleted = false")),
        Index("ix_users_email_active", "email", unique=True, postgresql_where=text("email IS NOT NULL AND is_deleted = false")),
        Index("ix_users_oauth", "oauth_provider", "oauth_id", unique=True, postgresql_where=text("oauth_provider IS NOT NULL")),
    )
