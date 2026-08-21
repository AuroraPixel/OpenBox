"""Uploaded-asset records: files that moved browser → OSS → cloud desktop.

The bytes never touch the backend — this table is the ledger: who uploaded
what, under which OSS key, and whether the upload actually completed.
"""
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class FileAsset(Base):
    __tablename__ = "file_assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Object key inside the asset bucket (assets/{user}/{asset}/{name}).
    oss_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime: Mapped[str] = mapped_column(String(128), nullable=False, default="application/octet-stream")
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: pending → the PUT URL was issued; ready → object verified in OSS.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (Index("ix_file_assets_user_created", "user_id", "created_at"),)
