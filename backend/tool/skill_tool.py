"""Skill tool: load and inject skill content."""
from __future__ import annotations

from dataclasses import replace
from pydantic import BaseModel, Field

from tool.tool import ToolResult, ToolContext, ToolInfo, define_tool


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


async def build_skill_tool_with_listing(sandbox=None) -> ToolInfo:
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

    if not skills:
        return skill_tool  # No skills — use original static description

    # Build the enriched description with available skills list
    lines = [
        _BASE_DESCRIPTION,
        "",
        "<available_skills>",
    ]
    for s in skills:
        lines.append(f"  <skill>")
        lines.append(f"    <name>{s.get('name', '')}</name>")
        lines.append(f"    <description>{s.get('description', '')}</description>")
        lines.append(f"  </skill>")
    lines.append("</available_skills>")

    enriched_description = "\n".join(lines)
    return replace(skill_tool, description=enriched_description)
