"""What survives when the model rewrites the todo list.

The model sends a complete list on every write and knows nothing about ids,
about items the user added, or about items the user cancelled. Everything
here is about what the merge has to preserve anyway.
"""
import pytest

from models.message import TodoItem
from session.todo import merge_todos


def item(subject, status="pending", source="model", **kw):
    return TodoItem(subject=subject, status=status, source=source, **kw)


# ── identity ──

def test_an_unchanged_item_keeps_its_id():
    before = [item("read the file"), item("write the file")]
    after = merge_todos(before, [item("read the file"), item("write the file")])
    assert [t.id for t in after] == [t.id for t in before]


def test_a_reworded_item_keeps_the_id_of_the_one_it_replaced():
    before = [item("read the file"), item("write the file")]
    after = merge_todos(before, [item("read the config file"), item("write the file")])
    assert after[0].id == before[0].id


def test_a_genuinely_new_item_gets_a_new_id():
    before = [item("read the file")]
    after = merge_todos(before, [item("read the file"), item("run the tests")])
    assert after[1].id != before[0].id


def test_a_real_match_is_not_stolen_by_an_earlier_positional_guess():
    # "b" moved to the front. Matching in order would let the reworded "z"
    # claim previous[0] before "b" — which is its own item — got the chance.
    before = [item("b"), item("c")]
    after = merge_todos(before, [item("z"), item("b")])
    assert after[1].id == before[0].id
    assert after[0].id not in {t.id for t in before}


# ── start time ──

def test_a_task_that_starts_is_stamped():
    after = merge_todos([item("build")], [item("build", status="in_progress")])
    assert after[0].started_at


def test_a_running_task_keeps_the_time_it_actually_started():
    started = merge_todos([item("build")], [item("build", status="in_progress")])
    again = merge_todos(started, [item("build", status="in_progress")])
    assert again[0].started_at == started[0].started_at


def test_a_task_that_has_not_started_has_no_start_time():
    after = merge_todos([], [item("build")])
    assert after[0].started_at is None


# ── the user's items ──

def test_an_item_the_user_added_survives_a_write_that_omits_it():
    before = [item("model task"), item("user task", source="user")]
    after = merge_todos(before, [item("model task")])
    assert [t.subject for t in after] == ["model task", "user task"]


def test_a_user_item_the_model_adopts_is_not_duplicated():
    before = [item("user task", source="user")]
    after = merge_todos(before, [item("user task"), item("model task")])
    assert [t.subject for t in after] == ["user task", "model task"]
    assert after[0].id == before[0].id
    assert after[0].source == "user"


def test_a_completed_user_item_does_not_come_back():
    before = [item("user task", status="completed", source="user")]
    after = merge_todos(before, [item("user task", status="completed")])
    assert len(after) == 1


# ── the user's veto ──

def test_a_cancelled_item_stays_cancelled_when_the_model_still_wants_it():
    before = [item("scrap this", status="cancelled")]
    after = merge_todos(before, [item("scrap this", status="in_progress")])
    assert after[0].status == "cancelled"


def test_a_cancelled_item_is_gone_once_the_model_drops_it():
    before = [item("scrap this", status="cancelled"), item("keep this")]
    after = merge_todos(before, [item("keep this")])
    assert [t.subject for t in after] == ["keep this"]


def test_a_cancelled_item_is_not_given_a_start_time():
    before = [item("scrap this", status="cancelled")]
    after = merge_todos(before, [item("scrap this", status="in_progress")])
    assert after[0].started_at is None


# ── ordinary rewrites ──

def test_status_otherwise_follows_the_model():
    before = [item("build", status="in_progress")]
    after = merge_todos(before, [item("build", status="completed")])
    assert after[0].status == "completed"


def test_clearing_the_list_leaves_nothing_but_the_users_own_items():
    before = [item("model task"), item("user task", source="user")]
    assert [t.subject for t in merge_todos(before, [])] == ["user task"]


def test_two_tasks_sharing_a_subject_keep_two_rows():
    before = [item("retry"), item("retry")]
    after = merge_todos(before, [item("retry"), item("retry")])
    assert {t.id for t in after} == {t.id for t in before}
