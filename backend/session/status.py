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


def trigger_abort(session_id: str) -> None:
    """Trigger abort for a session."""
    signal = _abort_signals.get(session_id)
    if signal:
        signal.set()


def clear_abort(session_id: str) -> None:
    """Clear abort signal for a session."""
    signal = _abort_signals.pop(session_id, None)
    if signal:
        signal.clear()


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
