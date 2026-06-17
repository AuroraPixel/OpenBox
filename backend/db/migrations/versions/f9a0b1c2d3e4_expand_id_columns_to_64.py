"""expand_id_columns_to_64

Revision ID: f9a0b1c2d3e4
Revises: e2b3c4d5e6f8
Create Date: 2026-03-10 16:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, None] = "e2b3c4d5e6f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUMNS = [
    ("users", "id"),
    ("audit_logs", "id"),
    ("audit_logs", "user_id"),
    ("audit_logs", "resource_id"),
    ("projects", "id"),
    ("projects", "user_id"),
    ("prompt_history", "id"),
    ("prompt_history", "user_id"),
    ("user_preferences", "id"),
    ("user_preferences", "user_id"),
    ("containers", "id"),
    ("containers", "user_id"),
    ("containers", "project_id"),
    ("permission_rules", "id"),
    ("permission_rules", "user_id"),
    ("permission_rules", "project_id"),
    ("sessions", "id"),
    ("sessions", "user_id"),
    ("sessions", "project_id"),
    ("sessions", "parent_id"),
    ("messages", "id"),
    ("messages", "session_id"),
    ("messages", "user_id"),
    ("messages", "parent_id"),
    ("todos", "id"),
    ("todos", "session_id"),
    ("todos", "user_id"),
    ("parts", "id"),
    ("parts", "message_id"),
    ("parts", "session_id"),
    ("parts", "user_id"),
]


def upgrade() -> None:
    for table, column in COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.String(length=26),
            type_=sa.String(length=64),
        )


def downgrade() -> None:
    for table, column in reversed(COLUMNS):
        op.alter_column(
            table,
            column,
            existing_type=sa.String(length=64),
            type_=sa.String(length=26),
        )
