"""add_cron_tables

Revision ID: e2b3c4d5e6f8
Revises: c3a1b2d4e5f6
Create Date: 2026-03-10 16:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e2b3c4d5e6f8"
down_revision: Union[str, None] = "c3a1b2d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cron_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("schedule", postgresql.JSONB().with_variant(sa.Text(), "sqlite"), nullable=False),
        sa.Column("task_prompt", sa.Text(), nullable=False),
        sa.Column("agent", sa.String(length=64), server_default="build", nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), server_default=sa.text("1800"), nullable=False),
        sa.Column("delivery", postgresql.JSONB().with_variant(sa.Text(), "sqlite"), server_default="{}", nullable=False),
        sa.Column("delete_after_run", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("running_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=16), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_duration_ms", sa.Integer(), nullable=True),
        sa.Column("consecutive_errors", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("summary_cache", sa.Text(), nullable=True),
        sa.Column("summary_cache_msg_id", sa.String(length=64), nullable=True),
        sa.Column("total_runs", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_successes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_failures", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cron_jobs_timer",
        "cron_jobs",
        ["enabled", "next_run_at"],
        unique=False,
        postgresql_where=sa.text("NOT is_deleted AND enabled = true"),
    )
    op.create_index(
        "ix_cron_jobs_user",
        "cron_jobs",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("NOT is_deleted"),
    )
    op.create_index(
        "ix_cron_jobs_session",
        "cron_jobs",
        ["session_id"],
        unique=False,
        postgresql_where=sa.text("NOT is_deleted"),
    )

    op.create_table(
        "cron_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("temp_session_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("task_prompt", sa.Text(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("context_summary", sa.Text(), nullable=True),
        sa.Column("injected", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("injected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("duration_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cron_runs_pending",
        "cron_runs",
        ["session_id", "injected"],
        unique=False,
        postgresql_where=sa.text("status = 'ok' AND injected = false"),
    )
    op.create_index("ix_cron_runs_job", "cron_runs", ["job_id", "started_at"], unique=False)
    op.create_index(
        "ix_cron_runs_cleanup",
        "cron_runs",
        ["started_at"],
        unique=False,
        postgresql_where=sa.text("temp_session_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_cron_runs_cleanup", table_name="cron_runs")
    op.drop_index("ix_cron_runs_job", table_name="cron_runs")
    op.drop_index("ix_cron_runs_pending", table_name="cron_runs")
    op.drop_table("cron_runs")

    op.drop_index("ix_cron_jobs_session", table_name="cron_jobs")
    op.drop_index("ix_cron_jobs_user", table_name="cron_jobs")
    op.drop_index("ix_cron_jobs_timer", table_name="cron_jobs")
    op.drop_table("cron_jobs")
