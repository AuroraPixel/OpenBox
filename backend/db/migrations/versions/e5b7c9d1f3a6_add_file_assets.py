"""add_file_assets

Ledger for files transferred browser -> OSS -> cloud desktop. The backend
never carries the bytes; it signs URLs and records the uploads here.

Revision ID: e5b7c9d1f3a6
Revises: d4f6a8c0e2b4
Create Date: 2026-08-21 14:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'e5b7c9d1f3a6'
down_revision: Union[str, None] = 'd4f6a8c0e2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "file_assets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("oss_key", sa.String(512), nullable=False),
        sa.Column("mime", sa.String(128), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_file_assets_user_created", "file_assets", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_file_assets_user_created", table_name="file_assets")
    op.drop_table("file_assets")
