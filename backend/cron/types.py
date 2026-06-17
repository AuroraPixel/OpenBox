"""Type definitions for the cron system."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Schedule types
# ---------------------------------------------------------------------------

class CronScheduleAt(BaseModel):
    """One-shot at a specific time."""
    kind: Literal["at"] = "at"
    at: str  # ISO 8601 datetime string


class CronScheduleEvery(BaseModel):
    """Fixed interval schedule."""
    kind: Literal["every"] = "every"
    every_ms: int  # Interval in milliseconds
    anchor_ms: int | None = None  # Anchor point for interval alignment


class CronScheduleCron(BaseModel):
    """Standard cron expression schedule."""
    kind: Literal["cron"] = "cron"
    expr: str  # Cron expression (e.g. "0 9 * * *")
    tz: str = "UTC"  # Timezone


CronSchedule = CronScheduleAt | CronScheduleEvery | CronScheduleCron


# ---------------------------------------------------------------------------
# Job status
# ---------------------------------------------------------------------------

class CronJobStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    SKIPPED = "skipped"
    RUNNING = "running"


# ---------------------------------------------------------------------------
# Delivery config (extensible)
# ---------------------------------------------------------------------------

class CronDeliveryConfig(BaseModel):
    mode: Literal["none", "webhook", "channel"] = "none"
    webhook_url: str | None = None
    webhook_token: str | None = None
    channel: str | None = None
    to: str | None = None


# ---------------------------------------------------------------------------
# Job definition (API input)
# ---------------------------------------------------------------------------

class CronJobCreate(BaseModel):
    """Input for creating a new cron job."""
    session_id: str
    name: str
    description: str = ""
    schedule: CronSchedule
    task_prompt: str
    agent: str = "build"
    model: str | None = None  # None = follow session model
    timeout_seconds: int = 1800
    delivery: CronDeliveryConfig = Field(default_factory=CronDeliveryConfig)
    enabled: bool = True
    delete_after_run: bool | None = None  # None = auto (True for "at" jobs)
    max_retries: int = 3


class CronJobUpdate(BaseModel):
    """Input for updating a cron job."""
    name: str | None = None
    description: str | None = None
    schedule: CronSchedule | None = None
    task_prompt: str | None = None
    agent: str | None = None
    model: str | None = None
    timeout_seconds: int | None = None
    delivery: CronDeliveryConfig | None = None
    enabled: bool | None = None


# ---------------------------------------------------------------------------
# Backoff constants (matching OpenClaw)
# ---------------------------------------------------------------------------

BACKOFF_SCHEDULE_MS = [
    30_000,       # 1st error  → 30 seconds
    60_000,       # 2nd error  → 1 minute
    5 * 60_000,   # 3rd error  → 5 minutes
    15 * 60_000,  # 4th error  → 15 minutes
    60 * 60_000,  # 5th+ error → 60 minutes
]

# Timer constants
MAX_TIMER_DELAY_MS = 60_000   # Wake at least once per minute
MIN_REFIRE_GAP_MS = 2_000     # Min 2s between same job fires
STUCK_RUN_MS = 2 * 60 * 60 * 1000  # 2 hours = stuck

# Transient error patterns (for one-shot retry)
TRANSIENT_PATTERNS = {
    "rate_limit": r"(?i)(rate[_ ]limit|too many requests|429|resource has been exhausted)",
    "network": r"(?i)(network|econnreset|econnrefused|fetch failed|socket)",
    "timeout": r"(?i)(timeout|etimedout)",
    "server_error": r"\b5\d{2}\b",
}
