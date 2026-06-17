"""Grep tool: file content search in the sandbox."""
from pydantic import BaseModel, Field

from tool.tool import ToolResult, ToolContext, define_tool


class GrepArgs(BaseModel):
    pattern: str = Field(description="Regex pattern to search for")
    path: str = Field(default="/workspace", description="File or directory to search in")
    type: str | None = Field(default=None, description="File type filter (e.g. 'py', 'js')")


async def execute(args: GrepArgs, ctx: ToolContext) -> ToolResult:
    """Search file contents using grep."""
    # Use session workdir as default search path
    search_path = args.path if args.path != "/workspace" else ctx.workdir
    output = await ctx.sandbox.grep(
        pattern=args.pattern,
        path=search_path,
        file_type=args.type,
    )

    if not output.strip():
        return ToolResult(
            title=f"No matches for '{args.pattern}'",
            output="No matches found.",
        )

    return ToolResult(
        title=f"grep: {args.pattern}",
        output=output,
    )


GREP_DESCRIPTION = """\
Fast content search tool that works with any codebase size.

- Searches file contents using regular expressions
- Supports full regex syntax (e.g. "log.*Error", "function\\s+\\w+", etc.)
- Filter files by type with the type parameter (e.g. "py", "js")
- Returns file paths and line numbers with at least one match sorted by modification time
- Use this tool when you need to find files containing specific patterns
- If you need to identify/count the number of matches within files, use the Bash tool with `rg` (ripgrep) directly
- When you are doing an open-ended search that may require multiple rounds of globbing and grepping, use the Task tool instead"""

grep_tool = define_tool(
    "grep",
    description=GREP_DESCRIPTION,
    parameters=GrepArgs,
    execute=execute,
)
