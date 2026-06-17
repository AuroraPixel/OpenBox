"""Session revert: undo file changes by restoring snapshots.

Uses the snapshot system to find step-start snapshots in the message
history and restore the sandbox to that state.
"""
from session.session import get_messages, save_part
from snapshot import snapshot
from core.log import create_logger

log = create_logger("session.revert")

# Store the pre-revert snapshot so unrevert can restore it
_revert_snapshots: dict[str, str] = {}  # session_id -> pre-revert snapshot


async def revert_to_message(session_id: str, message_id: str) -> bool:
    """Revert file changes to the state before a message was processed.

    Finds the step-start snapshot for the target message and restores
    the sandbox to that state. Saves the current state for unrevert.
    """
    try:
        msgs = await get_messages(session_id)
        if not msgs:
            log.warning(f"No messages found for session {session_id}")
            return False

        # Find the target message and its step-start snapshot
        target_snapshot = None
        found_message = False

        for msg in msgs:
            if msg.id == message_id:
                found_message = True
                # Look for step-start part in this message
                target_snapshot = _find_step_start_snapshot(msg)
                break

        if not found_message:
            # Look for the step-start snapshot in the assistant message
            # that corresponds to the target user message (parentID match)
            for msg in msgs:
                role = msg.role if isinstance(msg.role, str) else msg.role.value
                if role == "assistant" and msg.parent_id == message_id:
                    target_snapshot = _find_step_start_snapshot(msg)
                    if target_snapshot:
                        break

        if not target_snapshot:
            # Fallback: find step-start snapshot just before the message
            for i, msg in enumerate(msgs):
                if msg.id == message_id or (hasattr(msg, 'parent_id') and msg.parent_id == message_id):
                    # Search backwards for the nearest step-start snapshot
                    for j in range(i - 1, -1, -1):
                        snap = _find_step_finish_snapshot(msgs[j])
                        if snap:
                            target_snapshot = snap
                            break
                    break

        if not target_snapshot:
            log.warning(f"No snapshot found for message {message_id}")
            return False

        # Save current state for unrevert
        from sandbox import sandbox_manager
        sandbox = await sandbox_manager.get_client(session_id)
        current_snapshot = await snapshot.track(session_id, sandbox)
        if current_snapshot:
            _revert_snapshots[session_id] = current_snapshot

        # Restore to target snapshot
        success = await snapshot.restore(target_snapshot, session_id, sandbox)
        if success:
            log.info(f"Reverted session {session_id} to snapshot {target_snapshot[:12]}")
        return success

    except Exception as e:
        log.error(f"Failed to revert session {session_id}: {e}")
        return False


async def unrevert(session_id: str) -> bool:
    """Undo a revert by restoring the pre-revert snapshot."""
    try:
        pre_revert = _revert_snapshots.pop(session_id, None)
        if not pre_revert:
            log.warning(f"No revert to undo for session {session_id}")
            return False

        success = await snapshot.restore(pre_revert, session_id)
        if success:
            log.info(f"Unreverted session {session_id} to snapshot {pre_revert[:12]}")
        return success

    except Exception as e:
        log.error(f"Failed to unrevert session {session_id}: {e}")
        return False


def _find_step_start_snapshot(msg) -> str | None:
    """Find a step-start snapshot in a message's parts."""
    for part in (msg.parts or []):
        p = part if isinstance(part, dict) else (part.model_dump() if hasattr(part, "model_dump") else {})
        if isinstance(p, dict) and p.get("type") == "step-start" and p.get("snapshot"):
            return p["snapshot"]
    return None


def _find_step_finish_snapshot(msg) -> str | None:
    """Find a step-finish snapshot in a message's parts."""
    for part in (msg.parts or []):
        p = part if isinstance(part, dict) else (part.model_dump() if hasattr(part, "model_dump") else {})
        if isinstance(p, dict) and p.get("type") == "step-finish" and p.get("snapshot"):
            return p["snapshot"]
    return None
