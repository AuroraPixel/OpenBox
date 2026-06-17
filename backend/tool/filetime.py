"""FileTime tracking: detect stale edits by recording file modification times.

When the Read tool reads a file, it records the file's mtime.
When Edit/Write tools modify a file, they check whether the mtime has changed
since the last read — indicating the file was modified externally.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FileTimeTracker:
    """Per-session tracker for file read timestamps."""
    _mtimes: dict[str, float] = field(default_factory=dict)

    def record(self, file_path: str, mtime: float) -> None:
        """Record the last-known mtime for a file."""
        self._mtimes[file_path] = mtime

    def get(self, file_path: str) -> Optional[float]:
        """Get the recorded mtime for a file, or None if not tracked."""
        return self._mtimes.get(file_path)

    def clear(self, file_path: str) -> None:
        """Remove tracking for a file."""
        self._mtimes.pop(file_path, None)


# Per-session tracker instances
_trackers: dict[str, FileTimeTracker] = {}


def get_tracker(session_id: str) -> FileTimeTracker:
    """Get or create a FileTimeTracker for a session."""
    if session_id not in _trackers:
        _trackers[session_id] = FileTimeTracker()
    return _trackers[session_id]


def remove_tracker(session_id: str) -> None:
    """Remove tracker when session ends."""
    _trackers.pop(session_id, None)
