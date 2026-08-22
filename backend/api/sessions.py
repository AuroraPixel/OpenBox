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
    #: Ready file_assets ids — pulled from OSS into the sandbox before the
    #: agent loop starts, and attached to the user message as file parts.
    attachments: list[str] | None = None


class UpdateSessionBody(BaseModel):
    title: str | None = None
    agent: str | None = None
    model: str | None = None


class CommandBody(BaseModel):
    command: str
    arguments: str | None = None


async def _remember_model(session, requested: str | None, user_id: str) -> str:
    """Settle on a model for this turn and keep it on the session.

    Each conversation carries its own model, so reopening one restores what it
    was last using instead of snapping back to the global default. A model the
    deployment no longer offers is replaced here rather than at the provider,
    where it returns an opaque "no channel for model X" that the retry layer
    attempts five times before the turn fails.
    """
    from agent.model_resolve import resolve as resolve_model

    chosen, _dropped = resolve_model(requested or session.model, get_config(),
                                     context=f"session {session.id}")
    if chosen and chosen != session.model:
        await session_mod.update_session(session.id, model=chosen, user_id=user_id)
    return chosen


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
    # Validate at birth so a retired model never gets stored in the first place.
    from agent.model_resolve import resolve as resolve_model
    model, _ = resolve_model(body.model, config, context="new session")
    session = await session_mod.create_session(
        model=model,
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
    from project.workspace import workdir_for_session
    data = session.model_dump()
    # The project directory this session's tools run in (/workspace/<slug>).
    # The files panel scopes its tree here rather than to the whole sandbox.
    data["directory"] = await workdir_for_session(session)
    return data


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

    chosen_model = await _remember_model(session, body.model, user_id)

    user_msg = await session_mod.create_user_message(
        session_id=session_id,
        text=body.text,
        agent=body.agent or session.agent,
        model=chosen_model,
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

    # A model the deployment no longer offers must not reach the provider: it
    # comes back as an opaque "no channel for model X" that the retry layer
    # attempts five times before failing the turn.
    chosen_model = await _remember_model(session, body.model, user_id)

    user_msg = await session_mod.create_user_message(
        session_id=session_id,
        text=body.text,
        agent=body.agent or session.agent,
        model=chosen_model,
        variant=body.variant,
        client_message_id=body.client_message_id,
        output_format=body.format,
        user_id=user_id,
    )

    # Attachment cards: a file part per OSS asset on the user message, so the
    # chat renders previews instead of parsing paths out of the text trailer.
    if body.attachments:
        await _attach_file_parts(session_id, user_msg.id, user_id, body.attachments)

    # F4: Save to prompt history (fire-and-forget)
    try:
        from api.prompt_history import save_prompt_history_async
        asyncio.create_task(save_prompt_history_async(user_id, body.text))
    except Exception:
        pass

    # Launch agent loop in background
    from agent.loop import run_loop
    task = asyncio.create_task(_run_loop_with_log(session_id, user_id, body.attachments)); _background_tasks.add(task); task.add_done_callback(_background_tasks.discard)

    return {"ok": True}


async def _attach_file_parts(session_id: str, message_id: str, user_id: str, asset_ids: list[str]) -> None:
    from sqlalchemy import select
    from core.identifier import ascending
    from db.base import get_db_session
    from db.models.file_asset import FileAsset
    from models.message import FilePart

    async with get_db_session() as db:
        rows = (
            await db.execute(
                select(FileAsset).where(
                    FileAsset.id.in_(asset_ids),
                    FileAsset.user_id == user_id,
                    FileAsset.status == "ready",
                )
            )
        ).scalars().all()
    by_id = {r.id: r for r in rows}
    for asset_id in asset_ids:
        row = by_id.get(asset_id)
        if not row:
            continue
        await session_mod.save_part(
            FilePart(
                id=ascending("part"),
                path=f"/workspace/uploads/{row.name}",
                mime_type=row.mime,
                asset_id=row.id,
                oss_key=row.oss_key,
                size=row.size,
                session_id=session_id,
                message_id=message_id,
            ),
            is_new=True,
            user_id=user_id,
        )


# ─── Session fork ───

class ForkBody(BaseModel):
    message_id: str | None = None


class ReactionBody(BaseModel):
    reaction: str | None = None  # "up" | "down" | null to clear


class RegenerateBody(BaseModel):
    # Optional: retry on a different model. A turn that failed because of the
    # model it ran on is the main reason anyone presses regenerate.
    model: str | None = None


@router.get("/session/{session_id}/diff/step")
async def get_step_diff(
    session_id: str,
    from_snapshot: str,
    to_snapshot: str,
    current_user: dict = Depends(get_current_user),
):
    """Line-level diff for one step's snapshot range.

    The session diff is cumulative (first snapshot → last); a per-turn change
    card needs exactly what that step touched, which is this.
    """
    from snapshot import snapshot
    await _require_session_owned(session_id, current_user["user_id"])
    if not from_snapshot or not to_snapshot or from_snapshot == to_snapshot:
        return []
    return await snapshot.diff_full(from_snapshot, to_snapshot, session_id=session_id)


@router.post("/session/{session_id}/message/{message_id}/reaction")
async def set_message_reaction(
    session_id: str,
    message_id: str,
    body: ReactionBody,
    current_user: dict = Depends(get_current_user),
):
    """Thumbs up / down on an assistant reply (frontend-v2 message meta bar)."""
    user_id = current_user["user_id"]
    await _require_session_owned(session_id, user_id)
    if body.reaction not in (None, "up", "down"):
        raise HTTPException(400, "reaction must be 'up', 'down' or null")
    await session_mod.set_message_reaction(message_id, session_id, body.reaction)
    return {"ok": True, "reaction": body.reaction}


@router.delete("/session/{session_id}/message/{message_id}")
async def dismiss_failed_turn(
    session_id: str,
    message_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Remove a turn that failed, once the user has moved past it.

    Only errored assistant messages qualify — see `delete_failed_turn`. A 404
    here means "that message is not a failure", not "no such session".
    """
    user_id = current_user["user_id"]
    await _require_session_owned(session_id, user_id)
    removed = await session_mod.delete_failed_turn(session_id, message_id)
    if not removed:
        raise HTTPException(404, "No failed turn to dismiss at that message")
    return {"ok": True, "removed": removed}


@router.post("/session/{session_id}/regenerate/{message_id}")
async def regenerate_message(
    session_id: str,
    message_id: str,
    body: RegenerateBody | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Answer the same prompt again, discarding this assistant turn.

    `message_id` is the assistant message to replace. It and everything after
    it are removed, leaving the user message that prompted it as the newest in
    the history — which is exactly the state `run_loop` expects, so no new user
    message is created and the prompt is not duplicated.

    The common case is a turn that failed: the error is the only thing the user
    can see, and without this there is nothing to act on but retyping.
    """
    user_id = current_user["user_id"]
    config = get_config()
    await check_concurrent_agents(user_id, config)
    session = await session_mod.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(404, "Session not found")

    if session.status == SessionStatus.BUSY:
        # Same contract as prompt_async: the newest instruction wins, so cancel
        # the run in flight rather than refusing. Deleting messages out from
        # under a live loop is the one thing we must not do.
        from session.status import trigger_abort
        trigger_abort(session_id)
        await session_mod.set_session_status(session_id, SessionStatus.IDLE, user_id=user_id)
        await asyncio.sleep(0.3)

    # Let the caller switch models on the way, so "it failed on this model"
    # and "try it on another one" are a single action.
    if body and body.model:
        await _remember_model(session, body.model, user_id)

    last_user = await session_mod.delete_messages_from(session_id, message_id)
    if not last_user:
        raise HTTPException(404, "Nothing to regenerate: no prompt precedes that message")

    # No explicit "messages were deleted" event: the loop is about to emit a
    # fresh message stream for this same prompt, which is what any other open
    # tab needs anyway. The caller invalidates its own snapshot on success.
    task = asyncio.create_task(_run_loop_with_log(session_id, user_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"ok": True, "from_message": last_user}


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


class TodoAddBody(BaseModel):
    subject: str
    #: Insert right after this item; append when absent or unknown.
    after_id: str | None = None


async def _record_todo_edit(session_id: str, user_id: str, items: list) -> None:
    """Append the edited list to the conversation, as a TodoPart.

    The card is rebuilt from the part stream, not from the todo store, so an
    edit that only touched the store would be invisible on reload and would
    leave the tool rows around it attributed to the wrong task. The part
    hangs off the newest assistant message — a session with none has no card
    to edit yet, so there is nothing to record.
    """
    from models.message import TodoPart
    from session.session import get_messages, save_part

    messages = await get_messages(session_id, user_id=user_id)
    anchor = next((m for m in reversed(messages) if m.role == "assistant"), None)
    if anchor is None:
        return
    await save_part(
        TodoPart(
            items=items,
            source="user",
            session_id=session_id,
            message_id=anchor.id,
        ),
        is_new=True,
        user_id=user_id,
    )


@router.post("/session/{session_id}/todo/items")
async def add_todo_item(
    session_id: str, body: TodoAddBody, current_user: dict = Depends(get_current_user)
):
    """Add a task the user typed on the card."""
    user_id = current_user["user_id"]
    await _require_session_owned(session_id, user_id)

    subject = body.subject.strip()
    if not subject:
        raise HTTPException(status_code=400, detail="Task cannot be empty")

    from session.todo import add_notice, add_todo_item as add_item
    todo = await add_item(session_id, subject, after_id=body.after_id, user_id=user_id)
    await add_notice(session_id, f"- added: {subject}")
    await _record_todo_edit(session_id, user_id, todo.items)
    return todo.model_dump()


@router.delete("/session/{session_id}/todo/items/{item_id}")
async def remove_todo_item(
    session_id: str, item_id: str, current_user: dict = Depends(get_current_user)
):
    """Drop a task the user dismissed.

    Their own item goes away; one the model planned is marked cancelled, so
    the card keeps a struck-through trace and the model can see it was
    overruled rather than silently losing a step.
    """
    user_id = current_user["user_id"]
    await _require_session_owned(session_id, user_id)

    from session.todo import add_notice, get_todo, remove_todo_item as remove_item
    before = await get_todo(session_id)
    target = next((t for t in before.items if t.id == item_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Task not found")

    todo = await remove_item(session_id, item_id, user_id=user_id)
    await add_notice(session_id, f"- dropped: {target.subject}")
    await _record_todo_edit(session_id, user_id, todo.items)
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
    """Save the user's edits to the plan.

    Both copies have to move together. The file is what the build agent reads
    once the plan is approved; the plan part is what the card shows. Writing
    only the file would leave the user looking at the text they replaced while
    the agent went off and built something else.
    """
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
    await _sync_plan_part_content(session_id, body.content, user_id)
    return {"ok": True, "path": pp}


async def _sync_plan_part_content(session_id: str, content: str, user_id: str) -> None:
    """Point the newest plan part at what the user just saved."""
    from session.session import get_messages, update_part_data

    messages = await get_messages(session_id, user_id=user_id)
    for msg in reversed(messages):
        for part in reversed(msg.parts or []):
            p = part if isinstance(part, dict) else (
                part.model_dump() if hasattr(part, "model_dump") else {}
            )
            if isinstance(p, dict) and p.get("type") == "plan":
                p["content"] = content
                await update_part_data(p["id"], p, publish=True, user_id=user_id)
                return


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


async def _run_loop_with_log(session_id: str, user_id: str, attachment_ids: list[str] | None = None):
    """Wrapper that logs exceptions from run_loop.

    Attachments land in the sandbox BEFORE the loop starts — the message text
    references their /workspace/uploads paths, so the agent must find them.
    """
    # A stop nobody claimed belongs to work the user has already moved on from;
    # asking for new work retires it. A stop pressed from here on still lands,
    # because it is recorded after this point and consumed by register_run.
    from session.status import discard_pending_abort
    discard_pending_abort(session_id)
    try:
        if attachment_ids:
            try:
                await _deliver_attachments(session_id, user_id, attachment_ids)
            except Exception as e:
                import logging
                logging.getLogger("sessions").warning(f"attachment delivery failed for {session_id}: {e}")
        from agent.loop import run_loop
        await run_loop(session_id, user_id=user_id)
    except Exception as e:
        import logging
        logging.getLogger("sessions").error(f"run_loop FAILED for {session_id}: {e}", exc_info=True)


async def _deliver_attachments(session_id: str, user_id: str, asset_ids: list[str]) -> None:
    """Pull the message's OSS assets into the sandbox via obx-file."""
    from sqlalchemy import select
    from core.oss import get_oss
    from db.base import get_db_session
    from db.models.file_asset import FileAsset
    from sandbox.manager import sandbox_manager
    from sandbox.assets import deliver

    async with get_db_session() as db:
        rows = (
            await db.execute(
                select(FileAsset).where(
                    FileAsset.id.in_(asset_ids),
                    FileAsset.user_id == user_id,
                    FileAsset.status == "ready",
                )
            )
        ).scalars().all()
    if not rows:
        return
    client = await sandbox_manager.get_client(session_id, user_id=user_id)
    await deliver(client, f"{user_id}:{session_id}", get_oss(), rows)
