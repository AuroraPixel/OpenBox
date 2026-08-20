"""Single step of the agent loop: one LLM turn and the tool calls it produces.

Split out of `loop.py` along the same seam opencode draws between
`session/prompt.ts` (the outer loop) and `session/processor.ts` (one step), for
the same reason: the loop's job is deciding *whether to keep going*, and a
step's job is *running one turn*. Interleaving them produced a single function
with nine levels of nesting that could not be exercised without a live model,
a live sandbox and a database.

The contract is deliberately narrow. A step never decides the run's fate: it
classifies what happened and returns, and the loop applies policy — retry
budgets, compaction attempts, step ceilings. Notably a retryable LLM error
comes back as RETRY with no sleeping and no counter of its own.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum

from agent.agent import get_agent
from agent.compaction import create_compaction
from agent.doom_loop import DOOM_LOOP_THRESHOLD, is_repeat_of_recent
from agent.hooks import ToolHooks
from agent.llm import stream_llm
from agent.retry import ContextOverflowError, is_context_overflow, is_retryable
from bus import bus
from bus.events import (
    MESSAGE_TEXT_DELTA, PART_DELTA, SESSION_ERROR, SESSION_STATUS,
)
from core.identifier import ascending
from core.log import create_logger
from models.message import (
    ReasoningPart, TextPart, ToolPartData, ToolStatus,
)
from session.session import save_part, update_message_info, update_session
from tool.tool import ToolContext

log = create_logger("agent.processor")


class StepOutcome(str, Enum):
    """What the loop should do next."""

    CONTINUE = "continue"   # turn completed; the loop re-evaluates termination
    COMPACT = "compact"     # context overflowed; compaction has been requested
    RETRY = "retry"         # transient LLM failure; the loop owns the budget
    ERROR = "error"         # unrecoverable; the run ends


@dataclass
class StepResult:
    """Everything the loop needs to know about one turn."""

    outcome: StepOutcome
    finish_reason: str = "unknown"
    text: str = ""
    reasoning: str = ""
    usage: dict = field(default_factory=lambda: {"input": 0, "output": 0, "total": 0})
    # Completed tool parts from this step, appended to the loop's doom-loop
    # history. Returned rather than mutated so the step owns no shared state.
    completed_tool_parts: list = field(default_factory=list)
    agent_switch: str | None = None
    retry_reason: str | None = None
    error: str | None = None
    duration: float = 0.0


async def process_step(
    *,
    session_id: str,
    user_id: str,
    session,
    agent_def,
    system: list[str],
    llm_messages: list[dict],
    tools: dict,
    model_id: str,
    ctx: ToolContext,
    hooks: ToolHooks,
    assistant_info,
    sandbox,
    abort,
    doom_loop_history: list,
    user_variant: str | None = None,
    tool_choice: str | None = None,
) -> StepResult:
    """Run one LLM turn: stream it, persist its parts, execute its tool calls.

    `doom_loop_history` is read, never written — new parts come back on the
    result so the caller stays the only writer.
    """
    collected_text = ""
    collected_reasoning = ""
    text_part_id = None
    reasoning_part_id = None
    pending_tool_calls = []      # collected during the stream, executed after
    streaming_tool_parts: dict[int, str] = {}   # tool-call index -> part id
    total_usage = {"input": 0, "output": 0, "total": 0}
    finish_reason = "unknown"
    completed_tool_parts: list = []
    agent_switch: str | None = None
    step_start_time = time.time()

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
            tool_choice=tool_choice,
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
            if is_repeat_of_recent(doom_loop_history, tool_name, tool_args):
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
                completed_tool_parts.append(tool_part)

                # plan_exit: stop the loop so the user can review
                if result.metadata.get("plan_ready"):
                    finish_reason = "stop"

    except ContextOverflowError:
        await create_compaction(session_id, auto=True, user_id=user_id)
        finish_reason = "compact"
    except Exception as e:
        retry_msg = is_retryable(e)
        if retry_msg:
            # Classify only. Whether to retry at all, and how long to wait, is
            # retry *policy* — it belongs to the caller that owns the attempt
            # counter, not to a single step.
            return StepResult(
                outcome=StepOutcome.RETRY,
                retry_reason=retry_msg,
                error=str(e),
                duration=time.time() - step_start_time,
            )
        log.error(f"LLM error in session {session_id}: {e}")
        bus.publish(SESSION_ERROR, {
            "userId": user_id,
            "sessionId": session_id,
            "error": {"message": str(e)},
        })
        assistant_info.error = {"message": str(e)}
        await update_message_info(assistant_info, user_id=user_id)
        return StepResult(
            outcome=StepOutcome.ERROR,
            error=str(e),
            duration=time.time() - step_start_time,
        )

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

    return StepResult(
        outcome=StepOutcome.COMPACT if finish_reason == "compact" else StepOutcome.CONTINUE,
        finish_reason=finish_reason,
        text=collected_text,
        reasoning=collected_reasoning,
        usage=total_usage,
        completed_tool_parts=completed_tool_parts,
        agent_switch=agent_switch,
        duration=time.time() - step_start_time,
    )
