"""User preferences table ORM model."""
from sqlalchemy import String, Boolean, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, JSONType


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), unique=True, nullable=False)
    theme: Mapped[str] = mapped_column(String(16), server_default="system")
    default_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    default_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_variant: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sidebar_open: Mapped[bool] = mapped_column(Boolean, server_default="true")
    right_panel_open: Mapped[bool] = mapped_column(Boolean, server_default="false")
    bottom_panel_height: Mapped[int] = mapped_column(Integer, server_default="200")
    extra: Mapped[dict] = mapped_column(JSONType, server_default="{}")
