"""Bash tool: execute shell commands in the sandbox with real-time output streaming."""
import re

from pydantic import BaseModel, Field

from core.log import create_logger
from sandbox.client import IdleNotification
from tool.tool import ToolResult, ToolContext, define_tool

log = create_logger("tool.bash")


class BashArgs(BaseModel):
    command: str = Field(description="The command to execute")
    timeout: int = Field(default=120, description="Optional timeout in seconds. Default 120s (2 minutes). Max 600s (10 minutes).")
    description: str = Field(default="", description="Description of what this command does")


MAX_STREAM_OUTPUT = 100_000  # Max characters to stream (prevent memory overflow)
IDLE_TIMEOUT = 60   # Seconds without output before triggering idle check
MAX_IDLE_JUDGES = 5  # Max LLM judgment calls before force kill (~5 min total idle)
MAX_TIMEOUT = 600   # Absolute safety cap sent to action server (10 min)

# Protected command patterns — prevent agents from killing the action_server
# (the only communication channel between backend and container).
_PROTECTED_CMD_PATTERNS: list[tuple[str, str]] = [
    (r'\bkill\b[^|;]*\s+(-\w+\s+)*1\b',
     "Blocked: cannot kill PID 1 (container init process)"),
    (r'\bkill\b[^|;]*\s+-1\b',
     "Blocked: cannot send signals to all processes"),
    (r'\b(pkill|killall)\b[^|;]*\b(python[23]?|uvicorn|action_server)\b',
     "Blocked: killing python/uvicorn/action_server would destroy the sandbox execution interface"),
    (r'\bfuser\b[^|;]*-k[^|;]*\b8000\b',
     "Blocked: cannot kill processes on port 8000 (sandbox communication port)"),
    (r'\bfuser\b[^|;]*\b8000\b[^|;]*-k',
     "Blocked: cannot kill processes on port 8000 (sandbox communication port)"),
    (r'\blsof\b[^|]*\b8000\b.*\|\s*(xargs\s+)?kill',
     "Blocked: cannot kill processes on port 8000 (sandbox communication port)"),
    (r'\b(rm|mv)\b[^|;]*/opt/action_server',
     "Blocked: cannot modify /opt/action_server (sandbox execution interface)"),
    (r'\b(shutdown|poweroff|halt)\b',
     "Blocked: cannot shut down the container"),
]


def _check_protected_command(command: str) -> str | None:
    """Return error message if command would damage sandbox communication, None if safe."""
    for pattern, msg in _PROTECTED_CMD_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return msg
    return None


async def _judge_idle_command(
    command: str,
    recent_output: str,
    idle_seconds: int,
    total_seconds: int,
) -> str:
    """Ask LLM whether an idle command should be killed or kept waiting.

    Returns: "kill", "wait", or "success".
    """
    import litellm
    from agent.llm import _get_provider_kwargs
    from core.config import get_config

    config = get_config()
    model_id = config.model
    provider_kwargs = _get_provider_kwargs(model_id)

    prompt = f"""A shell command has been running with no output for {idle_seconds} seconds (total runtime: {total_seconds}s).

Command: {command}

Last output (tail):
{recent_output[-1000:] if recent_output else "(no output)"}

Classify this situation. Reply with ONLY one word:
- "wait" — command is likely still working (compiling, installing, downloading), just slow
- "kill" — command appears stuck, hung, or is in a state that won't progress
- "success" — command is a long-running server/service that has already started successfully

Reply with one word only: wait, kill, or success"""

    log.info(f"[LLM Judge] Calling model={model_id} for command='{command[:60]}' idle={idle_seconds}s total={total_seconds}s")

    try:
        response = await litellm.acompletion(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.0,
            **provider_kwargs,
        )
        raw_answer = response.choices[0].message.content.strip()
        answer = re.sub(r"<think>[\s\S]*?</think>\s*", "", raw_answer).strip().lower()
        log.info(f"[LLM Judge] Raw response: '{raw_answer}' → parsed: '{answer}'")
        if answer in ("kill", "wait", "success"):
            return answer
        log.warning(f"[LLM Judge] Unrecognized response '{answer}', defaulting to kill")
        return "kill"
    except Exception as e:
        log.warning(f"[LLM Judge] LLM call failed: {e}")
        return "kill"


async def execute(args: BashArgs, ctx: ToolContext) -> ToolResult:
    """Execute a shell command in the sandbox with real-time output streaming."""
    blocked = _check_protected_command(args.command)
    if blocked:
        return ToolResult(
            title="command blocked",
            output=blocked,
            metadata={"exit_code": 1, "blocked": True},
        )
    timeout = min(args.timeout, MAX_TIMEOUT)

    # The action server gets MAX_TIMEOUT as the hard safety cap.
    # Actual timeout decisions are made by the idle detection + LLM judgment system.
    # Timeline: idle check at IDLE_TIMEOUT intervals → LLM decides wait/kill/success
    #           MAX_TIMEOUT is only the absolute backstop.
    try:
        collected_output = ""
        exit_code = 0
        idle_judge_count = 0

        async for chunk in ctx.sandbox.execute_stream(
            command=args.command,
            timeout=MAX_TIMEOUT,
            idle_timeout=IDLE_TIMEOUT,
            workdir=ctx.workdir,
        ):
            if isinstance(chunk, IdleNotification):
                idle_judge_count += 1

                if idle_judge_count > MAX_IDLE_JUDGES:
                    # Too many idle checks — force kill
                    log.info(f"Force killing idle process (pid={chunk.pid}): {args.command[:80]}")
                    await ctx.sandbox.kill_command(chunk.pid)
                    collected_output += f"\n[Process killed: idle too long ({chunk.idle_seconds}s no output)]\n"
                    await ctx.update_output(collected_output)
                    continue

                # Ask LLM to judge
                log.info(f"Idle detected ({chunk.idle_seconds}s), asking LLM to judge: {args.command[:80]}")
                decision = await _judge_idle_command(
                    command=args.command,
                    recent_output=collected_output[-2000:],
                    idle_seconds=chunk.idle_seconds,
                    total_seconds=chunk.total_seconds,
                )
                log.info(f"LLM idle judgment: {decision}")

                if decision in ("kill", "success"):
                    await ctx.sandbox.kill_command(chunk.pid)
                    suffix = "completed successfully" if decision == "success" else "killed (idle)"
                    collected_output += f"\n[Process {suffix} after {chunk.total_seconds}s]\n"
                    await ctx.update_output(collected_output)
                else:
                    # decision == "wait" — continue waiting, show status
                    await ctx.update_output(
                        collected_output + f"\n[Waiting... no output for {chunk.idle_seconds}s]\n"
                    )

            elif isinstance(chunk, int):
                exit_code = chunk
            else:
                # OutputChunk with type and content
                collected_output += chunk.content
                idle_judge_count = 0  # Reset on new output
                # Push incremental update to frontend
                if len(collected_output) <= MAX_STREAM_OUTPUT:
                    await ctx.update_output(collected_output)

        output = collected_output
        if len(output) > MAX_STREAM_OUTPUT:
            output = output[:MAX_STREAM_OUTPUT] + "\n... (output truncated)"

        return ToolResult(
            title=f"exit code: {exit_code}",
            output=output,
            metadata={"exit_code": exit_code},
        )

    except Exception:
        # Fallback to non-streaming execution if streaming fails
        result = await ctx.sandbox.execute(
            command=args.command,
            timeout=timeout,
            workdir=ctx.workdir,
        )

        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"

        return ToolResult(
            title=f"exit code: {result.exit_code}",
            output=output,
            metadata={"exit_code": result.exit_code},
        )


BASH_DESCRIPTION = """\
Execute a bash command in the sandbox with real-time output streaming.

IMPORTANT: This tool is for terminal operations like git, npm, docker, etc. \
DO NOT use it for file operations (reading, writing, editing, searching, finding files) — use the specialized tools instead.

Before executing the command, please follow these steps:

1. Directory Verification:
   - If the command will create new directories or files, first use `ls` to verify the parent directory exists and is the correct location

2. Command Execution:
   - Always quote file paths that contain spaces with double quotes
   - You can specify an optional timeout in seconds. Default 120s (2 minutes), max 600s (10 minutes).
   - Write a clear, concise description of what this command does in 5-10 words.
   - If the output exceeds the maximum, it will be truncated. Use Read with offset/limit or Grep to search full content. You do NOT need to use `head`, `tail`, or other truncation commands.

   - Avoid using Bash with `find`, `grep`, `cat`, `head`, `tail`, `sed`, `awk`, or `echo` commands unless truly necessary. Instead, use dedicated tools:
     - File search: Use Glob (NOT find or ls)
     - Content search: Use Grep (NOT grep or rg)
     - Read files: Use Read (NOT cat/head/tail)
     - Edit files: Use Edit (NOT sed/awk)
     - Write files: Use Write (NOT echo >/cat <<EOF)
     - Communication: Output text directly (NOT echo/printf)
   - When issuing multiple commands:
     - If the commands are independent, make multiple Bash tool calls in a single message to run them in parallel.
     - If the commands depend on each other, use a single Bash call with '&&' to chain them.
     - Use ';' only when you need to run commands sequentially but don't care if earlier commands fail.
     - DO NOT use newlines to separate commands.

# Committing changes with git

Only create commits when requested by the user. If unclear, ask first. When the user asks you to create a new git commit, follow these steps:

Git Safety Protocol:
- NEVER update the git config
- NEVER run destructive/irreversible git commands (like push --force, hard reset) unless the user explicitly requests them
- NEVER skip hooks (--no-verify) unless the user explicitly requests it
- NEVER run force push to main/master, warn the user if they request it
- CRITICAL: Always create NEW commits rather than amending. Only amend when: (1) user explicitly requested it, (2) HEAD was created by you, (3) commit has NOT been pushed.
- If commit FAILED or was REJECTED by hook, NEVER amend — fix the issue and create a NEW commit.
- NEVER commit changes unless the user explicitly asks you to.

1. Run git status and git diff in parallel to see all changes.
2. Analyze all staged changes and draft a commit message:
   - Summarize the nature of the changes (new feature, bug fix, refactoring, etc.)
   - Do not commit files that likely contain secrets (.env, credentials.json, etc.)
3. Add relevant files, create the commit, and run git status to verify.
4. If the commit fails due to pre-commit hook, fix the issue and create a NEW commit.

Important:
- NEVER run additional commands to read or explore code, besides git bash commands
- DO NOT push to the remote repository unless the user explicitly asks
- NEVER use git commands with the -i flag (interactive) since they require input which is not supported

# Creating pull requests
Use the gh command for ALL GitHub-related tasks.

When creating a pull request:
1. Run git status, git diff, and git log in parallel to understand changes
2. Analyze ALL commits and draft a PR summary
3. Create branch if needed, push with -u, and create PR using gh pr create"""

bash_tool = define_tool(
    "bash",
    description=BASH_DESCRIPTION,
    parameters=BashArgs,
    execute=execute,
)
