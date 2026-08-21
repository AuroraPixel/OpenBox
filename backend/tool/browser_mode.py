"""browser_mode: read or change which browser the agent drives.

The two browsers behind the dev-browser skill are not interchangeable — one is
the cloud desktop's Chrome, the other is the user's own, and only the latter
has their logins. When a task turns out to need an identity the current
browser does not have, the agent should ask the user (with the `question`
tool) and then record the answer here, so the choice sticks for next time
instead of being re-litigated every session.
"""
from typing import Literal

from pydantic import BaseModel, Field

from core.log import create_logger
from session.browser_pref import (
    InvalidBrowserMode,
    get_browser_mode,
    relay_mode,
    set_browser_mode,
)
from tool.tool import ToolResult, ToolContext, define_tool

log = create_logger("tool.browser_mode")

_DESCRIBE = {
    "auto": "prefer the user's own browser, fall back to the cloud desktop's when it is not connected",
    "local": "always the cloud desktop's Chrome (no user logins)",
    "remote": "always the user's own Chrome via the extension (carries their logins)",
}


class BrowserModeArgs(BaseModel):
    action: Literal["get", "set"] = Field(
        default="get", description="Read the current setting, or change it"
    )
    mode: Literal["auto", "local", "remote"] | None = Field(
        default=None, description="Required for action=set"
    )


async def execute(args: BrowserModeArgs, ctx: ToolContext) -> ToolResult:
    from sandbox.browser import browser_status

    if args.action == "set":
        if not args.mode:
            return ToolResult(
                title="browser_mode: missing mode",
                output="action=set needs mode: auto, local or remote.",
            )
        try:
            stored = await set_browser_mode(ctx.user_id, args.mode)
        except InvalidBrowserMode as e:
            return ToolResult(title="browser_mode: invalid", output=str(e))
        # The relay is restarted lazily on the next dev-browser use rather than
        # here: restarting it now would kill any page state the current task is
        # still holding.
        log.info(f"browser mode for {ctx.user_id} -> {stored}")
        return ToolResult(
            title=f"browser mode: {stored}",
            output=(
                f"Saved. The agent will use: {_DESCRIBE[stored]}. "
                "It takes effect the next time dev-browser starts; a relay already "
                "running keeps its current mode until then."
            ),
            metadata={"mode": stored},
        )

    mode = await get_browser_mode(ctx.user_id)
    live = ""
    try:
        status = await browser_status(ctx.sandbox)
        relay = (status or {}).get("relay") or {}
        if relay:
            live = f" Relay is running in '{relay.get('mode', '?')}' mode."
        elif (status or {}).get("chrome"):
            live = " Cloud Chrome is up; the relay is not started yet."
    except Exception as e:
        log.debug(f"browser status probe skipped: {e}")

    return ToolResult(
        title=f"browser mode: {mode}",
        output=f"Setting is '{mode}' — {_DESCRIBE[mode]}.{live}",
        metadata={"mode": mode, "relay_mode": relay_mode(mode)},
    )


BROWSER_MODE_DESCRIPTION = """\
Read or change which browser the dev-browser skill drives.

`local` is Chrome on the cloud desktop — always available, but it has none of \
the user's logins. `remote` is the user's own Chrome through the browser \
extension — it carries their real sessions. `auto` prefers their own browser \
and falls back to the cloud one when the extension is not connected.

Use `get` when a task's outcome depends on being logged in as the user. If the \
current browser cannot reach what the task needs, ask the user which they want \
(the `question` tool), then record their answer with `set` so the choice \
persists instead of being asked again next session. Do not change the mode \
without asking — it decides whose browser and whose accounts get used."""

browser_mode_tool = define_tool(
    "browser_mode",
    description=BROWSER_MODE_DESCRIPTION,
    parameters=BrowserModeArgs,
    execute=execute,
    sandbox_required=False,
)
