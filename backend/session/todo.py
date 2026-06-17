"""Session-level todo list storage.

Uses full-replacement semantics (like opencode): the LLM provides the
complete todo list on every call, and the backend atomically replaces
all items.  This makes duplicate items structurally impossible.
"""
from bus import bus
from bus.events import TODO_UPDATED
from models.message import TodoItem, TodoList
from storage import storage


async def get_todo(session_id: str) -> TodoList:
    """Get todo list for a session."""
    data = await storage.read(["todo", session_id])
    if data:
        return TodoList(**data)
    return TodoList()


async def save_todo(session_id: str, todo: TodoList, user_id: str = "default") -> None:
    """Save todo list and broadcast update."""
    await storage.write(["todo", session_id], todo.model_dump())
    bus.publish(TODO_UPDATED, {"userId": user_id, "sessionId": session_id})


async def replace_todos(session_id: str, items: list[TodoItem], user_id: str = "default") -> TodoList:
    """Atomically replace the entire todo list for a session."""
    todo = TodoList(items=items)
    await save_todo(session_id, todo, user_id=user_id)
    return todo
