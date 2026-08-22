"""Task tool: spawn sub-agent sessions."""
from pydantic import BaseModel, Field

from core.log import create_logger
from tool.tool import ToolResult, ToolContext, define_tool

log = create_logger("tool.task")


class TaskArgs(BaseModel):
    description: str = Field(description="Short description of the task")
    prompt: str = Field(description="Detailed prompt for the sub-agent")
    subagent_type: str = Field(default="explore", description="Agent type: explore, general")


async def execute(args: TaskArgs, ctx: ToolContext) -> ToolResult:
    """Spawn a sub-agent to handle a task."""
    from session import session as session_mod
    from agent.agent import get_agent, list_subagents

    # Resolve model: agent override > parent session's model (matching opencode)
    agent_def = get_agent(args.subagent_type)
    # A primary agent is not spawnable. build and plan carry the whole
    # conversational contract — plan mode's review handshake, build's
    # todo bookkeeping — none of which means anything in a child session
    # that answers one prompt and exits. opencode draws the same line.
    if agent_def.mode == "primary":
        raise ValueError(
            f"'{args.subagent_type}' is not a subagent. Available: "
            + ", ".join(sorted(a.name for a in list_subagents()))
        )
    parent_session = await session_mod.get_session(ctx.session_id, user_id=ctx.user_id or "default")
    child_model = agent_def.model or (parent_session.model if parent_session else "")

    # Create a child session linked to parent (won't appear in sidebar)
    child = await session_mod.create_session(
        agent=args.subagent_type,
        title=f"{args.description} (@{args.subagent_type} subagent)",
        parent_id=ctx.session_id,
        model=child_model,
        user_id=ctx.user_id or "default",
    )

    # Share parent's sandbox with the child session so tools can access it
    from sandbox import sandbox_manager
    parent_project = sandbox_manager._session_project.get(ctx.session_id)
    if parent_project:
        sandbox_info = sandbox_manager._project_map.get(parent_project)
        if sandbox_info:
            sandbox_info.session_ids.add(child.id)
            sandbox_manager._session_project[child.id] = parent_project

    # Send the prompt
    await session_mod.create_user_message(
        session_id=child.id,
        text=args.prompt,
        agent=args.subagent_type,
        user_id=ctx.user_id or "default",
    )

    # Point this tool call at its child BEFORE the child runs. The UI follows
    # the child's own parts to show what the subagent is doing; without the
    # pointer it has nothing to follow, and the pointer is useless if it only
    # arrives with the result — by then there is nothing left to watch. This
    # is why the parent's row read "task · running" and nothing else.
    await _announce_child(ctx, child.id, args.subagent_type)

    # Run the agent loop, and let the parent's stop reach it. The child has
    # its own abort signal, so aborting the parent alone left the subagent
    # running to completion after the user had already stopped the run.
    from agent.loop import run_loop
    await _run_child(ctx, child.id)

    # Collect output: only the LAST text part (matching opencode's findLast)
    messages = await session_mod.get_messages(child.id)
    text = ""
    for msg in reversed(messages):
        role = msg.role if isinstance(msg.role, str) else msg.role.value
        if role == "assistant":
            parts = msg.parts if isinstance(msg.parts, list) else []
            for part in reversed(parts):
                p = part if isinstance(part, dict) else (part.model_dump() if hasattr(part, "model_dump") else {})
                if isinstance(p, dict) and p.get("type") == "text":
                    text = p.get("text", "")
                    break
            if text:
                break

    # Wrap output in <task_result> tags (matching opencode format)
    output = "\n".join([
        f"task_id: {child.id}",
        "",
        "<task_result>",
        text,
        "</task_result>",
    ]) if text else "Task completed with no text output."

    return ToolResult(
        title=args.description,
        output=output,
        # Carried on the finished part too, so a reloaded conversation can
        # still link the row to the child session it spawned.
        metadata={"child_session_id": child.id, "subagent_type": args.subagent_type},
    )


async def _announce_child(ctx: ToolContext, child_id: str, subagent_type: str) -> None:
    """Record the child session on this tool part, while it still matters."""
    from session.session import get_messages, update_part_data

    if not ctx.part_id:
        return
    try:
        messages = await get_messages(ctx.session_id, user_id=ctx.user_id or "default")
        for msg in reversed(messages):
            for part in reversed(msg.parts or []):
                p = part if isinstance(part, dict) else (
                    part.model_dump() if hasattr(part, "model_dump") else {}
                )
                if isinstance(p, dict) and p.get("id") == ctx.part_id:
                    meta = dict(p.get("metadata") or {})
                    meta.update({"child_session_id": child_id, "subagent_type": subagent_type})
                    p["metadata"] = meta
                    await update_part_data(
                        ctx.part_id, p, publish=True, user_id=ctx.user_id or "default"
                    )
                    return
    except Exception as e:  # never fail the task over a progress pointer
        log.debug(f"could not announce child session {child_id}: {e}")


async def _run_child(ctx: ToolContext, child_id: str) -> None:
    """Run the subagent, forwarding the parent's stop to it."""
    import asyncio

    from agent.loop import run_loop
    from session.status import trigger_abort

    user_id = ctx.user_id or "default"
    child = asyncio.create_task(run_loop(child_id, user_id=user_id))
    if ctx.abort is None:
        await child
        return

    watch = asyncio.create_task(ctx.abort.wait())
    done, _ = await asyncio.wait({child, watch}, return_when=asyncio.FIRST_COMPLETED)
    watch.cancel()
    if child in done:
        await child
        return
    # The parent was stopped. Signal the child and give it a moment to wind
    # down on its own before abandoning the wait.
    trigger_abort(child_id)
    try:
        await asyncio.wait_for(child, timeout=10)
    except (asyncio.TimeoutError, TimeoutError):
        child.cancel()


TASK_DESCRIPTION = """\
Launch a new agent to handle complex, multistep tasks autonomously.

Available agent types:
- explore: Fast agent for exploring codebases. Use for finding files by patterns, \
searching code for keywords, or answering questions about the codebase. Specify \
thoroughness: "quick", "medium", or "very thorough".
- general: General-purpose agent for researching complex questions and executing \
multi-step tasks. Use to execute multiple units of work in parallel.

When using the Task tool, you must specify a subagent_type parameter to select which \
agent type to use.

When to use the Task tool:
- When exploring the codebase to gather context or answer a non-trivial question
- For multi-step research that requires reading many files
- To execute independent work in parallel (launch multiple agents at once)
- When you are instructed to execute custom slash commands. Use the Task tool with \
the slash command invocation as the entire prompt. The slash command can take arguments. \
For example: Task(description="Check the file", prompt="/check-file path/to/file.py")

When NOT to use the Task tool:
- If you want to read a specific file path, use Read or Glob instead
- If you are searching for a specific class definition like "class Foo", use Glob instead
- If you are searching for code within a specific file or set of 2-3 files, use Read instead
- Other tasks that are not related to the agent descriptions above

Usage notes:
1. Launch multiple agents concurrently whenever possible, to maximize performance; \
to do that, use a single message with multiple tool uses
2. When the agent is done, it will return a single message back to you. The result \
returned by the agent is not visible to the user. To show the user the result, you \
should send a text message back to the user with a concise summary of the result.
3. Each invocation starts with a fresh context. Your prompt should contain a highly \
detailed task description for the agent to perform autonomously and you should specify \
exactly what information the agent should return back to you in its final and only \
message to you.
4. The agent's outputs should generally be trusted.
5. Clearly tell the agent whether you expect it to write code or just to do research \
(search, file reads, web fetches, etc.), since it is not aware of the user's intent. \
Tell it how to verify its work if possible (e.g., relevant test commands).
6. If the agent description mentions that it should be used proactively, then you should \
try your best to use it without the user having to ask for it first. Use your judgement.

Example usage (NOTE: The agents below are fictional examples for illustration only — \
use the actual agents listed above):

<example_agent_descriptions>
"code-reviewer": use this agent after you are done writing a significant piece of code
"greeting-responder": use this agent to respond to user greetings with a friendly joke
</example_agent_descriptions>

<example>
user: "Please write a function that checks if a number is prime"
assistant: Sure let me write a function that checks if a number is prime
assistant: First let me use the Write tool to write a function that checks if a number is prime
assistant: I'm going to use the Write tool to write the following code:
<code>
function isPrime(n) {
  if (n <= 1) return false
  for (let i = 2; i * i <= n; i++) {
    if (n % i === 0) return false
  }
  return true
}
</code>
<commentary>
Since a significant piece of code was written and the task was completed, now use the \
code-reviewer agent to review the code
</commentary>
assistant: Now let me use the code-reviewer agent to review the code
assistant: Uses the Task tool to launch the code-reviewer agent
</example>

<example>
user: "Hello"
<commentary>
Since the user is greeting, use the greeting-responder agent to respond with a friendly joke
</commentary>
assistant: "I'm going to use the Task tool to launch the greeting-responder agent"
</example>"""

task_tool = define_tool(
    "task",
    description=TASK_DESCRIPTION,
    parameters=TaskArgs,
    execute=execute,
    sandbox_required=False,
)
