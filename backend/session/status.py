"""Session status tracking."""
import asyncio
import time
from typing import Dict

from models.message import SessionStatus

# Active session abort signals
_abort_signals: Dict[str, asyncio.Event] = {}

#: Stops that arrived while no run held a signal, by session -> monotonic time.
#: A prompt is accepted and answered "202" long before the loop actually starts,
#: so there is a real window in which the user can see a stop button, press it,
#: and have no run to receive it. Remembering it here lets the run that starts
#: moments later honour the stop instead of ignoring it.
_pending_aborts: Dict[str, float] = {}

#: How long a stop with no run keeps looking for one. Long enough to cover the
#: gap (a prompt takes well under a second to reach the loop), short enough
#: that a stop pressed on an idle session cannot ambush an unrelated run
#: started minutes later.
PENDING_ABORT_TTL = 30.0


def get_abort_signal(session_id: str) -> asyncio.Event:
    """Get or create an abort signal for a session."""
    if session_id not in _abort_signals:
        _abort_signals[session_id] = asyncio.Event()
    return _abort_signals[session_id]


def register_run(session_id: str) -> asyncio.Event:
    """The signal for a new run (opencode: one AbortController per run).

    Normally fresh: the previous run may still be winding down holding its
    own — already set — event, and reusing that would abort the new run
    instantly. Owning the slot means trigger_abort always reaches the newest
    run.

    The exception is a stop that arrived with no run to receive it. The old
    code overwrote the slot unconditionally, which threw that stop away and
    left the run going while the UI reported it stopped — the "sometimes the
    stop button does nothing" report. Such a stop is consumed once, here.
    """
    signal = asyncio.Event()
    requested = _pending_aborts.pop(session_id, None)
    if requested is not None and (time.monotonic() - requested) <= PENDING_ABORT_TTL:
        signal.set()
    _abort_signals[session_id] = signal
    return signal


def trigger_abort(session_id: str) -> None:
    """Trigger abort for a session.

    With a run registered this simply sets its signal. With none, the stop is
    also remembered for the run that is about to start — see register_run.
    """
    if session_id not in _abort_signals:
        _pending_aborts[session_id] = time.monotonic()
    get_abort_signal(session_id).set()


def discard_pending_abort(session_id: str) -> None:
    """Forget a stop that was never claimed by a run.

    Called when the user asks for new work: whatever they meant to stop is
    over, and an unclaimed stop must not carry into what they just asked for.
    """
    _pending_aborts.pop(session_id, None)


def clear_abort(session_id: str, signal: asyncio.Event | None = None) -> None:
    """Clear a session's abort slot.

    When the finishing run passes its own signal, the slot is only removed if
    it still belongs to that run — a newer run's fresh signal must survive
    the old run's cleanup."""
    current = _abort_signals.get(session_id)
    if current is None:
        return
    if signal is not None and current is not signal:
        return
    _abort_signals.pop(session_id, None)
    current.clear()


def abort_all() -> int:
    """Set abort signals for all tracked sessions.

    Returns the number of sessions signalled.
    """
    count = 0
    for session_id, signal in _abort_signals.items():
        if not signal.is_set():
            signal.set()
            count += 1
    return count


def active_session_ids() -> list[str]:
    """Return IDs of all sessions with active (un-cleared) abort signals."""
    return list(_abort_signals.keys())
