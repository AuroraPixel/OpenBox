"""Skills are read from disk on a long-lived server.

The cache used to be filled once and never invalidated, so adding or editing a
skill did nothing until a restart — and the stale description kept going out to
the model on every request.
"""
import asyncio
import os
import shutil
import tempfile
from pathlib import Path

import pytest

import skill.skill as sk


def write_skill(base: Path, name: str, description: str) -> Path:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\nbody")
    return d


@pytest.fixture
def skills_dir(monkeypatch):
    """A throwaway project with a .openbox/skills tree, cache reset around it."""
    root = Path(tempfile.mkdtemp())
    base = root / ".openbox" / "skills"
    base.mkdir(parents=True)
    cwd = os.getcwd()
    os.chdir(root)
    monkeypatch.setattr(sk, "_skills", {})
    monkeypatch.setattr(sk, "_loaded", False)
    monkeypatch.setattr(sk, "_fingerprint", ())
    monkeypatch.setattr(sk, "_last_check", 0.0)
    # The throttle exists to bound I/O, not to be exercised here.
    monkeypatch.setattr(sk, "_CHECK_INTERVAL_SECONDS", 0.0)
    yield base
    os.chdir(cwd)
    shutil.rmtree(root, ignore_errors=True)


async def names():
    return sorted(s.name for s in await sk.list_skills())


@pytest.mark.asyncio
async def test_an_edited_description_is_picked_up(skills_dir):
    write_skill(skills_dir, "demo", "first")
    assert [s.description for s in await sk.list_skills()] == ["first"]

    write_skill(skills_dir, "demo", "second")
    assert [s.description for s in await sk.list_skills()] == ["second"]


@pytest.mark.asyncio
async def test_a_new_skill_appears(skills_dir):
    write_skill(skills_dir, "demo", "d")
    assert await names() == ["demo"]

    write_skill(skills_dir, "later", "d")
    assert await names() == ["demo", "later"]


@pytest.mark.asyncio
async def test_a_skill_nested_below_the_root_appears(skills_dir):
    # Only the nested directory's mtime changes, not the root's.
    write_skill(skills_dir, "demo", "d")
    await sk.list_skills()
    write_skill(skills_dir / "group", "deep", "d")
    assert "deep" in await names()


@pytest.mark.asyncio
async def test_a_removed_skill_disappears(skills_dir):
    write_skill(skills_dir, "demo", "d")
    write_skill(skills_dir, "gone", "d")
    assert await names() == ["demo", "gone"]

    shutil.rmtree(skills_dir / "gone")
    assert await names() == ["demo"]


@pytest.mark.asyncio
async def test_get_skill_sees_changes_too(skills_dir):
    write_skill(skills_dir, "demo", "first")
    assert (await sk.get_skill("demo")).description == "first"
    write_skill(skills_dir, "demo", "second")
    assert (await sk.get_skill("demo")).description == "second"


@pytest.mark.asyncio
async def test_an_unchanged_tree_is_not_rescanned(skills_dir, monkeypatch):
    write_skill(skills_dir, "demo", "d")
    await sk.list_skills()

    calls = []
    real = sk.load_skills

    async def counting():
        calls.append(1)
        await real()

    monkeypatch.setattr(sk, "load_skills", counting)
    for _ in range(5):
        await sk.list_skills()
    assert not calls, "a quiet directory must not trigger a reload"


@pytest.mark.asyncio
async def test_the_throttle_bounds_how_often_disk_is_touched(skills_dir, monkeypatch):
    write_skill(skills_dir, "demo", "d")
    await sk.list_skills()

    monkeypatch.setattr(sk, "_CHECK_INTERVAL_SECONDS", 3600.0)
    monkeypatch.setattr(sk, "_last_check", sk.time.monotonic())
    probes = []
    monkeypatch.setattr(sk, "_current_fingerprint",
                        lambda: probes.append(1) or ())
    for _ in range(10):
        await sk.list_skills()
    assert not probes, "within the interval, disk should not be stat-ed at all"
