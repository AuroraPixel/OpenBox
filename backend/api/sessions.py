"""Session routes: CRUD + messages + agent control."""
import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from auth.middleware import get_current_user
from auth.quota import check_session_quota, check_concurrent_agents
from core.config import get_config
from session import session as session_mod
from models.message import SessionStatus
from session.status import trigger_abort

_background_tasks = set()  # prevent GC of background tasks

router = APIRouter(dependencies=[Depends(get_current_user)])


class CreateSessionBody(BaseModel):
    model: str = ""
    agent: str = "build"
    title: str | None = None
    #: Project the session runs in. Accepts an id or a slug; omitting it files
    #: the session under the user's default project.
    project_id: str | None = None


class PromptBody(BaseModel):
    text: str
    agent: str | None = None
    model: str | None = None
    variant: str | None = None
    client_message_id: str | None = None
    # {"type": "json_schema", "schema": {...}} to require a structured answer.
    format: dict | None = None


class UpdateSessionBody(BaseModel):
    title: str | None = None
    agent: str | None = None
    model: str | None = None


class CommandBody(BaseModel):
    command: str
    arguments: str | None = None


async def _require_session_owned(session_id: str, user_id: str):
    session = await session_mod.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session


# ─── Sandbox Status ───

@router.get("/sandbox/status")
async def sandbox_status(current_user: dict = Depends(get_current_user)):
    """Check if a sandbox container is available and healthy."""
    user_id = current_user["user_id"]
    from sandbox.manager import sandbox_manager
    return await sandbox_manager.check_health(user_id=user_id)


@router.get("/session/{session_id}/sandbox")
async def get_session_sandbox(session_id: str, current_user: dict = Depends(get_current_user)):
    """Get sandbox container info bound to this session."""
    user_id = current_user["user_id"]
    session = await session_mod.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(404, "Session not found")

    from sandbox.manager import sandbox_manager
    info = sandbox_manager.get_info(session_id)
    if info and info.user_id and info.user_id != user_id:
        return {"available": False}
    if not info:
        # No sandbox tracked for this session — fall back to health check
        health = await sandbox_manager.check_health(user_id=user_id)
        if health.get("available"):
            return {
                "available": True,
                "container_id": health["container_id"],
                "container_name": health.get("container_name"),
            }
        return {"available": False}
    return {
        "available": True,
        "container_id": info.container_id,
        "port": info.port,
        "project_id": session.project_id,
    }


# ─── Session CRUD ───

@router.post("/session")
async def create_session(
    body: CreateSessionBody = CreateSessionBody(),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    config = get_config()
    await check_session_quota(user_id, config)
    session = await session_mod.create_session(
        model=body.model,
        agent=body.agent,
        title=body.title,
        user_id=user_id,
        project_id=body.project_id,
    )
    return session.model_dump()


@router.get("/session")
async def list_sessions(
    project_id: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Sessions for the user; pass project_id to narrow to one project."""
    user_id = current_user["user_id"]
    sessions = await session_mod.list_sessions(project_id=project_id, user_id=user_id)
    return [s.model_dump() for s in sessions]


@router.get("/session/{session_id}")
async def get_session(session_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    session = await session_mod.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session.model_dump()


@router.delete("/session/{session_id}")
async def delete_session(session_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    await session_mod.delete_session(session_id, user_id=user_id)
    return {"ok": True}


@router.patch("/session/{session_id}")
async def update_session(session_id: str, body: UpdateSessionBody, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    session = await session_mod.update_session(session_id, user_id=user_id, **updates)
    if not session:
        raise HTTPException(404, "Session not found")
    return session.model_dump()


# ─── Messages ───

@router.get("/session/{session_id}/message")
async def get_messages(session_id: str, offset: int = 0, limit: int = 200, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    await _require_session_owned(session_id, user_id)
    messages = await session_mod.get_messages(session_id, offset=offset, limit=limit, user_id=user_id)
    return [m.model_dump() for m in messages]


@router.post("/session/{session_id}/message")
async def send_message(
    session_id: str,
    body: PromptBody,
    current_user: dict = Depends(get_current_user),
):
    """Send a message synchronously (blocks until agent completes)."""
    user_id = current_user["user_id"]
    session = await session_mod.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.status == SessionStatus.BUSY:
        from session.status import trigger_abort
        trigger_abort(session_id)
        await session_mod.set_session_status(session_id, SessionStatus.IDLE, user_id=user_id)
        await asyncio.sleep(0.3)

    # Chat preflight: ensure user sandbox exists.
    from sandbox.manager import sandbox_manager
    await sandbox_manager.get_client(session_id, user_id=user_id)

    user_msg = await session_mod.create_user_message(
        session_id=session_id,
        text=body.text,
        agent=body.agent or session.agent,
        model=body.model,
        variant=body.variant,
        client_message_id=body.client_message_id,
        output_format=body.format,
        user_id=user_id,
    )

    from agent.loop import run_loop
    result = await run_loop(session_id, user_id=user_id)

    if result:
        return result.model_dump()
    return user_msg.model_dump()


@router.post("/session/{session_id}/prompt_async")
async def send_message_async(
    session_id: str,
    body: PromptBody,
    current_user: dict = Depends(get_current_user),
):
    """Send a message asynchronously (returns immediately, updates via SSE)."""
    user_id = current_user["user_id"]
    config = get_config()
    await check_concurrent_agents(user_id, config)
    session = await session_mod.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.status == SessionStatus.BUSY:
        # Force abort the running loop and reset status so user can send again.
        # This matches opencode's cancel() behavior: abort + set idle immediately.
        from session.status import trigger_abort
        trigger_abort(session_id)
        await session_mod.set_session_status(session_id, SessionStatus.IDLE, user_id=user_id)
        # Give the old loop a moment to detect the abort signal
        await asyncio.sleep(0.3)

    # Sandbox preflight moved into run_loop — don't block the HTTP response.
    # The agent loop calls sandbox_manager.get_client() which auto-creates
    # containers if needed. This lets the response return immediately.

    user_msg = await session_mod.create_user_message(
        session_id=session_id,
        text=body.text,
        agent=body.agent or session.agent,
        model=body.model,
        variant=body.variant,
        client_message_id=body.client_message_id,
        output_format=body.format,
        user_id=user_id,
    )

    # F4: Save to prompt history (fire-and-forget)
    try:
        from api.prompt_history import save_prompt_history_async
        asyncio.create_task(save_prompt_history_async(user_id, body.text))
    except Exception:
        pass

    # Launch agent loop in background
    from agent.loop import run_loop
    task = asyncio.create_task(_run_loop_with_log(session_id, user_id)); _background_tasks.add(task); task.add_done_callback(_background_tasks.discard)

    return {"ok": True}


# ─── Session fork ───

class ForkBody(BaseModel):
    message_id: str | None = None


@router.post("/session/{session_id}/fork")
async def fork_session_endpoint(
    session_id: str,
    body: ForkBody,
    current_user: dict = Depends(get_current_user),
):
    """Fork a session from a specific message point."""
    user_id = current_user["user_id"]
    session = await session_mod.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(404, "Session not found")

    from session.fork import fork_session
    new_session = await fork_session(
        source_session_id=session_id,
        up_to_message_id=body.message_id,
        user_id=user_id,
    )
    return new_session


# ─── Plan accept / reject ───

@router.post("/session/{session_id}/plan/accept")
async def accept_plan(session_id: str, current_user: dict = Depends(get_current_user)):
    """User accepted the plan — switch to build agent."""
    user_id = current_user["user_id"]
    from tool.plan import _update_plan_part_status
    from session.session import get_session, plan_path_for

    await _require_session_owned(session_id, user_id)
    await _update_plan_part_status(session_id, "accepted")

    session = await get_session(session_id, user_id=user_id)
    rel_path = (await plan_path_for(session)).replace("/workspace/", "") if session else ""
    await session_mod.create_user_message(
        session_id=session_id,
        text=f"The plan at {rel_path} has been approved, you can now edit files. Execute the plan",
        agent="build",
        model=session.model if session else None,
        synthetic=True,
        user_id=user_id,
    )

    from agent.loop import run_loop
    task = asyncio.create_task(_run_loop_with_log(session_id, user_id)); _background_tasks.add(task); task.add_done_callback(_background_tasks.discard)
    return {"ok": True}


@router.post("/session/{session_id}/plan/reject")
async def reject_plan(session_id: str, current_user: dict = Depends(get_current_user)):
    """User rejected the plan — plan agent regenerates."""
    user_id = current_user["user_id"]
    from tool.plan import _update_plan_part_status
    from session.session import get_session

    await _require_session_owned(session_id, user_id)
    await _update_plan_part_status(session_id, "rejected")

    session = await get_session(session_id, user_id=user_id)
    await session_mod.create_user_message(
        session_id=session_id,
        text="The user rejected the plan. Please revise and create a better plan based on their feedback.",
        agent="plan",
        model=session.model if session else None,
        synthetic=True,
        user_id=user_id,
    )

    from agent.loop import run_loop
    task = asyncio.create_task(_run_loop_with_log(session_id, user_id)); _background_tasks.add(task); task.add_done_callback(_background_tasks.discard)
    return {"ok": True}


@router.post("/session/{session_id}/abort")
async def abort_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """Abort a running session."""
    user_id = current_user["user_id"]
    await _require_session_owned(session_id, user_id)
    trigger_abort(session_id)
    await session_mod.set_session_status(session_id, SessionStatus.IDLE, user_id=user_id)
    return {"ok": True}


# ─── Compaction ───

@router.post("/session/{session_id}/summarize")
async def summarize_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Manually trigger context compaction.

    Creates the compaction request, then runs the agent loop in the background
    so the compaction is actually processed (matching opencode's flow).
    """
    user_id = current_user["user_id"]
    await _require_session_owned(session_id, user_id)
    from agent.compaction import create_compaction
    await create_compaction(session_id, auto=False, user_id=user_id)

    # Run agent loop so the compaction gets processed
    from agent.loop import run_loop
    background_tasks.add_task(run_loop, session_id, user_id)
    return {"ok": True}


# ─── Revert ───

@router.post("/session/{session_id}/revert/{message_id}")
async def revert_to_message(session_id: str, message_id: str, current_user: dict = Depends(get_current_user)):
    """Revert session to a specific message (undo changes)."""
    user_id = current_user["user_id"]
    await _require_session_owned(session_id, user_id)
    from session.revert import revert_to_message as do_revert
    success = await do_revert(session_id, message_id)
    if not success:
        raise HTTPException(400, "Revert failed: no snapshot found for message")
    return {"ok": True}


@router.post("/session/{session_id}/unrevert")
async def unrevert(session_id: str, current_user: dict = Depends(get_current_user)):
    """Undo a revert."""
    user_id = current_user["user_id"]
    await _require_session_owned(session_id, user_id)
    from session.revert import unrevert as do_unrevert
    success = await do_unrevert(session_id)
    if not success:
        raise HTTPException(400, "Unrevert failed: no revert to undo")
    return {"ok": True}


# ─── Command ───

@router.post("/session/{session_id}/command")
async def execute_command(
    session_id: str,
    body: CommandBody,
    current_user: dict = Depends(get_current_user),
):
    """Execute a slash command."""
    user_id = current_user["user_id"]
    from command.command import get_command, execute_command as resolve_command

    # Look up the command
    cmd_info = await get_command(body.command)
    if not cmd_info:
        raise HTTPException(404, f"Command '{body.command}' not found")

    # Resolve the command template with arguments
    resolved_text = await resolve_command(body.command, body.arguments or "")

    # Validate session
    session = await session_mod.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.status == SessionStatus.BUSY:
        raise HTTPException(409, "Session is busy")

    # Use command's agent if specified, otherwise fall back to session's agent
    agent = cmd_info.agent or session.agent

    # Create a user message with the resolved command text
    await session_mod.create_user_message(
        session_id=session_id,
        text=resolved_text,
        agent=agent,
        user_id=user_id,
    )

    # Launch agent loop in background (results arrive via SSE)
    from agent.loop import run_loop
    task = asyncio.create_task(_run_loop_with_log(session_id, user_id)); _background_tasks.add(task); task.add_done_callback(_background_tasks.discard)

    return {"ok": True}


# ─── Todo ───

@router.get("/session/{session_id}/todo")
async def get_todo(session_id: str, current_user: dict = Depends(get_current_user)):
    # Ownership check is mandatory; todo key is session_id-based.
    # Without this, users can read others' todo lists by guessing IDs.
    user_id = current_user["user_id"]
    await _require_session_owned(session_id, user_id)
    from session.todo import get_todo
    todo = await get_todo(session_id)
    return todo.model_dump()


# ─── Plan ───

class PlanUpdateBody(BaseModel):
    content: str


@router.get("/session/{session_id}/plan")
async def get_plan(session_id: str, current_user: dict = Depends(get_current_user)):
    """Read plan file content from sandbox."""
    user_id = current_user["user_id"]
    session = await session_mod.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(404, "Session not found")

    from session.session import plan_path_for
    pp = await plan_path_for(session)

    from sandbox import sandbox_manager
    client = await sandbox_manager.get_client(session_id, user_id=user_id)
    if not client:
        raise HTTPException(404, "No sandbox for session")

    try:
        content = await client.read_file_raw(pp)
        return {"content": content, "path": pp}
    except (FileNotFoundError, Exception):
        return {"content": None, "path": pp}


@router.put("/session/{session_id}/plan")
async def update_plan(session_id: str, body: PlanUpdateBody, current_user: dict = Depends(get_current_user)):
    """Write plan file content to sandbox."""
    user_id = current_user["user_id"]
    session = await session_mod.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(404, "Session not found")

    from session.session import plan_path_for
    pp = await plan_path_for(session)

    from sandbox import sandbox_manager
    client = await sandbox_manager.get_client(session_id, user_id=user_id)
    if not client:
        raise HTTPException(404, "No sandbox for session")

    await client.write_file(pp, body.content)
    return {"ok": True, "path": pp}


# ─── Diff ───

@router.get("/session/{session_id}/diff")
async def get_diff(session_id: str, full: bool = False, current_user: dict = Depends(get_current_user)):
    """Get file change diff for a session.

    Uses the first and last snapshots in the session to compute the diff.
    Pass ?full=true to include hunks with line-level detail.
    """
    from snapshot import snapshot
    from db.base import get_db_session
    from db.models.part import Part as PartORM
    from sqlalchemy import select
    user_id = current_user["user_id"]
    await _require_session_owned(session_id, user_id)

    # Find first step-start and last step-finish snapshots directly from parts table.
    # This avoids loading all messages/parts (which can be expensive on long sessions).
    first_snapshot = None
    last_snapshot = None
    async with get_db_session() as db:
        result = await db.execute(
            select(PartORM.type, PartORM.data)
            .where(
                PartORM.session_id == session_id,
                PartORM.type.in_(("step-start", "step-finish")),
            )
            .order_by(PartORM.created_at.asc())
        )
        rows = result.all()

    if not rows:
        return []

    for part_type, part_data in rows:
        p = part_data if isinstance(part_data, dict) else {}
        snapshot_id = p.get("snapshot")
        if not snapshot_id:
            continue
        if part_type == "step-start" and not first_snapshot:
            first_snapshot = snapshot_id
        elif part_type == "step-finish":
            last_snapshot = snapshot_id

    if not first_snapshot or not last_snapshot:
        return []

    if full:
        return await snapshot.diff_full(first_snapshot, last_snapshot, session_id=session_id)
    else:
        diffs = await snapshot.diff(first_snapshot, last_snapshot, session_id=session_id)
        return [{"path": d.path, "additions": d.additions, "deletions": d.deletions, "status": d.status} for d in diffs]


async def _run_loop_with_log(session_id: str, user_id: str):
    """Wrapper that logs exceptions from run_loop."""
    try:
        from agent.loop import run_loop
        await run_loop(session_id, user_id=user_id)
    except Exception as e:
        import logging
        logging.getLogger("sessions").error(f"run_loop FAILED for {session_id}: {e}", exc_info=True)
