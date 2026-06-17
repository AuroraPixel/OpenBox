"""Invalid tool handler for error recovery.

When the LLM calls a tool name that doesn't exist, tool name repair routes
the call here with the original tool name and error message in the args.
This gives the LLM feedback about the error so it can self-correct.
"""
from pydantic import BaseModel

from tool.tool import ToolResult, ToolContext, define_tool


class InvalidArgs(BaseModel):
    tool: str = ""
    error: str = ""


async def execute(args: dict, ctx: ToolContext) -> ToolResult:
    """Handle calls to non-existent tools."""
    tool_name = args.get("tool", "unknown")
    error = args.get("error", "")
    return ToolResult(
        title=f"Tool not found: {tool_name}",
        output=(
            f"Tool '{tool_name}' not found. "
            f"Error: {error}\n\n"
            "Please check the tool name and try again."
        ),
    )


invalid_tool = define_tool(
    "invalid",
    description="Error handler for invalid tool calls. Do not call directly.",
    parameters=InvalidArgs,
    execute=execute,
    sandbox_required=False,
)
