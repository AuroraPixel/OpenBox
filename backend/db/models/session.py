"""Sessions table ORM model."""
from datetime import datetime

from sqlalchemy import String, Boolean, Integer, Index, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, JSONType


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    slug: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), server_default="idle")
    parent_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("sessions.id"), nullable=True)
    token_usage: Mapped[dict] = mapped_column(JSONType, server_default="{}")
    additions: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    deletions: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    files_changed: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    sandbox_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        Index("ix_sessions_user_project_active", "user_id", "project_id", "is_deleted"),
        Index("ix_sessions_user_status_active", "user_id", "status", "is_deleted"),
        Index("ix_sessions_user_created", "user_id", "created_at"),
        Index("ix_sessions_parent", "parent_id"),
    )
