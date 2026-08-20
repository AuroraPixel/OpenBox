"""A scheduled task runs where the session that scheduled it runs.

Cron sessions used to be pinned to the default project, so "check my build
every morning", set up inside a project, executed against a different directory
and found nothing there.
"""
import pytest

import cron.executor as executor
import cron.reaper as reaper


class FakeSession:
    def __init__(self, sid, model="m"):
        self.id = sid
        self.model = model


@pytest.fixture
def captured(monkeypatch):
    """Capture the arguments create_session is called with."""
    calls = []

    async def fake_create_session(**kwargs):
        calls.append(kwargs)
        return FakeSession("session_TEMP")

    async def fake_get_session(sid, user_id=None, **kw):
        return FakeSession(sid, model="parent-model")

    import session.session as sess
    monkeypatch.setattr(sess, "create_session", fake_create_session)
    monkeypatch.setattr(sess, "get_session", fake_get_session)
    return calls


@pytest.mark.asyncio
async def test_the_temp_session_inherits_the_parent_project(captured, monkeypatch):
    import session.session as sess

    async def fake_project_id_for(session_id):
        return "proj_SNAKE"

    monkeypatch.setattr(sess, "project_id_for", fake_project_id_for)

    await executor._create_temp_session({
        "id": "job1", "user_id": "u1", "session_id": "session_PARENT",
        "name": "nightly", "agent": "build", "model": "m",
    })
    assert captured[0]["project_id"] == "proj_SNAKE"
    assert captured[0]["parent_id"] == "session_PARENT"


@pytest.mark.asyncio
async def test_a_parent_with_no_project_falls_back_to_the_default(captured, monkeypatch):
    import session.session as sess

    async def fake_project_id_for(session_id):
        return ""

    monkeypatch.setattr(sess, "project_id_for", fake_project_id_for)

    await executor._create_temp_session({
        "id": "job1", "user_id": "u1", "session_id": "gone",
        "name": "nightly", "agent": "build", "model": "m",
    })
    # None means "resolve the default" downstream rather than writing a bad id.
    assert captured[0]["project_id"] is None


@pytest.mark.asyncio
async def test_a_failing_sweep_step_does_not_stop_the_others(monkeypatch):
    # The workspace sweep needs a sandbox; the database ones do not. An
    # unreachable sandbox must not stop the cleanup that always works.
    ran = []

    async def ok_a(): ran.append("a")
    async def boom(): raise RuntimeError("sandbox down")
    async def ok_c(): ran.append("c")

    monkeypatch.setattr(reaper, "_sweep_temp_sessions", ok_a)
    monkeypatch.setattr(reaper, "_sweep_old_runs", boom)
    monkeypatch.setattr(reaper, "_sweep_workspace", ok_c)
    monkeypatch.setattr(reaper, "_last_sweep_at_ms", 0)

    await reaper.sweep_if_due()
    assert ran == ["a", "c"]


@pytest.mark.asyncio
async def test_the_sweep_respects_its_interval(monkeypatch):
    ran = []

    async def step(): ran.append(1)

    monkeypatch.setattr(reaper, "_sweep_temp_sessions", step)
    monkeypatch.setattr(reaper, "_sweep_old_runs", step)
    monkeypatch.setattr(reaper, "_sweep_workspace", step)
    monkeypatch.setattr(reaper, "_last_sweep_at_ms", 0)

    await reaper.sweep_if_due()
    first = len(ran)
    await reaper.sweep_if_due()  # immediately again
    assert len(ran) == first, "a second sweep inside the interval must be skipped"
