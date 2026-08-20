"""What a permission rule is actually matched against.

A rule like skill/secret-* => deny is evaluated against whatever pattern the
call site passes. Passing "*" makes every such rule inert — "*" does not match
"secret-*" — so a deny that reads as enforced silently allows. These tests pin
the subject each tool contributes.
"""
import pytest

from agent.hooks import ToolHooks
from permission.permission import Rule, evaluate


def patterns(tool_id, args):
    return ToolHooks.__new__(ToolHooks)._extract_patterns(tool_id, args)


def test_skill_is_matched_on_the_skill_name():
    assert patterns("skill", {"skill": "dev-browser"}) == ["dev-browser"]


def test_web_fetch_is_matched_on_the_url():
    assert patterns("web_fetch", {"url": "https://example.com"}) == ["https://example.com"]


def test_a_per_skill_deny_actually_denies():
    rules = [Rule(permission="skill", pattern="*", action="allow"),
             Rule(permission="skill", pattern="secret-*", action="deny")]
    denied = patterns("skill", {"skill": "secret-ops"})[0]
    allowed = patterns("skill", {"skill": "dev-browser"})[0]
    assert evaluate("skill", denied, rules).action == "deny"
    assert evaluate("skill", allowed, rules).action == "allow"


def test_a_per_url_deny_actually_denies():
    # ** rather than *, since * does not cross a path separator.
    rules = [Rule(permission="web_fetch", pattern="**", action="allow"),
             Rule(permission="web_fetch", pattern="**internal**", action="deny")]
    blocked = patterns("web_fetch", {"url": "https://wiki.internal.corp/x"})[0]
    fine = patterns("web_fetch", {"url": "https://example.com/docs"})[0]
    assert evaluate("web_fetch", blocked, rules).action == "deny"
    assert evaluate("web_fetch", fine, rules).action == "allow"


def test_missing_args_do_not_crash_the_check():
    # A model can emit a call with the argument absent; the permission check
    # still has to run rather than raising past it.
    assert patterns("skill", {}) == [""]
    assert patterns("web_fetch", {}) == [""]


def test_the_existing_extractors_still_hold():
    assert patterns("bash", {"command": "ls -la"}) == ["ls -la"]
    assert patterns("read", {"file_path": "/etc/passwd"}) == ["/etc/passwd"]
    assert patterns("edit", {"file_path": "/tmp/x"}) == ["/tmp/x"]
    assert patterns("grep", {"pattern": "TODO"}) == ["TODO"]


def test_tools_without_a_meaningful_subject_stay_wildcard():
    # These are all-or-nothing: there is no per-target rule to write.
    assert patterns("todo_write", {"todos": []}) == ["*"]
    assert patterns("question", {"questions": []}) == ["*"]
