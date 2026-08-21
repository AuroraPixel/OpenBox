"""Session status tracking."""
import asyncio
from typing import Dict

from models.message import SessionStatus

# Active session abort signals
_abort_signals: Dict[str, asyncio.Event] = {}


def get_abort_signal(session_id: str) -> asyncio.Event:
    """Get or create an abort signal for a session."""
    if session_id not in _abort_signals:
        _abort_signals[session_id] = asyncio.Event()
    return _abort_signals[session_id]


def register_run(session_id: str) -> asyncio.Event:
    """A FRESH signal for a new run (opencode: one AbortController per run).

    The previous run may still be winding down holding its own — already
    set — event; reusing it would abort the new run instantly. Overwriting
    the slot means trigger_abort always reaches the newest run."""
    signal = asyncio.Event()
    _abort_signals[session_id] = signal
    return signal


def trigger_abort(session_id: str) -> None:
    """Trigger abort for a session.

    Creates the signal when absent: a stop pressed in the instant before the
    loop registers must still land, not silently no-op (the loop then sees an
    already-set event and exits its first check)."""
    get_abort_signal(session_id).set()


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
