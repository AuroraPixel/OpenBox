"""Todos table ORM model."""
from datetime import datetime

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, JSONType


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("sessions.id"), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    items: Mapped[dict] = mapped_column(JSONType, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)
