"""Project discovery: identify projects by git root."""
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.log import create_logger

log = create_logger("project")


@dataclass
class Project:
    id: str
    name: str
    directory: str
    vcs: str | None = None  # "git" or None


def discover_project(directory: str | None = None) -> Project:
    """Discover the project in the given directory."""
    cwd = directory or os.getcwd()

    # Try to find git root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        if result.returncode == 0:
            git_root = result.stdout.strip()

            # Get a stable project ID from the first commit hash
            id_result = subprocess.run(
                ["git", "rev-list", "--max-parents=0", "HEAD"],
                capture_output=True, text=True, cwd=git_root, timeout=5,
            )
            project_id = id_result.stdout.strip()[:12] if id_result.returncode == 0 else Path(git_root).name

            return Project(
                id=project_id,
                name=Path(git_root).name,
                directory=git_root,
                vcs="git",
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # No git repo found
    return Project(
        id=Path(cwd).name,
        name=Path(cwd).name,
        directory=cwd,
        vcs=None,
    )
