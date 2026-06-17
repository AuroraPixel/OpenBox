"""Write tool: write files to the sandbox."""
from pydantic import BaseModel, Field

from tool.tool import ToolResult, ToolContext, define_tool


class WriteArgs(BaseModel):
    file_path: str = Field(description="Absolute path to write the file")
    content: str = Field(description="Content to write")


async def execute(args: WriteArgs, ctx: ToolContext) -> ToolResult:
    """Write content to a file in the sandbox."""
    # F9: Check for stale file
    stale_warning = ""
    try:
        from tool.filetime import get_tracker
        tracker = get_tracker(ctx.session_id)
        recorded_mtime = tracker.get(args.file_path)
        if recorded_mtime is not None:
            stat_result = await ctx.sandbox.execute(
                f"stat -c %Y {args.file_path} 2>/dev/null", timeout=5
            )
            if stat_result.exit_code == 0 and stat_result.stdout.strip():
                current_mtime = float(stat_result.stdout.strip())
                if current_mtime != recorded_mtime:
                    stale_warning = (
                        "WARNING: File has been modified since last read. "
                        "The file was overwritten. Re-read to verify.\n"
                    )
    except Exception:
        pass

    try:
        await ctx.sandbox.write_file(path=args.file_path, content=args.content)
    except Exception as e:
        return ToolResult(
            title=f"Error writing {args.file_path}",
            output=str(e),
        )

    output = f"{stale_warning}File written successfully ({len(args.content)} bytes)"

    # F6: Auto-format (best-effort)
    try:
        from core.config import get_config
        if getattr(get_config(), "auto_format", True):
            from lsp.format import auto_format
            formatter = await auto_format(ctx.sandbox, args.file_path)
            if formatter:
                output += f"\n(auto-formatted with {formatter})"
    except Exception:
        pass

    # F5: LSP diagnostics (best-effort)
    try:
        from core.config import get_config
        if getattr(get_config(), "lsp_diagnostics", True):
            from lsp.diagnostics import run_diagnostics, format_diagnostics
            diags = await run_diagnostics(ctx.sandbox, args.file_path)
            diag_str = format_diagnostics(diags)
            if diag_str:
                output += diag_str
    except Exception:
        pass

    # F9: Update mtime after write
    try:
        from tool.filetime import get_tracker
        stat_result = await ctx.sandbox.execute(
            f"stat -c %Y {args.file_path} 2>/dev/null", timeout=5
        )
        if stat_result.exit_code == 0 and stat_result.stdout.strip():
            get_tracker(ctx.session_id).record(args.file_path, float(stat_result.stdout.strip()))
    except Exception:
        pass

    return ToolResult(
        title=f"Wrote {args.file_path}",
        output=output,
    )


WRITE_DESCRIPTION = """\
Writes a file to the local filesystem.

Usage:
- This tool will overwrite the existing file if there is one at the provided path.
- If this is an existing file, you MUST use the Read tool first to read the file's contents. This tool will fail if you did not read the file first.
- ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
- NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the user.
- Only use emojis if the user explicitly requests it. Avoid writing emojis to files unless asked."""

write_tool = define_tool(
    "write",
    description=WRITE_DESCRIPTION,
    parameters=WriteArgs,
    execute=execute,
)
