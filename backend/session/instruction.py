"""Instruction files: long-term memory via AGENTS.md / CLAUDE.md / CONTEXT.md.

Loads instruction files from project and global directories.
These are injected into every LLM call as part of the system prompt,
providing persistent project-level context across sessions.
"""
import os
from pathlib import Path

import aiofiles

from core.log import create_logger

log = create_logger("instruction")

INSTRUCTION_FILES = ["AGENTS.md", "CLAUDE.md", "CONTEXT.md"]

# Track which instruction files have been loaded for which message
_claims: dict[str, set[str]] = {}  # message_id -> set of loaded file paths


async def instruction_system() -> list[str]:
    """Load all system-level instruction files.

    Discovery order:
    1. Project-level: from cwd upward, first match wins among AGENTS.md/CLAUDE.md/CONTEXT.md
    2. Global-level: ~/.config/openbox/AGENTS.md (or ~/.config/openagent/) or ~/.claude/CLAUDE.md
    3. config.instructions[] paths and URLs

    Returns a list of instruction content strings.
    """
    paths: set[str] = set()
    results: list[str] = []

    # 1. Project-level: walk up from cwd to find instruction files
    cwd = Path.cwd()
    project_root = _find_project_root(cwd)

    for filename in INSTRUCTION_FILES:
        found = _find_up(filename, cwd, project_root)
        if found:
            paths.update(found)
            break  # First matching filename wins

    # 2. Global-level
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    global_candidates = [
        os.path.join(config_home, "openbox", "AGENTS.md"),
        os.path.join(config_home, "openagent", "AGENTS.md"),
        os.path.expanduser("~/.claude/CLAUDE.md"),
    ]
    for p in global_candidates:
        if os.path.isfile(p) and p not in paths:
            paths.add(p)
            break  # First found global wins

    # 3. config.instructions[]
    try:
        from core.config import get_config
        import asyncio
        config = asyncio.get_event_loop().run_until_complete(get_config()) if not asyncio.get_event_loop().is_running() else None
        if config is None:
            # We're in an async context, try differently
            pass
    except Exception:
        config = None

    if config:
        for instruction in config.instructions:
            if instruction.startswith("http://") or instruction.startswith("https://"):
                content = await _fetch_url(instruction)
                if content:
                    results.append(f"Instructions from: {instruction}\n{content}")
                continue

            # Local path: support ~/ expansion and glob
            expanded = os.path.expanduser(instruction)
            if "*" in expanded or "?" in expanded:
                import glob
                for match in glob.glob(expanded, recursive=True):
                    if os.path.isfile(match):
                        paths.add(match)
            elif os.path.isfile(expanded):
                paths.add(expanded)

    # Read all collected files
    for p in sorted(paths):
        content = await _read_file(p)
        if content:
            results.append(f"Instructions from: {p}\n{content}")

    return results


async def instruction_system_with_config(config) -> list[str]:
    """Load instruction files using a pre-loaded config object."""
    paths: set[str] = set()
    results: list[str] = []

    cwd = Path.cwd()
    project_root = _find_project_root(cwd)

    for filename in INSTRUCTION_FILES:
        found = _find_up(filename, cwd, project_root)
        if found:
            paths.update(found)
            break

    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    global_candidates = [
        os.path.join(config_home, "openbox", "AGENTS.md"),
        os.path.join(config_home, "openagent", "AGENTS.md"),
        os.path.expanduser("~/.claude/CLAUDE.md"),
    ]
    for p in global_candidates:
        if os.path.isfile(p) and p not in paths:
            paths.add(p)
            break

    if config and config.instructions:
        for instruction in config.instructions:
            if instruction.startswith("http://") or instruction.startswith("https://"):
                content = await _fetch_url(instruction)
                if content:
                    results.append(f"Instructions from: {instruction}\n{content}")
                continue

            expanded = os.path.expanduser(instruction)
            if "*" in expanded or "?" in expanded:
                import glob
                for match in glob.glob(expanded, recursive=True):
                    if os.path.isfile(match):
                        paths.add(match)
            elif os.path.isfile(expanded):
                paths.add(expanded)

    for p in sorted(paths):
        content = await _read_file(p)
        if content:
            results.append(f"Instructions from: {p}\n{content}")

    return results


async def instruction_resolve(filepath: str, message_id: str) -> list[dict]:
    """Find directory-level instruction files for a given filepath.

    Called when the Read tool reads a file. Discovers instruction files
    between the file's directory and the project root, excluding
    already-loaded ones.

    Returns list of {"filepath": ..., "content": ...} dicts.
    """
    system_paths = await _get_system_paths()
    already_loaded = _get_loaded(message_id)

    results = []
    current = os.path.dirname(os.path.abspath(filepath))
    root = str(_find_project_root(Path.cwd()))

    while current.startswith(root) and current != os.path.dirname(root):
        for filename in INSTRUCTION_FILES:
            candidate = os.path.join(current, filename)
            if (os.path.isfile(candidate)
                    and candidate not in system_paths
                    and candidate not in already_loaded):
                _claim(message_id, candidate)
                content = await _read_file(candidate)
                if content:
                    results.append({
                        "filepath": candidate,
                        "content": f"Instructions from: {candidate}\n{content}",
                    })

        if current == root:
            break
        current = os.path.dirname(current)

    return results


def clear_claims(message_id: str) -> None:
    """Clear instruction file claims for a message."""
    _claims.pop(message_id, None)


def clear_all_claims() -> None:
    """Clear all instruction file claims (call on session end)."""
    _claims.clear()


# ─── Private helpers ───

def _find_project_root(start: Path) -> Path:
    """Find the project root (git root or cwd)."""
    current = start
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return start


def _find_up(filename: str, start: Path, root: Path) -> list[str]:
    """Search for a file from start directory up to root."""
    results = []
    current = start
    while True:
        candidate = current / filename
        if candidate.is_file():
            results.append(str(candidate))
        if current == root or current == current.parent:
            break
        current = current.parent
    return results


async def _read_file(path: str) -> str | None:
    """Read a file asynchronously."""
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            return await f.read()
    except Exception as e:
        log.warning(f"Failed to read instruction file {path}: {e}")
        return None


async def _fetch_url(url: str) -> str | None:
    """Fetch content from a URL with timeout."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        log.warning(f"Failed to fetch instruction URL {url}: {e}")
        return None


async def _get_system_paths() -> set[str]:
    """Get paths of system-level instruction files."""
    paths: set[str] = set()
    cwd = Path.cwd()
    root = _find_project_root(cwd)

    for filename in INSTRUCTION_FILES:
        found = _find_up(filename, cwd, root)
        if found:
            paths.update(found)
            break

    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    for p in [
        os.path.join(config_home, "openbox", "AGENTS.md"),
        os.path.join(config_home, "openagent", "AGENTS.md"),
        os.path.expanduser("~/.claude/CLAUDE.md"),
    ]:
        if os.path.isfile(p):
            paths.add(p)
            break

    return paths


def _get_loaded(message_id: str) -> set[str]:
    """Get already-loaded instruction files for a message."""
    return _claims.get(message_id, set())


def _claim(message_id: str, path: str) -> None:
    """Mark an instruction file as loaded for a message."""
    if message_id not in _claims:
        _claims[message_id] = set()
    _claims[message_id].add(path)
