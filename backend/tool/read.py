"""Read tool: read files from the sandbox."""
from pydantic import BaseModel, Field

from core.log import create_logger
from tool.tool import ToolResult, ToolContext, define_tool

log = create_logger("tool.read")


class ReadArgs(BaseModel):
    file_path: str = Field(description="Absolute path to the file to read")
    offset: int = Field(default=0, description="Line offset to start reading from")
    limit: int = Field(default=2000, description="Maximum number of lines to read")


async def execute(args: ReadArgs, ctx: ToolContext) -> ToolResult:
    """Read a file from the sandbox with line numbers."""
    try:
        content = await ctx.sandbox.read_file(
            path=args.file_path,
            offset=args.offset,
            limit=args.limit,
        )

        # F1: Inject directory-level instruction files (AGENTS.md / CLAUDE.md)
        try:
            from session.instruction import instruction_resolve
            instructions = await instruction_resolve(args.file_path, ctx.message_id)
            if instructions:
                extra = "\n\n".join(
                    f"[Directory instructions from: {inst['filepath']}]\n{inst['content']}"
                    for inst in instructions
                )
                content = content + "\n\n" + extra
        except Exception as e:
            log.debug(f"Instruction resolve skipped: {e}")

        # F9: Record file mtime for stale edit detection
        try:
            from tool.filetime import get_tracker
            stat_result = await ctx.sandbox.execute(
                f"stat -c %Y {args.file_path} 2>/dev/null", timeout=5
            )
            if stat_result.exit_code == 0 and stat_result.stdout.strip():
                mtime = float(stat_result.stdout.strip())
                get_tracker(ctx.session_id).record(args.file_path, mtime)
        except Exception:
            pass  # Best-effort

        return ToolResult(
            title=args.file_path,
            output=content,
        )
    except Exception as e:
        return ToolResult(
            title=f"Error reading {args.file_path}",
            output=str(e),
        )


READ_DESCRIPTION = """\
Read a file or directory from the local filesystem. If the path does not exist, an error is returned.

Usage:
- The file_path parameter should be an absolute path.
- By default, this tool returns up to 2000 lines from the start of the file.
- The offset parameter is the line number to start from (0-indexed).
- To read later sections, call this tool again with a larger offset.
- Use the Grep tool to find specific content in large files or files with long lines.
- If you are unsure of the correct file path, use the Glob tool to look up filenames by glob pattern.
- Contents are returned with each line prefixed by its line number.
- Any line longer than 2000 characters is truncated.
- Call this tool in parallel when you know there are multiple files you want to read.
- Avoid tiny repeated slices (30 line chunks). If you need more context, read a larger window.
- This tool can read image files and PDFs and return them as file attachments."""

read_tool = define_tool(
    "read",
    description=READ_DESCRIPTION,
    parameters=ReadArgs,
    execute=execute,
)
