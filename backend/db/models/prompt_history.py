"""Prompt history table ORM model."""
from datetime import datetime

from sqlalchemy import String, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class PromptHistory(Base):
    __tablename__ = "prompt_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        Index("ix_prompt_history_user_created", "user_id", "created_at"),
    )
