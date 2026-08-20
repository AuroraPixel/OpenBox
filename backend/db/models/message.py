"""Messages table ORM model."""
from datetime import datetime

from sqlalchemy import String, Boolean, Numeric, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, JSONType


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("sessions.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    client_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    variant: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    format: Mapped[dict | None] = mapped_column(JSONType, nullable=True)   # requested output schema
    system: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tokens: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    cost: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    finish: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary: Mapped[bool | None] = mapped_column(Boolean, server_default="false")
    error: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    structured: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # StructuredOutput payload
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        Index("ix_messages_session_created", "session_id", "created_at"),
        Index("ix_messages_user", "user_id"),
        Index("ix_messages_user_created", "user_id", "created_at"),
    )
