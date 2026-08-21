"""Desktop control plumbing for the `computer` tool (X11 sandboxes).

Two problems this module solves, both learned by probing the live Wuying
desktop rather than assuming:

1. **The X session is not where a headless process expects it.** The action
   server runs as root with no DISPLAY, while the desktop is `:1` guarded by
   an xauth file at a path that changes every boot (`/tmp/xauth_XXXXXX`).
   `obx-x` discovers both from the running session's own process environment.

2. **The screen is 4K; models cannot aim at 4K.** Vision models are calibrated
   around ~1024x768–1280x800, so `obx-shot` downscales and reports the exact
   scale factor, which the tool uses to map model coordinates back to real
   pixels.

Both are installed as system-level CLIs (like `obx-file`), so the agent can
also drive the desktop by hand from the terminal.
"""
import base64
import json
import shlex

from core.log import create_logger

log = create_logger("sandbox.desktop")

#: Bounding box the screenshot is fitted into before it reaches the model.
#: 1280x800 is the sweet spot the vendor guidance converges on: bigger burns
#: tokens and does not improve targeting; smaller loses UI text.
MODEL_MAX_W = 1280
MODEL_MAX_H = 800

SHOT_PATH = "/tmp/obx-screen.png"

#: Packages the desktop tools need. Installed once per container.
APT_PACKAGES = ["xdotool", "scrot", "x11-utils", "wmctrl"]

OBX_X_SCRIPT = """#!/bin/sh
# obx-x - run a command against the desktop's X session.
# Finds DISPLAY/XAUTHORITY from the running session because a headless
# service has neither, and the xauth path is regenerated every boot.
set -e
if [ -z "$DISPLAY" ] || [ -z "$XAUTHORITY" ]; then
  for p in $(pgrep -x gnome-shell 2>/dev/null) \
           $(pgrep -x gnome-session-binary 2>/dev/null) \
           $(pgrep -x plasmashell 2>/dev/null) \
           $(pgrep -x xfce4-session 2>/dev/null) \
           $(pgrep -x Xorg 2>/dev/null); do
    [ -r "/proc/$p/environ" ] || continue
    d=$(tr '\\0' '\\n' < "/proc/$p/environ" 2>/dev/null | grep '^DISPLAY=' | head -1)
    a=$(tr '\\0' '\\n' < "/proc/$p/environ" 2>/dev/null | grep '^XAUTHORITY=' | head -1)
    if [ -n "$d" ]; then
      export "$d"
      [ -n "$a" ] && export "$a"
      break
    fi
  done
fi
# Last resort: a live socket tells us the display number even if no session
# process exposed it.
if [ -z "$DISPLAY" ]; then
  for s in /tmp/.X11-unix/X*; do
    n=${s##*/X}
    case "$n" in [0-9]*) DISPLAY=":$n"; export DISPLAY; break;; esac
  done
fi
[ -n "$DISPLAY" ] || { echo "obx-x: no X display found" >&2; exit 3; }
exec "$@"
"""

OBX_SHOT_SCRIPT = '''#!/usr/bin/env python3
"""obx-shot <max_w> <max_h> <dest> - screenshot the desktop, downscaled.

Prints one JSON line describing the geometry so the caller can map model
coordinates back to real pixels. Downscaling happens HERE, on the desktop,
so a 4K PNG never crosses the network.
"""
import json
import os
import subprocess
import sys
import tempfile

from PIL import Image

max_w, max_h, dest = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]

tmp = tempfile.mktemp(suffix=".png")
try:
    # -o overwrites; -p keeps the pointer visible so the model can see it.
    subprocess.run(["scrot", "-o", "-p", tmp], check=True, capture_output=True, timeout=30)
    img = Image.open(tmp)
    native_w, native_h = img.size
    scale = min(1.0, max_w / native_w, max_h / native_h)
    img = img.convert("RGB")
    if scale < 1.0:
        img = img.resize((round(native_w * scale), round(native_h * scale)), Image.LANCZOS)
    img.save(dest, "PNG", optimize=True)
    print(json.dumps({
        "native": [native_w, native_h],
        "scaled": list(img.size),
        "bytes": os.path.getsize(dest),
    }))
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
'''

#: Container keys whose desktop tooling is ready, for this process lifetime.
_ready: set[str] = set()


def _install_script(name: str, body: str) -> str:
    """Shell that writes a script to PATH, preferring /usr/local/bin."""
    b64 = base64.b64encode(body.encode()).decode()
    return (
        f"printf %s {b64} | base64 -d > /tmp/.{name} && chmod +x /tmp/.{name} && "
        f"(sudo -n install -m755 /tmp/.{name} /usr/local/bin/{name} 2>/dev/null || "
        f'(mkdir -p "$HOME/.local/bin" && install -m755 /tmp/.{name} "$HOME/.local/bin/{name}"))'
    )


class NoDesktopError(RuntimeError):
    """The sandbox has no graphical session at all."""


async def has_display(client) -> bool:
    """Whether this sandbox has an X display to drive.

    Checked before installing anything: plain docker/k8s sandboxes are
    headless, and spending a 5-minute apt install to then fail with
    "cannot open display" is a miserable way to learn that.
    """
    probe = await client.execute(
        "ls /tmp/.X11-unix/X* >/dev/null 2>&1 && echo yes || echo no", timeout=15
    )
    return probe.stdout.strip().endswith("yes")


def invalidate(container_key: str) -> None:
    """Forget that a sandbox was prepared (it was recreated under us)."""
    _ready.discard(container_key)
    _x_ready.discard(container_key)


#: Containers that have `obx-x` alone, without the screenshot toolchain.
_x_ready: set[str] = set()


async def ensure_x_helper(client, container_key: str) -> None:
    """Install just `obx-x` — the X-session finder.

    Launching a browser needs the desktop's DISPLAY/XAUTHORITY and nothing
    else; making that path wait on the screenshot toolchain's apt install
    would put minutes of unrelated setup in front of the first page load.
    """
    if container_key in _ready or container_key in _x_ready:
        return
    result = await client.execute(_install_script("obx-x", OBX_X_SCRIPT), timeout=30)
    if result.exit_code != 0:
        raise RuntimeError(f"obx-x install failed: {result.stderr[:200]}")
    _x_ready.add(container_key)


async def ensure_desktop_tools(client, container_key: str) -> None:
    """Install xdotool/scrot + the obx-x / obx-shot helpers (idempotent).

    Raises NoDesktopError when the sandbox is headless, and RuntimeError with
    the actual apt output when a package is missing and cannot be installed —
    a silent failure here shows up much later as an inscrutable "command not
    found" mid-task.
    """
    if container_key in _ready:
        return

    if not await has_display(client):
        raise NoDesktopError(
            "This sandbox has no graphical desktop (no X display). The computer "
            "tool only works on desktop-backed sandboxes; use bash for headless work."
        )

    missing = await client.execute(
        "for t in xdotool scrot xdpyinfo; do command -v $t >/dev/null || echo $t; done",
        timeout=20,
    )
    needed = [t for t in missing.stdout.split() if t]
    if needed:
        pkgs = " ".join(APT_PACKAGES)
        install = await client.execute(
            f"sudo -n apt-get update -qq >/dev/null 2>&1; sudo -n DEBIAN_FRONTEND=noninteractive "
            f"apt-get install -y -qq {pkgs} 2>&1 | tail -5",
            timeout=300,
        )
        verify = await client.execute(
            "for t in xdotool scrot; do command -v $t >/dev/null || echo $t; done", timeout=20
        )
        still = [t for t in verify.stdout.split() if t]
        if still:
            raise RuntimeError(
                f"Desktop tools missing and apt could not install them: {', '.join(still)}. "
                f"apt said: {install.stdout.strip()[:300]}"
            )

    # PIL does the downscale; without it obx-shot cannot run.
    pil = await client.execute('python3 -c "import PIL" 2>&1', timeout=20)
    if pil.exit_code != 0:
        await client.execute(
            "sudo -n DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-pil 2>&1 | tail -3",
            timeout=300,
        )
        pil = await client.execute('python3 -c "import PIL" 2>&1', timeout=20)
        if pil.exit_code != 0:
            raise RuntimeError("python3-pil is required for screenshot scaling and could not be installed")

    for name, body in (("obx-x", OBX_X_SCRIPT), ("obx-shot", OBX_SHOT_SCRIPT)):
        result = await client.execute(_install_script(name, body), timeout=30)
        if result.exit_code != 0:
            raise RuntimeError(f"{name} install failed: {result.stderr[:200]}")

    _ready.add(container_key)


def x(command: str) -> str:
    """Wrap a command so it runs against the desktop's X session."""
    return f'PATH="$HOME/.local/bin:$PATH" obx-x {command}'


async def take_screenshot(client, dest: str = SHOT_PATH) -> dict:
    """Capture + downscale on the desktop. Returns geometry metadata."""
    result = await client.execute(
        x(f"obx-shot {MODEL_MAX_W} {MODEL_MAX_H} {shlex.quote(dest)}"), timeout=90
    )
    if result.exit_code != 0:
        raise RuntimeError(result.stderr.strip()[:300] or "screenshot failed")
    line = (result.stdout or "").strip().splitlines()
    if not line:
        raise RuntimeError("obx-shot returned no geometry")
    try:
        return json.loads(line[-1])
    except json.JSONDecodeError:
        raise RuntimeError(f"unexpected obx-shot output: {line[-1][:160]}")


def to_native(x_model: int, y_model: int, geometry: dict) -> tuple[int, int]:
    """Map model-space coordinates onto real screen pixels.

    The model aims at the downscaled screenshot it was shown; xdotool needs
    real pixels. Clamped to the screen so an overshoot lands on the edge
    rather than being silently dropped by X.
    """
    native_w, native_h = geometry["native"]
    scaled_w, scaled_h = geometry["scaled"]
    real_x = round(x_model * native_w / max(1, scaled_w))
    real_y = round(y_model * native_h / max(1, scaled_h))
    return (
        max(0, min(native_w - 1, real_x)),
        max(0, min(native_h - 1, real_y)),
    )
