"""Skill discovery and loading from SKILL.md files."""
import os
from dataclasses import dataclass
from pathlib import Path

from core.markdown import parse_frontmatter
from core.log import create_logger

log = create_logger("skill")


@dataclass
class SkillInfo:
    name: str
    description: str
    source: str  # "global", "project", "remote"
    content: str


# Cache
_skills: dict[str, SkillInfo] = {}
_loaded = False


MAX_DESCRIPTION_CHARS = 500


def _clip_description(text: str) -> str:
    """One-line trigger hint, collapsed and length-capped."""
    text = " ".join((text or "").split())
    if len(text) <= MAX_DESCRIPTION_CHARS:
        return text
    return text[:MAX_DESCRIPTION_CHARS].rstrip() + "…"


def _scan_directory(base_dir: Path, source: str) -> list[SkillInfo]:
    """Scan a directory for SKILL.md files."""
    results = []
    if not base_dir.exists():
        return results

    for skill_md in base_dir.rglob("SKILL.md"):
        try:
            content = skill_md.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)

            name = metadata.get("name", skill_md.parent.name)
            # Clipped at the source: the description is advertised on every
            # request, and a frontmatter that has grown into prose costs tokens
            # on all of them. The full text is in the body, which the skill tool
            # returns when the model actually loads it.
            description = _clip_description(metadata.get("description", ""))

            results.append(SkillInfo(
                name=name,
                description=description,
                source=source,
                content=body,
            ))
        except Exception as e:
            log.warning(f"Failed to load skill from {skill_md}: {e}")

    return results


async def load_skills() -> None:
    """Load all available skills."""
    global _skills, _loaded
    _skills.clear()

    # 1. Global skills
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    for global_name in ["openbox", "openagent"]:
        global_dir = Path(config_home) / global_name / "skills"
        for skill in _scan_directory(global_dir, "global"):
            _skills[skill.name] = skill

    # 2. Project-level skills
    cwd = Path.cwd()
    for skills_dir in [
        cwd / ".openbox" / "skills",
        cwd / ".openagent" / "skills",
        cwd / ".claude" / "skills",
        cwd / ".agents" / "skills",
    ]:
        for skill in _scan_directory(skills_dir, "project"):
            _skills[skill.name] = skill

    _loaded = True
    log.info(f"Loaded {len(_skills)} skills")


async def get_skill(name: str) -> SkillInfo | None:
    """Get a skill by name."""
    if not _loaded:
        await load_skills()
    return _skills.get(name)


async def list_skills() -> list[SkillInfo]:
    """List all available skills."""
    if not _loaded:
        await load_skills()
    return list(_skills.values())
