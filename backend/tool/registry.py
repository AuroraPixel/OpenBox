"""Tool registry: manages all available tools."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from tool.tool import ToolInfo
from core.log import create_logger

log = create_logger("tool.registry")

# Global tool registry
_tools: dict[str, ToolInfo] = {}


def register(tool: ToolInfo) -> None:
    """Register a tool."""
    _tools[tool.id] = tool
    log.debug(f"Registered tool: {tool.id}")


def get_tool(tool_id: str) -> ToolInfo | None:
    """Get a tool by ID."""
    return _tools.get(tool_id)


def list_tools() -> list[ToolInfo]:
    """List all registered tools."""
    return list(_tools.values())


def get_tools_for_agent(tool_ids: list[str]) -> dict[str, ToolInfo]:
    """Get tools filtered by a list of tool IDs."""
    return {tid: _tools[tid] for tid in tool_ids if tid in _tools}


def register_builtin_tools() -> None:
    """Register all built-in tools."""
    from tool.bash import bash_tool
    from tool.read import read_tool
    from tool.write import write_tool
    from tool.edit import edit_tool
    from tool.apply_patch import apply_patch_tool
    from tool.glob_tool import glob_tool
    from tool.grep import grep_tool
    from tool.task import task_tool
    from tool.batch import batch_tool
    from tool.question_tool import question_tool
    from tool.todo_tool import todo_write_tool, todo_read_tool
    from tool.plan import plan_enter_tool, plan_exit_tool
    from tool.skill_tool import skill_tool
    from tool.web_fetch import web_fetch_tool
    from tool.web_search import web_search_tool
    from tool.invalid import invalid_tool
    from tool.multiedit import multiedit_tool
    from tool.cron_tool import cron_tool
    from tool.view_image import view_image_tool
    from tool.computer import computer_tool
    from tool.browser_mode import browser_mode_tool

    for tool in [
        bash_tool, read_tool, write_tool, edit_tool, apply_patch_tool,
        glob_tool, grep_tool, task_tool, batch_tool, question_tool,
        todo_write_tool, todo_read_tool, plan_enter_tool, plan_exit_tool,
        skill_tool, web_fetch_tool, web_search_tool, invalid_tool,
        multiedit_tool, cron_tool, view_image_tool, computer_tool, browser_mode_tool,
    ]:
        register(tool)

    log.info(f"Registered {len(_tools)} built-in tools")

    # Load custom tools from .openbox/tools/*.py (fallback .openagent/tools/)
    register_custom_tools()


def register_custom_tools() -> None:
    """Scan .openbox/tools/*.py (or .openagent/tools/) in the cwd and register any ToolInfo instances found."""
    tools_dir = Path.cwd() / ".openbox" / "tools"
    if not tools_dir.is_dir():
        tools_dir = Path.cwd() / ".openagent" / "tools"
    if not tools_dir.is_dir():
        log.debug("No custom tools directory found")
        return

    py_files = sorted(tools_dir.glob("*.py"))
    if not py_files:
        log.debug(f"No .py files found in {tools_dir}")
        return

    loaded_count = 0
    for py_file in py_files:
        module_name = f"_openbox_custom_tool_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                log.warning(f"Cannot create module spec for {py_file}, skipping")
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception:
            log.warning(f"Failed to import custom tool file {py_file}, skipping", exc_info=True)
            # Clean up partial registration in sys.modules
            sys.modules.pop(module_name, None)
            continue

        # Scan module-level attributes for ToolInfo instances
        for attr_name in dir(module):
            attr = getattr(module, attr_name, None)
            if isinstance(attr, ToolInfo):
                register(attr)
                loaded_count += 1
                log.info(f"Loaded custom tool '{attr.id}' from {py_file.name}")

    log.info(f"Loaded {loaded_count} custom tool(s) from {tools_dir}")
