"""The user's side of the todo list: adding, dropping, and being announced.

Storage is stubbed to a dict — these are about the rules, not about where
the JSON lands.
"""
import pytest

import session.todo as todo_mod
from agent.loop import _insert_todo_notices, _unnudged_user_todos
from models.message import TodoItem


@pytest.fixture(autouse=True)
def fake_storage(monkeypatch):
    """An in-memory stand-in for the storage layer."""
    store: dict[str, dict] = {}

    async def read(key):
        return store.get("/".join(key))

    async def write(key, value):
        store["/".join(key)] = value

    monkeypatch.setattr(todo_mod.storage, "read", read)
    monkeypatch.setattr(todo_mod.storage, "write", write)
    monkeypatch.setattr(todo_mod.bus, "publish", lambda *a, **k: None)
    return store


# ── adding ──

async def test_an_added_task_lands_at_the_end():
    await todo_mod.replace_todos("s", [TodoItem(subject="first")])
    todo = await todo_mod.add_todo_item("s", "mine")
    assert [t.subject for t in todo.items] == ["first", "mine"]


async def test_an_added_task_is_marked_as_the_users():
    todo = await todo_mod.add_todo_item("s", "mine")
    assert todo.items[0].source == "user"
    assert todo.items[0].status == "pending"


async def test_a_task_can_be_inserted_after_a_specific_one():
    await todo_mod.replace_todos("s", [TodoItem(subject="a"), TodoItem(subject="b")])
    first = (await todo_mod.get_todo("s")).items[0]
    todo = await todo_mod.add_todo_item("s", "wedged", after_id=first.id)
    assert [t.subject for t in todo.items] == ["a", "wedged", "b"]


async def test_an_unknown_anchor_appends_rather_than_failing():
    await todo_mod.replace_todos("s", [TodoItem(subject="a")])
    todo = await todo_mod.add_todo_item("s", "mine", after_id="nonesuch")
    assert [t.subject for t in todo.items] == ["a", "mine"]


# ── dropping ──

async def test_dropping_the_users_own_task_removes_it():
    todo = await todo_mod.add_todo_item("s", "mine")
    todo = await todo_mod.remove_todo_item("s", todo.items[0].id)
    assert todo.items == []


async def test_dropping_a_planned_task_cancels_it_instead():
    await todo_mod.replace_todos("s", [TodoItem(subject="theirs")])
    item = (await todo_mod.get_todo("s")).items[0]
    todo = await todo_mod.remove_todo_item("s", item.id)
    assert [(t.subject, t.status) for t in todo.items] == [("theirs", "cancelled")]


async def test_a_cancelled_task_stays_cancelled_through_the_next_write():
    await todo_mod.replace_todos("s", [TodoItem(subject="theirs")])
    item = (await todo_mod.get_todo("s")).items[0]
    await todo_mod.remove_todo_item("s", item.id)
    todo = await todo_mod.replace_todos(
        "s", [TodoItem(subject="theirs", status="in_progress")]
    )
    assert todo.items[0].status == "cancelled"


async def test_an_added_task_survives_the_models_next_write():
    await todo_mod.replace_todos("s", [TodoItem(subject="theirs")])
    await todo_mod.add_todo_item("s", "mine")
    todo = await todo_mod.replace_todos(
        "s", [TodoItem(subject="theirs", status="completed")]
    )
    assert [t.subject for t in todo.items] == ["theirs", "mine"]


# ── announcing ──

async def test_notices_are_handed_over_once():
    await todo_mod.add_notice("s", "- added: mine")
    assert await todo_mod.take_notices("s") == ["- added: mine"]
    assert await todo_mod.take_notices("s") == []


async def test_a_notice_rides_along_on_the_last_user_message():
    await todo_mod.add_notice("s", "- added: mine")
    msgs = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "continue"},
    ]
    out = await _insert_todo_notices(msgs, "s")
    assert "- added: mine" in out[2]["content"]
    assert out[2]["content"].startswith("continue")
    assert out[0]["content"] == "go"


async def test_nothing_queued_leaves_the_messages_alone():
    msgs = [{"role": "user", "content": "go"}]
    assert await _insert_todo_notices(msgs, "s") is msgs


async def test_a_notice_survives_a_conversation_with_no_user_message():
    await todo_mod.add_notice("s", "- added: mine")
    out = await _insert_todo_notices([{"role": "assistant", "content": "x"}], "s")
    assert out == [{"role": "assistant", "content": "x"}]


# ── the end-of-run backstop ──

async def test_a_task_added_late_is_raised_before_the_run_ends():
    await todo_mod.add_todo_item("s", "mine")
    fresh = await _unnudged_user_todos("s", set())
    assert [t.subject for t in fresh] == ["mine"]


async def test_it_is_only_raised_once():
    await todo_mod.add_todo_item("s", "mine")
    seen = {t.id for t in await _unnudged_user_todos("s", set())}
    assert await _unnudged_user_todos("s", seen) == []


async def test_the_models_own_pending_task_is_not_raised_this_way():
    await todo_mod.replace_todos("s", [TodoItem(subject="theirs")])
    assert await _unnudged_user_todos("s", set()) == []


async def test_a_finished_task_is_not_raised():
    todo = await todo_mod.add_todo_item("s", "mine")
    await todo_mod.replace_todos(
        "s", [TodoItem(subject="mine", status="completed")]
    )
    assert await _unnudged_user_todos("s", set()) == []
