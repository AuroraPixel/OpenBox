"""Deciding which tools a step may call.

Three things happen here that used to be interleaved in the loop body: the
agent's declared toolset is looked up, tools the sandbox offers are merged in,
and anything the permission rules deny is removed *before the model sees the
schema*.

That last step is the point. Denying a tool at call time still lets the model
propose it, burn a turn and get refused; removing it from the schema means the
option never exists. Mirrors opencode's PermissionNext.disabled() feeding
resolveTools().
"""
from __future__ import annotations

from core.log import create_logger
from permission.permission import Rule, disabled_tools
from tool.registry import get_tools_for_agent

log = create_logger("agent.tool_resolution")


def agent_ruleset(agent_def) -> list[Rule]:
    """Permission rules declared on the agent, as Rule objects.

    Entries that are not dicts are skipped rather than raising: an agent
    definition is user-editable config, and one malformed rule should not take
    the whole run down.
    """
    return [
        Rule(
            permission=r.get("permission", "*"),
            pattern=r.get("pattern", "*"),
            action=r.get("action", "ask"),
        )
        for r in (agent_def.permission or [])
        if isinstance(r, dict)
    ]


def strip_denied(tools: dict, config_rules: list, agent_def) -> dict:
    """Drop tools denied by config or agent rules. Pure; returns a new dict."""
    merged = list(config_rules) + agent_ruleset(agent_def)
    denied = set(disabled_tools(list(tools.keys()), merged))
    return {name: t for name, t in tools.items() if name not in denied}


async def merge_sandbox_tools(tools: dict, sandbox, ruleset: list | None = None) -> dict:
    """Add the MCP tools a sandbox exposes.

    Every failure here is downgraded to a debug log: a sandbox without MCP
    configured is the normal case, not an error, and a run with fewer tools is
    far better than a run that cannot start.
    """
    if not sandbox:
        return tools

    try:
        from tool.mcp_tool import create_mcp_tools, create_mcp_resource_tool

        tools.update(await create_mcp_tools(sandbox))
        try:
            if await sandbox.list_mcp_resources():
                rt = create_mcp_resource_tool()
                tools[rt.id] = rt
        except Exception as e:
            log.debug(f"MCP resources not available: {e}")
    except Exception as e:
        log.debug(f"MCP tools not available: {e}")

    return tools


async def attach_skill_listing(tools: dict, sandbox, ruleset: list | None = None) -> dict:
    """Advertise the available skills in the skill tool's description.

    Deliberately not gated on a sandbox. Skills are discovered locally as well
    as in the container, and running without one used to mean the model was
    handed the skill tool with no idea which skills existed — so it never
    called it.
    """
    if "skill" not in tools:
        return tools
    try:
        from tool.skill_tool import build_skill_tool_with_listing

        tools["skill"] = await build_skill_tool_with_listing(sandbox, ruleset)
    except Exception as e:
        log.debug(f"Failed to enrich skill tool: {e}")
    return tools


async def resolve_step_tools(agent_def, sandbox, config_rules: list) -> dict:
    """The full set of tools a step may call, schema included."""
    tools = get_tools_for_agent(agent_def.tools)
    # The same rules that strip tools also decide which skills are worth listing.
    ruleset = list(config_rules) + agent_ruleset(agent_def)
    tools = await merge_sandbox_tools(tools, sandbox, ruleset)
    tools = await attach_skill_listing(tools, sandbox, ruleset)
    return strip_denied(tools, config_rules, agent_def)
