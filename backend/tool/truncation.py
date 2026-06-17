"""Output truncation for tool results.

Truncates tool output to MAX_LINES/MAX_BYTES, saves full output
to a temp file, and includes a hint for the LLM to access it.
Includes periodic cleanup of old truncated output files.
"""
import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path

from core.log import create_logger

log = create_logger("truncation")

MAX_LINES = 2000
MAX_BYTES = 50 * 1024  # 50KB
RETENTION_MS = 7 * 24 * 3600 * 1000  # 7 days in ms
CLEANUP_INTERVAL_S = 3600  # 1 hour

# Storage directory for truncated output files
_data_dir: str | None = None
_cleanup_task: asyncio.Task | None = None


def _get_data_dir() -> str:
    """Get or create the data directory for truncated output."""
    global _data_dir
    if _data_dir is None:
        data_home = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        _data_dir = os.path.join(data_home, "openbox", "tool-output")
        os.makedirs(_data_dir, exist_ok=True)
    return _data_dir


@dataclass
class TruncateResult:
    content: str
    truncated: bool = False
    output_path: str | None = None


async def truncate_output(
    text: str,
    max_lines: int = MAX_LINES,
    max_bytes: int = MAX_BYTES,
    direction: str = "head",
    has_task_tool: bool = False,
) -> TruncateResult:
    """Truncate tool output to stay within limits.

    If truncated, saves full output to a temp file and includes
    a hint for the LLM on how to access it.
    """
    if not text:
        return TruncateResult(content="", truncated=False)

    lines = text.split("\n")
    total_bytes = len(text.encode("utf-8"))

    # Check if within limits
    if len(lines) <= max_lines and total_bytes <= max_bytes:
        return TruncateResult(content=text, truncated=False)

    # Truncate
    out = []
    bytes_count = 0
    hit_bytes = False

    if direction == "head":
        for i, line in enumerate(lines):
            if i >= max_lines:
                break
            size = len(line.encode("utf-8")) + (1 if i > 0 else 0)
            if bytes_count + size > max_bytes:
                hit_bytes = True
                break
            out.append(line)
            bytes_count += size
    else:  # tail
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i]
            size = len(line.encode("utf-8")) + 1
            if bytes_count + size > max_bytes:
                hit_bytes = True
                break
            if len(out) >= max_lines:
                break
            out.insert(0, line)
            bytes_count += size

    # Save full output to temp file
    output_path = None
    try:
        from core.identifier import ascending
        data_dir = _get_data_dir()
        filename = ascending("tool")
        filepath = os.path.join(data_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)
        output_path = filepath
    except Exception as e:
        log.warning(f"Failed to save truncated output: {e}")

    # Build hint
    if has_task_tool:
        hint = (
            "Use the Task tool to have the explore agent process this file "
            "with Grep and Read to find the specific content you need."
        )
    else:
        hint = "Use Grep to search the full content or Read with offset/limit to see more."

    if output_path:
        hint = f"Full output saved to: {output_path}\n{hint}"

    removed = total_bytes - bytes_count if hit_bytes else len(lines) - len(out)
    unit = "bytes" if hit_bytes else "lines"
    preview = "\n".join(out)

    return TruncateResult(
        content=f"{preview}\n\n...{removed} {unit} truncated...\n\n{hint}",
        truncated=True,
        output_path=output_path,
    )


async def cleanup_old_outputs() -> int:
    """Delete truncated output files older than RETENTION_MS.

    Returns the number of files deleted.
    """
    data_dir = _get_data_dir()
    deleted = 0
    cutoff_ms = time.time() * 1000 - RETENTION_MS

    try:
        for filename in os.listdir(data_dir):
            filepath = os.path.join(data_dir, filename)
            if not os.path.isfile(filepath):
                continue
            try:
                mtime_ms = os.path.getmtime(filepath) * 1000
                if mtime_ms < cutoff_ms:
                    os.remove(filepath)
                    deleted += 1
            except OSError:
                continue
    except Exception as e:
        log.warning(f"Cleanup error: {e}")

    if deleted > 0:
        log.info(f"Cleaned up {deleted} old truncated output files")

    return deleted


async def _cleanup_loop():
    """Periodic cleanup loop, runs every CLEANUP_INTERVAL_S."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_S)
        try:
            await cleanup_old_outputs()
        except Exception as e:
            log.warning(f"Cleanup loop error: {e}")


def start_cleanup_task():
    """Start the periodic cleanup task."""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_loop())
        log.info("Started truncation cleanup task")


def stop_cleanup_task():
    """Stop the periodic cleanup task."""
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        _cleanup_task = None
