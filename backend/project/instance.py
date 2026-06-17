"""Runtime instance context."""
from project.project import Project, discover_project


# Singleton project instance
_project: Project | None = None


def get_project() -> Project:
    """Get the current project."""
    global _project
    if _project is None:
        _project = discover_project()
    return _project


def set_project(project: Project) -> None:
    """Override the current project (for testing)."""
    global _project
    _project = project
