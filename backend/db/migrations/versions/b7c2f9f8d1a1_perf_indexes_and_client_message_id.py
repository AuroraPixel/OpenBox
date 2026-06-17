"""perf_indexes_and_client_message_id

Revision ID: b7c2f9f8d1a1
Revises: ea9d90d96835
Create Date: 2026-03-01 17:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'b7c2f9f8d1a1'
down_revision: Union[str, None] = 'ea9d90d96835'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('messages', sa.Column('client_message_id', sa.String(length=64), nullable=True))

    op.create_index('ix_messages_user_created', 'messages', ['user_id', 'created_at'], unique=False)
    op.create_index('ix_parts_message_created', 'parts', ['message_id', 'created_at'], unique=False)
    op.create_index('ix_parts_session_type_created', 'parts', ['session_id', 'type', 'created_at'], unique=False)
    op.create_index('ix_sessions_user_status_active', 'sessions', ['user_id', 'status', 'is_deleted'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_sessions_user_status_active', table_name='sessions')
    op.drop_index('ix_parts_session_type_created', table_name='parts')
    op.drop_index('ix_parts_message_created', table_name='parts')
    op.drop_index('ix_messages_user_created', table_name='messages')

    op.drop_column('messages', 'client_message_id')
