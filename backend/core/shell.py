"""Shell integration utilities."""
import os
import signal
from core.log import create_logger

log = create_logger("shell")


def preferred_shell() -> str:
    """Get the preferred shell, avoiding incompatible ones."""
    shell = os.environ.get("SHELL", "/bin/bash")
    basename = os.path.basename(shell)

    # Avoid incompatible shells
    if basename in ("fish", "nu", "nushell"):
        return "/bin/bash"

    return shell


async def kill_tree(pid: int, timeout: float = 5.0) -> None:
    """Kill a process and all its children."""
    import asyncio

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    await asyncio.sleep(timeout)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
