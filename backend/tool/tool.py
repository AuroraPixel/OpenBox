"""Tool base class and define_tool factory."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from pydantic import BaseModel

from core.log import create_logger

log = create_logger("tool")


class ToolResult(BaseModel):
    """Result returned by a tool execution."""
    title: str = ""
    output: str = ""
    metadata: dict[str, Any] = {}


@dataclass
class ToolContext:
    """Context passed to tool execution functions."""
    session_id: str = ""
    origin_session_id: str = ""  # Original session for cron jobs (cron tool uses this)
    user_id: str = ""
    project_id: str = ""
    sandbox: Any = None  # SandboxClient
    bus: Any = None
    abort: asyncio.Event = field(default_factory=asyncio.Event)
    message_id: str = ""
    part_id: str = ""  # The tool call's part ID
    workdir: str = "/workspace"  # Session-specific working directory
    _on_output: Any = None  # Callback: async fn(output: str) for incremental output updates

    async def update_output(self, output: str) -> None:
        """Push incremental output update (for real-time tool display)."""
        if self._on_output:
            await self._on_output(output)


@dataclass
class ToolInfo:
    """Definition of a tool."""
    id: str
    description: str
    parameters: type[BaseModel]
    execute: Callable[..., Awaitable[ToolResult]]
    # Metadata
    sandbox_required: bool = True  # Whether this tool needs sandbox access
    never_prune: bool = False  # Whether output should never be pruned


def define_tool(
    tool_id: str,
    *,
    description: str,
    parameters: type[BaseModel],
    execute: Callable[..., Awaitable[ToolResult]],
    sandbox_required: bool = True,
    never_prune: bool = False,
) -> ToolInfo:
    """Factory function to create a tool with automatic validation and truncation."""
    from tool.truncation import truncate_output

    async def wrapped_execute(args: dict, ctx: ToolContext) -> ToolResult:
        # Validate input
        try:
            validated = parameters.model_validate(args)
        except Exception as e:
            log.warning(f"Tool {tool_id} validation failed. Args received: {args!r}. Error: {e}")
            return ToolResult(
                title=f"Invalid input for {tool_id}",
                output=f"Parameter validation error: {e}",
            )

        # Execute
        result = await execute(validated, ctx)

        # Truncate output
        truncated = await truncate_output(result.output)
        return ToolResult(
            title=result.title,
            output=truncated.content,
            metadata={**result.metadata, "truncated": truncated.truncated},
        )

    return ToolInfo(
        id=tool_id,
        description=description,
        parameters=parameters,
        execute=wrapped_execute,
        sandbox_required=sandbox_required,
        never_prune=never_prune,
    )
