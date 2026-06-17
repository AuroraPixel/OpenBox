"""Tool execution hooks: permission checks, doom loop detection, SSE events."""
import json
import time
from typing import Any

from bus import bus
from bus.events import TOOL_RUNNING, TOOL_COMPLETED, TOOL_ERROR
from permission import permission as perm_mod
from tool.tool import ToolResult, ToolContext
from core.log import create_logger

log = create_logger("agent.hooks")

DOOM_LOOP_THRESHOLD = 3


class ToolHooks:
    """Wraps tool execution with permission checks, doom loop detection, and SSE events."""

    def __init__(self, session_id: str, user_id: str = "default", config_rules: list | None = None, agent_rules: list | None = None):
        self.session_id = session_id
        self.user_id = user_id
        self.config_rules = config_rules or []
        self.agent_rules = self._parse_agent_rules(agent_rules or [])
        self.call_history: list[tuple[str, str]] = []  # (tool_name, args_json)

    @staticmethod
    def _parse_agent_rules(raw_rules: list[dict]) -> list:
        """Convert agent permission dicts to Rule objects."""
        from permission.permission import Rule
        rules = []
        for r in raw_rules:
            if isinstance(r, dict):
                rules.append(Rule(
                    permission=r.get("permission", "*"),
                    pattern=r.get("pattern", "*"),
                    action=r.get("action", "ask"),
                ))
        return rules

    async def wrap_execute(
        self,
        tool_id: str,
        execute_fn: Any,
        args: dict,
        ctx: ToolContext,
        part_id: str = "",
    ) -> ToolResult:
        """Wrap a tool execution with hooks."""
        start_time = time.time()

        # 1. Doom loop detection (check BEFORE normal permission)
        is_doom = self._check_doom_loop(tool_id, args)
        if is_doom:
            try:
                await perm_mod.ask(
                    session_id=self.session_id,
                    permission="doom_loop",
                    patterns=[tool_id],
                    input_data=args,
                    metadata={"tool": tool_id, "input": args},
                    config_rules=self.config_rules,
                    is_doom_loop=True,
                    user_id=self.user_id,
                )
            except (perm_mod.PermissionDeniedError, perm_mod.PermissionRejectedError):
                return ToolResult(
                    title="Doom loop detected",
                    output=f"The same tool call ({tool_id}) was repeated {DOOM_LOOP_THRESHOLD} times with identical arguments. Execution was blocked.",
                    metadata={"blocked": True, "doom_loop": True},
                )

        # 2. Agent-level permission check (takes precedence over config rules)
        # Agent rules are evaluated first; if they produce a deny, block immediately.
        # Map edit-family tools to the "edit" permission (matching opencode's EDIT_TOOLS)
        perm_name = "edit" if tool_id in perm_mod.EDIT_TOOLS else tool_id
        patterns = self._extract_patterns(tool_id, args)

        # In Docker sandbox, "always allow" grants blanket permission for the tool
        always_patterns = ["*"]

        merged_rules = (self.config_rules + self.agent_rules) if self.agent_rules else self.config_rules
        try:
            await perm_mod.ask(
                session_id=self.session_id,
                permission=perm_name,
                patterns=patterns,
                input_data=args,
                config_rules=merged_rules,
                always=always_patterns,
                user_id=self.user_id,
            )
        except perm_mod.PermissionDeniedError:
            return ToolResult(
                title="Permission denied",
                output=f"Permission denied for tool '{tool_id}'. This tool is restricted in the current agent mode.",
                metadata={"blocked": True},
            )
        except perm_mod.PermissionCorrectedError as e:
            return ToolResult(
                title="Permission rejected with feedback",
                output=f"The user rejected with feedback: {e.feedback}",
                metadata={"blocked": True},
            )
        except perm_mod.PermissionRejectedError:
            return ToolResult(
                title="Permission rejected",
                output="The user rejected permission to use this tool.",
                metadata={"blocked": True},
            )

        # 2. Record call for doom loop detection
        call_sig = json.dumps(args, sort_keys=True)
        self.call_history.append((tool_id, call_sig))

        # Set part_id on context so tools can reference their own tool call
        ctx.part_id = part_id

        # 3. Publish tool.running event
        bus.publish(TOOL_RUNNING, {
            "userId": self.user_id,
            "sessionId": self.session_id,
            "partId": part_id,
            "tool": tool_id,
            "input": args,
        })

        # 4. Set up incremental output callback for real-time streaming
        from bus.events import PART_UPDATED
        _last_output = {"text": ""}

        async def _on_output(output: str) -> None:
            """Push incremental tool output to frontend via part.updated."""
            if output == _last_output["text"]:
                return
            _last_output["text"] = output
            bus.publish(PART_UPDATED, {
                "userId": self.user_id,
                "sessionId": self.session_id,
                "messageId": ctx.message_id,
                "part": {
                    "type": "tool",
                    "id": part_id,
                    "tool": tool_id,
                    "status": "running",
                    "output": output[-2000:] if len(output) > 2000 else output,
                    "input": args,
                },
            })

        ctx._on_output = _on_output

        # 5. Execute
        try:
            result = await execute_fn(args, ctx)
        except Exception as e:
            # Handle plan mode rejection gracefully (not a real error)
            from tool.plan import PlanRejectedError
            from question.question import QuestionRejectedError
            if isinstance(e, (PlanRejectedError, QuestionRejectedError)):
                return ToolResult(
                    title="Rejected",
                    output=str(e),
                    metadata={"rejected": True},
                )

            # Handle container connection errors with a clear message
            import httpx as _httpx
            if isinstance(e, (_httpx.ConnectError, _httpx.ReadError, _httpx.RemoteProtocolError, ConnectionError, OSError)):
                log.warning(f"Container connection error during {tool_id}: {e}")
                bus.publish(TOOL_ERROR, {
                    "userId": self.user_id,
                    "sessionId": self.session_id,
                    "partId": part_id,
                    "error": f"Container unavailable: {e}",
                })
                return ToolResult(
                    title="Container Error",
                    output=f"The sandbox container is not available: {e}. The container will be recreated automatically on the next attempt.",
                    metadata={"error": True, "container_error": True},
                )

            bus.publish(TOOL_ERROR, {
                "userId": self.user_id,
                "sessionId": self.session_id,
                "partId": part_id,
                "error": str(e),
            })
            return ToolResult(
                title=f"Error in {tool_id}",
                output=str(e),
                metadata={"error": True},
            )
        finally:
            ctx._on_output = None  # Clean up callback

        # 6. Publish tool.completed event
        duration = time.time() - start_time
        bus.publish(TOOL_COMPLETED, {
            "userId": self.user_id,
            "sessionId": self.session_id,
            "partId": part_id,
            "output": result.output[:2000] if result.output else "",
            "title": result.title,
        })

        result.metadata["duration"] = duration
        return result

    def _extract_patterns(self, tool_id: str, args: dict) -> list[str]:
        """Extract permission patterns from tool args."""
        if tool_id == "bash":
            return [args.get("command", "")]
        elif tool_id in ("read", "write", "edit", "multiedit", "apply_patch"):
            return [args.get("file_path", "")]
        elif tool_id == "glob":
            return [args.get("pattern", "")]
        elif tool_id == "grep":
            return [args.get("pattern", "")]
        return ["*"]

    def _check_doom_loop(self, tool_id: str, args: dict) -> bool:
        """Check if we're in a doom loop (same call repeated N times)."""
        if len(self.call_history) < DOOM_LOOP_THRESHOLD:
            return False

        call_sig = json.dumps(args, sort_keys=True)
        recent = self.call_history[-DOOM_LOOP_THRESHOLD:]
        return all(
            name == tool_id and sig == call_sig
            for name, sig in recent
        )
