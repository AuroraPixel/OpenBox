"""Cron jobs and runs ORM models."""
from datetime import datetime

from sqlalchemy import String, Boolean, Integer, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, JSONType


class CronJob(Base):
    """Scheduled task definition."""
    __tablename__ = "cron_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Basic info
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, server_default="")
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    # Schedule config (stored as JSON for flexibility)
    schedule: Mapped[dict] = mapped_column(JSONType, nullable=False)

    # Task config
    task_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    agent: Mapped[str] = mapped_column(String(64), server_default="build")
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, server_default=text("1800"))

    # Delivery config
    delivery: Mapped[dict] = mapped_column(JSONType, server_default="{}")

    # Retry config
    delete_after_run: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    max_retries: Mapped[int] = mapped_column(Integer, server_default=text("3"))

    # Scheduler state
    next_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    running_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consecutive_errors: Mapped[int] = mapped_column(Integer, server_default=text("0"))

    # Summary cache
    summary_cache: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_cache_msg_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Stats
    total_runs: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    total_successes: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    total_failures: Mapped[int] = mapped_column(Integer, server_default=text("0"))

    # Metadata
    is_deleted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        # Timer query: find due jobs efficiently
        Index(
            "ix_cron_jobs_timer",
            "enabled", "next_run_at",
            postgresql_where=text("NOT is_deleted AND enabled = true"),
        ),
        # User's jobs
        Index(
            "ix_cron_jobs_user",
            "user_id",
            postgresql_where=text("NOT is_deleted"),
        ),
        # Session's jobs
        Index(
            "ix_cron_jobs_session",
            "session_id",
            postgresql_where=text("NOT is_deleted"),
        ),
    )


class CronRun(Base):
    """Execution history for cron jobs."""
    __tablename__ = "cron_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    temp_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Execution state
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Content
    task_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Injection state
    injected: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    injected_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Token stats
    input_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    total_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    duration_ms: Mapped[int] = mapped_column(Integer, server_default=text("0"))

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        # Pending injection query
        Index(
            "ix_cron_runs_pending",
            "session_id", "injected",
            postgresql_where=text("status = 'ok' AND injected = false"),
        ),
        # Job history (newest first)
        Index("ix_cron_runs_job", "job_id", "started_at"),
        # Cleanup query
        Index(
            "ix_cron_runs_cleanup",
            "started_at",
            postgresql_where=text("temp_session_id IS NOT NULL"),
        ),
    )
