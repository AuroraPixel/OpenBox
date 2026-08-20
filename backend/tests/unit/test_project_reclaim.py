"""Reclaiming workspace directories.

This is the only thing that removes a deleted project's files: the sandbox
outlives sessions, and WUYING's delete_container does nothing. It runs
unattended against a directory full of the user's work, so the rules about what
it will *not* touch matter more than what it will.
"""
import pytest

import project.reclaim as reclaim
from project.workspace import TRASH_ROOT, WORKSPACE_ROOT


class FakeSandbox:
    """Records commands; answers `ls` and `find` from a scripted listing."""

    def __init__(self, present=(), stale_trash=()):
        self.present = list(present)
        self.stale_trash = list(stale_trash)
        self.commands = []

    async def execute(self, command, timeout=None, workdir=None):
        self.commands.append(command)
        if command.startswith(f"ls -1 {WORKSPACE_ROOT}"):
            return _Result("\n".join(self.present))
        if command.startswith("find "):
            return _Result("\n".join(self.stale_trash))
        return _Result("")


class _Result:
    def __init__(self, stdout="", exit_code=0):
        self.stdout = stdout
        self.stderr = ""
        self.exit_code = exit_code


@pytest.fixture
def slugs(monkeypatch):
    """Control what the database claims is live vs expired."""
    state = {"live": set(), "expired": set()}

    async def fake_live(user_id=None):
        return state["live"]

    async def fake_expired(user_id=None):
        return state["expired"]

    monkeypatch.setattr(reclaim, "_live_slugs", fake_live)
    monkeypatch.setattr(reclaim, "_expired_slugs", fake_expired)
    return state


@pytest.mark.asyncio
async def test_a_live_project_is_never_touched(slugs):
    slugs["live"] = {"my-app"}
    sandbox = FakeSandbox(present=["my-app"])
    result = await reclaim.reclaim(sandbox)
    assert result["binned"] == []
    assert not any("mv " in c for c in sandbox.commands)


@pytest.mark.asyncio
async def test_a_long_deleted_project_is_binned(slugs):
    slugs["expired"] = {"gone"}
    sandbox = FakeSandbox(present=["gone"])
    result = await reclaim.reclaim(sandbox)
    assert result["binned"] == ["gone"]
    assert any(f"mv {WORKSPACE_ROOT}/gone {TRASH_ROOT}/gone-" in c for c in sandbox.commands)


@pytest.mark.asyncio
async def test_a_recently_deleted_project_keeps_its_grace_period(slugs):
    # Deleted but not yet expired: absent from both sets.
    slugs["live"] = set()
    slugs["expired"] = set()
    sandbox = FakeSandbox(present=["just-deleted"])
    result = await reclaim.reclaim(sandbox)
    assert result["binned"] == []
    assert result["unknown"] == ["just-deleted"]


@pytest.mark.asyncio
async def test_an_unrecognised_directory_is_reported_not_deleted(slugs):
    # Something the database has never heard of is far likelier to be work
    # worth keeping than garbage worth deleting.
    sandbox = FakeSandbox(present=["mystery"])
    result = await reclaim.reclaim(sandbox)
    assert result["unknown"] == ["mystery"]
    assert not any("rm -rf" in c for c in sandbox.commands)


@pytest.mark.asyncio
async def test_openbox_internals_are_skipped(slugs):
    sandbox = FakeSandbox(present=[".openbox", ".hidden"])
    result = await reclaim.reclaim(sandbox)
    assert result["binned"] == []
    assert result["unknown"] == []


@pytest.mark.asyncio
async def test_stale_trash_is_purged(slugs):
    sandbox = FakeSandbox(stale_trash=[f"{TRASH_ROOT}/old-20260101-000000"])
    result = await reclaim.reclaim(sandbox)
    assert result["purged"] == [f"{TRASH_ROOT}/old-20260101-000000"]
    assert any(c == f"rm -rf {TRASH_ROOT}/old-20260101-000000" for c in sandbox.commands)


@pytest.mark.asyncio
async def test_a_purge_path_outside_the_trash_is_refused(slugs):
    # A bug producing an empty or wrong path here would otherwise expand into
    # `rm -rf /`, so the guard is checked explicitly.
    sandbox = FakeSandbox(stale_trash=["/workspace/my-app", "/", ""])
    await reclaim.reclaim(sandbox)
    assert not any("rm -rf" in c for c in sandbox.commands)


@pytest.mark.asyncio
async def test_dry_run_changes_nothing(slugs):
    slugs["expired"] = {"gone"}
    sandbox = FakeSandbox(present=["gone"], stale_trash=[f"{TRASH_ROOT}/x-1"])
    result = await reclaim.reclaim(sandbox, dry_run=True)
    assert result["binned"] == ["gone"]
    assert not any("mv " in c or "rm -rf" in c for c in sandbox.commands)


@pytest.mark.asyncio
async def test_no_sandbox_is_not_an_error(slugs):
    result = await reclaim.reclaim(None)
    assert result["binned"] == []
    assert result["skipped"] == "no sandbox"
