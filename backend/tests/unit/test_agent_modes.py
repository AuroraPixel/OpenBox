"""Which agents a person may pick, and which the task tool may spawn.

Two disjoint jobs that were sharing one list. `explore` and `general` are
built to be handed a single self-contained prompt and to answer once; they
have no conversational prompt, and `explore` cannot edit a file. They were
being offered as modes to chat in — two dead ends in the picker.
"""
import pytest

from agent.agent import AGENTS, get_agent, is_subagent, list_agents, list_subagents
from agent.loop import resolve_agent_name


class Session:
    def __init__(self, agent=None, parent_id=None):
        self.agent, self.parent_id = agent, parent_id


class UserMsg:
    def __init__(self, agent=None):
        self.agent = agent


# ── the picker ──

def test_a_person_can_pick_build_and_plan():
    assert {a.name for a in list_agents()} == {"build", "plan"}


def test_no_subagent_is_offered_as_a_mode():
    assert not any(a.mode == "subagent" for a in list_agents())


def test_nothing_hidden_is_offered():
    assert not any(a.hidden for a in list_agents())


# ── what task may spawn ──

def test_the_task_tool_may_spawn_the_subagents():
    assert {"explore", "general"} <= {a.name for a in list_subagents()}


def test_it_may_not_spawn_a_primary_agent():
    spawnable = {a.name for a in list_subagents()}
    assert "build" not in spawnable
    assert "plan" not in spawnable


def test_the_two_lists_do_not_overlap():
    assert not ({a.name for a in list_agents()} & {a.name for a in list_subagents()})


def test_every_agent_lands_in_one_list_or_is_hidden():
    covered = {a.name for a in list_agents()} | {a.name for a in list_subagents()}
    missing = {n for n, a in AGENTS.items() if n not in covered and not a.hidden}
    assert missing == set()


# ── the mode vocabulary ──

def test_only_the_two_modes_opencode_has_are_used():
    # opencode also has "all" for config-defined agents; we define none, so
    # the value would be unreachable. Nothing here may invent a third mode.
    assert {a.mode for a in AGENTS.values()} <= {"primary", "subagent"}


def test_is_subagent_agrees_with_the_definitions():
    assert is_subagent("explore") and is_subagent("general")
    assert not is_subagent("build") and not is_subagent("plan")


def test_an_unknown_name_is_not_a_subagent():
    assert not is_subagent("nonesuch")


# ── running as a session's agent ──

def test_a_top_level_session_ignores_a_subagent_and_falls_back():
    assert resolve_agent_name(UserMsg("explore"), Session()) == "build"


def test_a_subagent_stored_on_the_session_is_ignored_too():
    assert resolve_agent_name(UserMsg(), Session(agent="general")) == "build"


def test_a_child_session_may_run_its_subagent():
    session = Session(agent="explore", parent_id="session_parent")
    assert resolve_agent_name(UserMsg("explore"), session, is_child=True) == "explore"


def test_a_primary_agent_is_untouched():
    assert resolve_agent_name(UserMsg("plan"), Session()) == "plan"
    assert resolve_agent_name(UserMsg(), Session(agent="plan")) == "plan"


def test_the_default_is_still_build():
    assert resolve_agent_name(UserMsg(), Session()) == "build"


# ── the definitions themselves ──

def test_the_agents_match_opencode_by_name():
    assert set(AGENTS) == {
        "build", "plan", "explore", "general", "compaction", "title", "summary",
    }


def test_explore_cannot_edit():
    assert not ({"edit", "write", "multiedit", "apply_patch"} & set(get_agent("explore").tools))
