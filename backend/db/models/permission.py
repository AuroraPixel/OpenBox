"""Permission rules table ORM model."""
from datetime import datetime

from sqlalchemy import String, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class PermissionRule(Base):
    __tablename__ = "permission_rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("projects.id"), nullable=True)
    permission: Mapped[str] = mapped_column(String(128), nullable=False)
    pattern: Mapped[str | None] = mapped_column(String(512), nullable=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        Index("ix_permission_rules_user_project", "user_id", "project_id"),
    )
