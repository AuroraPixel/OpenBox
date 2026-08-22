"""Config folded over the built-in agents.

The same config entry retunes a built-in, hides it, removes it, or introduces
one of the user's own — matching opencode's `agent` block. Before this the
registry was a frozen dict and config could only reach a handful of run-time
fields, so an agent you defined simply did not exist.
"""
import pytest

import agent.agent as mod
from core.config import AgentOverride


class Cfg:
    def __init__(self, agent):
        self.agent = agent


@pytest.fixture
def with_config(monkeypatch):
    def apply(agents: dict):
        monkeypatch.setattr(mod, "get_config", lambda: Cfg(agents), raising=False)
        import core.config
        monkeypatch.setattr(core.config, "get_config", lambda: Cfg(agents))
    return apply


# ── defining one of your own ──

def test_a_config_agent_is_created(with_config):
    with_config({"reviewer": AgentOverride(description="Reviews code")})
    assert mod.get_agent("reviewer").description == "Reviews code"


def test_it_defaults_to_being_usable_both_ways(with_config):
    with_config({"reviewer": AgentOverride()})
    assert mod.get_agent("reviewer").mode == "all"
    names_pickable = {a.name for a in mod.list_agents()}
    names_spawnable = {a.name for a in mod.list_subagents()}
    assert "reviewer" in names_pickable
    assert "reviewer" in names_spawnable


def test_it_can_be_narrowed_to_a_subagent(with_config):
    with_config({"reviewer": AgentOverride(mode="subagent")})
    assert "reviewer" not in {a.name for a in mod.list_agents()}
    assert "reviewer" in {a.name for a in mod.list_subagents()}


def test_a_nonsense_mode_is_ignored_rather_than_stored(with_config):
    with_config({"reviewer": AgentOverride(mode="sideways")})
    assert mod.get_agent("reviewer").mode == "all"


# ── retuning a built-in ──

def test_a_built_in_can_be_retuned(with_config):
    with_config({"build": AgentOverride(model="anthropic/claude", temperature=0.7)})
    build = mod.get_agent("build")
    assert (build.model, build.temperature) == ("anthropic/claude", 0.7)


def test_retuning_does_not_leak_into_the_built_in_defaults(with_config):
    with_config({"build": AgentOverride(model="x")})
    mod.get_agent("build")
    assert mod.AGENTS["build"].model is None


def test_permission_rules_accumulate(with_config):
    before = len(mod.AGENTS["build"].permission)
    with_config({"build": AgentOverride(
        permission=[{"permission": "bash", "pattern": "*", "action": "deny"}]
    )})
    assert len(mod.get_agent("build").permission) == before + 1


def test_tools_are_replaced_not_widened(with_config):
    # A toolset is a whitelist; accumulating would widen an agent the user
    # just narrowed.
    with_config({"build": AgentOverride(tools=["read"])})
    assert mod.get_agent("build").tools == ["read"]


def test_a_built_in_can_be_hidden(with_config):
    with_config({"plan": AgentOverride(hidden=True)})
    assert "plan" not in {a.name for a in mod.list_agents()}


# ── removing one ──

def test_a_built_in_can_be_disabled(with_config):
    with_config({"plan": AgentOverride(disable=True)})
    with pytest.raises(ValueError):
        mod.get_agent("plan")
    assert "plan" not in {a.name for a in mod.list_agents()}


def test_disabling_leaves_the_others_alone(with_config):
    with_config({"plan": AgentOverride(disable=True)})
    assert "build" in {a.name for a in mod.list_agents()}


# ── mode "all" in both lists ──

def test_an_all_agent_is_both_pickable_and_spawnable(with_config):
    with_config({"helper": AgentOverride(mode="all")})
    assert "helper" in {a.name for a in mod.list_agents()}
    assert "helper" in {a.name for a in mod.list_subagents()}


def test_an_all_agent_is_not_treated_as_a_subagent_only(with_config):
    with_config({"helper": AgentOverride(mode="all")})
    assert not mod.is_subagent("helper")
