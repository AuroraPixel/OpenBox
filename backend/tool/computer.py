"""computer: drive the sandbox's graphical desktop — see it, click it, type.

The model runs in the backend and the desktop lives on a cloud VM, so every
action is a round trip: xdotool injects input over the desktop's X session,
`scrot` captures the result, and the screenshot travels desktop → OSS →
model (never through the tunnel — see sandbox/assets.attach_sandbox_image).

Coordinates are the subtle part. The real screen is 4K; the model is shown a
downscaled screenshot and aims at THAT, so every coordinate it sends is
mapped back through the same scale factor the screenshot was taken with.
Geometry is re-read on each capture rather than assumed.
"""
import asyncio
import shlex
from typing import Literal

from pydantic import BaseModel, Field

from core.log import create_logger
from sandbox.desktop import (
    SHOT_PATH,
    NoDesktopError,
    ensure_desktop_tools,
    invalidate,
    take_screenshot,
    to_native,
    x,
)
from tool.tool import ToolResult, ToolContext, define_tool

log = create_logger("tool.computer")

#: Let the UI settle before capturing the result of an action. Menus animate;
#: capturing instantly shows the pre-action frame and the agent misreads it.
#:
#: This delay is also why no xdotool call uses `--sync`. `--sync` blocks until
#: the X server reports the pointer moved — and when the pointer is ALREADY at
#: the target that event never comes, so the call hangs for ~15s (measured on
#: the live desktop; trivially reproduced by moving to the same spot twice).
#: Settling here covers the same race without that failure mode.
SETTLE_SECONDS = 1.2

#: Actions that change the screen, so the result is worth showing the model.
_VISUAL_ACTIONS = {
    "left_click", "right_click", "middle_click", "double_click", "triple_click",
    "left_click_drag", "type", "key", "hold_key", "scroll", "mouse_move",
}

_CLICK_BUTTON = {
    "left_click": "1",
    "middle_click": "2",
    "right_click": "3",
    "double_click": "1",
    "triple_click": "1",
}

_SCROLL_BUTTON = {"up": "4", "down": "5", "left": "6", "right": "7"}

#: Cached per container: the geometry of the last capture, so a click that
#: follows a screenshot needs no extra round trip.
_geometry_cache: dict[str, dict] = {}


def _sandbox_key(ctx: ToolContext) -> str:
    """Cache identity of the machine, not the conversation.

    The desktop tooling and the screen resolution belong to the container;
    keying them by session made every new chat re-verify the install and
    re-measure a screen that had not changed.
    """
    return getattr(ctx.sandbox, "base_url", "") or f"{ctx.user_id}:{ctx.session_id}"


class ComputerArgs(BaseModel):
    action: Literal[
        "screenshot",
        "left_click",
        "right_click",
        "middle_click",
        "double_click",
        "triple_click",
        "left_click_drag",
        "mouse_move",
        "left_mouse_down",
        "left_mouse_up",
        "type",
        "key",
        "hold_key",
        "scroll",
        "cursor_position",
        "wait",
    ] = Field(description="What to do on the desktop")
    coordinate: list[int] | None = Field(
        default=None,
        description="[x, y] in the coordinate space of the screenshot you were shown. "
        "Required for clicks, mouse_move, scroll and the start of a drag.",
    )
    to_coordinate: list[int] | None = Field(
        default=None, description="[x, y] the drag releases at (left_click_drag only)"
    )
    text: str | None = Field(
        default=None,
        description="Text to type (action=type), or the key combo to press "
        "(action=key), e.g. 'Return', 'ctrl+c', 'alt+Tab', 'super'.",
    )
    scroll_direction: Literal["up", "down", "left", "right"] | None = Field(
        default=None, description="Scroll direction (action=scroll)"
    )
    scroll_amount: int = Field(default=3, description="Number of scroll clicks (action=scroll)")
    duration: float = Field(default=1.0, description="Seconds to wait (action=wait), max 10")


def _bad(message: str) -> ToolResult:
    return ToolResult(title="computer: invalid arguments", output=message)


def _validate_keys(text: str) -> str | None:
    """Shell-safe, space-separated xdotool keysyms, or None if unrecognisable.

    Keysyms are alphanumeric with `+` for combos and `_` inside names
    (Page_Down, Control_L). Anything else is not a key the model meant, and
    quoting alone should not be the only thing standing between a model
    hallucination and a shell.
    """
    keys = text.split()
    if not keys or not all(k.replace("+", "").replace("_", "").isalnum() for k in keys):
        return None
    return " ".join(shlex.quote(k) for k in keys)


def _point(value: list[int] | None, field: str) -> tuple[int, int] | None:
    if not value or len(value) != 2:
        return None
    try:
        return int(value[0]), int(value[1])
    except (TypeError, ValueError):
        log.debug(f"non-numeric {field}: {value!r}")
        return None


async def _geometry(ctx: ToolContext, key: str) -> dict:
    """Screen geometry for coordinate mapping, capturing once if unknown.

    Deliberately the geometry of the LAST capture, not a fresh reading: the
    model aimed at that screenshot, so its scale is the one that maps those
    coordinates correctly. Every action re-captures afterwards, so the cache
    tracks the screen within one action.
    """
    cached = _geometry_cache.get(key)
    if cached:
        return cached
    geometry = await take_screenshot(ctx.sandbox)
    _geometry_cache[key] = geometry
    return geometry


async def _prepare(ctx: ToolContext, key: str) -> None:
    """Ensure the desktop tooling is present, healing a stale cache.

    `ensure_desktop_tools` remembers what it installed, but a sandbox can be
    recreated under us (desktop reboot, container replaced) — then the helper
    scripts are gone while the cache still says "ready". A probe for the
    helper is one cheap round trip and turns a confusing mid-task failure
    into a silent reinstall.
    """
    await ensure_desktop_tools(ctx.sandbox, key)
    probe = await ctx.sandbox.execute(
        'PATH="$HOME/.local/bin:$PATH" command -v obx-shot >/dev/null && command -v xdotool >/dev/null'
        " && echo ok || echo gone",
        timeout=20,
    )
    if probe.stdout.strip().endswith("gone"):
        log.info(f"desktop tooling vanished for {key}; reinstalling")
        invalidate(key)
        _geometry_cache.pop(key, None)
        await ensure_desktop_tools(ctx.sandbox, key)


def _build_command(action: str, args: ComputerArgs, geometry: dict) -> str | ToolResult:
    """The xdotool invocation for an action, or a ToolResult explaining why not."""
    point = _point(args.coordinate, "coordinate")

    if action in _CLICK_BUTTON:
        if not point:
            return _bad(f"action '{action}' needs coordinate: [x, y]")
        nx, ny = to_native(*point, geometry)
        button = _CLICK_BUTTON[action]
        repeat = {"double_click": " --repeat 2 --delay 80", "triple_click": " --repeat 3 --delay 80"}.get(action, "")
        return f"xdotool mousemove {nx} {ny} click{repeat} --clearmodifiers {button}"

    if action == "mouse_move":
        if not point:
            return _bad("action 'mouse_move' needs coordinate: [x, y]")
        nx, ny = to_native(*point, geometry)
        return f"xdotool mousemove {nx} {ny}"

    if action == "left_click_drag":
        end = _point(args.to_coordinate, "to_coordinate")
        if not point or not end:
            return _bad("action 'left_click_drag' needs both coordinate and to_coordinate")
        sx, sy = to_native(*point, geometry)
        ex, ey = to_native(*end, geometry)
        return (
            f"xdotool mousemove {sx} {sy} sleep 0.1 mousedown 1 "
            f"mousemove {ex} {ey} sleep 0.2 mouseup 1"
        )

    if action == "type":
        if not args.text:
            return _bad("action 'type' needs text")
        # --delay keeps fast typing from outrunning the target app's input
        # handling; -- stops a leading dash being read as a flag.
        return f"xdotool type --clearmodifiers --delay 12 -- {shlex.quote(args.text)}"

    if action == "key":
        if not args.text:
            return _bad("action 'key' needs text, e.g. 'Return' or 'ctrl+s'")
        keys = _validate_keys(args.text)
        if keys is None:
            return _bad(f"unsupported key syntax: {args.text!r}")
        return f"xdotool key --clearmodifiers -- {keys}"

    if action == "scroll":
        if not args.scroll_direction:
            return _bad("action 'scroll' needs scroll_direction")
        button = _SCROLL_BUTTON[args.scroll_direction]
        amount = max(1, min(25, args.scroll_amount))
        move = ""
        if point:
            nx, ny = to_native(*point, geometry)
            move = f"mousemove {nx} {ny} "
        return f"xdotool {move}click --repeat {amount} --delay 60 --clearmodifiers {button}"

    if action in ("left_mouse_down", "left_mouse_up"):
        # Held-button gestures the standard action set exposes for drawing,
        # text selection and drag-and-drop that a single drag cannot express.
        verb = "mousedown" if action == "left_mouse_down" else "mouseup"
        prefix = ""
        if point:
            nx, ny = to_native(*point, geometry)
            prefix = f"mousemove {nx} {ny} "
        return f"xdotool {prefix}{verb} 1"

    if action == "hold_key":
        if not args.text:
            return _bad("action 'hold_key' needs text, e.g. 'shift'")
        key = _validate_keys(args.text)
        if key is None:
            return _bad(f"unsupported key syntax: {args.text!r}")
        seconds = max(0.1, min(10.0, args.duration))
        return f"xdotool keydown -- {key} sleep {seconds:g} keyup -- {key}"

    if action == "cursor_position":
        return "xdotool getmouselocation --shell"

    return _bad(f"unknown action: {action}")


async def _attach_screenshot(ctx: ToolContext, geometry: dict) -> str:
    """Push the current /tmp screenshot to OSS and pin it on the message."""
    from sandbox.assets import attach_sandbox_image

    width, height = geometry["scaled"]
    asset_id, size = await attach_sandbox_image(
        ctx,
        SHOT_PATH,
        "image/png",
        int(geometry.get("bytes", 0)),
        name=f"screen-{ctx.part_id or 'shot'}.png",
        transient=True,
    )
    log.debug(f"screenshot asset={asset_id} {width}x{height} {size}B")
    return f"{width}x{height}"


async def execute(args: ComputerArgs, ctx: ToolContext) -> ToolResult:
    from core.oss import OssNotConfigured, get_oss

    action = args.action
    key = _sandbox_key(ctx)

    if action == "wait":
        await asyncio.sleep(max(0.0, min(10.0, args.duration)))
        return ToolResult(title=f"waited {args.duration:g}s", output="Waited.")

    # A screenshot must reach the model as an image, which needs OSS. Fail
    # loudly here rather than silently acting blind.
    try:
        get_oss()
    except OssNotConfigured as e:
        return ToolResult(
            title="computer unavailable",
            output=f"Screenshots need OSS transfer, which is not configured: {e}",
        )

    try:
        await _prepare(ctx, key)
    except NoDesktopError as e:
        return ToolResult(title="no graphical desktop", output=str(e))
    except Exception as e:
        return ToolResult(title="computer unavailable", output=str(e)[:400])

    try:
        if action == "screenshot":
            geometry = await take_screenshot(ctx.sandbox)
            _geometry_cache[key] = geometry
            dims = await _attach_screenshot(ctx, geometry)
            native = "x".join(str(v) for v in geometry["native"])
            return ToolResult(
                title=f"screenshot {dims}",
                output=(
                    f"Screenshot attached ({dims}, downscaled from {native}). "
                    "It becomes visible to you on your next turn. Use these "
                    f"{dims} coordinates when clicking."
                ),
                metadata={"geometry": geometry},
            )

        geometry = await _geometry(ctx, key)
        command = _build_command(action, args, geometry)
        if isinstance(command, ToolResult):
            return command

        result = await ctx.sandbox.execute(x(command), timeout=60)
        if result.exit_code != 0:
            return ToolResult(
                title=f"computer: {action} failed",
                output=(result.stderr or result.stdout).strip()[:300] or "xdotool failed",
            )

        if action == "cursor_position":
            values = dict(
                line.split("=", 1) for line in result.stdout.split() if "=" in line
            )
            try:
                nx, ny = int(values.get("X", 0)), int(values.get("Y", 0))
                native_w, native_h = geometry["native"]
                scaled_w, scaled_h = geometry["scaled"]
                mx = round(nx * scaled_w / max(1, native_w))
                my = round(ny * scaled_h / max(1, native_h))
                return ToolResult(title="cursor position", output=f"Cursor is at ({mx}, {my}).")
            except (TypeError, ValueError):
                return ToolResult(title="cursor position", output=result.stdout.strip()[:200])

        # Show the model what the action did — a computer-use agent that acts
        # without seeing the result drifts within a few steps.
        note = ""
        if action in _VISUAL_ACTIONS:
            await asyncio.sleep(SETTLE_SECONDS)
            try:
                geometry = await take_screenshot(ctx.sandbox)
                _geometry_cache[key] = geometry
                dims = await _attach_screenshot(ctx, geometry)
                note = f" Screenshot attached ({dims}); you will see it next turn."
            except Exception as e:
                log.warning(f"post-action screenshot failed: {e}")
                note = " (screenshot after the action failed; take one explicitly)"

        described = _describe(action, args)
        return ToolResult(title=described, output=f"Done: {described}.{note}")

    except Exception as e:
        log.warning(f"computer {action} failed: {e}")
        return ToolResult(title=f"computer: {action} failed", output=str(e)[:400])


def _describe(action: str, args: ComputerArgs) -> str:
    if action == "type":
        preview = (args.text or "")[:40]
        return f"typed {preview!r}"
    if action == "key":
        return f"pressed {args.text}"
    if action == "scroll":
        return f"scrolled {args.scroll_direction} x{args.scroll_amount}"
    if args.coordinate:
        return f"{action} at {tuple(args.coordinate)}"
    return action


COMPUTER_DESCRIPTION = """\
Control the sandbox's graphical desktop: take a screenshot, move and click the \
mouse, type text, press keys, scroll. Use this for anything that only exists \
in a GUI — a browser page, a desktop app, a dialog — when no CLI can do the job.

Workflow: take a `screenshot` first, read it on your next turn, then act on \
what you see. Actions return a fresh screenshot automatically, so you can \
chain steps without asking for one each time.

Coordinates: the screenshot you are shown is downscaled from the real screen. \
Always give coordinates in the screenshot's own pixel space (its size is \
reported with every capture) — they are mapped back to the real display for \
you. Never guess coordinates you have not seen in a screenshot.

Typing goes to whatever currently has keyboard focus, which is often NOT the \
window you just opened. Click the window (or the field) first, then type, and \
check the next screenshot to confirm the text landed where you meant. If a \
launcher or overview overlay is covering the screen, press Escape — twice if \
a search box still holds text, since the first Escape only clears it.

Keys use xdotool names: Return, Escape, Tab, BackSpace, Delete, Up/Down/Left/\
Right, super, and combos like ctrl+c, ctrl+shift+t, alt+Tab."""

computer_tool = define_tool(
    "computer",
    description=COMPUTER_DESCRIPTION,
    parameters=ComputerArgs,
    execute=execute,
)
