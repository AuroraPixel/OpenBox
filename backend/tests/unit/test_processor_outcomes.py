"""Control-flow contract of a single agent step.

process_step classifies what happened in one LLM turn; the loop applies policy
to that classification. These assert the classification, since getting it wrong
either strands a run or spins it forever — and neither surfaces as an error.

The model, the persistence layer and the event bus are all stubbed: the subject
here is the branch taken, not what gets written.
"""
import asyncio
import pytest

from agent import processor as P
from agent.processor import StepOutcome, process_step
from agent.retry import ContextOverflowError, RetryableError


class Info:
    def __init__(self):
        self.id = "msg_assistant"
        self.error = None


class Ctx:
    """ToolContext stand-in — the step stamps message_id onto it."""

    message_id = ""
    part_id = ""


class NotAborted:
    """An abort signal that never fires.

    Needs `wait()` as well as `is_set()`: the processor races each stream chunk
    against `abort.wait()` so a stop takes effect mid-silence rather than at
    the next chunk. A never-resolving future is what "not aborted" means to
    that race.
    """

    @staticmethod
    def is_set():
        return False

    @staticmethod
    async def wait():
        await asyncio.Event().wait()


@pytest.fixture(autouse=True)
def stub_side_effects(monkeypatch):
    """Neutralise persistence, events and compaction."""
    async def anoop(*a, **k):
        return None

    monkeypatch.setattr(P, "save_part", anoop)
    monkeypatch.setattr(P, "update_message_info", anoop)
    monkeypatch.setattr(P, "update_session", anoop)
    monkeypatch.setattr(P, "create_compaction", anoop)
    monkeypatch.setattr(P.bus, "publish", lambda *a, **k: None)


def fake_stream(events=None, raises=None):
    """Build a stand-in for stream_llm yielding the given events."""
    async def _stream(**kwargs):
        if raises is not None:
            raise raises
        for e in events or []:
            yield e
    return _stream


async def run(monkeypatch, **stream_kwargs):
    monkeypatch.setattr(P, "stream_llm", fake_stream(**stream_kwargs))
    return await process_step(
        session_id="s1", user_id="u1", session=None, agent_def=None,
        system=[], llm_messages=[], tools={}, model_id="test/model",
        ctx=Ctx(), hooks=None, assistant_info=Info(), sandbox=None,
        abort=NotAborted(), doom_loop_history=[],
    )


# ── plain completion ──

async def test_text_only_turn_continues(monkeypatch):
    result = await run(monkeypatch, events=[
        {"type": "text_delta", "text": "hello "},
        {"type": "text_delta", "text": "world"},
        {"type": "finish", "reason": "stop", "usage": {"input": 5, "output": 2, "total": 7}},
    ])
    assert result.outcome is StepOutcome.CONTINUE
    assert result.finish_reason == "stop"
    assert result.text == "hello world"


async def test_reasoning_is_collected_separately(monkeypatch):
    result = await run(monkeypatch, events=[
        {"type": "reasoning_delta", "text": "thinking..."},
        {"type": "text_delta", "text": "answer"},
        {"type": "finish", "reason": "stop", "usage": {}},
    ])
    assert result.reasoning == "thinking..."
    assert result.text == "answer"


async def test_empty_stream_still_returns_a_result(monkeypatch):
    result = await run(monkeypatch, events=[])
    assert result.outcome is StepOutcome.CONTINUE
    assert result.finish_reason == "unknown"


# ── failure classification ──

async def test_context_overflow_asks_for_compaction(monkeypatch):
    result = await run(monkeypatch, raises=ContextOverflowError("prompt is too long"))
    assert result.outcome is StepOutcome.COMPACT
    assert result.finish_reason == "compact"


async def test_retryable_error_is_reported_not_retried(monkeypatch):
    """The step must not sleep or count attempts — that budget belongs to the
    loop, which is the only place that can see the whole run."""
    result = await run(monkeypatch, raises=RetryableError("rate limited", 429, {}))
    assert result.outcome is StepOutcome.RETRY
    assert result.retry_reason
    assert result.error


async def test_fatal_error_ends_the_run(monkeypatch):
    result = await run(monkeypatch, raises=ValueError("malformed request"))
    assert result.outcome is StepOutcome.ERROR
    assert "malformed request" in (result.error or "")


async def test_fatal_error_is_recorded_on_the_message(monkeypatch):
    monkeypatch.setattr(P, "stream_llm", fake_stream(raises=ValueError("boom")))
    info = Info()
    await process_step(
        session_id="s1", user_id="u1", session=None, agent_def=None,
        system=[], llm_messages=[], tools={}, model_id="test/model",
        ctx=Ctx(), hooks=None, assistant_info=info, sandbox=None,
        abort=NotAborted(), doom_loop_history=[],
    )
    assert info.error and "boom" in info.error["message"]


# ── the step owns no shared state ──

async def test_doom_loop_history_is_not_mutated(monkeypatch):
    history = []
    monkeypatch.setattr(P, "stream_llm", fake_stream(events=[
        {"type": "finish", "reason": "stop", "usage": {}},
    ]))
    result = await process_step(
        session_id="s1", user_id="u1", session=None, agent_def=None,
        system=[], llm_messages=[], tools={}, model_id="test/model",
        ctx=Ctx(), hooks=None, assistant_info=Info(), sandbox=None,
        abort=NotAborted(), doom_loop_history=history,
    )
    assert history == [], "the caller stays the only writer of doom-loop history"
    assert result.completed_tool_parts == []


async def test_duration_is_reported(monkeypatch):
    result = await run(monkeypatch, events=[{"type": "finish", "reason": "stop", "usage": {}}])
    assert result.duration >= 0
