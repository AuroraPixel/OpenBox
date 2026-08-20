"""Skill discovery and loading from SKILL.md files."""
import os
import time
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
    # Directory holding SKILL.md, on the machine running the backend. Note this
    # is NOT reachable from the agent's tools, which execute in the sandbox.
    path: str = ""


# Cache
_skills: dict[str, SkillInfo] = {}
_loaded = False
# Fingerprint of what the last scan saw, so an edit on disk is noticed. The
# server is long-lived; without this, adding or editing a skill did nothing
# until a restart, and the description shipped to the model stayed stale.
_fingerprint: tuple = ()
# The freshness check stats every SKILL.md, which measured 7.3ms at 250 skills.
# That is nothing against an LLM step, but it is blocking I/O on the event loop
# and the loop asks once per step per session. Rate-limiting it bounds the cost
# no matter how fast sessions step, and two seconds is well inside what someone
# editing a skill file would notice.
_CHECK_INTERVAL_SECONDS = 2.0
_last_check = 0.0


def _skill_dirs() -> list[Path]:
    """Every directory scanned for SKILL.md files."""
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    cwd = Path.cwd()
    return [Path(config_home) / n / "skills" for n in ("openbox", "openagent")] + [
        cwd / ".openbox" / "skills",
        cwd / ".openagent" / "skills",
        cwd / ".claude" / "skills",
        cwd / ".agents" / "skills",
    ]


def _current_fingerprint() -> tuple:
    """Cheap stat-only signature of the skills on disk.

    Files catch edits and deletions; the directories holding them catch
    additions, since a new skill directory bumps its parent's mtime.
    """
    entries = []
    for base in _skill_dirs():
        try:
            if not base.exists():
                continue
            entries.append((str(base), base.stat().st_mtime_ns))
            for md in base.rglob("SKILL.md"):
                entries.append((str(md), md.stat().st_mtime_ns))
                entries.append((str(md.parent), md.parent.stat().st_mtime_ns))
        except OSError:
            # A directory that vanished mid-scan just contributes nothing.
            continue
    return tuple(sorted(set(entries)))


async def _ensure_fresh() -> None:
    """Reload if the skills on disk no longer match what is cached."""
    global _last_check
    if not _loaded:
        await load_skills()
        return
    now = time.monotonic()
    if now - _last_check < _CHECK_INTERVAL_SECONDS:
        return
    _last_check = now
    try:
        current = _current_fingerprint()
    except Exception as e:
        log.debug(f"Could not fingerprint skills, keeping cache: {e}")
        return
    if current != _fingerprint:
        log.info("Skills changed on disk, reloading")
        await load_skills()


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
                path=str(skill_md.parent),
            ))
        except Exception as e:
            log.warning(f"Failed to load skill from {skill_md}: {e}")

    return results


async def load_skills() -> None:
    """Load all available skills."""
    global _skills, _loaded, _fingerprint, _last_check
    _skills.clear()

    globals_, projects = _skill_dirs()[:2], _skill_dirs()[2:]
    for global_dir in globals_:
        for skill in _scan_directory(global_dir, "global"):
            _skills[skill.name] = skill
    for skills_dir in projects:
        for skill in _scan_directory(skills_dir, "project"):
            _skills[skill.name] = skill

    try:
        _fingerprint = _current_fingerprint()
    except Exception:
        _fingerprint = ()
    _loaded = True
    _last_check = time.monotonic()
    log.info(f"Loaded {len(_skills)} skills")


async def get_skill(name: str) -> SkillInfo | None:
    """Get a skill by name."""
    await _ensure_fresh()
    return _skills.get(name)


async def list_skills() -> list[SkillInfo]:
    """List all available skills."""
    await _ensure_fresh()
    return list(_skills.values())
