"""Backoff schedule for LLM retries.

The delay is what stands between a rate limit and a stampede, so the schedule
is asserted directly. `rand` is injected everywhere to keep these deterministic.
"""
import pytest

from agent.retry import (
    MAX_RETRIES,
    RETRY_BACKOFF_FACTOR,
    RETRY_INITIAL_DELAY,
    RETRY_JITTER_FACTOR,
    RETRY_MAX_DELAY,
    RetryableError,
    retry_delay,
)

MID = 0.5  # jitter midpoint — yields exactly the nominal delay


# ── exponential growth ──

@pytest.mark.parametrize("attempt,expected", [
    (1, RETRY_INITIAL_DELAY),
    (2, RETRY_INITIAL_DELAY * RETRY_BACKOFF_FACTOR),
    (3, RETRY_INITIAL_DELAY * RETRY_BACKOFF_FACTOR ** 2),
    (4, RETRY_INITIAL_DELAY * RETRY_BACKOFF_FACTOR ** 3),
])
def test_delay_doubles_each_attempt(attempt, expected):
    assert retry_delay(attempt, rand=MID) == pytest.approx(expected)


def test_delay_is_capped_without_headers():
    # Far enough out that the uncapped value would be astronomically large.
    assert retry_delay(MAX_RETRIES, rand=MID) == pytest.approx(RETRY_MAX_DELAY)


# ── jitter ──

def test_jitter_spans_the_configured_band():
    nominal = RETRY_INITIAL_DELAY
    assert retry_delay(1, rand=0.0) == pytest.approx(nominal * (1 - RETRY_JITTER_FACTOR))
    assert retry_delay(1, rand=1.0) == pytest.approx(nominal * (1 + RETRY_JITTER_FACTOR))


def test_jitter_never_collapses_to_a_single_value():
    """Two callers hitting the same limit must not wake on the same tick."""
    delays = {retry_delay(3, rand=r) for r in (0.0, 0.25, 0.5, 0.75, 1.0)}
    assert len(delays) == 5


def test_jitter_stays_positive():
    assert retry_delay(1, rand=0.0) > 0


def test_default_rand_is_random(monkeypatch):
    monkeypatch.setattr("agent.retry.random.random", lambda: 1.0)
    assert retry_delay(1) == pytest.approx(RETRY_INITIAL_DELAY * (1 + RETRY_JITTER_FACTOR))


# ── server-supplied retry-after wins, unjittered ──

def test_retry_after_ms_is_honoured_verbatim():
    err = RetryableError("429", 429, {"retry-after-ms": "1500"})
    assert retry_delay(1, err, rand=0.0) == pytest.approx(1.5)
    assert retry_delay(9, err, rand=1.0) == pytest.approx(1.5)  # attempt-independent


def test_retry_after_seconds_is_honoured_verbatim():
    err = RetryableError("429", 429, {"retry-after": "7"})
    assert retry_delay(1, err, rand=0.0) == pytest.approx(7.0)


def test_retry_after_is_not_capped():
    """A server asking for two minutes means two minutes; capping it at
    RETRY_MAX_DELAY would hammer a provider that just told us to back off."""
    err = RetryableError("429", 429, {"retry-after": "120"})
    assert retry_delay(1, err, rand=MID) == pytest.approx(120.0)


def test_retry_after_ms_takes_precedence_over_seconds():
    err = RetryableError("429", 429, {"retry-after-ms": "500", "retry-after": "60"})
    assert retry_delay(1, err, rand=MID) == pytest.approx(0.5)


def test_unparseable_retry_after_falls_back_to_backoff():
    err = RetryableError("429", 429, {"retry-after": "soon"})
    assert retry_delay(2, err, rand=MID) == pytest.approx(
        RETRY_INITIAL_DELAY * RETRY_BACKOFF_FACTOR
    )


def test_headers_without_retry_after_are_uncapped():
    """Having headers at all means we are talking to a real API; let the
    backoff grow past the no-information cap."""
    err = RetryableError("429", 429, {"x-request-id": "abc"})
    assert retry_delay(MAX_RETRIES, err, rand=MID) > RETRY_MAX_DELAY


def test_non_retryable_error_uses_plain_backoff():
    assert retry_delay(2, ValueError("nope"), rand=MID) == pytest.approx(
        RETRY_INITIAL_DELAY * RETRY_BACKOFF_FACTOR
    )
