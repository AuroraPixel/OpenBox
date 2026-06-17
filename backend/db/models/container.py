"""Containers table ORM model."""
from datetime import datetime

from sqlalchemy import String, Boolean, Integer, Index, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, JSONType


class Container(Base):
    __tablename__ = "containers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("projects.id"), nullable=True)
    docker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True, server_default=text("'localhost'"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_limits: Mapped[dict] = mapped_column(JSONType, server_default="{}")
    is_deleted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        Index("ix_containers_user_project", "user_id", "project_id"),
        Index("ix_containers_docker_id", "docker_id", unique=True, postgresql_where=text("docker_id IS NOT NULL")),
        Index("ix_containers_port_active", "port", unique=True, postgresql_where=text("port IS NOT NULL AND is_deleted = false")),
    )
