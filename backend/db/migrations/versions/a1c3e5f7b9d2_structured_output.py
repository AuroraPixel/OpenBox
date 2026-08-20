"""structured_output

Widens messages.format so it can hold a JSON Schema, and adds
messages.structured for the payload the model returns against it.

`format` was declared as String(32) but never written by any code path, so the
type change has no existing values to preserve.

Revision ID: a1c3e5f7b9d2
Revises: f9a0b1c2d3e4
Create Date: 2026-08-20 14:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1c3e5f7b9d2"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type(bind):
    # SQLite (used by the test suite) has no JSONB.
    return postgresql.JSONB() if bind.dialect.name == "postgresql" else sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    json_type = _json_type(bind)

    if bind.dialect.name == "postgresql":
        op.alter_column(
            "messages", "format",
            existing_type=sa.String(32),
            type_=json_type,
            existing_nullable=True,
            # The column is unconditionally NULL today; the cast is here so the
            # migration is still correct if that ever stops being true.
            postgresql_using="format::jsonb",
        )
    else:
        with op.batch_alter_table("messages") as batch:
            batch.alter_column("format", existing_type=sa.String(32), type_=json_type)

    op.add_column("messages", sa.Column("structured", json_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_column("messages", "structured")

    if bind.dialect.name == "postgresql":
        op.alter_column(
            "messages", "format",
            existing_type=postgresql.JSONB(),
            type_=sa.String(32),
            existing_nullable=True,
            postgresql_using="format::text",
        )
    else:
        with op.batch_alter_table("messages") as batch:
            batch.alter_column("format", existing_type=sa.JSON(), type_=sa.String(32))
