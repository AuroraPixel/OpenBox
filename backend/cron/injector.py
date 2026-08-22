"""Result injection — inject cron results into the main session.

Handles overflow checking, compaction before injection, and BUSY queueing.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.log import create_logger

log = create_logger("cron.injector")


async def try_inject_result(run_id: str, job: dict, result_text: str) -> bool:
    """Try to inject a cron result into the main session.

    If session is BUSY, the result stays in cron_runs with injected=False.
    It will be flushed when the session becomes IDLE (via flush_pending_cron_results).

    Returns True if injected immediately, False if queued.
    """
    session_id = job["session_id"]
    user_id = job["user_id"]

    # Check session status
    from session.session import get_session
    session = await get_session(session_id, user_id=user_id)
    if not session:
        log.warning(f"Cannot inject cron result: session {session_id} not found")
        return False

    status = session.status if isinstance(session.status, str) else session.status.value
    if status == "busy":
        log.info(f"Session {session_id} is BUSY, queueing cron result {run_id}")
        return False

    # Session is IDLE, inject directly
    return await _do_inject(run_id, job, result_text, session_id, user_id)


async def flush_pending_cron_results(session_id: str, user_id: str) -> int:
    """Flush all pending cron results into the session.

    Called from run_loop's finally block, BEFORE setting session to IDLE.
    Returns number of results injected.
    """
    from db.base import get_db_session
    from db.models.cron import CronRun, CronJob
    from sqlalchemy import select

    async with get_db_session() as db:
        result = await db.execute(
            select(CronRun)
            .where(
                CronRun.session_id == session_id,
                CronRun.status == "ok",
                CronRun.injected == False,
            )
            .order_by(CronRun.started_at.asc())
        )
        pending = result.scalars().all()

    if not pending:
        return 0

    log.info(f"Flushing {len(pending)} pending cron result(s) for session {session_id}")

    injected_count = 0
    for run in pending:
        try:
            # Get job info for the name
            async with get_db_session() as db:
                job_result = await db.execute(
                    select(CronJob).where(CronJob.id == run.job_id)
                )
                job = job_result.scalar_one_or_none()

            job_name = job.name if job else "unknown"
            summary = run.summary_text or "(No output)"

            # Check overflow before injection
            await _check_and_compact_if_needed(session_id, user_id, job_name, summary)

            # Inject the messages
            await _inject_messages(session_id, user_id, run.job_id, job_name, run.task_prompt or "", summary)

            # Mark as injected
            await _mark_injected(run.id)
            injected_count += 1

            # Publish injection event
            from bus import bus
            from bus.events import CRON_JOB_INJECTED
            bus.publish(CRON_JOB_INJECTED, {
                "userId": user_id,
                "sessionId": session_id,
                "jobId": run.job_id,
                "runId": run.id,
                "jobName": job_name,
            })

        except Exception as e:
            log.error(f"Failed to inject cron result {run.id}: {e}")

    return injected_count


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _do_inject(run_id: str, job: dict, result_text: str, session_id: str, user_id: str) -> bool:
    """Actually inject the result messages into the session."""
    job_name = job.get("name", "unnamed")
    task_prompt = job.get("task_prompt", "")

    try:
        # Check overflow
        await _check_and_compact_if_needed(session_id, user_id, job_name, result_text)

        # Inject messages
        await _inject_messages(session_id, user_id, job["id"], job_name, task_prompt, result_text)

        # Mark as injected
        await _mark_injected(run_id)

        # Publish event
        from bus import bus
        from bus.events import CRON_JOB_INJECTED
        bus.publish(CRON_JOB_INJECTED, {
            "userId": user_id,
            "sessionId": session_id,
            "jobId": job["id"],
            "runId": run_id,
            "jobName": job_name,
        })

        log.info(f"Injected cron result {run_id} into session {session_id}")
        return True

    except Exception as e:
        log.error(f"Failed to inject cron result {run_id}: {e}")
        return False


async def _check_and_compact_if_needed(
    session_id: str, user_id: str, job_name: str, result_text: str
) -> None:
    """Check if injecting would overflow context, compact if needed."""
    from session.session import get_session
    from agent.compaction import is_overflow, get_model_context_limit
    from models.message import TokenUsage

    session = await get_session(session_id, user_id=user_id)
    if not session or not session.token_usage:
        return

    # Rough estimate: 1 token ≈ 4 chars
    inject_tokens = (len(job_name) + len(result_text)) // 4 + 100
    current_context = session.token_usage.context or 0
    limit = session.token_usage.limit or get_model_context_limit(session.model or "")

    # If injection would push past 90% of limit, compact first
    if current_context + inject_tokens > limit * 0.9:
        log.info(f"Compacting session {session_id} before cron injection (context={current_context}, inject~{inject_tokens}, limit={limit})")
        try:
            from agent.compaction import create_compaction, process_compaction
            from session.session import get_messages
            await create_compaction(session_id, auto=True, user_id=user_id)
            messages = await get_messages(session_id, user_id=user_id)
            model_id = session.model or "openai/claude-sonnet-4-20250514"
            await process_compaction(session_id, messages, model_id, auto=True, user_id=user_id)
        except Exception as e:
            log.warning(f"Pre-injection compaction failed: {e}")


async def _inject_messages(
    session_id: str, user_id: str, job_id: str,
    job_name: str, task_prompt: str, result_text: str
) -> None:
    """Create the synthetic user + assistant message pair in the session."""
    from session.session import create_user_message, create_assistant_message, save_part
    from models.message import TextPart
    from core.identifier import ascending

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Synthetic user message: the task
    user_text = f"[Scheduled Task: {job_name} | job_id: {job_id} | {now}]\n{task_prompt}"
    user_msg = await create_user_message(
        session_id=session_id,
        text=user_text,
        synthetic=True,
        user_id=user_id,
    )

    # Assistant message: the result
    assistant_info = await create_assistant_message(
        session_id=session_id,
        parent_id=user_msg.id,
        agent="cron",
        user_id=user_id,
    )

    # Add text part with the result
    text_part = TextPart(
        id=ascending("part"),
        text=result_text,
        session_id=session_id,
        message_id=assistant_info.id,
    )
    await save_part(text_part, is_new=True, user_id=user_id)

    # Mark assistant as finished
    from session.session import update_message_info
    assistant_info.finish = "stop"
    await update_message_info(assistant_info, user_id=user_id)


async def _mark_injected(run_id: str) -> None:
    """Mark a cron_runs entry as injected."""
    from db.base import get_db_session
    from db.models.cron import CronRun
    from sqlalchemy import update

    now = datetime.now(timezone.utc)

    async with get_db_session() as db:
        await db.execute(
            update(CronRun)
            .where(CronRun.id == run_id)
            .values(injected=True, injected_at=now)
        )
