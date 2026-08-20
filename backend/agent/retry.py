"""Retry logic with exponential backoff."""
import asyncio
import random
import re
from typing import Any, Callable, Awaitable

from bus import bus
from bus.events import SESSION_STATUS
from core.log import create_logger

log = create_logger("agent.retry")

RETRY_INITIAL_DELAY = 2.0  # seconds
RETRY_BACKOFF_FACTOR = 2
RETRY_MAX_DELAY = 30.0  # seconds
MAX_RETRIES = 10
# Without jitter every caller that hit the same rate limit retries on the same
# tick and stampedes the provider again. Spreads each delay over [1-f, 1+f].
RETRY_JITTER_FACTOR = 0.25

# Context overflow error patterns
OVERFLOW_PATTERNS = [
    r"prompt is too long",
    r"input is too long for requested model",
    r"exceeds the context window",
    r"input token count.*exceeds the maximum",
    r"maximum prompt length is \d+",
    r"reduce the length of the messages",
    r"maximum context length is \d+ tokens",
    r"exceeds the limit of \d+",
    r"exceeds the available context size",
    r"greater than the context length",
    r"context window exceeds limit",
    r"exceeded model token limit",
    r"context[_ ]length[_ ]exceeded",
]


class RetryableError(Exception):
    """Error that can be retried."""
    def __init__(self, message: str, status_code: int | None = None, headers: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.headers = headers or {}


class ContextOverflowError(Exception):
    """Context window exceeded - do not retry, trigger compaction."""
    pass


class MaxRetriesExceeded(Exception):
    """Maximum retry attempts exhausted."""
    pass


def is_context_overflow(message: str) -> bool:
    """Check if an error message indicates context overflow."""
    return any(re.search(p, message, re.IGNORECASE) for p in OVERFLOW_PATTERNS)


def is_retryable(error: Exception) -> str | None:
    """Check if an error is retryable. Returns a display message or None."""
    if isinstance(error, ContextOverflowError):
        return None

    msg = str(error).lower()

    if isinstance(error, RetryableError):
        if error.status_code in (429, 503, 529):
            return "Rate limited" if error.status_code == 429 else "Service unavailable"
        if error.status_code == 502:
            return "Bad gateway"
        if "overloaded" in msg:
            return "Provider is overloaded"
        return str(error)

    # Check for retryable patterns in generic errors
    retryable_patterns = [
        "too_many_requests", "rate_limit", "exhausted",
        "unavailable", "overloaded", "timeout", "connection",
        "bad_gateway", "badgateway", "502",
    ]
    for pattern in retryable_patterns:
        if pattern in msg:
            return f"Retryable error: {pattern}"

    return None


def _jitter(seconds: float, rand: float) -> float:
    """Spread a delay over [1-f, 1+f] of its nominal value."""
    return seconds * (1.0 + RETRY_JITTER_FACTOR * (2.0 * rand - 1.0))


def retry_delay(attempt: int, error: Exception | None = None, rand: float | None = None) -> float:
    """Calculate retry delay in seconds.

    `rand` is injectable so the schedule can be asserted in tests; it defaults
    to random.random(). A server-supplied retry-after is honoured verbatim —
    jitter is only applied to delays we invented ourselves.
    """
    if rand is None:
        rand = random.random()
    if isinstance(error, RetryableError) and error.headers:
        headers = error.headers
        # 1. retry-after-ms
        if "retry-after-ms" in headers:
            return float(headers["retry-after-ms"]) / 1000.0
        # 2. retry-after (seconds)
        if "retry-after" in headers:
            try:
                return float(headers["retry-after"])
            except ValueError:
                pass
        # Has headers but no retry-after, exponential backoff (no cap)
        return _jitter(RETRY_INITIAL_DELAY * (RETRY_BACKOFF_FACTOR ** (attempt - 1)), rand)

    # No headers, exponential backoff with cap
    return _jitter(
        min(
            RETRY_INITIAL_DELAY * (RETRY_BACKOFF_FACTOR ** (attempt - 1)),
            RETRY_MAX_DELAY,
        ),
        rand,
    )


async def with_retry(
    fn: Callable[[], Awaitable[Any]],
    session_id: str = "",
    max_retries: int = MAX_RETRIES,
    user_id: str = "default",
) -> Any:
    """Execute a function with retry logic."""
    for attempt in range(1, max_retries + 1):
        try:
            return await fn()
        except ContextOverflowError:
            raise  # Never retry context overflow
        except Exception as e:
            retry_msg = is_retryable(e)
            if retry_msg is None or attempt >= max_retries:
                raise

            delay = retry_delay(attempt, e)
            log.warning(f"Attempt {attempt}/{max_retries} failed: {retry_msg}. Retrying in {delay:.1f}s")

            if session_id:
                bus.publish(SESSION_STATUS, {
                    "userId": user_id,
                    "sessionId": session_id,
                    "status": "retry",
                })

            await asyncio.sleep(delay)

    raise MaxRetriesExceeded(f"Failed after {max_retries} attempts")
