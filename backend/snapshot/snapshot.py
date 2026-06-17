"""File snapshot system using git for tracking changes in the sandbox.

Each agent step records a snapshot (git tree hash) before and after execution.
This enables:
- Computing diffs between steps
- Reverting to a specific snapshot
- Tracking file changes across the session
"""
import asyncio
from dataclasses import dataclass

from core.log import create_logger

log = create_logger("snapshot")


def _get_workdir(session_id: str) -> str:
    """Get the session-specific working directory for snapshot operations."""
    from sandbox import sandbox_manager
    return sandbox_manager.get_session_workdir(session_id)


@dataclass
class FileDiff:
    path: str
    additions: int = 0
    deletions: int = 0
    status: str = "modified"  # "added", "modified", "deleted"


async def track(session_id: str, sandbox=None) -> str | None:
    """Create a snapshot of the current state using git write-tree.

    Returns a snapshot ID (git tree hash) or None on failure.
    Requires a SandboxClient instance to execute git commands inside the sandbox.
    """
    if sandbox is None:
        try:
            from sandbox import sandbox_manager
            sandbox = await sandbox_manager.get_client(session_id)
        except Exception as e:
            log.warning(f"Cannot get sandbox for snapshot: {e}")
            return None

    try:
        workdir = _get_workdir(session_id)
        # Ensure git repo is initialized in session workdir
        await sandbox.execute(f"git init -q {workdir} 2>/dev/null || true", workdir=workdir)

        # Stage all files
        result = await sandbox.execute("git add -A", workdir=workdir)
        if result.exit_code != 0:
            log.warning(f"git add failed: {result.stderr}")
            return None

        # Write the tree object (does not create a commit)
        result = await sandbox.execute("git write-tree", workdir=workdir)
        if result.exit_code != 0:
            log.warning(f"git write-tree failed: {result.stderr}")
            return None

        tree_hash = result.stdout.strip()
        if tree_hash:
            log.debug(f"Snapshot created: {tree_hash[:12]} for session {session_id[:8]}")
            return tree_hash

        return None

    except Exception as e:
        log.warning(f"Failed to create snapshot for session {session_id}: {e}")
        return None


async def restore(snapshot_id: str, session_id: str, sandbox=None) -> bool:
    """Restore the working directory to a snapshot state.

    Uses git read-tree + checkout-index to restore files.
    Returns True on success, False on failure.
    """
    if not snapshot_id:
        return False

    if sandbox is None:
        try:
            from sandbox import sandbox_manager
            sandbox = await sandbox_manager.get_client(session_id)
        except Exception as e:
            log.warning(f"Cannot get sandbox for restore: {e}")
            return False

    try:
        workdir = _get_workdir(session_id)
        # Read the tree into the index
        result = await sandbox.execute(
            f"git read-tree {snapshot_id}", workdir=workdir
        )
        if result.exit_code != 0:
            log.warning(f"git read-tree failed: {result.stderr}")
            return False

        # Force checkout from index to working directory
        result = await sandbox.execute(
            "git checkout-index -a -f", workdir=workdir
        )
        if result.exit_code != 0:
            log.warning(f"git checkout-index failed: {result.stderr}")
            return False

        # Clean untracked files that don't belong to this tree
        result = await sandbox.execute(
            "git clean -fd", workdir=workdir
        )

        log.info(f"Restored snapshot {snapshot_id[:12]} for session {session_id[:8]}")
        return True

    except Exception as e:
        log.warning(f"Failed to restore snapshot {snapshot_id}: {e}")
        return False


async def diff(from_snapshot: str, to_snapshot: str, sandbox=None, session_id: str = "") -> list[FileDiff]:
    """Compute diff between two snapshots using git diff-tree.

    Returns a list of FileDiff objects describing the changes.
    """
    if not from_snapshot or not to_snapshot:
        return []

    if from_snapshot == to_snapshot:
        return []

    if sandbox is None:
        try:
            from sandbox import sandbox_manager
            sandbox = await sandbox_manager.get_client(session_id)
        except Exception as e:
            log.warning(f"Cannot get sandbox for diff: {e}")
            return []

    try:
        # Get diff stats between two tree objects
        result = await sandbox.execute(
            f"git diff-tree --numstat -r {from_snapshot} {to_snapshot}",
            workdir=_get_workdir(session_id),
        )
        if result.exit_code != 0:
            log.warning(f"git diff-tree failed: {result.stderr}")
            return []

        diffs = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t", 2)
            if len(parts) < 3:
                continue

            additions_str, deletions_str, path = parts
            additions = int(additions_str) if additions_str != "-" else 0
            deletions = int(deletions_str) if deletions_str != "-" else 0

            # Determine status
            if additions > 0 and deletions == 0:
                status = "added"
            elif additions == 0 and deletions > 0:
                status = "deleted"
            else:
                status = "modified"

            diffs.append(FileDiff(
                path=path,
                additions=additions,
                deletions=deletions,
                status=status,
            ))

        # Also get file status (A/M/D) for more accurate status info
        status_result = await sandbox.execute(
            f"git diff-tree --name-status -r {from_snapshot} {to_snapshot}",
            workdir=_get_workdir(session_id),
        )
        if status_result.exit_code == 0:
            status_map = {}
            for line in status_result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    status_char, path = parts
                    if status_char.startswith("A"):
                        status_map[path] = "added"
                    elif status_char.startswith("D"):
                        status_map[path] = "deleted"
                    else:
                        status_map[path] = "modified"

            for d in diffs:
                if d.path in status_map:
                    d.status = status_map[d.path]

        return diffs

    except Exception as e:
        log.warning(f"Failed to compute diff: {e}")
        return []


async def diff_full(from_snapshot: str, to_snapshot: str, sandbox=None, session_id: str = "") -> list[dict]:
    """Compute full diff with hunks between two snapshots.

    Returns a list of DiffEntry-compatible dicts including hunks.
    """
    if not from_snapshot or not to_snapshot or from_snapshot == to_snapshot:
        return []

    if sandbox is None:
        try:
            from sandbox import sandbox_manager
            sandbox = await sandbox_manager.get_client(session_id)
        except Exception as e:
            log.warning(f"Cannot get sandbox for diff_full: {e}")
            return []

    try:
        # Get unified diff
        result = await sandbox.execute(
            f"git diff {from_snapshot} {to_snapshot} --unified=3",
            workdir=_get_workdir(session_id),
        )
        if result.exit_code != 0:
            # Fallback to basic diff
            basic = await diff(from_snapshot, to_snapshot, sandbox, session_id)
            return [
                {"path": d.path, "additions": d.additions,
                 "deletions": d.deletions, "status": d.status, "hunks": []}
                for d in basic
            ]

        return _parse_unified_diff(result.stdout)

    except Exception as e:
        log.warning(f"Failed to compute full diff: {e}")
        return []


def _parse_unified_diff(diff_text: str) -> list[dict]:
    """Parse unified diff output into DiffEntry-compatible dicts."""
    import re

    entries = []
    current_entry = None
    current_hunk = None

    for line in diff_text.split("\n"):
        # New file diff header
        if line.startswith("diff --git"):
            if current_entry:
                if current_hunk:
                    current_entry["hunks"].append(current_hunk)
                entries.append(current_entry)
            current_entry = {
                "path": "", "additions": 0, "deletions": 0,
                "status": "modified", "hunks": [],
            }
            current_hunk = None
            continue

        if not current_entry:
            continue

        # File path from --- / +++ lines
        if line.startswith("+++ b/"):
            current_entry["path"] = line[6:]
        elif line.startswith("--- /dev/null"):
            current_entry["status"] = "added"
        elif line.startswith("+++ /dev/null"):
            current_entry["status"] = "deleted"

        # Hunk header
        hunk_match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if hunk_match:
            if current_hunk:
                current_entry["hunks"].append(current_hunk)
            current_hunk = {
                "old_start": int(hunk_match.group(1)),
                "old_count": int(hunk_match.group(2) or 1),
                "new_start": int(hunk_match.group(3)),
                "new_count": int(hunk_match.group(4) or 1),
                "lines": [],
            }
            continue

        if current_hunk is None:
            continue

        # Diff lines
        if line.startswith("+"):
            current_hunk["lines"].append({
                "type": "add", "content": line[1:],
                "old_line": None,
                "new_line": current_hunk["new_start"] + sum(
                    1 for l in current_hunk["lines"] if l["type"] in ("add", "context")
                ),
            })
            current_entry["additions"] += 1
        elif line.startswith("-"):
            current_hunk["lines"].append({
                "type": "del", "content": line[1:],
                "old_line": current_hunk["old_start"] + sum(
                    1 for l in current_hunk["lines"] if l["type"] in ("del", "context")
                ),
                "new_line": None,
            })
            current_entry["deletions"] += 1
        elif line.startswith(" "):
            old_line = current_hunk["old_start"] + sum(
                1 for l in current_hunk["lines"] if l["type"] in ("del", "context")
            )
            new_line = current_hunk["new_start"] + sum(
                1 for l in current_hunk["lines"] if l["type"] in ("add", "context")
            )
            current_hunk["lines"].append({
                "type": "context", "content": line[1:],
                "old_line": old_line, "new_line": new_line,
            })

    # Don't forget the last entry
    if current_entry:
        if current_hunk:
            current_entry["hunks"].append(current_hunk)
        entries.append(current_entry)

    return entries
