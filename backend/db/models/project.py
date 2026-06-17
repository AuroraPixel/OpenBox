"""Projects table ORM model."""
from datetime import datetime

from sqlalchemy import String, Boolean, Index, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        Index("ix_projects_user_id", "user_id"),
        Index("ix_projects_user_slug_active", "user_id", "slug", unique=True, postgresql_where=text("is_deleted = false")),
    )
