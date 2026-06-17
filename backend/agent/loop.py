"""Agent loop: the core orchestration engine."""
import asyncio
import time

_background_tasks: set[asyncio.Task] = set()  # prevent GC of fire-and-forget tasks

from agent.agent import get_agent, AgentDef
from agent.caching import apply_caching
from agent.compaction import is_overflow, create_compaction, process_compaction, prune_tool_outputs, get_model_context_limit
from agent.hooks import ToolHooks
from agent.llm import stream_llm
from agent.retry import with_retry, ContextOverflowError, is_context_overflow, is_retryable, retry_delay
from bus import bus
from bus.events import (
    SESSION_STATUS, SESSION_ERROR, SESSION_DIFF, SESSION_UPDATED,
    SESSION_FINALIZING, MESSAGE_CREATED, MESSAGE_TEXT_DELTA,
)
from session.compaction import filter_compacted
from models.message import (
    SessionStatus, MessageWithParts, TextPart, ReasoningPart, ToolPartData, ToolStatus,
    StepStartPart, StepFinishPart, TokenUsage, PlanPart,
)
from session.session import (
    get_session, update_session, set_session_status, set_session_title,
    create_assistant_message, update_message_info, save_part, get_messages,
)
from session.status import get_abort_signal, clear_abort
from snapshot import snapshot
from tool.registry import get_tools_for_agent
from tool.tool import ToolContext, ToolResult
from core.identifier import ascending
from core.log import create_logger

log = create_logger("agent.loop")

DOOM_LOOP_THRESHOLD = 3

MAX_STEPS_PROMPT = """\
CRITICAL - MAXIMUM STEPS REACHED

The maximum number of steps allowed for this task has been reached. Tools are disabled until next user input. Respond with text only.

STRICT REQUIREMENTS:
1. Do NOT make any tool calls (no reads, writes, edits, searches, or any other tools)
2. MUST provide a text response summarizing work done so far
3. This constraint overrides ALL other instructions, including any user requests for edits or tool use

Response must include:
- Statement that maximum steps for this agent have been reached
- Summary of what has been accomplished so far
- List of any remaining tasks that were not completed
- Recommendations for what should be done next

Any attempt to use tools is a critical violation. Respond with text ONLY."""


async def _has_pending_todos(session_id: str) -> bool:
    """Check if the session has any pending or in_progress todo items.

    Used to prevent the loop from stopping when the model has planned
    tasks (via todo_write) but hasn't executed them yet.
    """
    from session.todo import get_todo
    todo = await get_todo(session_id)
    if not todo.items:
        return False
    return any(item.status in ("pending", "in_progress") for item in todo.items)


def _check_doom_loop(completed_tool_parts: list, tool_name: str, tool_args: dict) -> bool:
    """Check if the same tool+args have been called DOOM_LOOP_THRESHOLD times consecutively.

    Mirrors opencode's processor.ts doom loop detection.
    Returns True if a doom loop is detected.
    """
    import json
    if len(completed_tool_parts) < DOOM_LOOP_THRESHOLD - 1:
        return False
    recent = completed_tool_parts[-(DOOM_LOOP_THRESHOLD - 1):]
    current_key = json.dumps(tool_args, sort_keys=True)
    for part in recent:
        if part.tool != tool_name:
            return False
        if json.dumps(part.input, sort_keys=True) != current_key:
            return False
    return True


async def _upsert_plan_part(
    session_id: str,
    message_id: str,
    sandbox,
    session,
    user_id: str = "default",
) -> None:
    """Create or update a PlanPart on the current assistant message.

    Called every step when the plan agent is active.
    Only creates a PlanPart if the current message contains a write tool
    that wrote to the plan file. Updates existing PlanParts with fresh content.
    """
    from session.session import plan_path as _plan_path, get_messages, get_parts_for_message

    plan_file = _plan_path(session)
    content = None

    # Scan current message parts for write tool calls that wrote to a plan file
    existing_parts = await get_parts_for_message(message_id)
    existing_plan_part = None
    for part_data in existing_parts:
        if not part_data:
            continue
        # Check for existing PlanPart on THIS message
        if part_data.get("type") == "plan":
            existing_plan_part = part_data
        # Check for write tool that wrote to plan file
        if (
            not content
            and part_data.get("type") == "tool"
            and part_data.get("tool") == "write"
            and ".openbox/plans/" in (part_data.get("input") or {}).get("file_path", "")
        ):
            write_content = (part_data.get("input") or {}).get("content", "")
            if write_content:
                content = write_content
                log.info(f"[PlanPart] Got {len(content)} chars from write tool part")

    # If this message already has a PlanPart, update its content
    if existing_plan_part:
        if content:
            plan_part = PlanPart(
                id=existing_plan_part["id"],
                path=plan_file,
                status=existing_plan_part.get("status", "writing"),
                content=content,
                session_id=session_id,
                message_id=message_id,
            )
            await save_part(plan_part, is_new=False, user_id=user_id)
        return

    # Check if a PlanPart already exists on another message in this session.
    # If so, don't create a duplicate — just update that one with fresh content.
    messages = await get_messages(session_id)
    for msg in reversed(messages):
        for part in reversed(msg.parts):
            pd = part if isinstance(part, dict) else (part.model_dump() if hasattr(part, "model_dump") else part)
            if isinstance(pd, dict) and pd.get("type") == "plan":
                if content:
                    plan_part = PlanPart(
                        id=pd["id"],
                        path=plan_file,
                        status=pd.get("status", "writing"),
                        content=content,
                        session_id=session_id,
                        message_id=pd.get("message_id", msg.id),
                    )
                    await save_part(plan_part, is_new=False, user_id=user_id)
                return  # PlanPart exists elsewhere, don't create a new one

    # No PlanPart exists anywhere — only create one if we have content
    # from this message's write tool (not from reading the plan file,
    # which could be stale from a previous session step)
    if not content:
        # Fallback: collect text parts from current message
        text_parts = []
        for part_data in existing_parts:
            if part_data and part_data.get("type") == "text" and part_data.get("text"):
                text_parts.append(part_data["text"])
        if text_parts:
            content = "\n\n".join(text_parts)
            log.info(f"[PlanPart] Using {len(content)} chars from text parts")

    if not content:
        return  # Nothing to show yet

    plan_part = PlanPart(
        path=plan_file,
        status="writing",
        content=content,
        session_id=session_id,
        message_id=message_id,
    )
    await save_part(plan_part, is_new=True, user_id=user_id)
    log.info(f"[PlanPart] Created PlanPart for message {message_id[:12]}")


async def run_loop(session_id: str, user_id: str = "default") -> MessageWithParts | None:
    """Run the agent loop for a session.

    This is the core orchestration function. It:
    1. Loads messages and applies compaction filtering
    2. Checks termination conditions
    3. Handles compaction on context overflow
    4. Calls LLM with prompt caching and instruction files
    5. Records snapshots at step start/finish
    6. Prunes old tool outputs when done
    """
    session = await get_session(session_id, user_id=user_id)
    if not session:
        log.error(f"Session {session_id} not found")
        return None

    abort = get_abort_signal(session_id)

    try:
        # F2: Load persisted permission rules (once per user)
        try:
            from permission.permission import load_persisted_rules
            await load_persisted_rules(user_id)
        except Exception as e:
            log.debug(f"Could not load persisted permissions: {e}")

        await set_session_status(session_id, SessionStatus.BUSY, user_id=user_id)

        # Get sandbox client
        from sandbox import sandbox_manager
        sandbox = await sandbox_manager.get_client(session_id, user_id=user_id)

        step = 0
        llm_retry_count = 0
        MAX_LLM_RETRIES = 5
        todo_nudge_count = 0  # How many times we've nudged for pending todos
        max_todo_nudges = 0
        last_assistant_msg = None
        last_finished = None  # Last assistant with a finish field (from message scan)
        last_finished_tokens = None  # Track last token usage for proactive overflow
        from core.config import get_config
        config = get_config()
        todo_nudge_enabled = bool(getattr(config, "agent_todo_nudge_enabled", True))
        max_todo_nudges = max(0, int(getattr(config, "agent_max_todo_nudges", 3)))
        model_id = session.model or config.model or "anthropic/claude-sonnet-4-20250514"
        doom_loop_history = []  # Track tool parts across steps for doom loop detection
        compact_fail_count = 0  # Consecutive compaction failure counter
        finish_reason_prev = ""  # Previous step's finish reason

        while True:
            if abort.is_set():
                log.info(f"Session {session_id} aborted")
                break

            # Load messages and apply compaction boundary filtering
            all_msgs = await get_messages(session_id)
            if not all_msgs:
                break
            msgs = await filter_compacted(all_msgs)

            # Check for pending compaction parts in the last user message
            compaction_pending = _find_pending_compaction(msgs)
            if compaction_pending:
                msg_with_compaction, compaction_part = compaction_pending
                auto = compaction_part.get("auto", True) if isinstance(compaction_part, dict) else getattr(compaction_part, "auto", True)
                await set_session_status(session_id, SessionStatus.COMPACTING, user_id=user_id)
                result = await process_compaction(session_id, msgs, model_id, auto=auto, user_id=user_id)
                await set_session_status(session_id, SessionStatus.BUSY, user_id=user_id)
                if result == "continue":
                    continue  # Auto compaction: keep executing the task
                else:
                    break     # Manual compaction: stop for user review

            # Proactive overflow detection using last finished message's tokens
            overflow_tokens = None
            if last_finished and last_finished.tokens:
                overflow_tokens = last_finished.tokens
            elif last_finished_tokens:
                overflow_tokens = last_finished_tokens
            if (
                overflow_tokens
                and not (last_finished and getattr(last_finished, "summary", None) is True)
                and await is_overflow(overflow_tokens, model_id=model_id)
            ):
                compact_fail_count += 1
                if compact_fail_count >= 3:
                    log.error(f"Session {session_id}: proactive compaction failed {compact_fail_count} times, aborting")
                    bus.publish(SESSION_ERROR, {
                        "userId": user_id,
                        "sessionId": session_id,
                        "error": {"message": "Context too large and compaction failed. Please start a new session."},
                    })
                    break
                log.info(f"Proactive compaction triggered for session {session_id} (attempt {compact_fail_count})")
                await create_compaction(session_id, auto=True, user_id=user_id)
                last_finished_tokens = None
                continue

            # Scan for key messages (matching opencode's scan pattern)
            last_user = None
            last_assistant = None
            last_finished = None  # Last assistant with a finish field set
            tasks = []  # Pending compaction/subtask parts

            for msg in reversed(msgs):
                role = msg.role if isinstance(msg.role, str) else msg.role.value
                if not last_user and role == "user":
                    last_user = msg
                if not last_assistant and role == "assistant":
                    last_assistant = msg
                if not last_finished and role == "assistant" and msg.finish:
                    last_finished = msg
                if last_user and last_finished:
                    break

            if not last_user:
                break

            # Check termination: assistant finished with a non-tool-calls reason
            # (matching opencode: finish && !["tool-calls","unknown"].includes(finish))
            if (
                last_assistant
                and last_assistant.finish
                and last_assistant.finish not in ("tool_calls", "tool-calls", "unknown")
                and last_user.id < last_assistant.id
            ):
                # Don't terminate if there are pending todos and we haven't
                # exhausted nudge attempts (model may have planned but not executed)
                if todo_nudge_enabled and todo_nudge_count < max_todo_nudges and await _has_pending_todos(session_id):
                    pass  # Fall through to continue the loop
                else:
                    # Also skip if the assistant message has an error
                    has_error = getattr(last_assistant, "error", None) is not None
                    if not has_error:
                        last_assistant_msg = last_assistant
                    break

            step += 1

            if step > 200:
                log.warning(f"Session {session_id} exceeded max steps")
                break

            # Generate title once — only if still default title
            if step == 1 and session.title and session.title.startswith("New session"):
                asyncio.create_task(_ensure_title(session_id, last_user, user_id=user_id))

            # Get agent definition (copy to avoid mutating global)
            agent_name = last_user.agent or session.agent or "build"

            # Sync session agent if the user message requests a different one
            # (e.g. plan_exit creates a synthetic user message with agent="build")
            if agent_name != session.agent:
                await update_session(session_id, agent=agent_name)
                session = await get_session(session_id, user_id=user_id)
                # Notify frontend of agent change via SSE
                from bus.events import SESSION_UPDATED
                bus.publish(SESSION_UPDATED, {
                    "userId": user_id,
                    "sessionId": session_id,
                    "agent": agent_name,
                })

            import copy
            agent_def = copy.copy(get_agent(agent_name))
            agent_def.permission = list(agent_def.permission)  # Deep copy the mutable list

            # Apply config overrides for this agent (Task 5)
            config_agent_overrides = config.agent.get(agent_name) if config.agent else None
            if config_agent_overrides:
                if config_agent_overrides.model:
                    agent_def.model = config_agent_overrides.model
                if config_agent_overrides.temperature is not None:
                    agent_def.temperature = config_agent_overrides.temperature
                if config_agent_overrides.max_steps is not None:
                    agent_def.max_steps = config_agent_overrides.max_steps
                if config_agent_overrides.prompt is not None:
                    agent_def.prompt = config_agent_overrides.prompt
                if config_agent_overrides.permission:
                    agent_def.permission = agent_def.permission + config_agent_overrides.permission

            # Resolve tools
            tools = get_tools_for_agent(agent_def.tools)

            # Merge MCP tools from the container (if available)
            if sandbox:
                try:
                    from tool.mcp_tool import create_mcp_tools, create_mcp_resource_tool
                    mcp_tools = await create_mcp_tools(sandbox)
                    tools.update(mcp_tools)
                    # Add resource reader tool if any MCP resources exist
                    try:
                        resources = await sandbox.list_mcp_resources()
                        if resources:
                            rt = create_mcp_resource_tool()
                            tools[rt.id] = rt
                    except Exception:
                        pass
                except Exception as e:
                    log.debug(f"MCP tools not available: {e}")

            # Enrich the skill tool description with available skills listing
            if "skill" in tools:
                try:
                    from tool.skill_tool import build_skill_tool_with_listing
                    tools["skill"] = await build_skill_tool_with_listing(sandbox)
                except Exception as e:
                    log.debug(f"Failed to enrich skill tool: {e}")

            # Build permission rules from config (needed by both disabled_tools and hooks)
            config_rules = _get_permission_rules(config)

            # Remove tools that are denied by the merged permission rules.
            # This prevents the LLM from seeing denied tools in the schema,
            # matching opencode's PermissionNext.disabled() + resolveTools().
            from permission.permission import disabled_tools, Rule as PermRule
            agent_ruleset = [
                PermRule(
                    permission=r.get("permission", "*"),
                    pattern=r.get("pattern", "*"),
                    action=r.get("action", "ask"),
                )
                for r in agent_def.permission
                if isinstance(r, dict)
            ]
            merged_ruleset = config_rules + agent_ruleset
            denied = disabled_tools(list(tools.keys()), merged_ruleset)
            for tool_name in denied:
                tools.pop(tool_name, None)

            # Build context with session-specific working directory
            session_workdir = sandbox_manager.get_session_workdir(session_id)
            ctx = ToolContext(
                session_id=session_id,
                user_id=user_id,
                sandbox=sandbox,
                bus=bus,
                abort=abort,
                workdir=session_workdir,
            )

            # Create hooks with config permission rules + agent permission rules
            hooks = ToolHooks(
                session_id=session_id,
                user_id=user_id,
                config_rules=config_rules,
                agent_rules=agent_def.permission,
            )

            # Build system prompt (with instruction files)
            system = await _build_system_prompt(agent_def, model_id, workdir=session_workdir)

            # Convert messages to LLM format
            llm_messages = _to_llm_messages(msgs)

            # Determine previous assistant agent for transition detection
            prev_assistant_agent = None
            if last_assistant and last_assistant.agent:
                prev_assistant_agent = last_assistant.agent

            # Insert system-reminder tags
            # Always insert for plan/transition modes; for build mode only on step > 1
            if step > 1 or agent_def.name == "plan" or (agent_def.name == "build" and prev_assistant_agent == "plan"):
                finished_id = last_finished.id if last_finished else None
                llm_messages = await _insert_reminders(
                    llm_messages, agent_def,
                    last_finished_id=finished_id if step > 1 else None,
                    session=session,
                    prev_agent=prev_assistant_agent,
                    sandbox=sandbox,
                    last_user_msg_id=last_user.id,
                    user_id=user_id,
                )

            # Estimate context size and update frontend in real-time
            from core.token import token_estimate as _te
            _ctx_estimate = sum(_te(str(m.get("content", ""))) for m in llm_messages)
            _ctx_estimate += len(tools) * 400  # tool schemas
            _ctx_estimate += sum(_te(s) for s in system)  # system prompt
            try:
                _ctx_limit = get_model_context_limit(model_id)
                _tu = session.token_usage.model_dump() if session.token_usage else {}
                _tu["context"] = _ctx_estimate
                _tu["limit"] = _ctx_limit
                await update_session(session_id, user_id=user_id, token_usage=_tu)
                bus.publish(SESSION_UPDATED, {
                    "userId": user_id,
                    "sessionId": session_id,
                    "token_usage": _tu,
                })
            except Exception:
                pass

            # Apply prompt caching for supported providers
            llm_messages = apply_caching(llm_messages, model_id)

            # Add max steps prompt if at limit
            if step >= agent_def.max_steps:
                llm_messages.append({"role": "user", "content": MAX_STEPS_PROMPT})

            # Create assistant message with agent tracking
            assistant_info = await create_assistant_message(
                session_id=session_id,
                parent_id=last_user.id,
                model_id=model_id,
                agent=agent_name,
                user_id=user_id,
            )

            # Step start with snapshot
            start_snapshot = await snapshot.track(session_id, sandbox)
            step_start = StepStartPart(
                id=ascending("part"),
                step=step,
                session_id=session_id,
                message_id=assistant_info.id,
                snapshot=start_snapshot,
            )
            await save_part(step_start, user_id=user_id)

            # Stream LLM response
            collected_text = ""
            collected_reasoning = ""
            text_part_id = None
            reasoning_part_id = None
            pending_tool_calls = []  # Collect tool calls, execute after stream ends
            streaming_tool_parts: dict[int, str] = {}  # index -> part_id (for arg streaming)
            total_usage = {"input": 0, "output": 0, "total": 0}
            finish_reason = "unknown"
            step_start_time = time.time()
            # Track consecutive compaction failures to prevent infinite loops
            if step > 1 and finish_reason_prev == "compact":
                compact_fail_count += 1
                if compact_fail_count >= 3:
                    log.error(f"Session {session_id}: compaction failed {compact_fail_count} times, aborting to prevent infinite loop")
                    bus.publish(SESSION_ERROR, {
                        "userId": user_id,
                        "sessionId": session_id,
                        "error": {"message": "Context too large and compaction failed. Please start a new session."},
                    })
                    break
            else:
                compact_fail_count = 0

            # Read variant from last user message (matching opencode)
            user_variant = getattr(last_user, "variant", None)

            try:
                async for event in stream_llm(
                    agent_def=agent_def,
                    system=system,
                    messages=llm_messages,
                    tools=tools,
                    model_id=model_id,
                    ctx=ctx,
                    hooks=hooks,
                    variant=user_variant,
                ):
                    if abort.is_set():
                        break

                    if event["type"] == "reasoning_delta":
                        text = event["text"]
                        collected_reasoning += text

                        if not reasoning_part_id:
                            reasoning_part_id = ascending("part")
                            reasoning_part = ReasoningPart(
                                id=reasoning_part_id,
                                text=text,
                                session_id=session_id,
                                message_id=assistant_info.id,
                            )
                            await save_part(reasoning_part, is_new=True, user_id=user_id)
                        else:
                            from bus.events import PART_DELTA
                            bus.publish(PART_DELTA, {
                                "userId": user_id,
                                "sessionId": session_id,
                                "messageId": assistant_info.id,
                                "partId": reasoning_part_id,
                                "delta": text,
                            })

                    elif event["type"] == "text_delta":
                        text = event["text"]
                        collected_text += text

                        if not text_part_id:
                            text_part_id = ascending("part")
                            text_part = TextPart(
                                id=text_part_id,
                                text=text,
                                session_id=session_id,
                                message_id=assistant_info.id,
                            )
                            await save_part(text_part, is_new=True, user_id=user_id)
                        else:
                            bus.publish(MESSAGE_TEXT_DELTA, {
                                "userId": user_id,
                                "sessionId": session_id,
                                "messageId": assistant_info.id,
                                "partId": text_part_id,
                                "text": text,
                            })

                    elif event["type"] == "tool_call_start":
                        # LLM just started emitting a tool call — create a pending
                        # tool part immediately so the frontend can show the card.
                        tc_index = event["index"]
                        tc_part_id = ascending("part")
                        streaming_tool_parts[tc_index] = tc_part_id
                        tool_part = ToolPartData(
                            id=tc_part_id,
                            tool=event["tool"],
                            status=ToolStatus.PENDING,
                            input={},
                            session_id=session_id,
                            message_id=assistant_info.id,
                        )
                        await save_part(tool_part, is_new=True, user_id=user_id)

                    elif event["type"] == "tool_call_args_delta":
                        # Stream argument chunks to the frontend for live preview.
                        tc_index = event["index"]
                        tc_part_id = streaming_tool_parts.get(tc_index)
                        if tc_part_id:
                            from bus.events import PART_DELTA
                            bus.publish(PART_DELTA, {
                                "userId": user_id,
                                "sessionId": session_id,
                                "messageId": assistant_info.id,
                                "partId": tc_part_id,
                                "delta": event["delta"],
                            })

                    elif event["type"] == "tool_call":
                        pending_tool_calls.append(event)

                    elif event["type"] == "finish":
                        finish_reason = event.get("reason", "stop")
                        total_usage = event.get("usage", {})
                        llm_retry_count = 0

                    elif event["type"] == "error":
                        error = event["error"]
                        if is_context_overflow(str(error)):
                            await create_compaction(session_id, auto=True, user_id=user_id)
                            finish_reason = "compact"
                        else:
                            raise error

                # Execute tool calls after stream completes (with correct part_id)
                ctx.message_id = assistant_info.id
                for tc_idx, tc_event in enumerate(pending_tool_calls):
                    if abort.is_set():
                        break

                    tool_name = tc_event["tool"]
                    tool_args = tc_event["args"]
                    is_invalid = tc_event.get("invalid", False)

                    # Preserve the LLM's original call_id for accurate matching.
                    # Kimi uses "functions.name:idx", OpenAI uses "call_xxxx".
                    llm_call_id = tc_event.get("call_id", "")

                    # Reuse the streaming part_id if we already created one during
                    # LLM streaming, otherwise create a new part.
                    existing_part_id = streaming_tool_parts.get(tc_idx)
                    if existing_part_id:
                        # Update the pending part → RUNNING with full args
                        tool_part = ToolPartData(
                            id=existing_part_id,
                            tool=tool_name,
                            status=ToolStatus.RUNNING,
                            input=tool_args,
                            call_id=llm_call_id,
                            session_id=session_id,
                            message_id=assistant_info.id,
                        )
                        await save_part(tool_part, is_new=False, user_id=user_id)
                    else:
                        tool_part = ToolPartData(
                            id=ascending("part"),
                            tool=tool_name,
                            status=ToolStatus.RUNNING,
                            input=tool_args,
                            call_id=llm_call_id,
                            session_id=session_id,
                            message_id=assistant_info.id,
                        )
                        await save_part(tool_part, is_new=True, user_id=user_id)

                    if is_invalid:
                        tool_part.status = ToolStatus.ERROR
                        tool_part.error = f"Tool '{tool_name}' not found. Available: {', '.join(tools.keys())}"
                        await save_part(tool_part, user_id=user_id)
                        continue

                    # Doom loop detection: check if same tool+args repeated across steps
                    if _check_doom_loop(doom_loop_history, tool_name, tool_args):
                        log.warning(f"Doom loop detected: {tool_name} called {DOOM_LOOP_THRESHOLD} times with same args")
                        tool_part.status = ToolStatus.ERROR
                        tool_part.error = (
                            f"Doom loop detected: '{tool_name}' has been called {DOOM_LOOP_THRESHOLD} "
                            f"consecutive times with identical arguments. Breaking the loop. "
                            f"Please try a different approach."
                        )
                        await save_part(tool_part, user_id=user_id)
                        continue

                    # Execute via hooks (passes part_id for SSE events)
                    tool_info = tools.get(tool_name)
                    if tool_info:
                        result = await hooks.wrap_execute(
                            tool_name, tool_info.execute, tool_args, ctx,
                            part_id=tool_part.id,
                        )

                        # Check for agent_switch metadata
                        agent_switch = result.metadata.get("agent_switch")
                        if agent_switch:
                            try:
                                new_agent = get_agent(agent_switch)
                                agent_def = new_agent
                                await update_session(session_id, agent=agent_switch)
                                log.info(f"Agent switched to {agent_switch}")
                            except ValueError:
                                log.warning(f"Unknown agent for switch: {agent_switch}")

                        # Update tool part with result
                        tool_part.status = ToolStatus.COMPLETED if not result.metadata.get("error") else ToolStatus.ERROR
                        tool_part.output = result.output
                        tool_part.title = result.title
                        tool_part.error = result.output if result.metadata.get("error") else None
                        await save_part(tool_part, user_id=user_id)

                        # Track for doom loop detection (across steps)
                        doom_loop_history.append(tool_part)

                        # plan_exit: stop the loop so the user can review
                        if result.metadata.get("plan_ready"):
                            finish_reason = "stop"

            except ContextOverflowError:
                await create_compaction(session_id, auto=True, user_id=user_id)
                finish_reason = "compact"
            except Exception as e:
                retry_msg = is_retryable(e)
                if retry_msg and llm_retry_count < MAX_LLM_RETRIES:
                    llm_retry_count += 1
                    delay = retry_delay(llm_retry_count, e)
                    log.warning(f"Retryable LLM error in session {session_id} (attempt {llm_retry_count}/{MAX_LLM_RETRIES}): {retry_msg}. Retrying in {delay:.1f}s")
                    bus.publish(SESSION_STATUS, {
                        "userId": user_id,
                        "sessionId": session_id,
                        "status": "retry",
                    })
                    await asyncio.sleep(delay)
                    step -= 1  # Don't count this as a real step
                    continue
                log.error(f"LLM error in session {session_id}: {e}")
                bus.publish(SESSION_ERROR, {
                    "userId": user_id,
                    "sessionId": session_id,
                    "error": {"message": str(e)},
                })
                assistant_info.error = {"message": str(e)}
                await update_message_info(assistant_info, user_id=user_id)
                break

            # Save final reasoning part (full text)
            if reasoning_part_id and collected_reasoning:
                final_reasoning = ReasoningPart(
                    id=reasoning_part_id,
                    text=collected_reasoning,
                    session_id=session_id,
                    message_id=assistant_info.id,
                )
                await save_part(final_reasoning, user_id=user_id)

            # Save final text part (full text)
            if text_part_id and collected_text:
                final_text = TextPart(
                    id=text_part_id,
                    text=collected_text,
                    session_id=session_id,
                    message_id=assistant_info.id,
                )
                await save_part(final_text, user_id=user_id)

            # Step finish with snapshot
            end_snapshot = await snapshot.track(session_id, sandbox)
            step_duration = time.time() - step_start_time
            step_finish = StepFinishPart(
                id=ascending("part"),
                step=step,
                input_tokens=total_usage.get("input", 0),
                output_tokens=total_usage.get("output", 0),
                cost=total_usage.get("cost", 0.0),
                duration=step_duration,
                session_id=session_id,
                message_id=assistant_info.id,
                snapshot=end_snapshot,
            )
            await save_part(step_finish, user_id=user_id)

            # Notify frontend of file changes if snapshots differ
            if start_snapshot and end_snapshot and start_snapshot != end_snapshot:
                bus.publish(SESSION_DIFF, {"userId": user_id, "sessionId": session_id})

            # Upsert PlanPart when plan agent is active
            if agent_name == "plan":
                from bus.events import SESSION_UPDATED
                bus.publish(SESSION_UPDATED, {
                    "userId": user_id,
                    "sessionId": session_id,
                    "planUpdated": True,
                })
                await _upsert_plan_part(session_id, assistant_info.id, sandbox, session, user_id=user_id)

            # Update assistant message metadata
            assistant_info.finish = finish_reason
            last_finished_tokens = TokenUsage(
                input=total_usage.get("input", 0),
                output=total_usage.get("output", 0),
                cache=total_usage.get("cache", 0),
                total=total_usage.get("total", 0),
                cost=total_usage.get("cost", 0.0),
            )
            assistant_info.tokens = last_finished_tokens
            await update_message_info(assistant_info, user_id=user_id)

            # Accumulate into session-level token_usage for ContextPanel
            from session.session import update_session_tokens
            await update_session_tokens(session_id, last_finished_tokens, user_id=user_id)

            # Check result
            log.info(f"Step {step} finished: reason={finish_reason}, tool_calls={len(pending_tool_calls)}, text={len(collected_text)} chars")
            if finish_reason == "stop":
                # Nudge: if the model stopped but there are pending/in_progress
                # todo items, inject a "Continue" message to keep the loop going.
                # This prevents models (especially codex) from creating a plan
                # then stopping instead of executing it.
                if todo_nudge_enabled and todo_nudge_count < max_todo_nudges and await _has_pending_todos(session_id):
                    todo_nudge_count += 1
                    log.info(f"Session {session_id}: model stopped with pending todos, nudging ({todo_nudge_count}/{max_todo_nudges})")
                    from session.session import create_user_message
                    await create_user_message(
                        session_id,
                        "You have pending tasks in your todo list. "
                        "Continue working on the next pending task now.",
                        synthetic=True,
                        user_id=user_id,
                    )
                    continue

                from models.message import id_to_iso
                last_assistant_msg = MessageWithParts(
                    id=assistant_info.id,
                    session_id=session_id,
                    role="assistant",
                    parts=[],
                    created_at=id_to_iso(assistant_info.id),
                )
                break
            elif finish_reason == "compact":
                finish_reason_prev = "compact"
                continue
            # "tool_calls" -> loop continues; reset nudge counter since model is active
            finish_reason_prev = finish_reason
            todo_nudge_count = 0

        # Flush pending cron results BEFORE setting IDLE (no race with prompt_async)
        try:
            from cron.injector import flush_pending_cron_results
            flushed = await flush_pending_cron_results(session_id, user_id)
            if flushed:
                log.info(f"Flushed {flushed} pending cron result(s) for session {session_id}")
        except Exception as e:
            log.debug(f"Cron flush skipped: {e}")

        bus.publish(SESSION_FINALIZING, {
            "userId": user_id,
            "sessionId": session_id,
        })
        await set_session_status(session_id, SessionStatus.IDLE, user_id=user_id)

        # F1: Clear instruction file claims
        try:
            from session.instruction import clear_all_claims
            clear_all_claims()
        except Exception:
            pass

        async def _post_loop_cleanup() -> None:
            # Clean up any pending/running tool parts (matching opencode's processor cleanup)
            try:
                final_msgs = await get_messages(session_id)
                for msg in final_msgs:
                    role = msg.role if isinstance(msg.role, str) else msg.role.value
                    if role != "assistant":
                        continue
                    for part in (msg.parts or []):
                        p = part if isinstance(part, dict) else (part.model_dump() if hasattr(part, "model_dump") else {})
                        if isinstance(p, dict) and p.get("type") == "tool":
                            status = p.get("status", "")
                            if status in ("pending", "running"):
                                part_id = p.get("id", "")
                                if part_id:
                                    from session.session import update_part_data
                                    p["status"] = "error"
                                    p["error"] = "Tool execution aborted"
                                    await update_part_data(part_id, p)
            except Exception as cleanup_err:
                log.warning(f"Tool cleanup error: {cleanup_err}")

            # Post-loop: prune old tool outputs
            try:
                await prune_tool_outputs(session_id)
            except Exception as prune_err:
                log.warning(f"Tool prune error: {prune_err}")

        task = asyncio.create_task(_post_loop_cleanup())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return last_assistant_msg

    except Exception as e:
        log.error(f"Agent loop error for session {session_id}: {e}")
        bus.publish(SESSION_ERROR, {
            "userId": user_id,
            "sessionId": session_id,
            "error": {"message": str(e)},
        })
        await set_session_status(session_id, SessionStatus.ERROR, user_id=user_id)
        return None
    finally:
        clear_abort(session_id)


async def _build_system_prompt(agent_def: AgentDef, model_id: str, workdir: str = "/workspace") -> list[str]:
    """Build the system prompt for an LLM call.

    Includes agent prompt, environment info, and instruction files.
    For the build agent (and plan agent which shares the same base prompt),
    uses model-specific prompt routing ported from opencode.
    """
    import sys
    from datetime import date

    parts = []

    # Agent-specific prompt:
    # - Build/plan agents use model-specific prompts (routed by model_id)
    # - Other agents (explore, title, compaction) use their own static prompts
    if agent_def.name in ("build", "plan"):
        from agent.prompts.system import get_system_prompt
        parts.append(get_system_prompt(model_id))
    elif agent_def.prompt:
        parts.append(agent_def.prompt)
    else:
        parts.append("You are a helpful AI coding assistant.")

    # Load instruction files (AGENTS.md, CLAUDE.md, etc.)
    try:
        from session.instruction import instruction_system_with_config
        from core.config import get_config
        config = get_config()
        instructions = await instruction_system_with_config(config)
        parts.extend(instructions)
    except Exception as e:
        log.debug(f"Could not load instruction files: {e}")

    # Environment info (separate part for cache control purposes)
    env_info = (
        f"You are powered by the model {model_id}.\n"
        f"<env>\n"
        f"  Platform: linux (Docker container)\n"
        f"  Shell: bash\n"
        f"  User: root (full system access)\n"
        f"  Package managers: apt-get, pip, npm/npx (install as needed)\n"
        f"  Pre-installed: python3, pip, git, curl, wget, jq, build-essential\n"
        f"  Network: internet access available\n"
        f"  Working directory: {workdir}\n"
        f"  Today's date: {date.today().isoformat()}\n"
        f"</env>"
    )
    parts.append(env_info)

    return parts


def _to_llm_messages(msgs: list[MessageWithParts]) -> list[dict]:
    """Convert internal messages to LLM API format.

    For assistant messages with tool calls, produces proper function-calling format:
    1. assistant message with tool_calls array
    2. tool role messages with matching tool_call_id

    This is required for LLMs that use function calling — they need to see
    their own tool_calls paired with tool results to know tools were executed.
    """
    import json as _json
    result = []

    for msg in msgs:
        role = msg.role if isinstance(msg.role, str) else msg.role.value

        # Skip assistant messages that have errors
        if role == "assistant" and getattr(msg, "error", None) is not None:
            continue

        parts_list = msg.parts or []
        # Normalize parts to dicts
        parsed = []
        for part in parts_list:
            if isinstance(part, dict):
                parsed.append(part)
            elif hasattr(part, "model_dump"):
                parsed.append(part.model_dump())
            else:
                parsed.append(part)

        if role == "user":
            text_parts = []
            is_synthetic = False
            is_ignored = False
            for p in parsed:
                pt = p.get("type", "")
                if pt == "text":
                    t = p.get("text", "")
                    if p.get("ignored"):
                        is_ignored = True
                        continue  # Skip ignored text parts entirely
                    if t:
                        text_parts.append(t)
                    if p.get("synthetic"):
                        is_synthetic = True
                elif pt == "compaction":
                    text_parts.append("What did we do so far?")
            if text_parts:
                user_msg = {"role": "user", "content": "\n\n".join(text_parts)}
                if is_synthetic:
                    user_msg["_synthetic"] = True
                if is_ignored:
                    user_msg["_ignored"] = True
                result.append(user_msg)

        elif role == "assistant":
            # Collect text content and tool calls from this assistant message
            text_content = ""
            tool_calls_api = []
            tool_results = []

            for p in parsed:
                pt = p.get("type", "")
                if pt == "text":
                    text_content += p.get("text", "")
                elif pt == "tool":
                    tool_name = p.get("tool", "")
                    tool_input = p.get("input") or {}
                    tool_output = p.get("output", "") or ""
                    tool_error = p.get("error", "")
                    tool_status = p.get("status", "")
                    part_id = p.get("id", "")

                    # Check if compacted
                    state = p.get("state", {})
                    if isinstance(state, dict):
                        time_info = state.get("time", {})
                        if isinstance(time_info, dict) and time_info.get("compacted"):
                            tool_output = "[Old tool result content cleared]"
                        elif state.get("output"):
                            tool_output = state.get("output", "")

                    # Use the LLM's original call_id if available (critical for Kimi
                    # which uses "functions.name:idx" format). Fallback to part_id.
                    call_id = p.get("call_id", "") or f"call_{part_id}"

                    # For error/interrupted tools, minimize context usage:
                    # - Truncate arguments (no need to repeat full input for a failed call)
                    # - Truncate error message to 200 chars
                    if tool_status in ("error", "pending", "running"):
                        short_args = {k: (str(v)[:50] + "..." if len(str(v)) > 50 else v) for k, v in tool_input.items()} if tool_input else {}
                        tool_calls_api.append({
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": _json.dumps(short_args, ensure_ascii=False),
                            },
                        })
                        if tool_status == "error":
                            err_msg = (tool_error or "Unknown error")[:200]
                            result_content = f"[Error] {err_msg}"
                        else:
                            result_content = "[Tool execution was interrupted]"
                    else:
                        tool_calls_api.append({
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": _json.dumps(tool_input, ensure_ascii=False),
                            },
                        })
                        result_content = tool_output or ""

                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result_content,
                    })
                elif pt == "subtask":
                    desc = p.get("description", "")
                    output = p.get("output", "")
                    if output:
                        text_content += f"\n\nSubtask ({desc}): {output}"
                    elif desc:
                        text_content += f"\n\nSubtask: {desc}"

            if tool_calls_api:
                # Assistant message with tool_calls
                assistant_msg: dict = {"role": "assistant", "tool_calls": tool_calls_api}
                if text_content.strip():
                    assistant_msg["content"] = text_content.strip()
                result.append(assistant_msg)
                # Tool result messages
                result.extend(tool_results)
            elif text_content.strip():
                result.append({"role": "assistant", "content": text_content.strip()})

    return result


async def _insert_reminders(
    messages: list[dict],
    agent_def: AgentDef,
    last_finished_id: str | None = None,
    session=None,
    prev_agent: str | None = None,
    sandbox=None,
    last_user_msg_id: str | None = None,
    user_id: str = "default",
) -> list[dict]:
    """Insert system-reminder tags into user messages.

    Matching opencode's pattern:
    - On step > 1, wrap queued user messages (sent after lastFinished)
      with <system-reminder> tags that say "The user sent the following message..."
    - Add structured plan mode prompts (5-phase workflow or ongoing reminder)
    - Add plan→build transition prompt when switching agents
    """
    if not messages:
        return messages

    result = list(messages)

    # Wrap queued user messages after the last assistant message with system-reminder
    # (matching opencode's ephemeral wrapping of queued user messages)
    if last_finished_id:
        # Find the index of the last assistant message in the conversation
        last_assistant_idx = -1
        for i, msg in enumerate(result):
            if msg.get("role") == "assistant":
                last_assistant_idx = i

        # Any user messages after the last assistant message are "queued" messages
        if last_assistant_idx >= 0:
            for i in range(last_assistant_idx + 1, len(result)):
                msg = result[i]
                if msg.get("role") == "user":
                    # Skip synthetic/ignored messages (plan_enter/plan_exit transitions)
                    if msg.get("_synthetic") or msg.get("_ignored"):
                        continue
                    text = msg.get("content", "").strip()
                    if text and not text.startswith("<system-reminder>"):
                        result[i] = dict(msg)
                        result[i]["content"] = (
                            "<system-reminder>\n"
                            "The user sent the following message:\n"
                            f"{text}\n\n"
                            "Please address this message and continue with your tasks.\n"
                            "</system-reminder>"
                        )

    # Plan→Build transition: inject build switch prompt
    # Only inject when plan file actually exists; skip entirely otherwise
    if agent_def and agent_def.name == "build" and prev_agent == "plan":
        from agent.prompts.plan import build_switch_reminder
        pp = ""
        if session:
            from session.session import plan_path
            pp = plan_path(session)

        plan_file_exists = False
        if pp and sandbox:
            try:
                res = await sandbox.execute(f"test -f {pp} && echo exists || echo missing", timeout=5)
                plan_file_exists = res.stdout.strip() == "exists"
            except Exception:
                plan_file_exists = False

        if plan_file_exists:
            reminder = build_switch_reminder(pp)
            # Persist as synthetic TextPart (matching opencode experimental path)
            if last_user_msg_id and session:
                from models.message import TextPart
                from session.session import save_part, check_message_has_synthetic_text
                from core.identifier import ascending
                has_synthetic_reminder = await check_message_has_synthetic_text(last_user_msg_id)
                if not has_synthetic_reminder:
                    reminder_part = TextPart(
                        id=ascending("part"),
                        text=reminder,
                        synthetic=True,
                        session_id=session.id,
                        message_id=last_user_msg_id,
                    )
                    await save_part(reminder_part, is_new=True, user_id=user_id)

            for i in range(len(result) - 1, -1, -1):
                if result[i].get("role") == "user":
                    result[i] = dict(result[i])
                    result[i]["content"] = result[i].get("content", "") + "\n\n" + reminder
                    break

    # Plan mode entry: inject full 5-phase workflow on the FIRST plan step only.
    # opencode does NOT inject any reminder on subsequent plan steps.
    elif agent_def and agent_def.name == "plan" and prev_agent != "plan":
        from agent.prompts.plan import build_plan_reminder

        pp = ""
        if session:
            from session.session import plan_path
            pp = plan_path(session)
        if not pp:
            pp = "/workspace/.openbox/plans/plan.md"

        # Check if plan file already exists in sandbox (e.g. re-entering plan mode)
        plan_exists = False
        if sandbox:
            try:
                res = await sandbox.execute(f"test -f {pp} && echo exists || echo missing", timeout=5)
                plan_exists = res.stdout.strip() == "exists"
            except Exception:
                plan_exists = False

            # Ensure the plans directory exists (matching opencode: mkdir -p on entry)
            if not plan_exists:
                try:
                    await sandbox.execute(f"mkdir -p $(dirname {pp})", timeout=5)
                except Exception:
                    pass

        reminder = build_plan_reminder(pp, plan_exists=plan_exists)

        # Persist as synthetic TextPart (matching opencode experimental path)
        if last_user_msg_id and session:
            from models.message import TextPart
            from session.session import save_part
            from core.identifier import ascending
            # Check if already persisted (avoid duplicates on re-entry)
            from session.session import check_message_has_synthetic_text
            has_synthetic_reminder = await check_message_has_synthetic_text(last_user_msg_id)
            if not has_synthetic_reminder:
                reminder_part = TextPart(
                    id=ascending("part"),
                    text=reminder,
                    synthetic=True,
                    session_id=session.id,
                    message_id=last_user_msg_id,
                )
                await save_part(reminder_part, is_new=True, user_id=user_id)

        # Still modify in-memory content for THIS iteration
        for i in range(len(result) - 1, -1, -1):
            if result[i].get("role") == "user":
                result[i] = dict(result[i])
                result[i]["content"] = result[i].get("content", "") + "\n\n" + reminder
                break

    # Strip internal metadata before returning to LLM
    for msg in result:
        msg.pop("_synthetic", None)
        msg.pop("_ignored", None)

    return result


def _find_pending_compaction(msgs: list[MessageWithParts]) -> tuple | None:
    """Scan messages for a pending compaction part that needs processing.

    Returns (message, compaction_part_dict) or None.
    Checks the last user message for a compaction part without a completed
    summary response from the assistant.
    """
    if not msgs:
        return None

    # Walk backwards to find the last user message with a compaction part
    for msg in reversed(msgs):
        role = msg.role if isinstance(msg.role, str) else msg.role.value
        if role != "user":
            continue

        for part in (msg.parts or []):
            p = part if isinstance(part, dict) else (part.model_dump() if hasattr(part, "model_dump") else {})
            if isinstance(p, dict) and p.get("type") == "compaction":
                # Check if there's already a completed summary after this message
                found_msg = False
                for m2 in msgs:
                    if m2.id == msg.id:
                        found_msg = True
                        continue
                    if found_msg:
                        r2 = m2.role if isinstance(m2.role, str) else m2.role.value
                        if r2 == "assistant" and m2.summary:
                            return None  # Already processed
                return (msg, p)
        break  # Only check the last user message

    return None


async def _ensure_title(session_id: str, user_msg: MessageWithParts, user_id: str = "default") -> None:
    """Generate a title for the session using an LLM (small model).

    Matches opencode's ensureTitle pattern: uses a small/cheap model to generate
    a concise title from the user's first message.
    Falls back to truncation if LLM call fails.
    """
    try:
        text = ""
        for part in (user_msg.parts or []):
            p = part if isinstance(part, dict) else (part.model_dump() if hasattr(part, "model_dump") else {})
            if isinstance(p, dict) and p.get("type") == "text":
                # Skip synthetic parts
                if p.get("synthetic"):
                    continue
                text = p.get("text", "")
                break

        if not text:
            return

        # Try LLM-based title generation
        try:
            title = await _generate_title_with_llm(text)
        except Exception as e:
            log.debug(f"LLM title generation failed, using truncation: {e}")
            title = None

        if not title:
            # Fallback: truncate first line
            title = text.split("\n")[0][:100].strip()
            if len(text.split("\n")[0]) > 100:
                title += "..."

        await set_session_title(session_id, title, user_id=user_id)
    except Exception as e:
        log.warning(f"Failed to generate title: {e}")


async def _generate_title_with_llm(user_text: str) -> str | None:
    """Use mcp_filter_model (cheap/fast) to generate a session title.

    Uses the same model configured for MCP tool filtering to save costs.
    No max_tokens limit — thinking models need space for reasoning before content.
    """
    try:
        import litellm
        litellm.drop_params = True
        from agent.llm import _get_provider_kwargs
        from core.config import get_config

        config = get_config()
        # Use mcp_filter_model (cheap), fallback to main model
        model_id = config.mcp_filter_model or config.model or "openai/gpt-4o-mini"
        provider_kwargs = _get_provider_kwargs(model_id)

        response = await litellm.acompletion(
            model=model_id,
            messages=[
                {"role": "user", "content": (
                    "Generate a short title (max 10 words) for this conversation based on the user's message below. "
                    "Reply with ONLY the title text, nothing else. No quotes, no explanation.\n\n"
                    f"User message: {user_text[:500]}"
                )},
            ],
            temperature=0.6,
            **provider_kwargs,
        )

        title = (response.choices[0].message.content or "").strip()
        # Clean up: remove thinking tags, quotes, get first non-empty line
        import re
        title = re.sub(r"<think>[\s\S]*?</think>\s*", "", title)
        title = title.strip('"\'')
        lines = [l.strip() for l in title.split("\n") if l.strip()]
        title = lines[0] if lines else None
        if title and len(title) > 80:
            title = title[:77] + "..."
        return title

    except Exception as e:
        log.debug(f"LLM title generation error: {e}")
        return None


def _get_permission_rules(config) -> list:
    """Build permission rules from config.

    Defaults are designed for Docker sandbox mode:
    - Allow all tools by default (sandbox is the protection)
    - Ask before reading .env files (secrets shouldn't leak casually)
    - Ask on doom loop detection
    """
    from permission.permission import Rule

    # Start with sandbox defaults (matching opencode's agent defaults,
    # adapted for Docker sandbox where external_directory isn't needed)
    rules = [
        Rule(permission="*", pattern="*", action="allow"),
        Rule(permission="doom_loop", pattern="*", action="ask"),
        # Deny question/plan tools by default (agents override via their own rules)
        Rule(permission="question", pattern="*", action="deny"),
        Rule(permission="plan_enter", pattern="*", action="deny"),
        Rule(permission="plan_exit", pattern="*", action="deny"),
        # .env protection: mirrors github.com/github/gitignore Node.gitignore pattern
        Rule(permission="read", pattern="*.env", action="ask"),
        Rule(permission="read", pattern="*.env.*", action="ask"),
        Rule(permission="read", pattern="*.env.example", action="allow"),
    ]

    # Parse config permission rules (user config overrides defaults)
    perm_config = config.permission or {}
    for perm_name, rule_data in perm_config.items():
        if isinstance(rule_data, str):
            rules.append(Rule(permission=perm_name, pattern="*", action=rule_data))
        elif isinstance(rule_data, dict):
            # Support nested permission config: {"read": {"*.env": "allow", "*": "allow"}}
            for pattern, action in rule_data.items():
                if isinstance(action, str):
                    rules.append(Rule(permission=perm_name, pattern=pattern, action=action))

    return rules
