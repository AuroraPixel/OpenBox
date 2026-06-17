"""Parts table ORM model (single-table polymorphic)."""
from datetime import datetime

from sqlalchemy import String, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, JSONType


class Part(Base):
    __tablename__ = "parts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(64), ForeignKey("messages.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        Index("ix_parts_message", "message_id"),
        Index("ix_parts_message_created", "message_id", "created_at"),
        Index("ix_parts_session_type", "session_id", "type"),
        Index("ix_parts_session_type_created", "session_id", "type", "created_at"),
        Index("ix_parts_user", "user_id"),
    )
