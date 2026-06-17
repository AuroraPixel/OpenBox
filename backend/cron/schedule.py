"""Schedule computation — compute next/previous run times for cron jobs.

Uses `croniter` for cron expression parsing (Python equivalent of OpenClaw's `croner`).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING

from core.log import create_logger

if TYPE_CHECKING:
    from cron.types import CronSchedule

log = create_logger("cron.schedule")


def compute_next_run_at(schedule: CronSchedule, after: datetime) -> datetime | None:
    """Compute the next run time after the given datetime.

    Returns None if no next run is possible (e.g., one-shot in the past).
    """
    if schedule.kind == "at":
        at = _parse_iso(schedule.at)
        if at is None:
            return None
        return at if at > after else None

    if schedule.kind == "every":
        every_ms = max(1, schedule.every_ms)
        every_td = timedelta(milliseconds=every_ms)
        anchor = datetime.fromtimestamp(
            (schedule.anchor_ms or 0) / 1000, tz=timezone.utc
        ) if schedule.anchor_ms else after

        if after < anchor:
            return anchor

        elapsed = (after - anchor).total_seconds() * 1000
        steps = max(1, int((elapsed + every_ms - 1) // every_ms))
        return anchor + timedelta(milliseconds=steps * every_ms)

    if schedule.kind == "cron":
        try:
            from croniter import croniter
            import zoneinfo

            tz = zoneinfo.ZoneInfo(schedule.tz) if schedule.tz else timezone.utc
            # croniter works with local times in the given tz
            after_local = after.astimezone(tz)
            cron = croniter(schedule.expr, after_local)
            next_dt = cron.get_next(datetime)
            # Convert back to UTC
            return next_dt.astimezone(timezone.utc)
        except Exception as e:
            log.error(f"Failed to compute next cron run: {e}")
            return None

    return None


def compute_previous_run_at(schedule: CronSchedule, before: datetime) -> datetime | None:
    """Compute the most recent run time before the given datetime.

    Used for missed job detection on startup.
    """
    if schedule.kind == "at":
        at = _parse_iso(schedule.at)
        if at is None:
            return None
        return at if at < before else None

    if schedule.kind == "every":
        every_ms = max(1, schedule.every_ms)
        anchor = datetime.fromtimestamp(
            (schedule.anchor_ms or 0) / 1000, tz=timezone.utc
        ) if schedule.anchor_ms else before

        if before <= anchor:
            return None

        elapsed = (before - anchor).total_seconds() * 1000
        steps = int(elapsed // every_ms)
        return anchor + timedelta(milliseconds=steps * every_ms)

    if schedule.kind == "cron":
        try:
            from croniter import croniter
            import zoneinfo

            tz = zoneinfo.ZoneInfo(schedule.tz) if schedule.tz else timezone.utc
            before_local = before.astimezone(tz)
            cron = croniter(schedule.expr, before_local)
            prev_dt = cron.get_prev(datetime)
            return prev_dt.astimezone(timezone.utc)
        except Exception as e:
            log.error(f"Failed to compute previous cron run: {e}")
            return None

    return None


def compute_job_interval_ms(schedule: CronSchedule) -> int | None:
    """Estimate the average interval between runs in milliseconds.

    Used for container keepalive decisions.
    Returns None if interval cannot be determined (one-shot jobs).
    """
    if schedule.kind == "at":
        return None

    if schedule.kind == "every":
        return max(1, schedule.every_ms)

    if schedule.kind == "cron":
        try:
            from croniter import croniter
            now = datetime.now(timezone.utc)
            cron = croniter(schedule.expr, now)
            t1 = cron.get_next(datetime)
            t2 = cron.get_next(datetime)
            return int((t2 - t1).total_seconds() * 1000)
        except Exception:
            return None

    return None


def _parse_iso(s: str) -> datetime | None:
    """Parse an ISO 8601 datetime string to UTC datetime."""
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None
