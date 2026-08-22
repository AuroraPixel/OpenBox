"""Session-level todo list storage.

The model rewrites the whole list on every ``todo_write`` (opencode's
full-replacement semantics), which makes duplicate items structurally
impossible. But the list has a second author — the user, who can add and
cancel items from the card — and a blind replacement would throw their
edits away every time the model spoke. So a write is a *merge*, not an
overwrite: see :func:`merge_todos` for what survives and why.
"""
import asyncio
from datetime import datetime, timezone

from bus import bus
from bus.events import TODO_UPDATED
from models.message import TodoItem, TodoList
from storage import storage

#: One lock per session, so that a model write and a user edit cannot
#: interleave their read-merge-write. Same shape as snapshot.py's per-gitdir
#: locks; there is no session-wide lock in this codebase to borrow.
_locks: dict[str, asyncio.Lock] = {}


def session_lock(session_id: str) -> asyncio.Lock:
    """The write lock for one session's todo list.

    Every path that reads-then-writes the list must hold this, or the last
    writer silently wins and one side's edit disappears.
    """
    lock = _locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[session_id] = lock
    return lock


async def get_todo(session_id: str) -> TodoList:
    """Get todo list for a session."""
    data = await storage.read(["todo", session_id])
    if data:
        return TodoList(**data)
    return TodoList()


async def save_todo(session_id: str, todo: TodoList, user_id: str = "default") -> None:
    """Save todo list and broadcast update."""
    await storage.write(["todo", session_id], todo.model_dump())
    bus.publish(
        TODO_UPDATED,
        {
            "userId": user_id,
            "sessionId": session_id,
            # Carried so the card can render straight from the event. Without
            # it every change costs a round-trip, and the list visibly lags
            # the tool rows that belong under it.
            "items": [item.model_dump() for item in todo.items],
        },
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def merge_todos(previous: list[TodoItem], incoming: list[TodoItem]) -> list[TodoItem]:
    """Fold the model's new list into what the session already had.

    The model does not know about ids, and it does not know what the user
    changed behind its back. Four things therefore survive a replacement:

    * **Identity.** An item matched to an existing one keeps its id, so the
      UI's expand state and progress bar stay attached to the same row
      instead of resetting on every write.
    * **Start time.** ``started_at`` is stamped once, when an item first
      becomes in_progress, and then carried forward.
    * **User items.** Anything the user added stays on the list even though
      the model's replacement omits it — it has no idea it exists yet.
    * **Cancellations.** An item the user cancelled stays cancelled, even
      when the model's list still has it as pending or in_progress. The
      model is working from a stale copy; the user's veto wins until the
      model drops the item entirely.

    Matching is by subject, falling back to position — the model does not
    echo ids back, so there is nothing sturdier to match on. Rewording a
    task therefore reads as a new item; that is documented, not fixed.
    """
    by_subject: dict[str, list[TodoItem]] = {}
    for item in previous:
        by_subject.setdefault(item.subject, []).append(item)

    claimed: set[str] = set()
    matches: list[TodoItem | None] = []

    # Pass 1 — exact subject. Done for the whole list before any positional
    # guess, so a later item's real match is never stolen by an earlier
    # item's fallback.
    for item in incoming:
        old = next(
            (c for c in by_subject.get(item.subject, []) if c.id not in claimed), None
        )
        if old is not None:
            claimed.add(old.id)
        matches.append(old)

    # Pass 2 — same slot, reworded. Only unclaimed items are still available,
    # so this can only ever pick up an item nothing else wanted.
    for index, old in enumerate(matches):
        if old is not None or index >= len(previous):
            continue
        positional = previous[index]
        if positional.id in claimed:
            continue
        claimed.add(positional.id)
        matches[index] = positional

    merged: list[TodoItem] = []
    for item, old in zip(incoming, matches):
        if old is None:
            merged.append(
                item.model_copy(
                    update={"started_at": _now() if item.status == "in_progress" else None}
                )
            )
            continue
        status = item.status
        if old.status == "cancelled":
            status = "cancelled"
        elif old.source == "user" and status == "cancelled":
            # The model does not get to drop a task the user asked for. Left
            # to itself it reads an unfamiliar item as leftover noise and
            # cancels it — which is precisely what the user's edit existed to
            # prevent. Only the user removes their own tasks.
            status = old.status
        started_at = old.started_at
        if status == "in_progress" and not started_at:
            started_at = _now()
        merged.append(
            item.model_copy(
                update={
                    "id": old.id,
                    "status": status,
                    "source": old.source,
                    "started_at": started_at,
                }
            )
        )

    # User items the model never saw. Kept in their original relative order,
    # appended after the model's list — inserting them mid-list would fight
    # with the ordering the model just expressed.
    survivors = [
        item for item in previous if item.source == "user" and item.id not in claimed
    ]
    return merged + survivors


async def replace_todos(
    session_id: str, items: list[TodoItem], user_id: str = "default"
) -> TodoList:
    """Apply the model's full-replacement write, merged with what exists."""
    async with session_lock(session_id):
        previous = await get_todo(session_id)
        todo = TodoList(items=merge_todos(previous.items, items))
        await save_todo(session_id, todo, user_id=user_id)
        return todo


def pacing_note(
    previous: list[TodoItem], incoming: list[TodoItem], merged: list[TodoItem]
) -> str:
    """What to tell the model about *how* it is using the list.

    Left to itself a model treats the list as paperwork: it writes the plan,
    does all the work, then marks everything done in one final write. The
    list ends up correct and completely useless — it never says which task
    was running, so nothing that happened can be attributed to a step, and
    the user watches an unchanging list for the whole run.

    Saying so in the tool description is not enough; it is one paragraph in
    a long page the model skims once. Saying it here puts it in the tool's
    own result, at the exact moment the mistake was made.

    Takes the model's own ``incoming`` list as well as the ``merged`` result,
    because some of what it needs to hear is about a change the merge just
    refused to make.
    """
    was_done = {t.id for t in previous if t.status == "completed"}
    just_done = [t for t in merged if t.status == "completed" and t.id not in was_done]
    running = [t for t in merged if t.status == "in_progress"]
    waiting = [t for t in merged if t.status == "pending"]
    dropped = {t.subject for t in incoming if t.status == "cancelled"}
    refused = [
        t for t in merged
        if t.source == "user" and t.status != "cancelled" and t.subject in dropped
    ]

    lines: list[str] = []
    if len(just_done) > 1:
        lines.append(
            f"You marked {len(just_done)} tasks complete in one write. Mark each "
            "task complete as you finish it, not in a batch at the end — the "
            "user is watching this list to follow along."
        )
    if len(running) > 1:
        lines.append(
            f"{len(running)} tasks are in_progress. Exactly one task may be "
            "in_progress at a time."
        )
    if refused:
        subjects = ", ".join(f'"{t.subject}"' for t in refused)
        lines.append(
            f"You cannot cancel a task the user added ({subjects}); it is still "
            "on the list. Do the work it describes and mark it completed. If it "
            "is genuinely already done, mark it completed rather than cancelled."
        )
    if not running and waiting:
        lines.append(
            f'Nothing is in_progress. Before you start the next task, call '
            f'todo_write again marking "{waiting[0].subject}" as in_progress. '
            "Do that first, then do the work."
        )
    return "\n".join(lines)


async def pending_notices(session_id: str) -> list[str]:
    """Edits the user made that the model has not been told about yet."""
    data = await storage.read(["todo_notice", session_id])
    return list(data.get("notices", [])) if data else []


async def add_notice(session_id: str, notice: str) -> None:
    """Queue one line to hand the model at the start of its next step.

    The merge already guarantees a user's item survives, so a lost notice
    costs attention, not data — the item is still on the list either way.
    """
    notices = await pending_notices(session_id)
    notices.append(notice)
    await storage.write(["todo_notice", session_id], {"notices": notices[-20:]})


async def take_notices(session_id: str) -> list[str]:
    """Read the queued notices and clear them, so they are said once."""
    notices = await pending_notices(session_id)
    if notices:
        await storage.write(["todo_notice", session_id], {"notices": []})
    return notices


async def add_todo_item(
    session_id: str,
    subject: str,
    after_id: str | None = None,
    user_id: str = "default",
) -> TodoList:
    """Add a task the user typed, optionally right after an existing one."""
    async with session_lock(session_id):
        todo = await get_todo(session_id)
        item = TodoItem(subject=subject, source="user")
        items = list(todo.items)
        index = next((i for i, t in enumerate(items) if t.id == after_id), None)
        if index is None:
            items.append(item)
        else:
            items.insert(index + 1, item)
        merged = TodoList(items=items)
        await save_todo(session_id, merged, user_id=user_id)
        return merged


async def remove_todo_item(
    session_id: str, item_id: str, user_id: str = "default"
) -> TodoList:
    """Drop a task the user dismissed.

    A task the user added is removed outright. A task the *model* planned is
    marked cancelled instead, so the card keeps a struck-through trace of the
    refusal and the model can see its plan was overruled.
    """
    async with session_lock(session_id):
        todo = await get_todo(session_id)
        items: list[TodoItem] = []
        for item in todo.items:
            if item.id != item_id:
                items.append(item)
            elif item.source == "model":
                items.append(item.model_copy(update={"status": "cancelled"}))
        merged = TodoList(items=items)
        await save_todo(session_id, merged, user_id=user_id)
        return merged
