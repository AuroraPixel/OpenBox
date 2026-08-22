"""File snapshot system using git for tracking changes in the sandbox.

Each agent step records a snapshot (git tree hash) before and after execution.
This enables:
- Computing diffs between steps
- Reverting to a specific snapshot
- Tracking file changes across the session

The git store lives *outside* the directory it snapshots — one store per
project, under /workspace/.openbox/snapshots — driven with `--git-dir` and
`--work-tree`. Initialising a repo inside the project instead would put a .git
the agent can see (and commit into) in the middle of the user's files, and
would collide with whatever repository the agent clones there itself.

Sessions in one project share a directory, so they share a store, so they share
one index file. Two concurrent `git add -A` runs against one index corrupt it;
every command here is therefore serialised per store.
"""
import asyncio
from dataclasses import dataclass

from core.log import create_logger
from project.workspace import SNAPSHOT_ROOT, project_directory, slug_for

log = create_logger("snapshot")

#: Paths that must never enter a snapshot. Restoring one would take minutes and
#: the contents are reproducible from a lockfile. `git clean` also leaves
#: ignored paths alone, so this doubles as protection during a revert.
EXCLUDE = [
    "node_modules/", ".venv/", "venv/", "__pycache__/", ".mypy_cache/",
    ".pytest_cache/", ".ruff_cache/", "dist/", "build/", ".next/", ".cache/",
    "target/", "*.pyc", ".DS_Store",
]

#: One lock per store, so two sessions in the same project cannot run git
#: against the same index at once.
_locks: dict[str, asyncio.Lock] = {}
#: Stores already initialised this process; `git init` is idempotent but the
#: round trip to the sandbox is not free.
_ready: set[str] = set()


def _lock(gitdir: str) -> asyncio.Lock:
    lock = _locks.get(gitdir)
    if lock is None:
        lock = _locks.setdefault(gitdir, asyncio.Lock())
    return lock


@dataclass
class Store:
    """Where a session's snapshots are kept, and what they cover."""

    gitdir: str
    workdir: str

    def git(self, args: str) -> str:
        return f"git --git-dir={self.gitdir} --work-tree={self.workdir} {args}"


async def _store(session_id: str) -> Store:
    """Resolve the snapshot store for a session's project."""
    slug = "default"
    try:
        from session.session import project_id_for
        slug = await slug_for(await project_id_for(session_id))
    except Exception as e:
        log.debug(f"Could not resolve project for {session_id}: {e}")
    return Store(gitdir=f"{SNAPSHOT_ROOT}/{slug}", workdir=project_directory(slug))


async def _ensure_store(sandbox, store: Store) -> bool:
    """Create the store and its exclude file. Idempotent."""
    if store.gitdir in _ready:
        return True
    excludes = "\n".join(EXCLUDE)
    script = (
        f"mkdir -p {store.gitdir} {store.workdir} && "
        f"git --git-dir={store.gitdir} init -q && "
        f"mkdir -p {store.gitdir}/info && "
        f"printf '{excludes}\n' > {store.gitdir}/info/exclude"
    )
    try:
        result = await sandbox.execute(script, workdir=store.workdir, timeout=60)
    except Exception as e:
        log.warning(f"Could not initialise snapshot store {store.gitdir}: {e}")
        return False
    if result.exit_code != 0:
        log.warning(f"Snapshot store init failed: {result.stderr}")
        return False
    _ready.add(store.gitdir)
    return True


@dataclass
class FileDiff:
    path: str
    additions: int = 0
    deletions: int = 0
    status: str = "modified"  # "added", "modified", "deleted"


async def track(session_id: str, sandbox=None, user_id: str | None = None) -> str | None:
    """Create a snapshot of the current state using git write-tree.

    Returns a snapshot ID (git tree hash) or None on failure.
    Requires a SandboxClient instance to execute git commands inside the sandbox.
    """
    if sandbox is None:
        try:
            from sandbox import sandbox_manager
            # Whose sandbox this is has to be said, not assumed. Falling back
            # to a default user here could acquire — or create — a container
            # belonging to someone else. A snapshot is best effort; skipping
            # one is strictly better than touching the wrong sandbox.
            if not user_id:
                log.warning("No sandbox and no user_id for snapshot; skipping")
                raise RuntimeError("snapshot needs an owner to acquire a sandbox")
            sandbox = await sandbox_manager.get_client(session_id, user_id=user_id)
        except Exception as e:
            log.warning(f"Cannot get sandbox for snapshot: {e}")
            return None

    store = await _store(session_id)
    try:
        async with _lock(store.gitdir):
            if not await _ensure_store(sandbox, store):
                return None

            result = await sandbox.execute(store.git("add -A"), workdir=store.workdir)
            if result.exit_code != 0:
                log.warning(f"git add failed: {result.stderr}")
                return None

            # write-tree, not commit: the tree hash alone is enough to restore
            # from, and skipping the commit keeps the store free of a history
            # nobody reads.
            result = await sandbox.execute(store.git("write-tree"), workdir=store.workdir)
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


async def restore(snapshot_id: str, session_id: str, sandbox=None, user_id: str | None = None) -> bool:
    """Restore the working directory to a snapshot state.

    Uses git read-tree + checkout-index to restore files.
    Returns True on success, False on failure.

    Note this reverts the whole project directory, not just one session's work.
    Sessions in a project share the directory by design, so a revert is scoped
    to the project the same way an `undo` in a shared checkout would be.
    """
    if not snapshot_id:
        return False

    if sandbox is None:
        try:
            from sandbox import sandbox_manager
            # Whose sandbox this is has to be said, not assumed. Falling back
            # to a default user here could acquire — or create — a container
            # belonging to someone else. A snapshot is best effort; skipping
            # one is strictly better than touching the wrong sandbox.
            if not user_id:
                log.warning("No sandbox and no user_id for snapshot; skipping")
                raise RuntimeError("snapshot needs an owner to acquire a sandbox")
            sandbox = await sandbox_manager.get_client(session_id, user_id=user_id)
        except Exception as e:
            log.warning(f"Cannot get sandbox for restore: {e}")
            return False

    store = await _store(session_id)
    try:
        async with _lock(store.gitdir):
            if not await _ensure_store(sandbox, store):
                return False

            result = await sandbox.execute(
                store.git(f"read-tree {snapshot_id}"), workdir=store.workdir)
            if result.exit_code != 0:
                log.warning(f"git read-tree failed: {result.stderr}")
                return False

            result = await sandbox.execute(
                store.git("checkout-index -a -f"), workdir=store.workdir)
            if result.exit_code != 0:
                log.warning(f"git checkout-index failed: {result.stderr}")
                return False

            # Untracked files added after the snapshot go too. Ignored paths
            # (node_modules and friends) survive: `clean -fd` without -x leaves
            # them alone, which is what makes a revert survivable.
            await sandbox.execute(store.git("clean -fd"), workdir=store.workdir)

        log.info(f"Restored snapshot {snapshot_id[:12]} for session {session_id[:8]}")
        return True

    except Exception as e:
        log.warning(f"Failed to restore snapshot {snapshot_id}: {e}")
        return False


async def diff(from_snapshot: str, to_snapshot: str, sandbox=None, session_id: str = "", user_id: str | None = None) -> list[FileDiff]:
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
            # Whose sandbox this is has to be said, not assumed. Falling back
            # to a default user here could acquire — or create — a container
            # belonging to someone else. A snapshot is best effort; skipping
            # one is strictly better than touching the wrong sandbox.
            if not user_id:
                log.warning("No sandbox and no user_id for snapshot; skipping")
                raise RuntimeError("snapshot needs an owner to acquire a sandbox")
            sandbox = await sandbox_manager.get_client(session_id, user_id=user_id)
        except Exception as e:
            log.warning(f"Cannot get sandbox for diff: {e}")
            return []

    store = await _store(session_id)
    try:
        # Get diff stats between two tree objects
        result = await sandbox.execute(
            store.git(f"diff-tree --numstat -r {from_snapshot} {to_snapshot}"),
            workdir=store.workdir,
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
            store.git(f"diff-tree --name-status -r {from_snapshot} {to_snapshot}"),
            workdir=store.workdir,
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


async def diff_full(from_snapshot: str, to_snapshot: str, sandbox=None, session_id: str = "", user_id: str | None = None) -> list[dict]:
    """Compute full diff with hunks between two snapshots.

    Returns a list of DiffEntry-compatible dicts including hunks.
    """
    if not from_snapshot or not to_snapshot or from_snapshot == to_snapshot:
        return []

    if sandbox is None:
        try:
            from sandbox import sandbox_manager
            # Whose sandbox this is has to be said, not assumed. Falling back
            # to a default user here could acquire — or create — a container
            # belonging to someone else. A snapshot is best effort; skipping
            # one is strictly better than touching the wrong sandbox.
            if not user_id:
                log.warning("No sandbox and no user_id for snapshot; skipping")
                raise RuntimeError("snapshot needs an owner to acquire a sandbox")
            sandbox = await sandbox_manager.get_client(session_id, user_id=user_id)
        except Exception as e:
            log.warning(f"Cannot get sandbox for diff_full: {e}")
            return []

    store = await _store(session_id)
    try:
        # Get unified diff
        result = await sandbox.execute(
            store.git(f"diff {from_snapshot} {to_snapshot} --unified=3"),
            workdir=store.workdir,
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
