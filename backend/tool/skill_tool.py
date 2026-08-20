"""Skill tool: load and inject skill content."""
from __future__ import annotations

from dataclasses import replace
from pydantic import BaseModel, Field

from core.log import create_logger
from tool.tool import ToolResult, ToolContext, ToolInfo, define_tool

log = create_logger("tool.skill")


class SkillArgs(BaseModel):
    skill: str = Field(description="Name of the skill to load")
    args: str = Field(default="", description="Optional arguments for the skill")


#: Where the container keeps user-installed skills, and the convenience symlink
#: inside the workspace that points at it. Built-in skills live elsewhere and
#: are not covered by that link.
USER_SKILLS_DIR = "/data/skills"
WORKSPACE_SKILLS_LINK = "/workspace/skills"

_BASE_DESCRIPTION = """\
Load a specialized skill that provides domain-specific instructions and workflows.

When you recognize that a task matches one of the available skills, use this tool to load the full skill instructions. The skill will inject detailed instructions, workflows, and access to bundled resources into the conversation context.

Usage:
- Use the skill name as the parameter (e.g., "dev-browser")
- Skills can accept optional arguments via the args parameter
- When a user references a "slash command" or "/<something>", it may map to a skill — use this tool to load it
- The skill content will be returned in the tool output for you to follow"""


# Never worth naming: the model cannot act on them and they crowd out the files
# that matter. A single skill with a node_modules tree contributed 890 entries,
# which is what a 50-line listing gets spent on if nothing filters it.
_SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv",
              "dist", "build", ".next", ".cache"}


def _host_files(base: str, limit: int = 20) -> list[str]:
    """Files bundled beside a host skill's SKILL.md, sampled.

    SKILL.md itself is excluded — its content is inlined right above the
    listing. So are dotfiles and macOS AppleDouble stubs (._foo), which appear
    whenever a skill has been zipped on a Mac.
    """
    from pathlib import Path
    try:
        out = []
        root = Path(base)
        for f in sorted(root.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(root)
            if any(p in _SKIP_DIRS for p in rel.parts):
                continue
            if any(p.startswith(".") for p in rel.parts):
                continue
            if rel.name == "SKILL.md":
                continue
            out.append(str(rel))
            if len(out) >= limit:
                break
        return out
    except OSError:
        return []


async def execute(args: SkillArgs, ctx: ToolContext) -> ToolResult:
    """Load a skill and inject its content. Tries container first, then local."""
    content = None
    base_dir = ""
    files: list[str] = []
    host_only = False
    container_error: str | None = None

    # Try loading from container sandbox first
    if ctx.sandbox:
        try:
            skill_data = await ctx.sandbox.get_skill(args.skill)
            content = skill_data.get("content", "")
            base_dir = skill_data.get("base_dir", "")
            files = skill_data.get("files", [])
        except Exception as e:
            # Kept, not swallowed: an unreachable container and a genuinely
            # missing skill need different answers. Reporting "not found" for a
            # dropped tunnel tells the model to give up on a skill that exists.
            container_error = str(e) or e.__class__.__name__
            log.debug(f"Container lookup for skill {args.skill!r} failed: {e}")

    # Fall back to local skills
    if not content:
        from skill.skill import get_skill
        skill = await get_skill(args.skill)
        if not skill:
            if container_error:
                return ToolResult(
                    title=f"Could not reach the container to load: {args.skill}",
                    output=(
                        f"The skill could not be loaded because the container was "
                        f"unreachable: {container_error}\n"
                        f"No skill named '{args.skill}' exists on the backend host "
                        f"either, so this may still be a valid skill. This is an "
                        f"infrastructure failure, not a missing skill — retrying "
                        f"may work."
                    ),
                    metadata={"error": "container_unreachable"},
                )
            return ToolResult(
                title=f"Skill not found: {args.skill}",
                output=f"No skill named '{args.skill}' found.",
            )
        content = skill.content
        # A host skill's bundled files live on the backend, which the agent's
        # tools cannot see — they run in the sandbox. Name them, but do not hand
        # over a path the model would only fail to read.
        host_only = True
        files = _host_files(skill.path) if skill.path else []

    if args.args:
        content = content.replace("$ARGUMENTS", args.args)

    # Build output following opencode's pattern: content + base dir + file listing
    output_parts = [
        f"<skill_content name=\"{args.skill}\">",
        content.strip(),
    ]
    if base_dir:
        output_parts.append("")
        output_parts.append(f"Base directory for this skill: {base_dir}")
        output_parts.append("Relative paths in this skill should be resolved from this directory.")
        # Only user-installed skills live under the path /workspace/skills points
        # at. Saying this for a built-in skill sent the model to an empty
        # directory, one line after being given the correct base directory.
        if base_dir.startswith(USER_SKILLS_DIR):
            output_parts.append(
                f"The skill directory is also reachable at {WORKSPACE_SKILLS_LINK}/.")
    if files:
        output_parts.append("")
        if host_only:
            output_parts.append("This skill is installed on the backend host, not in")
            output_parts.append("your workspace. The files below ship with it but are")
            output_parts.append("NOT readable from here — follow the instructions above")
            output_parts.append("without trying to open them.")
        output_parts.append("<skill_files>")
        for f in files[:50]:
            output_parts.append(f"  {f}")
        if len(files) > 50:
            output_parts.append(f"  ... and {len(files) - 50} more files")
        output_parts.append("</skill_files>")
    output_parts.append("</skill_content>")

    return ToolResult(
        title=f"Loaded skill: {args.skill}",
        output="\n".join(output_parts),
    )


skill_tool = define_tool(
    "skill",
    description=_BASE_DESCRIPTION,
    parameters=SkillArgs,
    execute=execute,
    sandbox_required=False,
    never_prune=True,
)


# The listing rides along on every request of every step, so it is budgeted
# rather than unbounded. Measured on synthetic catalogues: at full description a
# 250-skill install rendered 16,454 tokens per request, and a single skill whose
# frontmatter description had run to 40k characters rendered 10,188 on its own.
#
# A frontmatter description is a one-line trigger hint by design — enough for the
# model to decide whether to load the skill, which is when the real content
# arrives. Anything past that is paid for on every request and read on none.
MAX_DESCRIPTION_CHARS = 500
LISTING_BUDGET_TOKENS = 2_000


def _clip(text: str, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _permitted(skills: list[dict], ruleset: list) -> list[dict]:
    """Drop skills the agent is denied, so its catalogue matches its reach.

    Mirrors opencode's SkillV2.available(). Listing a skill the agent cannot
    load costs tokens on every request to advertise a guaranteed refusal.
    """
    if not ruleset:
        return skills
    from permission.permission import evaluate
    out = []
    for s in skills:
        try:
            if evaluate("skill", s.get("name", ""), ruleset).action != "deny":
                out.append(s)
        except Exception:
            out.append(s)  # a malformed rule must not hide a working skill
    return out


def render_listing(skills: list[dict], budget: int = LISTING_BUDGET_TOKENS) -> str:
    """Render <available_skills>, degrading to names once the budget is spent.

    Names are kept for every skill even when descriptions have to go: the model
    can still load one by name, and a silently truncated list would read as
    "these are all the skills there are".
    """
    from core.token import token_estimate

    entries = sorted(skills, key=lambda s: s.get("name", ""))
    lines = ["<available_skills>"]
    spent = 0
    names_only: list[str] = []

    for s in entries:
        name = s.get("name", "")
        if not name:
            continue
        if names_only:
            names_only.append(name)
            continue
        block = [
            "  <skill>",
            f"    <name>{name}</name>",
            f"    <description>{_clip(s.get('description', ''))}</description>",
            "  </skill>",
        ]
        cost = token_estimate("\n".join(block))
        if spent + cost > budget:
            names_only.append(name)
            continue
        lines.extend(block)
        spent += cost

    if names_only:
        log.info(f"Skill listing over budget: {len(names_only)} of {len(entries)} "
                 f"listed by name only")
        lines.append("  <!-- Description budget reached. These skills are also")
        lines.append("       available; call the tool by name to see what one does. -->")
        for name in names_only:
            lines.append(f"  <skill><name>{name}</name></skill>")

    lines.append("</available_skills>")
    return "\n".join(lines)


async def build_skill_tool_with_listing(sandbox=None, ruleset: list | None = None) -> ToolInfo:
    """Build a copy of skill_tool with <available_skills> injected into the description.

    This is called per-loop-iteration so the model knows which skills are available.
    Follows the same pattern as opencode's SkillTool.init().
    """
    skills: list[dict] = []

    # 1. Gather skills from the container
    if sandbox:
        try:
            container_skills = await sandbox.list_skills()
            if isinstance(container_skills, list):
                skills.extend(container_skills)
        except Exception:
            pass

    # 2. Gather local skills
    try:
        from skill.skill import list_skills as list_local_skills
        local = await list_local_skills()
        container_names = {cs.get("name") for cs in skills}
        for s in local:
            # Container skills win: they are the ones the agent's tools can
            # actually reach. Say so, though — a host skill being shadowed by a
            # different container skill of the same name is worth knowing about
            # when the loaded instructions are not the ones that were edited.
            if s.name in container_names:
                log.info(f"Skill {s.name!r} exists in both the container and on "
                         f"the host; using the container's copy")
                continue
            skills.append({"name": s.name, "description": s.description})
    except Exception:
        pass

    skills = _permitted(skills, ruleset or [])

    if not skills:
        return skill_tool  # No skills — use original static description

    enriched_description = "\n".join([_BASE_DESCRIPTION, "", render_listing(skills)])
    return replace(skill_tool, description=enriched_description)
