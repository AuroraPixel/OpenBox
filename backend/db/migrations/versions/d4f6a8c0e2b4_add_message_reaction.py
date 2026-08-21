"""add_message_reaction

Adds a per-message reaction column so the chat UI can persist the
thumbs-up / thumbs-down feedback shown in the message meta bar.

Revision ID: d4f6a8c0e2b4
Revises: a1c3e5f7b9d2
Create Date: 2026-08-20 23:50:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'd4f6a8c0e2b4'
down_revision: Union[str, None] = 'a1c3e5f7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("reaction", sa.String(8), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "reaction")
