"""Cron job executor — runs agent in a temporary session.

Flow: summary(main session) → create temp session → run_loop → extract result → write cron_runs.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from core.log import create_logger
from core.identifier import ascending

log = create_logger("cron.executor")


async def execute_cron_job(job: dict) -> dict:
    """Execute a single cron job. Called by the timer.

    Returns {"status": "ok"|"error"|"skipped", "error"?: str, "summary_text"?: str, ...}
    """
    job_id = job["id"]
    user_id = job["user_id"]
    session_id = job["session_id"]
    job_name = job.get("name", "unnamed")

    log.info(f"Executing cron job {job_id} ({job_name}) for session {session_id}")

    # Publish start event
    from bus import bus
    from bus.events import CRON_JOB_STARTED
    bus.publish(CRON_JOB_STARTED, {
        "userId": user_id,
        "jobId": job_id,
        "sessionId": session_id,
        "jobName": job_name,
    })

    started_at = datetime.now(timezone.utc)
    run_id = ascending("cron_run")

    # Create cron_runs entry with status=running
    await _create_run_entry(run_id, job, started_at)

    temp_session_id = None
    try:
        # 1. Generate session summary (or reuse cache)
        context_summary = await _get_session_summary(job)

        # 2. Create temporary session
        temp_session_id = await _create_temp_session(job)

        # 3. Build prompt and inject into temp session
        prompt = _build_cron_prompt(job, context_summary)
        await _inject_prompt(temp_session_id, user_id, prompt)

        # 4. Acquire sandbox and run agent loop
        result_text = await _run_agent_loop(temp_session_id, user_id, job)

        # 5. Extract result
        ended_at = datetime.now(timezone.utc)
        duration_ms = int((ended_at - started_at).total_seconds() * 1000)

        # Update cron_runs
        await _update_run_entry(
            run_id, job_id, temp_session_id,
            status="ok",
            summary_text=result_text,
            context_summary=context_summary,
            ended_at=ended_at,
            duration_ms=duration_ms,
        )

        # Publish success event
        from bus.events import CRON_JOB_COMPLETED
        bus.publish(CRON_JOB_COMPLETED, {
            "userId": user_id,
            "jobId": job_id,
            "sessionId": session_id,
            "jobName": job_name,
            "runId": run_id,
            "durationMs": duration_ms,
        })

        # 6. Try to inject result into main session
        from cron.injector import try_inject_result
        await try_inject_result(run_id, job, result_text)

        log.info(f"Cron job {job_id} completed in {duration_ms}ms")
        return {"status": "ok", "summary_text": result_text, "run_id": run_id}

    except Exception as e:
        ended_at = datetime.now(timezone.utc)
        duration_ms = int((ended_at - started_at).total_seconds() * 1000)
        error_msg = str(e)

        await _update_run_entry(
            run_id, job_id, temp_session_id,
            status="error",
            error_message=error_msg,
            ended_at=ended_at,
            duration_ms=duration_ms,
        )

        from bus.events import CRON_JOB_FAILED
        bus.publish(CRON_JOB_FAILED, {
            "userId": user_id,
            "jobId": job_id,
            "sessionId": session_id,
            "jobName": job_name,
            "error": error_msg,
        })

        log.error(f"Cron job {job_id} failed after {duration_ms}ms: {error_msg}")
        return {"status": "error", "error": error_msg, "run_id": run_id}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_session_summary(job: dict) -> str:
    """Get or generate a summary of the main session's conversation history."""
    session_id = job["session_id"]
    cached_summary = job.get("summary_cache")
    cached_msg_id = job.get("summary_cache_msg_id")

    # Check if cache is still valid
    from session.session import get_messages
    messages = await get_messages(session_id)
    if not messages:
        return ""

    latest_msg_id = messages[-1].id if messages else None

    # Cache hit
    if cached_summary and cached_msg_id == latest_msg_id:
        log.debug(f"Summary cache hit for session {session_id}")
        return cached_summary

    # Check if there's a recent compaction summary we can reuse
    for msg in reversed(messages):
        if getattr(msg, "summary", False) and msg.role == "assistant":
            for part in (msg.parts or []):
                p = part if isinstance(part, dict) else (part.model_dump() if hasattr(part, "model_dump") else {})
                text = p.get("text", "")
                if text and len(text) > 50:
                    log.debug(f"Reusing compaction summary for session {session_id}")
                    # Update cache
                    await _update_summary_cache(job["id"], text, latest_msg_id)
                    return text

    # Generate new summary using LLM (small/cheap model)
    try:
        summary = await _generate_summary(messages, job)
        if summary:
            await _update_summary_cache(job["id"], summary, latest_msg_id)
            return summary
    except Exception as e:
        log.warning(f"Summary generation failed for session {session_id}: {e}")

    # Fallback: no summary
    return ""


async def _generate_summary(messages, job: dict) -> str:
    """Generate a summary of conversation history using LLM."""
    from agent.loop import _to_llm_messages
    from agent.llm import stream_llm

    llm_messages = _to_llm_messages(messages)

    # Truncate to last ~20 messages to keep summary request small
    if len(llm_messages) > 20:
        llm_messages = llm_messages[-20:]

    prompt = (
        "Summarize the conversation above in 200 words or less. "
        "Focus on: 1) What the user asked for, 2) What was accomplished, "
        "3) Key files or resources involved, 4) Any pending tasks."
    )
    llm_messages.append({"role": "user", "content": prompt})

    # Use a smaller model if available, otherwise use the job's model
    model_id = job.get("model") or "openai/gpt-4o-mini"

    summary = ""
    try:
        async for event in stream_llm(
            agent_def=None,
            system=[],
            messages=llm_messages,
            tools={},
            model_id=model_id,
        ):
            if event["type"] == "text_delta":
                summary += event["text"]
            elif event["type"] == "error":
                break
    except Exception as e:
        log.warning(f"Summary LLM call failed: {e}")

    return summary


async def _update_summary_cache(job_id: str, summary: str, msg_id: str | None) -> None:
    """Update the summary cache on the cron job."""
    from db.base import get_db_session
    from db.models.cron import CronJob
    from sqlalchemy import update

    async with get_db_session() as db:
        await db.execute(
            update(CronJob)
            .where(CronJob.id == job_id)
            .values(summary_cache=summary, summary_cache_msg_id=msg_id)
        )


async def _create_temp_session(job: dict) -> str:
    """Create a temporary session for cron execution."""
    from session.session import create_session
    from core.config import get_config

    # Resolve model: job override > main session model > config default
    model = job.get("model") or ""
    if not model:
        from session.session import get_session
        main_session = await get_session(job["session_id"], user_id=job["user_id"])
        if main_session and main_session.model:
            model = main_session.model
    if not model:
        config = get_config()
        model = config.model or ""

    # The run belongs in the same project as the session that scheduled it.
    # Pinning it to "default" meant a task set up from a project ran against a
    # different directory — "check my build every morning" would find nothing.
    from session.session import project_id_for
    project_id = await project_id_for(job["session_id"]) or None

    session = await create_session(
        user_id=job["user_id"],
        agent=job.get("agent", "build"),
        model=model,
        title=f"[Cron] {job.get('name', 'task')}",
        parent_id=job["session_id"],
        project_id=project_id,
    )
    return session.id


def _build_cron_prompt(job: dict, context_summary: str) -> str:
    """Build the prompt for cron execution."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = []

    if context_summary:
        parts.append(f"[Session Context Summary]\n{context_summary}")

    parts.append(
        f"[Scheduled Task: {job.get('name', 'unnamed')} | "
        f"job_id: {job['id']} | {now}]\n"
        f"{job['task_prompt']}"
    )

    return "\n\n".join(parts)


async def _inject_prompt(temp_session_id: str, user_id: str, prompt: str) -> None:
    """Inject the cron prompt as a user message in the temp session."""
    from session.session import create_user_message
    await create_user_message(
        session_id=temp_session_id,
        text=prompt,
        synthetic=True,
        user_id=user_id,
    )


async def _run_agent_loop(temp_session_id: str, user_id: str, job: dict) -> str:
    """Run the agent loop in the temp session and extract the result."""
    from sandbox import sandbox_manager

    # Ensure sandbox is available (may create container)
    try:
        sandbox = await sandbox_manager.get_client(temp_session_id, user_id=user_id)
    except Exception as e:
        log.warning(f"Sandbox acquisition failed for cron job {job['id']}: {e}")
        # Try to continue without sandbox (some tools may not work)
        sandbox = None

    # Run the agent loop
    from agent.loop import run_loop
    result_msg = await run_loop(temp_session_id, user_id)

    log.info(f"run_loop completed for temp session {temp_session_id}")

    # Check if the last assistant message has an error
    from session.session import get_messages as _get_temp_msgs
    temp_msgs = await _get_temp_msgs(temp_session_id)
    for msg in reversed(temp_msgs):
        role = msg.role if isinstance(msg.role, str) else msg.role.value
        if role == "assistant" and getattr(msg, "error", None):
            error_info = msg.error
            error_msg = error_info.get("message", str(error_info)) if isinstance(error_info, dict) else str(error_info)
            raise RuntimeError(f"Agent error: {error_msg}")

    # Extract all assistant text parts as the result
    # Agent may produce text across multiple assistant messages (between tool calls)
    from session.session import get_messages
    messages = await get_messages(temp_session_id)

    text_parts = []
    for msg in messages:
        role = msg.role if isinstance(msg.role, str) else msg.role.value
        if role != "assistant":
            continue
        for part in (msg.parts or []):
            p = part if isinstance(part, dict) else (part.model_dump() if hasattr(part, "model_dump") else {})
            if p.get("type") == "text" and p.get("text", "").strip():
                text_parts.append(p["text"].strip())

    if text_parts:
        # Use the last substantial text part as the primary result
        return text_parts[-1]

    # Fallback: check if there are any tool outputs we can summarize
    tool_outputs = []
    for msg in messages:
        role = msg.role if isinstance(msg.role, str) else msg.role.value
        if role != "assistant":
            continue
        for part in (msg.parts or []):
            p = part if isinstance(part, dict) else (part.model_dump() if hasattr(part, "model_dump") else {})
            if p.get("type") == "tool" and p.get("output"):
                output = p["output"]
                if isinstance(output, str) and len(output) > 10:
                    tool_outputs.append(output[:200])

    if tool_outputs:
        return "Tool execution completed:\n" + "\n---\n".join(tool_outputs[-3:])

    return "(No output)"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _create_run_entry(run_id: str, job: dict, started_at: datetime) -> None:
    """Create a cron_runs entry with status=running."""
    from db.base import get_db_session
    from db.models.cron import CronRun

    async with get_db_session() as db:
        row = CronRun(
            id=run_id,
            job_id=job["id"],
            user_id=job["user_id"],
            session_id=job["session_id"],
            status="running",
            task_prompt=job.get("task_prompt"),
            started_at=started_at,
        )
        db.add(row)


async def _update_run_entry(
    run_id: str,
    job_id: str,
    temp_session_id: str | None,
    status: str,
    summary_text: str | None = None,
    context_summary: str | None = None,
    error_message: str | None = None,
    ended_at: datetime | None = None,
    duration_ms: int = 0,
) -> None:
    """Update a cron_runs entry with final results."""
    from db.base import get_db_session
    from db.models.cron import CronRun
    from sqlalchemy import update

    values: dict = {
        "status": status,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
    }
    if temp_session_id:
        values["temp_session_id"] = temp_session_id
    if summary_text is not None:
        values["summary_text"] = summary_text
    if context_summary is not None:
        values["context_summary"] = context_summary
    if error_message is not None:
        values["error_message"] = error_message

    async with get_db_session() as db:
        await db.execute(
            update(CronRun).where(CronRun.id == run_id).values(**values)
        )
