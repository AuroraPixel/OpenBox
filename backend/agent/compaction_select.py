"""Choosing how much recent history survives a compaction verbatim.

Summarising the whole conversation and keeping only the prose leaves the model
with a description of what it was doing instead of the thing itself: the file
it just read, the exact error it just hit, the arguments of the call that
failed. The next turn then re-reads and re-runs to recover them.

So a tail of recent messages is kept as-is alongside the summary, sized to a
token budget. Ported from opencode's SessionCompaction.select(), including its
turn awareness — the split lands on a message boundary inside a turn, never
between a user message and the assistant work answering it.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.log import create_logger
from core.token import token_estimate

log = create_logger("agent.compaction_select")

# Floor and ceiling for the preserved tail, in tokens. The floor keeps the tail
# useful on small-context models; the ceiling stops it eating a 1M window.
MIN_PRESERVE_RECENT_TOKENS = 8_000
MAX_PRESERVE_RECENT_TOKENS = 60_000
PRESERVE_RECENT_FRACTION = 0.25


@dataclass
class Turn:
    """One user message and every assistant message answering it."""

    start: int
    end: int
    id: str


@dataclass
class Selection:
    """head is summarised; everything from tail_start_id onward is kept as-is."""

    head: list
    tail_start_id: str | None = None


def preserve_recent_budget(usable_tokens: int, configured: int | None = None) -> int:
    """How many tokens of recent history to keep verbatim."""
    if configured is not None:
        return max(0, configured)
    quarter = int(usable_tokens * PRESERVE_RECENT_FRACTION)
    return min(MAX_PRESERVE_RECENT_TOKENS, max(MIN_PRESERVE_RECENT_TOKENS, quarter))


def _role(msg) -> str:
    role = getattr(msg, "role", "")
    return role if isinstance(role, str) else getattr(role, "value", "")


def _has_compaction_part(msg) -> bool:
    for part in (getattr(msg, "parts", None) or []):
        t = part.get("type") if isinstance(part, dict) else getattr(part, "type", None)
        if t == "compaction":
            return True
    return False


def turns(messages: list) -> list[Turn]:
    """Group messages into turns, each opened by a real user message.

    Compaction requests are skipped: they are bookkeeping, not a turn the model
    would recognise as a unit of work.
    """
    result: list[Turn] = []
    for i, msg in enumerate(messages):
        if _role(msg) != "user" or _has_compaction_part(msg):
            continue
        result.append(Turn(start=i, end=len(messages), id=msg.id))
    for i in range(len(result) - 1):
        result[i].end = result[i + 1].start
    return result


def estimate(messages: list) -> int:
    """Rough token size of a message slice."""
    total = 0
    for msg in messages:
        for part in (getattr(msg, "parts", None) or []):
            p = part if isinstance(part, dict) else (
                part.model_dump() if hasattr(part, "model_dump") else {})
            for field in ("text", "output", "error"):
                value = p.get(field)
                if value:
                    total += token_estimate(str(value))
            if p.get("input"):
                total += token_estimate(str(p["input"]))
    return total


def split_turn(messages: list, turn: Turn, budget: int) -> tuple[int, str] | None:
    """Find the earliest split inside `turn` whose tail fits `budget`.

    Never splits at turn.start: the user message that opened the turn stays
    with the head, so the tail cannot begin mid-exchange with no prompt.
    """
    if budget <= 0 or turn.end - turn.start <= 1:
        return None
    for start in range(turn.start + 1, turn.end):
        if estimate(messages[start:turn.end]) <= budget:
            return start, messages[start].id
    return None


def select(messages: list, usable_tokens: int, configured_budget: int | None = None,
           tail_turns: int | None = None) -> Selection:
    """Split history into a part to summarise and a tail to keep verbatim.

    tail_turns caps how many recent turns are eligible; 0 disables the tail
    entirely, restoring summary-only behaviour.
    """
    if tail_turns is not None and tail_turns <= 0:
        return Selection(head=messages)

    budget = preserve_recent_budget(usable_tokens, configured_budget)
    all_turns = turns(messages)
    if not all_turns:
        return Selection(head=messages)

    recent = all_turns if tail_turns is None else all_turns[-tail_turns:]

    total = 0
    keep: tuple[int, str] | None = None
    # Walk backwards so the newest turns are the ones that fit.
    for turn in reversed(recent):
        size = estimate(messages[turn.start:turn.end])
        if total + size <= budget:
            total += size
            keep = (turn.start, turn.id)
            continue
        split = split_turn(messages, turn, budget - total)
        if split:
            keep = split
        elif keep is None:
            log.info(f"compaction tail: nothing fits (budget={budget}, turn={size})")
        break

    if keep is None or keep[0] == 0:
        # Splitting at 0 would keep everything and summarise nothing.
        return Selection(head=messages)
    return Selection(head=messages[:keep[0]], tail_start_id=keep[1])
