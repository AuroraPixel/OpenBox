"""MultiEdit tool: apply multiple find-and-replace edits to a single file.

Reduces token waste when multiple locations in the same file need editing.
Reuses the 9-strategy progressive matching from edit.py.
"""
from pydantic import BaseModel, Field

from core.log import create_logger
from tool.edit import replace, _strip_line_numbers
from tool.tool import ToolResult, ToolContext, define_tool

log = create_logger("tool.multiedit")


class EditEntry(BaseModel):
    old_string: str = Field(description="The text to find")
    new_string: str = Field(description="The replacement text")


class MultiEditArgs(BaseModel):
    file_path: str = Field(description="Path to the file to edit")
    edits: list[EditEntry] = Field(description="List of edits to apply sequentially")


async def execute(args: MultiEditArgs, ctx: ToolContext) -> ToolResult:
    """Apply multiple edits to a single file sequentially."""
    if not args.edits:
        return ToolResult(title="MultiEdit: no edits", output="No edits provided")

    if len(args.edits) > 50:
        return ToolResult(title="MultiEdit: too many edits", output="Maximum 50 edits per call")

    # F9: Check for stale file
    stale_warning = ""
    try:
        from tool.filetime import get_tracker
        tracker = get_tracker(ctx.session_id)
        recorded_mtime = tracker.get(args.file_path)
        if recorded_mtime is not None:
            result = await ctx.sandbox.execute(
                f"stat -c %Y {args.file_path} 2>/dev/null", timeout=5
            )
            if result.exit_code == 0 and result.stdout.strip():
                current_mtime = float(result.stdout.strip())
                if current_mtime != recorded_mtime:
                    stale_warning = (
                        "WARNING: File modified since last read. "
                        "Edits applied but re-read to verify.\n"
                    )
    except Exception:
        pass

    # Read file from sandbox
    try:
        raw_content = await ctx.sandbox.read_file(args.file_path, offset=0, limit=100000)
        content = _strip_line_numbers(raw_content)
    except Exception as e:
        return ToolResult(title=f"Error reading {args.file_path}", output=str(e))

    # Apply edits sequentially
    results = []
    for i, edit in enumerate(args.edits):
        try:
            content = replace(content, edit.old_string, edit.new_string)
            results.append(f"Edit {i + 1}: OK")
        except ValueError as e:
            results.append(f"Edit {i + 1}: FAILED — {e}")
            return ToolResult(
                title=f"MultiEdit failed at edit {i + 1}",
                output=stale_warning + "\n".join(results),
            )

    # Write back to sandbox
    try:
        await ctx.sandbox.write_file(args.file_path, content)
    except Exception as e:
        return ToolResult(title=f"Error writing {args.file_path}", output=str(e))

    output = stale_warning + "\n".join(results)

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
        result = await ctx.sandbox.execute(
            f"stat -c %Y {args.file_path} 2>/dev/null", timeout=5
        )
        if result.exit_code == 0 and result.stdout.strip():
            get_tracker(ctx.session_id).record(args.file_path, float(result.stdout.strip()))
    except Exception:
        pass

    return ToolResult(
        title=f"MultiEdit {args.file_path} ({len(args.edits)} edits)",
        output=output,
    )


MULTIEDIT_DESCRIPTION = """\
Apply multiple find-and-replace edits to a single file in one operation.

This is more efficient than calling the edit tool multiple times when you need
to make several changes to the same file. Edits are applied sequentially.

Parameters:
- file_path: Path to the file to edit.
- edits: Array of {old_string, new_string} objects. Each edit replaces one occurrence.

Rules:
- You must Read the file before using this tool.
- Each old_string must be unique in the file at the time it is applied.
- Edits are applied in order — later edits see the result of earlier ones.
- If any edit fails, the operation stops and no partial result is written.
- Maximum 50 edits per call."""

multiedit_tool = define_tool(
    "multiedit",
    description=MULTIEDIT_DESCRIPTION,
    parameters=MultiEditArgs,
    execute=execute,
)
