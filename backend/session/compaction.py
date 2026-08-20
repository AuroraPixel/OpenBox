"""Session compaction: context window management helpers.

Implements filter_compacted which detects compaction boundaries
and truncates older messages to keep context within limits.
"""
from models.message import MessageWithParts
from core.log import create_logger

log = create_logger("session.compaction")


async def filter_compacted(messages: list[MessageWithParts]) -> list[MessageWithParts]:
    """Filter messages to only include those after the last compaction boundary.

    A compaction boundary is a user message with a compaction part whose
    corresponding assistant response has summary=True and a finish reason.

    Scans from newest to oldest. When a boundary is found, older messages are
    discarded — except a tail the compaction marked to survive verbatim, which
    is spliced back in ahead of the boundary. Without that tail the model gets
    a prose description of what it was doing instead of the thing itself, and
    re-reads files it had just read.

    The result is [boundary_user_msg, summary_msg, *preserved_tail, ...newer]:
    the summary first, because it stands in for everything older than the tail.
    Array position is therefore not chronological.
    """
    if not messages:
        return messages

    # Work from newest to oldest
    reversed_msgs = list(reversed(messages))

    # Track which user message IDs have completed compaction summaries
    completed_compaction_parents: set[str] = set()

    # First pass: find assistant messages with summary=True and finish set
    for msg in reversed_msgs:
        role = msg.role if isinstance(msg.role, str) else msg.role.value
        if role == "assistant" and msg.summary and msg.finish:
            if msg.parent_id:
                completed_compaction_parents.add(msg.parent_id)

    if not completed_compaction_parents:
        return messages

    # Second pass: find the boundary user message and truncate
    result = []
    boundary: MessageWithParts | None = None
    tail_start_id: str | None = None
    for msg in reversed_msgs:
        result.append(msg)

        role = msg.role if isinstance(msg.role, str) else msg.role.value
        if role == "user" and msg.id in completed_compaction_parents:
            part = _compaction_part(msg)
            if part is not None:
                boundary = msg
                tail_start_id = part.get("tail_start_id")
                break  # Found the boundary - stop here

    result.reverse()  # Restore chronological order (old -> new)

    if not tail_start_id or boundary is None:
        return result

    # The summary describes everything before the tail, so it has to come
    # first — reading recent work and only then a summary of what preceded it
    # reads as if the older material happened afterwards.
    summary_idx = next(
        (i for i, m in enumerate(result)
         if i > 0 and m.parent_id == boundary.id and m.summary),
        -1,
    )
    if summary_idx < 0:
        return result

    tail_idx = next((i for i, m in enumerate(messages) if m.id == tail_start_id), -1)
    boundary_idx = next(i for i, m in enumerate(messages) if m.id == boundary.id)
    if tail_idx < 0:
        log.debug(f"Compaction tail {tail_start_id} no longer present")
        return result

    tail = messages[tail_idx:boundary_idx]
    if not tail:
        return result

    log.debug(f"Preserving {len(tail)} messages verbatim from {tail_start_id}")
    return result[:summary_idx + 1] + tail + result[summary_idx + 1:]


def _compaction_part(msg: MessageWithParts) -> dict | None:
    """The message's compaction part as a dict, or None."""
    for part in (msg.parts or []):
        p = part if isinstance(part, dict) else (
            part.model_dump() if hasattr(part, "model_dump") else None)
        if isinstance(p, dict) and p.get("type") == "compaction":
            return p
    return None


def _has_compaction_part(msg: MessageWithParts) -> bool:
    """Check if a message has a compaction part."""
    return _compaction_part(msg) is not None
