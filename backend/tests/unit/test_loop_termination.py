"""Termination and doom-loop rules for the agent loop.

These are the decisions that end a run. Both have failed silently in the past —
a stranded tool call looks like the agent simply stopping mid-task — so they are
kept as pure functions and asserted directly rather than through the loop.
"""
import pytest

from agent.doom_loop import DOOM_LOOP_THRESHOLD, is_repeat_of_recent
from agent.loop import (
    ABORTED_TOOL_ERROR,
    has_live_tool_calls,
    is_orphaned_interrupted_tool,
    should_terminate,
)


class Msg:
    """Minimal stand-in for MessageWithParts."""

    def __init__(self, id, finish=None, parts=None):
        self.id = id
        self.finish = finish
        self.parts = parts or []


def tool_part(status="completed", error=None, **extra):
    return {"type": "tool", "tool": "bash", "status": status, "error": error, **extra}


USER = Msg("msg_001")


# ── orphaned tool parts ──

def test_orphan_is_an_aborted_error_part():
    assert is_orphaned_interrupted_tool(tool_part(status="error", error=ABORTED_TOOL_ERROR))


@pytest.mark.parametrize("part", [
    tool_part(status="error", error="Command not found"),  # a real failure
    tool_part(status="completed"),
    tool_part(status="running"),
])
def test_other_parts_are_not_orphans(part):
    assert not is_orphaned_interrupted_tool(part)


def test_orphan_check_accepts_pydantic_style_parts():
    class P:
        def model_dump(self):
            return tool_part(status="error", error=ABORTED_TOOL_ERROR)

    assert is_orphaned_interrupted_tool(P())


# ── live tool calls ──

def test_no_parts_means_no_live_tool_calls():
    assert not has_live_tool_calls(Msg("m", parts=[]))
    assert not has_live_tool_calls(None)


def test_text_parts_are_not_tool_calls():
    assert not has_live_tool_calls(Msg("m", parts=[{"type": "text", "text": "hi"}]))


def test_a_tool_part_counts_as_live():
    assert has_live_tool_calls(Msg("m", parts=[tool_part()]))


def test_orphaned_parts_do_not_count_as_live():
    assert not has_live_tool_calls(
        Msg("m", parts=[tool_part(status="error", error=ABORTED_TOOL_ERROR)])
    )


def test_provider_executed_parts_do_not_count_as_live():
    # The provider already ran it; no result of ours is outstanding.
    assert not has_live_tool_calls(Msg("m", parts=[tool_part(provider_executed=True)]))


def test_one_live_part_among_orphans_still_counts():
    assert has_live_tool_calls(Msg("m", parts=[
        tool_part(status="error", error=ABORTED_TOOL_ERROR),
        {"type": "text", "text": "..."},
        tool_part(status="completed"),
    ]))


# ── termination ──

def test_unfinished_assistant_does_not_terminate():
    assert not should_terminate(Msg("msg_002"), USER)


@pytest.mark.parametrize("finish", ["tool_calls", "tool-calls"])
def test_tool_calls_finish_never_terminates(finish):
    assert not should_terminate(Msg("msg_002", finish=finish), USER)


def test_plain_stop_terminates():
    assert should_terminate(Msg("msg_002", finish="stop"), USER)


def test_stop_with_tool_calls_does_not_terminate():
    """The regression this guard exists for.

    Some providers report finish="stop" on a message that still carries tool
    calls. Terminating there strands them: their results are never fed back and
    the run halts mid-task with no error surfaced anywhere.
    """
    stranded = Msg("msg_002", finish="stop", parts=[tool_part(status="running")])
    assert not should_terminate(stranded, USER)


def test_stop_with_only_orphaned_tools_does_terminate():
    # Nothing is actually outstanding, so the run is genuinely over.
    abandoned = Msg("msg_002", finish="stop",
                    parts=[tool_part(status="error", error=ABORTED_TOOL_ERROR)])
    assert should_terminate(abandoned, USER)


def test_unknown_finish_terminates_when_nothing_is_pending():
    """"unknown" used to be whitelisted, which swallowed real terminations from
    providers reporting an unrecognised reason. The tool-call check covers the
    case that whitelist was standing in for."""
    assert should_terminate(Msg("msg_002", finish="unknown"), USER)


def test_assistant_older_than_user_does_not_terminate():
    # A newer user message means there is fresh work; ids sort ascending.
    stale = Msg("msg_000", finish="stop")
    assert not should_terminate(stale, USER)


def test_missing_messages_do_not_terminate():
    assert not should_terminate(None, USER)
    assert not should_terminate(Msg("m", finish="stop"), None)


# ── doom loop ──

def _part(tool, args):
    class P:
        pass
    p = P()
    p.tool, p.input = tool, args
    return p


def test_doom_loop_needs_a_full_run_of_identical_calls():
    history = [_part("bash", {"command": "ls"})] * (DOOM_LOOP_THRESHOLD - 1)
    assert is_repeat_of_recent(history, "bash", {"command": "ls"})


def test_differing_args_break_the_run():
    history = [_part("bash", {"command": "ls"})] * (DOOM_LOOP_THRESHOLD - 1)
    assert not is_repeat_of_recent(history, "bash", {"command": "pwd"})


def test_differing_tool_breaks_the_run():
    history = [_part("bash", {"command": "ls"})] * (DOOM_LOOP_THRESHOLD - 1)
    assert not is_repeat_of_recent(history, "read", {"command": "ls"})


def test_key_order_does_not_affect_the_comparison():
    history = [_part("edit", {"a": 1, "b": 2})] * (DOOM_LOOP_THRESHOLD - 1)
    assert is_repeat_of_recent(history, "edit", {"b": 2, "a": 1})


def test_short_history_is_never_a_doom_loop():
    assert not is_repeat_of_recent([], "bash", {"command": "ls"})
