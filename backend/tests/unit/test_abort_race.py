"""A stop must not be lost in the gap before the run starts.

Accepting a prompt and actually starting the loop are two separate steps, and
the composer shows a stop button across both. Pressing it in that gap used to
be silently discarded: the run registered a fresh signal over the one the stop
had set, so the loop never saw it. The UI reported the run stopped while it
kept going — the intermittent "stop button does nothing".
"""
import time

import pytest

from session import status as st


@pytest.fixture(autouse=True)
def clean_registry():
    st._abort_signals.clear()
    st._pending_aborts.clear()
    yield
    st._abort_signals.clear()
    st._pending_aborts.clear()


SID = "session_x"


def test_a_stop_during_a_run_reaches_that_run():
    signal = st.register_run(SID)
    st.trigger_abort(SID)
    assert signal.is_set()


def test_an_ordinary_run_does_not_start_aborted():
    assert not st.register_run(SID).is_set()


def test_a_stop_in_the_gap_reaches_the_run_that_follows():
    st.trigger_abort(SID)          # no run registered yet
    assert st.register_run(SID).is_set()


def test_such_a_stop_is_consumed_once():
    st.trigger_abort(SID)
    st.register_run(SID)
    st.clear_abort(SID)
    assert not st.register_run(SID).is_set()


def test_a_stale_stop_does_not_ambush_a_much_later_run():
    st.trigger_abort(SID)
    st._pending_aborts[SID] = time.monotonic() - (st.PENDING_ABORT_TTL + 1)
    del st._abort_signals[SID]
    assert not st.register_run(SID).is_set()


def test_asking_for_new_work_retires_an_unclaimed_stop():
    st.trigger_abort(SID)
    del st._abort_signals[SID]
    st.discard_pending_abort(SID)
    assert not st.register_run(SID).is_set()


def test_a_stop_aimed_at_a_live_run_is_not_left_pending_for_the_next_one():
    # The run is live, so the stop lands on it directly and must not also be
    # remembered — the next run is different work and starts clean.
    st.register_run(SID)
    st.trigger_abort(SID)
    st.clear_abort(SID)
    assert not st.register_run(SID).is_set()


def test_one_session_stop_does_not_touch_another():
    st.trigger_abort(SID)
    assert not st.register_run("session_other").is_set()
