"""Command templates: predefined slash commands."""
import os
from dataclasses import dataclass
from pathlib import Path

from core.markdown import parse_frontmatter
from core.log import create_logger

log = create_logger("command")


@dataclass
class CommandInfo:
    name: str
    description: str
    agent: str
    content: str
    arguments: str = ""


# Cache
_commands: dict[str, CommandInfo] = {}
_loaded = False


async def load_commands() -> None:
    """Load all command templates."""
    global _commands, _loaded
    _commands.clear()

    # Scan command directories
    cwd = Path.cwd()
    for commands_dir in [
        cwd / ".openbox" / "commands",
        cwd / ".openagent" / "commands",
        cwd / ".claude" / "commands",
    ]:
        if not commands_dir.exists():
            continue

        for md_file in commands_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                metadata, body = parse_frontmatter(content)

                name = metadata.get("name", md_file.stem)
                cmd = CommandInfo(
                    name=name,
                    description=metadata.get("description", ""),
                    agent=metadata.get("agent", "build"),
                    content=body,
                    arguments=metadata.get("arguments", ""),
                )
                _commands[name] = cmd
            except Exception as e:
                log.warning(f"Failed to load command from {md_file}: {e}")

    _loaded = True
    log.info(f"Loaded {len(_commands)} commands")


async def get_command(name: str) -> CommandInfo | None:
    """Get a command by name."""
    if not _loaded:
        await load_commands()
    return _commands.get(name)


async def execute_command(name: str, arguments: str = "") -> str:
    """Get the resolved command text."""
    cmd = await get_command(name)
    if not cmd:
        return f"Command '{name}' not found."

    content = cmd.content
    content = content.replace("$ARGUMENTS", arguments)
    return content


async def list_commands() -> list[dict]:
    """List all available commands."""
    if not _loaded:
        await load_commands()
    return [
        {
            "name": c.name,
            "description": c.description,
            "arguments": c.arguments,
        }
        for c in _commands.values()
    ]
