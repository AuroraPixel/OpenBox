"""Choosing what the next step runs: which messages anchor it, which agent,
which tools.

All pure, and all previously only reachable through a live run.
"""
import pytest

from agent.loop import apply_agent_overrides, resolve_agent_name, scan_messages
from agent.tool_resolution import agent_ruleset, strip_denied


class Msg:
    def __init__(self, id, role, finish=None):
        self.id, self.role, self.finish = id, role, finish


class Session:
    def __init__(self, agent=None):
        self.agent = agent


class UserMsg:
    def __init__(self, agent=None):
        self.agent = agent


# ── message scan ──

def test_empty_history_finds_nothing():
    scan = scan_messages([])
    assert (scan.last_user, scan.last_assistant, scan.last_finished) == (None, None, None)


def test_finds_the_newest_of_each():
    msgs = [
        Msg("1", "user"), Msg("2", "assistant", finish="stop"),
        Msg("3", "user"), Msg("4", "assistant"),
    ]
    scan = scan_messages(msgs)
    assert scan.last_user.id == "3"
    assert scan.last_assistant.id == "4"
    # newest assistant *carrying a finish*, which is not the newest assistant
    assert scan.last_finished.id == "2"


def test_last_assistant_and_last_finished_can_coincide():
    scan = scan_messages([Msg("1", "user"), Msg("2", "assistant", finish="stop")])
    assert scan.last_assistant.id == scan.last_finished.id == "2"


def test_enum_style_roles_are_handled():
    class Role:
        def __init__(self, value): self.value = value

    class M:
        def __init__(self, id, role): self.id, self.role, self.finish = id, Role(role), None

    scan = scan_messages([M("1", "user")])
    assert scan.last_user.id == "1"


def test_scan_stops_once_both_anchors_are_found():
    """History is unbounded and this runs every step; it must not read it all."""
    seen = []

    class Tracking(Msg):
        @property
        def finish_(self): ...

    msgs = [Msg(str(i), "assistant", finish="stop") for i in range(100)]
    msgs.append(Msg("user", "user"))
    # reversed() hits the user first, then the newest assistant, then stops.
    scan = scan_messages(msgs)
    assert scan.last_user.id == "user"
    assert scan.last_finished.id == "99"


def test_assistant_without_finish_does_not_become_last_finished():
    scan = scan_messages([Msg("1", "user"), Msg("2", "assistant")])
    assert scan.last_assistant.id == "2"
    assert scan.last_finished is None


# ── agent selection ──

def test_user_message_agent_wins():
    """plan_exit hands control over by synthesising a user message that names
    the next agent, so it has to outrank the session."""
    assert resolve_agent_name(UserMsg("build"), Session("plan")) == "build"


def test_falls_back_to_session_agent():
    assert resolve_agent_name(UserMsg(None), Session("plan")) == "plan"


def test_defaults_to_build():
    assert resolve_agent_name(UserMsg(None), Session(None)) == "build"


# ── per-agent config overrides ──

class Agent:
    def __init__(self):
        self.model = "base/model"
        self.temperature = 0.0
        self.max_steps = 200
        self.prompt = None
        self.permission = [{"permission": "edit", "pattern": "*", "action": "ask"}]


class Overrides:
    def __init__(self, **kw):
        self.model = kw.get("model")
        self.temperature = kw.get("temperature")
        self.max_steps = kw.get("max_steps")
        self.prompt = kw.get("prompt")
        self.permission = kw.get("permission")


def test_no_overrides_leaves_the_agent_alone():
    a = Agent()
    apply_agent_overrides(a, None)
    assert (a.model, a.max_steps) == ("base/model", 200)


def test_scalar_fields_are_replaced():
    a = Agent()
    apply_agent_overrides(a, Overrides(model="other/model", max_steps=10, prompt="hi"))
    assert (a.model, a.max_steps, a.prompt) == ("other/model", 10, "hi")


def test_zero_temperature_is_applied_not_skipped():
    """0.0 is falsy but meaningful — the check must be `is not None`."""
    a = Agent()
    a.temperature = 0.7
    apply_agent_overrides(a, Overrides(temperature=0.0))
    assert a.temperature == 0.0


def test_permission_rules_accumulate():
    """Config rules tighten an agent's defaults; replacing them would silently
    drop whatever the agent declared."""
    a = Agent()
    extra = {"permission": "bash", "pattern": "rm *", "action": "deny"}
    apply_agent_overrides(a, Overrides(permission=[extra]))
    assert len(a.permission) == 2
    assert extra in a.permission


# ── tool denial ──

class Tool:
    def __init__(self, id): self.id = id


class AgentWithRules:
    def __init__(self, rules): self.permission = rules


def test_denied_tools_are_removed_from_the_schema():
    """Denying at call time still lets the model propose the tool and waste a
    turn; it must not appear in the schema at all."""
    tools = {"bash": Tool("bash"), "read": Tool("read")}
    rules = [{"permission": "bash", "pattern": "*", "action": "deny"}]
    out = strip_denied(tools, [], AgentWithRules(rules))
    assert set(out) == {"read"}


def test_nothing_denied_returns_everything():
    tools = {"bash": Tool("bash"), "read": Tool("read")}
    assert set(strip_denied(tools, [], AgentWithRules([]))) == {"bash", "read"}


def test_strip_denied_does_not_mutate_its_input():
    tools = {"bash": Tool("bash")}
    strip_denied(tools, [], AgentWithRules([{"permission": "bash", "pattern": "*", "action": "deny"}]))
    assert "bash" in tools


def test_malformed_rules_are_skipped_not_fatal():
    """Agent definitions are user-editable config; one bad rule must not take
    the run down."""
    a = AgentWithRules(["not-a-dict", {"permission": "bash", "pattern": "*", "action": "deny"}])
    assert len(agent_ruleset(a)) == 1


def test_missing_rule_fields_get_wildcards():
    a = AgentWithRules([{"permission": "bash"}])
    rule = agent_ruleset(a)[0]
    assert (rule.pattern, rule.action) == ("*", "ask")
