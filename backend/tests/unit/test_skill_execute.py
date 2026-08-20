"""Loading a skill — what the model gets back, and what it is told went wrong.

Skills come from two places with different reach: the container, whose files
the agent's tools can open, and the backend host, whose files they cannot.
Conflating the two, or reporting an unreachable container as a missing skill,
both send the model down a path it cannot recover from.
"""
import os
import shutil
import tempfile
from pathlib import Path

import pytest

import skill.skill as sk
from tool.skill_tool import SkillArgs, execute
from tool.tool import ToolContext


class DeadSandbox:
    """A container that cannot be reached — e.g. the SSH tunnel dropped."""

    async def get_skill(self, name):
        raise ConnectionError("tunnel down: connection refused")

    async def list_skills(self):
        raise ConnectionError("tunnel down")


class LiveSandbox:
    def __init__(self, payload):
        self.payload = payload

    async def get_skill(self, name):
        return self.payload


@pytest.fixture
def host_skill(monkeypatch):
    """A skill on the backend host, with bundled files beside it."""
    root = Path(tempfile.mkdtemp())
    d = root / ".openbox" / "skills" / "demo"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: demo\ndescription: d\n---\nRun scripts/setup.sh")
    (d / "scripts").mkdir()
    (d / "scripts" / "setup.sh").write_text("x")
    (d / "reference").mkdir()
    (d / "reference" / "api.md").write_text("x")
    cwd = os.getcwd()
    os.chdir(root)
    monkeypatch.setattr(sk, "_skills", {})
    monkeypatch.setattr(sk, "_loaded", False)
    monkeypatch.setattr(sk, "_fingerprint", ())
    monkeypatch.setattr(sk, "_last_check", 0.0)
    monkeypatch.setattr(sk, "_CHECK_INTERVAL_SECONDS", 0.0)
    yield d
    os.chdir(cwd)
    shutil.rmtree(root, ignore_errors=True)


def ctx(sandbox=None):
    c = ToolContext(session_id="s")
    c.sandbox = sandbox
    return c


@pytest.mark.asyncio
async def test_a_host_skill_returns_its_content(host_skill):
    out = (await execute(SkillArgs(skill="demo"), ctx())).output
    assert "Run scripts/setup.sh" in out


@pytest.mark.asyncio
async def test_a_host_skills_bundled_files_are_named(host_skill):
    # Without these the model is told to run scripts/setup.sh with no idea
    # what exists.
    out = (await execute(SkillArgs(skill="demo"), ctx())).output
    assert "scripts/setup.sh" in out
    assert "reference/api.md" in out


@pytest.mark.asyncio
async def test_a_host_skill_does_not_hand_over_an_unreachable_path(host_skill):
    # The agent's tools run in the sandbox; the host path would only produce
    # failed reads.
    out = (await execute(SkillArgs(skill="demo"), ctx())).output
    assert str(host_skill) not in out
    assert "NOT readable from here" in out


@pytest.mark.asyncio
async def test_a_container_skill_keeps_its_base_directory(host_skill):
    payload = {"content": "body", "base_dir": "/workspace/skills/pdf",
               "files": ["a.py"]}
    out = (await execute(SkillArgs(skill="pdf"), ctx(LiveSandbox(payload)))).output
    assert "/workspace/skills/pdf" in out
    assert "NOT readable from here" not in out, "container files are reachable"


@pytest.mark.asyncio
async def test_an_unreachable_container_is_not_reported_as_a_missing_skill(host_skill):
    # "Not found" tells the model to give up on a skill that may well exist.
    result = await execute(SkillArgs(skill="pdf-tools"), ctx(DeadSandbox()))
    assert result.metadata.get("error") == "container_unreachable"
    assert "unreachable" in result.output.lower()
    assert "retry" in result.output.lower()


@pytest.mark.asyncio
async def test_a_genuinely_missing_skill_still_says_so(host_skill):
    result = await execute(SkillArgs(skill="nope"), ctx())
    assert "not found" in result.title.lower()
    assert result.metadata.get("error") != "container_unreachable"


@pytest.mark.asyncio
async def test_the_host_copy_is_used_when_the_container_lacks_the_skill(host_skill):
    # A dropped container must not hide a skill that is available locally.
    out = (await execute(SkillArgs(skill="demo"), ctx(DeadSandbox()))).output
    assert "Run scripts/setup.sh" in out


@pytest.mark.asyncio
async def test_arguments_are_substituted(host_skill):
    (host_skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: d\n---\nTarget is $ARGUMENTS")
    out = (await execute(SkillArgs(skill="demo", args="prod"), ctx())).output
    assert "Target is prod" in out
