"""`computer` must be able to open a browser, not hunt for its icon.

The failure this covers, observed live: the user closed the desktop's Chrome,
and the agent — mid computer-use task — went looking for a launcher. It clicked
dock coordinates, pressed super, typed "Chrome", pressed Return, and eventually
alt+F4, never reaching a browser.

Two things were wrong. There was no action that opens one, so the icon hunt was
the only move available. And the hunt is not merely unreliable: Chrome started
from its icon has no remote-debugging port, so dev-browser cannot drive it —
succeeding would have produced a browser that looks right and fails later.
"""
import pytest

from tool.computer import ComputerArgs, computer_tool, execute


class _Ctx:
    """Minimal ToolContext stand-in — these paths never reach the sandbox."""

    def __init__(self, sandbox=None):
        self.sandbox = sandbox
        self.user_id = "u1"
        self.session_id = "s1"


def test_open_browser_is_an_available_action():
    """It has to be in the schema, or the model cannot call it."""
    assert "open_browser" in str(ComputerArgs.model_fields["action"].annotation)


def test_the_description_steers_away_from_the_icon_hunt():
    """The action existing is not enough — the tool has to say when to use it,
    at the moment the model is standing in front of a missing browser."""
    text = computer_tool.description
    assert "open_browser" in text
    assert "icon" in text, "the description must name the wrong move, not just the right one"


@pytest.mark.asyncio
async def test_without_a_sandbox_it_says_so_plainly():
    result = await execute(ComputerArgs(action="open_browser"), _Ctx(sandbox=None))
    assert "no sandbox" in result.title.lower()


@pytest.mark.asyncio
async def test_a_launch_failure_forbids_the_icon_fallback(monkeypatch):
    """A model told only "it failed" will try the next plausible thing, which
    is the icon. The error has to close that door explicitly."""
    import sandbox.browser as browser_mod
    import session.browser_pref as pref_mod

    async def boom(*_a, **_k):
        raise RuntimeError("chrome did not open its debug port")

    async def mode(*_a, **_k):
        return "auto"

    monkeypatch.setattr(browser_mod, "ensure_browser", boom)
    monkeypatch.setattr(pref_mod, "get_browser_mode", mode)

    result = await execute(ComputerArgs(action="open_browser"), _Ctx(sandbox=object()))

    assert result.metadata.get("error") is True
    assert "debug port" in result.output
    assert "clicking a browser icon" in result.output.lower()


@pytest.mark.asyncio
async def test_opening_the_user_own_browser_warns_it_is_not_on_this_screen(monkeypatch):
    """In extension mode the browser runs on the user's machine. An agent that
    then screenshots this desktop sees no browser and starts hunting again."""
    import sandbox.browser as browser_mod
    import session.browser_pref as pref_mod

    async def ready(*_a, **_k):
        return {"mode": "extension"}

    async def mode(*_a, **_k):
        return "remote"

    monkeypatch.setattr(browser_mod, "ensure_browser", ready)
    monkeypatch.setattr(pref_mod, "get_browser_mode", mode)

    result = await execute(ComputerArgs(action="open_browser"), _Ctx(sandbox=object()))

    assert result.metadata["mode"] == "extension"
    assert "NOT on this" in result.output


def test_an_agent_that_can_open_a_browser_can_also_drive_one():
    """Tool whitelists have to stay coherent as a set, not just individually.

    `general` carried `computer` and `browser_mode` but not `skill`. With
    `open_browser` it could now start a browser and then have no way to drive
    one — leaving it to click pixels, which is exactly what the system prompt
    forbids. `skill` grants no extra authority here (these agents already have
    `bash`, which can run anything a skill instructs); what it grants is the
    instructions.
    """
    from agent.agent import AGENTS

    for name, agent_def in AGENTS.items():
        tools = getattr(agent_def, "tools", None)
        if tools and "computer" in tools:
            assert "skill" in tools, (
                f"agent {name!r} can open a browser but cannot load dev-browser to use it"
            )
