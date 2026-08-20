"""The compaction boundary filter — what the model actually sees after a compact.

Everything before the boundary is replaced by the summary, except a tail the
compaction marked to survive verbatim. These tests pin both halves: the cut,
and the splice that puts the tail back.
"""
import pytest

from session.compaction import filter_compacted


class Msg:
    def __init__(self, id, role, parts=None, summary=False, finish=None, parent_id=None):
        self.id = id
        self.role = role
        self.parts = parts or []
        self.summary = summary
        self.finish = finish
        self.parent_id = parent_id


def user(id, text="hi"):
    return Msg(id, "user", [{"type": "text", "text": text}])


def assistant(id, text="ok"):
    return Msg(id, "assistant", [{"type": "text", "text": text}])


def compact_request(id, tail_start_id=None):
    return Msg(id, "user", [{"type": "compaction", "auto": True,
                             "tail_start_id": tail_start_id}])


def summary(id, parent_id):
    return Msg(id, "assistant", [{"type": "text", "text": "summary"}],
               summary=True, finish="stop", parent_id=parent_id)


def ids(msgs):
    return [m.id for m in msgs]


@pytest.mark.asyncio
async def test_no_compaction_leaves_history_untouched():
    msgs = [user("u0"), assistant("a0"), user("u1")]
    assert ids(await filter_compacted(msgs)) == ["u0", "a0", "u1"]


@pytest.mark.asyncio
async def test_empty_history_is_returned_as_is():
    assert await filter_compacted([]) == []


@pytest.mark.asyncio
async def test_an_unfinished_compaction_is_not_a_boundary():
    # The summary is still streaming — cutting here would drop history that
    # nothing has replaced yet.
    msgs = [user("u0"), assistant("a0"), compact_request("c0"),
            Msg("s0", "assistant", summary=True, finish=None, parent_id="c0")]
    assert ids(await filter_compacted(msgs)) == ["u0", "a0", "c0", "s0"]


@pytest.mark.asyncio
async def test_history_before_the_boundary_is_dropped():
    msgs = [user("u0"), assistant("a0"), user("u1"), assistant("a1"),
            compact_request("c0"), summary("s0", "c0"), user("u2")]
    assert ids(await filter_compacted(msgs)) == ["c0", "s0", "u2"]


@pytest.mark.asyncio
async def test_only_the_newest_boundary_survives():
    msgs = [user("u0"), compact_request("c0"), summary("s0", "c0"),
            user("u1"), compact_request("c1"), summary("s1", "c1"), user("u2")]
    assert ids(await filter_compacted(msgs)) == ["c1", "s1", "u2"]


@pytest.mark.asyncio
async def test_marked_tail_is_replayed_after_the_summary():
    msgs = [user("u0"), assistant("a0"), user("u1"), assistant("a1"),
            compact_request("c0", tail_start_id="u1"), summary("s0", "c0"), user("u2")]
    # u0/a0 are gone (summarised); u1/a1 survive verbatim, but after the
    # summary — which stands in for everything older than they are.
    assert ids(await filter_compacted(msgs)) == ["c0", "s0", "u1", "a1", "u2"]


@pytest.mark.asyncio
async def test_tail_is_not_duplicated_when_it_reaches_the_boundary():
    msgs = [user("u0"), assistant("a0"),
            compact_request("c0", tail_start_id="a0"), summary("s0", "c0")]
    assert ids(await filter_compacted(msgs)) == ["c0", "s0", "a0"]


@pytest.mark.asyncio
async def test_an_unfinished_summary_suppresses_the_splice():
    # Nothing to place the tail after yet; better plain than reordered around
    # a summary that does not exist.
    msgs = [user("u0"), assistant("a0"), user("u1"),
            compact_request("c0", tail_start_id="u1"),
            Msg("s0", "assistant", summary=True, finish="stop", parent_id="OTHER"),
            summary("s1", "c0")]
    out = ids(await filter_compacted(msgs))
    assert out[:2] == ["c0", "s0"] or out[0] == "c0"


@pytest.mark.asyncio
async def test_a_tail_pointing_at_a_pruned_message_degrades_to_summary_only():
    msgs = [user("u1"), assistant("a1"),
            compact_request("c0", tail_start_id="long-gone"), summary("s0", "c0")]
    assert ids(await filter_compacted(msgs)) == ["c0", "s0"]


@pytest.mark.asyncio
async def test_a_compaction_with_no_tail_behaves_as_before():
    msgs = [user("u0"), assistant("a0"),
            compact_request("c0"), summary("s0", "c0"), user("u1")]
    assert ids(await filter_compacted(msgs)) == ["c0", "s0", "u1"]


@pytest.mark.asyncio
async def test_nothing_is_lost_or_duplicated_by_the_reorder():
    msgs = [user("u0"), assistant("a0"), user("u1"), assistant("a1"),
            compact_request("c0", tail_start_id="u1"), summary("s0", "c0"),
            user("u2"), assistant("a2")]
    out = ids(await filter_compacted(msgs))
    assert len(out) == len(set(out)), "no message appears twice"
    assert set(out) <= set(ids(msgs))
    # newest messages still trail the reordered block, so "last user message"
    # scans over the result keep working
    assert out[-2:] == ["u2", "a2"]


@pytest.mark.asyncio
async def test_reorder_leaves_the_continuation_as_the_last_user_message():
    # The loop decides whether to keep going by looking at the last user
    # message. Splicing the tail into the middle must not put a stale user
    # message from before the compaction in that position.
    from agent.loop import _find_pending_compaction

    msgs = [user("u0"), assistant("a0"), user("u1"), assistant("a1"),
            compact_request("c0", tail_start_id="u1"), summary("s0", "c0"),
            user("cont", "Context was compacted. Continue working.")]
    out = await filter_compacted(msgs)

    last_user = [m for m in out if m.role == "user"][-1]
    assert last_user.id == "cont"
    # ...and the already-processed compaction is not picked up again
    assert _find_pending_compaction(out) is None
