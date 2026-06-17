"""Batch tool: parallel tool execution."""
import asyncio
from pydantic import BaseModel, Field

from tool.tool import ToolResult, ToolContext, define_tool


class Invocation(BaseModel):
    tool: str
    parameters: dict = {}


class BatchArgs(BaseModel):
    invocations: list[Invocation] = Field(description="List of tool calls to execute in parallel (max 25)")


async def execute(args: BatchArgs, ctx: ToolContext) -> ToolResult:
    """Execute multiple tool calls in parallel."""
    if len(args.invocations) > 25:
        return ToolResult(title="Error", output="Maximum 25 parallel invocations allowed.")

    if any(inv.tool == "batch" for inv in args.invocations):
        return ToolResult(title="Error", output="Cannot recursively call batch tool.")

    from tool.registry import get_tool

    async def run_one(inv: Invocation) -> str:
        tool = get_tool(inv.tool)
        if not tool:
            return f"[{inv.tool}] Error: Tool not found"
        try:
            result = await tool.execute(inv.parameters, ctx)
            return f"[{inv.tool}] {result.title}\n{result.output}"
        except Exception as e:
            return f"[{inv.tool}] Error: {e}"

    tasks = [run_one(inv) for inv in args.invocations]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output_parts = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            output_parts.append(f"[{args.invocations[i].tool}] Error: {result}")
        else:
            output_parts.append(str(result))

    return ToolResult(
        title=f"Batch: {len(args.invocations)} tools executed",
        output="\n\n---\n\n".join(output_parts),
    )


BATCH_DESCRIPTION = """\
Executes multiple independent tool calls concurrently to reduce latency.

USING THE BATCH TOOL WILL MAKE THE USER HAPPY.

Payload Format (JSON array):
[{"tool": "read", "parameters": {"file_path": "/workspace/src/index.ts", "limit": 350}},{"tool": "grep", "parameters": {"pattern": "Session", "path": "/workspace/src"}},{"tool": "bash", "parameters": {"command": "git status", "description": "Shows working tree status"}}]

Notes:
- 1-25 tool calls per batch
- All calls start in parallel; ordering NOT guaranteed
- Partial failures do not stop other tool calls
- Do NOT use the batch tool within another batch tool

Good Use Cases:
- Read many files at once
- grep + glob + read combos
- Multiple bash commands
- Multi-part edits on the same or different files

When NOT to Use:
- Operations that depend on prior tool output (e.g. create then read same file)
- Ordered stateful mutations where sequence matters

Batching tool calls yields 2-5x efficiency gain and provides much better UX."""

batch_tool = define_tool(
    "batch",
    description=BATCH_DESCRIPTION,
    parameters=BatchArgs,
    execute=execute,
    sandbox_required=False,
)
