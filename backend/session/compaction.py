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

    Scans from newest to oldest. When a boundary is found, all older
    messages are discarded. The result is [boundary_user_msg, summary_msg, ...newer].
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
    for msg in reversed_msgs:
        result.append(msg)

        role = msg.role if isinstance(msg.role, str) else msg.role.value
        if role == "user" and msg.id in completed_compaction_parents:
            if _has_compaction_part(msg):
                break  # Found the boundary - stop here

    result.reverse()  # Restore chronological order (old -> new)
    return result


def _has_compaction_part(msg: MessageWithParts) -> bool:
    """Check if a message has a compaction part."""
    for part in (msg.parts or []):
        if isinstance(part, dict):
            if part.get("type") == "compaction":
                return True
        elif hasattr(part, "type") and part.type == "compaction":
            return True
    return False
