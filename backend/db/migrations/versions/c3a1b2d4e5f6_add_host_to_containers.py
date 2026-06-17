"""add_host_to_containers

Revision ID: c3a1b2d4e5f6
Revises: b7c2f9f8d1a1
Create Date: 2026-03-06 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'c3a1b2d4e5f6'
down_revision: Union[str, None] = 'b7c2f9f8d1a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('containers', sa.Column('host', sa.String(255), nullable=True, server_default='localhost'))


def downgrade() -> None:
    op.drop_column('containers', 'host')
