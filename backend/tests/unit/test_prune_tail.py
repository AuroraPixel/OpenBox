"""Pruning must not gut the tail that compaction is preserving.

Prune erases old tool outputs to free context. The compaction tail is replayed
verbatim and never reaches the summarizer, so pruning inside it saves nothing
and costs exactly what the tail exists to buy: not re-reading the file you
just read.
"""
import pytest

import agent.compaction as compaction


class Msg:
    def __init__(self, id, role, parts=None, summary=False):
        self.id = id
        self.role = role
        self.parts = parts or []
        self.summary = summary


def tool_part(id, message_id, output):
    return {"type": "tool", "id": id, "message_id": message_id, "tool": "read",
            "status": "completed", "output": output, "state": {"time": {}}}


def history(n_turns, output_tokens=20_000):
    """n_turns of user + assistant-with-one-big-tool-output."""
    msgs = []
    for t in range(n_turns):
        msgs.append(Msg(f"u{t}", "user", [{"type": "text", "text": "go"}]))
        msgs.append(Msg(f"a{t}", "assistant",
                        [tool_part(f"p{t}", f"a{t}", "x" * (output_tokens * 4))]))
    return msgs


@pytest.mark.asyncio
async def test_without_a_tail_old_outputs_are_pruned(monkeypatch):
    msgs = history(6)
    pruned = await _run(monkeypatch, msgs, aggressive=True)
    assert pruned, "aggressive prune should erase something in a 120k-token history"
    # The exact parts the next test expects the tail to save. Without this,
    # that test would pass even if the tail skip did nothing.
    assert {"p3", "p4"} & set(pruned), (
        f"unprotected prune must reach the would-be tail, got {pruned}")


@pytest.mark.asyncio
async def test_nothing_inside_the_tail_is_pruned(monkeypatch):
    msgs = history(6)
    # Tail starts at turn 3, so p3/p4/p5 must survive untouched.
    pruned = await _run(monkeypatch, msgs, aggressive=True, protect_from_id="u3")
    assert not ({"p3", "p4", "p5"} & set(pruned)), f"tail was pruned: {pruned}"


@pytest.mark.asyncio
async def test_the_head_is_still_pruned_below_the_tail(monkeypatch):
    msgs = history(8)
    pruned = await _run(monkeypatch, msgs, aggressive=True, protect_from_id="u6")
    assert pruned, "head below the tail should still be prunable"
    assert all(p in {"p0", "p1", "p2", "p3", "p4", "p5"} for p in pruned), pruned


@pytest.mark.asyncio
async def test_an_unknown_tail_id_does_not_disable_pruning(monkeypatch):
    # A tail pointing at a message that has since gone must degrade to normal
    # pruning, not silently protect the entire session.
    msgs = history(6)
    pruned = await _run(monkeypatch, msgs, aggressive=True, protect_from_id="long-gone")
    assert pruned, "a stale tail id must not turn prune into a no-op"


async def _run(monkeypatch, msgs, **kwargs):
    pruned: list[str] = []

    async def fake_get_messages(session_id, *a, **k):
        return msgs

    async def fake_update_part_data(part_id, data):
        pruned.append(part_id)

    import session.session as sess
    monkeypatch.setattr(sess, "get_messages", fake_get_messages)
    monkeypatch.setattr(sess, "update_part_data", fake_update_part_data)
    await compaction.prune_tool_outputs("s", **kwargs)
    return pruned
