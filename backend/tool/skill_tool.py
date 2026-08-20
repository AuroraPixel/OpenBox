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


_BASE_DESCRIPTION = """\
Load a specialized skill that provides domain-specific instructions and workflows.

When you recognize that a task matches one of the available skills, use this tool to load the full skill instructions. The skill will inject detailed instructions, workflows, and access to bundled resources into the conversation context.

Usage:
- Use the skill name as the parameter (e.g., "dev-browser")
- Skills can accept optional arguments via the args parameter
- When a user references a "slash command" or "/<something>", it may map to a skill — use this tool to load it
- The skill content will be returned in the tool output for you to follow"""


async def execute(args: SkillArgs, ctx: ToolContext) -> ToolResult:
    """Load a skill and inject its content. Tries container first, then local."""
    content = None
    base_dir = ""
    files: list[str] = []

    # Try loading from container sandbox first
    if ctx.sandbox:
        try:
            skill_data = await ctx.sandbox.get_skill(args.skill)
            content = skill_data.get("content", "")
            base_dir = skill_data.get("base_dir", "")
            files = skill_data.get("files", [])
        except Exception:
            pass  # Fall back to local

    # Fall back to local skills
    if not content:
        from skill.skill import get_skill
        skill = await get_skill(args.skill)
        if not skill:
            return ToolResult(
                title=f"Skill not found: {args.skill}",
                output=f"No skill named '{args.skill}' found.",
            )
        content = skill.content

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
        output_parts.append("The skill directory is also symlinked at /workspace/skills/ for convenience.")
    if files:
        output_parts.append("")
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
        for s in local:
            # Avoid duplicates (container skills take precedence)
            if not any(cs.get("name") == s.name for cs in skills):
                skills.append({"name": s.name, "description": s.description})
    except Exception:
        pass

    skills = _permitted(skills, ruleset or [])

    if not skills:
        return skill_tool  # No skills — use original static description

    enriched_description = "\n".join([_BASE_DESCRIPTION, "", render_listing(skills)])
    return replace(skill_tool, description=enriched_description)
