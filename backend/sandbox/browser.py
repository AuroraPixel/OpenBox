"""Bring up browser automation *on the cloud desktop*, over raw CDP.

The dev-browser skill drives Chrome through the DevTools protocol, but it can
reach two very different browsers:

* **local** — a headed Chrome that this module launches on the Wuying desktop
  itself, exposing a debug port the relay attaches to. This is the browser the
  agent gets when the user is not watching.
* **extension** — the user's *own* browser, wherever they are, connected back
  to the desktop's relay by the dev-browser extension. The agent then acts
  inside a real, logged-in session the user can see.

Everything here runs against the desktop's loopback (ports 9333 for Chrome,
9222 for the relay), so every probe is a `curl` executed *on the desktop* — the
backend only reaches the desktop through the action-server tunnel and cannot
open those ports directly. Chrome must run inside the X session as the desktop
user, not as the root action server, which is why launches go through the
`obx-x` wrapper and `sudo -u`.
"""
import asyncio
import base64
import json
import shlex
import time

from core.log import create_logger
from sandbox.desktop import ensure_x_helper, x

log = create_logger("sandbox.browser")

#: Debug port for the desktop-local Chrome. Distinct from Chrome's usual 9222
#: so it never collides with the relay, which owns 9222.
CHROME_PORT = 9333
RELAY_PORT = 9222

CHROME_LOG = "/tmp/obx-chrome.log"
RELAY_LOG = "/tmp/obx-relay.log"
RELAY_PID = "/tmp/obx-relay.pid"

#: Dedicated profile, relative to the desktop user's home. See the launch script
#: for why a non-default profile is mandatory.
CHROME_PROFILE = ".config/obx-chrome"

#: Where wuying_bootstrap.py deploys the relay.
SKILL_DIR = "/opt/openbox/skills/dev-browser"

#: The desktop's browser, in preference order.
#:
#: Ordinary Google Chrome, deliberately. An earlier iteration installed Chrome
#: for Testing here because it is the last build honouring --load-extension —
#: but on this desktop the extension was never needed. In `local` mode the
#: relay is only a page directory: it hands back Chrome's own
#: webSocketDebuggerUrl and Playwright speaks CDP to Chrome directly, so the
#: relay is not on the data path and no extension is involved. Carrying a
#: second 290MB Chrome to enable a flag nothing used was pure weight.
#:
#: The extension still matters in `extension` mode — but that is the user's
#: OWN browser on their OWN machine, which this desktop never launches.
CHROME_CANDIDATES = (
    "/usr/bin/google-chrome-stable",
    "/usr/bin/google-chrome",
    "/opt/google/chrome/google-chrome",
)

_VALID_MODES = ("local", "extension", "auto")

#: How long a fresh Chrome / relay is given to answer before we give up.
CHROME_READY_BUDGET = 15
RELAY_READY_BUDGET = 20

#: Container keys whose Chrome / relay we have successfully brought up this
#: process lifetime. Recorded for symmetry with desktop.py and to let callers
#: `invalidate()` a rebooted desktop — but never used to skip the live HTTP
#: probe below, because a desktop can be rebooted out from under a cache hit.
_chrome_ready: set[str] = set()
_relay_ready: set[str] = set()


class ChromeUnavailable(RuntimeError):
    """The desktop-local Chrome never opened its remote-debugging port."""


class RelayUnavailable(RuntimeError):
    """The dev-browser relay never came up on its port."""


def invalidate(container_key: str) -> None:
    """Forget that a desktop had a working browser (it was recreated under us)."""
    _chrome_ready.discard(container_key)
    _relay_ready.discard(container_key)


def _chrome_url(path: str = "") -> str:
    return f"http://127.0.0.1:{CHROME_PORT}{path}"


def _relay_url(path: str = "/") -> str:
    return f"http://127.0.0.1:{RELAY_PORT}{path}"


def _parse_json(text: str | None) -> dict | None:
    """Best-effort JSON out of curl's stdout (which may be empty or noisy)."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # curl -s can still emit a stray warning line ahead of the body; retry
        # on the last brace-delimited line rather than failing the whole probe.
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
    return None


async def _curl_json(client, url: str, timeout: int = 3) -> dict | None:
    """Fetch and parse a loopback endpoint on the desktop. Never raises."""
    try:
        res = await client.execute(
            f"curl -s --max-time {timeout} {shlex.quote(url)}", timeout=timeout + 7
        )
    except Exception:
        return None
    return _parse_json(res.stdout)


#: How long to wait on a command whose only job is to *start* something.
#:
#: The action server waits for every descendant of the command it runs, and no
#: amount of detaching changes that — measured on the live desktop, a bare
#: `( setsid sleep 25 >/dev/null 2>&1 </dev/null & )` still blocks the exec for
#: the full timeout. Chrome and the relay are long-lived by definition, so both
#: launches sat there until their timeout expired: 30s and 60s of dead waiting
#: on every cold start, while the ports were actually answering within a second
#: of the command returning.
#:
#: Cutting the wait short is safe: the timeout does not kill what was started.
#: Verified by launching a 20s marker with a 3s timeout — the exec returned at
#: 5s and the marker still ran to completion.
LAUNCH_SETTLE = 3


async def _fire_and_forget(client, command: str) -> None:
    """Start something long-lived without waiting for it to finish.

    Readiness is never inferred from this call: the caller polls the port it
    expects, which is the only signal that means anything. A timeout here is
    the expected outcome, not an error.

    Only the timeout is tolerated. Swallowing every exception would turn a real
    failure — a dropped tunnel, a missing binary, a permission error — into a
    full readiness poll followed by a vague "it never came up", hiding the one
    piece of information that would have explained it.
    """
    try:
        await client.execute(command, timeout=LAUNCH_SETTLE)
    except (asyncio.TimeoutError, TimeoutError):
        log.debug("launch command hit its settle timeout, as expected; polling for readiness")


async def _log_tail(client, path: str, lines: int = 40) -> str:
    try:
        res = await client.execute(f"tail -n {lines} {shlex.quote(path)} 2>/dev/null", timeout=10)
        return (res.stdout or "").strip()
    except Exception:
        return ""


#: Where branded Google Chrome reads enterprise policy on Linux. Confirmed
#: loaded from here — chrome://policy lists these entries as
#: Platform / Machine / Mandatory / OK.
POLICY_DIRS = (
    "/etc/opt/chrome/policies/managed",
)

#: An automation browser must never stop and ask a human something. The native
#: dialogs are the dangerous ones: they are drawn by the browser, not the page,
#: so no amount of CDP can dismiss them and the run simply hangs. The worst
#: offender is the external-protocol prompt ("Open xdg-open?") that Chinese
#: sites trigger constantly trying to hand off to their native app.
AUTOMATION_POLICY = {
    # Default-deny, then allow back what automation actually navigates to.
    #
    # This replaced a list of 29 app schemes (`douyin:*`, `snssdk1128:*`, …).
    # Enumeration cannot win: the scheme behind the report that prompted this
    # was `bitbrowser://cc/`, a fingerprint-browser probe on
    # creator.douyin.com, which nobody would have thought to list.
    #
    # **This does NOT suppress the "Open xdg-open?" hand-off dialog**, and it
    # is important not to believe otherwise. `URLBlocklist` is enforced by
    # PolicyBlocklistNavigationThrottle at the navigation layer, while the
    # dialog is drawn by ExternalProtocolHandler, whose GetBlockState() never
    # consults it — a renderer-initiated launch reaches the handler without
    # passing the throttle. The only policy that acts on that path is
    # AutoLaunchProtocolsFromOrigins — and it suppresses the prompt by actually
    # *launching* the handler, which on a desktop the user shares with the agent
    # means starting real programs. Not enabled here for that reason.
    #
    # What this setting does buy is real: it cancels throttled navigations to
    # anything that is not an automation scheme. Verified on the live desktop —
    # example.com and creator.douyin.com both load and interact normally
    # (132 a11y refs after a login click).
    "URLBlocklist": ["*"],
    "URLAllowlist": [
        "http://*", "https://*", "ws://*", "wss://*",
        # chrome:// and devtools:// keep chrome://policy and DevTools usable;
        # about:// covers the about:blank we launch with.
        "chrome://*", "chrome-extension://*", "devtools://*", "about://*",
        "blob://*", "data://*", "file://*",
    ],
    "ExternalProtocolDialogShowAlwaysOpenCheckbox": False,
    # 5 == open the New Tab page. Policy rather than a profile preference,
    # because the two failure modes here trade off against each other and only
    # a policy pins both: an unclean exit makes Chrome offer "Restore pages?"
    # (a browser-drawn bubble no CDP call can dismiss), while marking the exit
    # clean makes it silently reopen every tab of the last run instead —
    # measured, a killed session came back with ten stale tabs. This setting
    # closes the second door, and it cannot be undone from inside the profile.
    "RestoreOnStartup": 5,
    # 2 == block, for every prompt that would otherwise stop the run dead.
    "DefaultNotificationsSetting": 2,
    "DefaultGeolocationSetting": 2,
    "DefaultPopupsSetting": 2,
    "DefaultMediaStreamSetting": 2,
    "DefaultSensorsSetting": 2,
    "DefaultFileSystemWriteGuardSetting": 2,
    "PromptForDownloadLocation": False,
    # Nothing here should try to be a browser for a person.
    "PasswordManagerEnabled": False,
    "AutofillAddressEnabled": False,
    "AutofillCreditCardEnabled": False,
    "BrowserSignin": 0,
    "SyncDisabled": True,
    "DefaultBrowserSettingEnabled": False,
    "MetricsReportingEnabled": False,
    "BackgroundModeEnabled": False,
}


def _policy_install_script() -> str:
    """Shell that drops the automation policy into every path Chrome reads."""
    payload = json.dumps(AUTOMATION_POLICY, indent=2)
    b64 = base64.b64encode(payload.encode()).decode()
    dirs = " ".join(shlex.quote(d) for d in POLICY_DIRS)
    return f"""set -e
printf %s {b64} | base64 -d > /tmp/.obx-chrome-policy.json
for d in {dirs}; do
  mkdir -p "$d" 2>/dev/null || continue
  cp /tmp/.obx-chrome-policy.json "$d/openbox-automation.json" 2>/dev/null || true
  chmod 644 "$d/openbox-automation.json" 2>/dev/null || true
done
rm -f /tmp/.obx-chrome-policy.json
"""


def _chrome_launch_script() -> str:
    """Shell that launches a headed, debuggable Chrome as the desktop user.

    Detached with setsid + a log file so it outlives the exec call, and run
    through `sudo -u` because the action server is root while Chrome must live
    in the desktop user's X session (DISPLAY/XAUTHORITY are exported into this
    script by the obx-x wrapper).
    """
    # Chrome 136+ refuses --remote-debugging-port when it is pointed at the
    # DEFAULT user-data-dir, a hardening measure against other local processes
    # hijacking the debug endpoint. A dedicated obx-chrome profile sidesteps it,
    # which is what lets ordinary Google Chrome serve as the automation browser
    # — verified on this desktop: Chrome 151 opens the port on this profile.
    return f"""set -e
U=$(ps -o user= -p "$(pgrep -x gnome-shell | head -n1)" 2>/dev/null | tr -d ' ')
if [ -z "$U" ] || [ "$U" = root ]; then U=$(stat -c %U /tmp/.X11-unix/X* 2>/dev/null | grep -v '^root$' | head -n1); fi
if [ -z "$U" ]; then U=$(getent passwd 1000 | cut -d: -f1); fi
H=$(getent passwd "$U" | cut -d: -f6)
BIN=""
for c in {" ".join(CHROME_CANDIDATES)}; do [ -x "$c" ] && {{ BIN="$c"; break; }}; done
[ -n "$BIN" ] || BIN=$(command -v google-chrome || command -v chromium || true)
[ -n "$BIN" ] || {{ echo "no chrome binary found" >&2; exit 3; }}
# An automation browser must start from nothing every time, and two separate
# mechanisms fight that.
#
# 1. We stop Chrome with a signal, so it records an unclean exit and offers
#    "Restore pages?" on the next start — a bubble the BROWSER draws, so no CDP
#    call can dismiss it, over the top-right of whatever page is loaded.
#    --disable-session-crashed-bubble no longer suppresses it; marking the exit
#    clean in the profile does.
# 2. Marking it clean then lets Chrome silently reopen the previous session
#    instead — measured here: a killed run came back with ten stale tabs, which
#    cost memory and pollute the relay's page list. RestoreOnStartup=5 in the
#    managed policy did NOT stop it.
#
# Deleting the session files closes both: there is no crash to report and
# nothing to restore. They are pure scratch state; the profile's cookies,
# logins and history live in other files and survive.
PROF="$H/{CHROME_PROFILE}"
PREF="$PROF/Default/Preferences"
if [ -f "$PREF" ]; then
  sudo -u "$U" sed -i 's/"exit_type":"[^"]*"/"exit_type":"Normal"/g; s/"exited_cleanly":false/"exited_cleanly":true/g' "$PREF" 2>/dev/null || true
fi
sudo -u "$U" rm -rf "$PROF/Default/Sessions" 2>/dev/null || true
sudo -u "$U" rm -f "$PROF/Default/Current Session" "$PROF/Default/Current Tabs" \
                   "$PROF/Default/Last Session" "$PROF/Default/Last Tabs" 2>/dev/null || true
( setsid sudo -u "$U" -H env -u CHROME_HEADLESS -u PLAYWRIGHT_HEADLESS -u PUPPETEER_HEADLESS \\
  DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" \\
  "$BIN" \\
  --remote-debugging-port={CHROME_PORT} \\
  --remote-debugging-address=127.0.0.1 \\
  --user-data-dir="$H/{CHROME_PROFILE}" \\
  --no-first-run \\
  --no-default-browser-check \\
  --disable-session-crashed-bubble \\
  --restore-last-session=false \\
  --disable-features=TranslateUI,MediaRouter \\
  --disable-notifications \\
  --deny-permission-prompts \\
  --disable-infobars \\
  --no-service-autorun \\
  --password-store=basic \\
  --use-mock-keychain \\
  --start-maximized \\
  about:blank \\
  >{CHROME_LOG} 2>&1 </dev/null & ) >/dev/null 2>&1 </dev/null
exit 0
"""


def _relay_start_script(mode: str) -> str:
    """Shell that (re)starts the dev-browser relay detached, in `mode`.

    The double fork matters. The action server reads the command's stdout to
    completion, so a background child that merely redirects its own output
    still holds the pipe open through the process group and the exec never
    returns — the relay would come up and the caller would hang until its
    timeout. Detaching with `setsid` in a subshell, and closing every
    descriptor, hands the pipe back immediately.
    """
    # Stopping the old relay by PID file, not `pkill -f start-relay`: that
    # pattern also matches the very shell running it (the command line contains
    # the string), so the restart killed itself and the port never opened.
    return f"""set -e
if [ -f {RELAY_PID} ]; then
  kill -TERM "-$(cat {RELAY_PID})" 2>/dev/null || kill -TERM "$(cat {RELAY_PID})" 2>/dev/null || true
  rm -f {RELAY_PID}
  sleep 1
fi
fuser -k -TERM {RELAY_PORT}/tcp >/dev/null 2>&1 || true
sleep 0.5
cd {SKILL_DIR}
( DEV_BROWSER_MODE={shlex.quote(mode)} DEV_BROWSER_CHROME_PORT={CHROME_PORT} PATH=/usr/local/bin:$PATH \\
  setsid npm run start-relay >{RELAY_LOG} 2>&1 </dev/null &
  echo $! > {RELAY_PID} ) >/dev/null 2>&1 </dev/null
exit 0
"""


async def ensure_chrome(client, container_key: str) -> dict:
    """Launch (or reuse) a headed, debuggable Chrome on the desktop.

    Idempotent: if the debug port already answers we return its /json/version
    verbatim without touching anything. The cache is deliberately *not* trusted
    to short-circuit the probe — a rebooted desktop would hand back a dead port.
    Returns the parsed /json/version JSON (webSocketDebuggerUrl, Browser, ...).
    """
    existing = await _curl_json(client, _chrome_url("/json/version"))
    if existing:
        _chrome_ready.add(container_key)
        return existing

    # obx-x is what discovers the desktop's X session for the sudo launch below.
    await ensure_x_helper(client, container_key)
    # Policy must be on disk before Chrome starts: it is read once at launch.
    await client.execute(_policy_install_script(), timeout=30)
    log.info("launching headed Chrome with remote debugging on :%d", CHROME_PORT)
    await _fire_and_forget(client, x("sh -c " + shlex.quote(_chrome_launch_script())))

    deadline = time.monotonic() + CHROME_READY_BUDGET
    while time.monotonic() < deadline:
        await asyncio.sleep(1.0)
        data = await _curl_json(client, _chrome_url("/json/version"))
        if data:
            _chrome_ready.add(container_key)
            return data

    raise ChromeUnavailable(
        f"Chrome did not open its debug port on :{CHROME_PORT} within "
        f"{CHROME_READY_BUDGET}s.\nchrome log:\n{await _log_tail(client, CHROME_LOG)}"
    )


async def ensure_relay(client, container_key: str, mode: str) -> dict:
    """Ensure the dev-browser relay is running on the desktop in `mode`.

    Reuses a running relay only when its reported `configuredMode` already
    matches — a relay wired to the wrong browser is worse than useless, so a
    mismatch forces a clean restart. Returns the relay's parsed GET / JSON.
    """
    if mode not in _VALID_MODES:
        raise ValueError(f"mode must be one of {_VALID_MODES}, got {mode!r}")

    existing = await _curl_json(client, _relay_url())
    if existing and existing.get("configuredMode") == mode:
        _relay_ready.add(container_key)
        return existing

    log.info("(re)starting dev-browser relay in %s mode", mode)
    await _fire_and_forget(client, _relay_start_script(mode))

    deadline = time.monotonic() + RELAY_READY_BUDGET
    while time.monotonic() < deadline:
        await asyncio.sleep(1.0)
        data = await _curl_json(client, _relay_url())
        if data:
            _relay_ready.add(container_key)
            return data

    raise RelayUnavailable(
        f"dev-browser relay did not answer on :{RELAY_PORT} within "
        f"{RELAY_READY_BUDGET}s.\nrelay log:\n{await _log_tail(client, RELAY_LOG)}"
    )


async def browser_status(client) -> dict:
    """Cheap read-only probe of both endpoints for the API. Never raises."""
    return {
        "chrome": await _curl_json(client, _chrome_url("/json/version")),
        "relay": await _curl_json(client, _relay_url()),
    }


async def ensure_local_browser(client, container_key: str) -> dict:
    """Bring up the desktop-local Chrome and a relay wired to it."""
    chrome = await ensure_chrome(client, container_key)
    relay = await ensure_relay(client, container_key, "local")
    return {"chrome": chrome, "relay": relay}


def _effective_mode(relay: dict | None, fallback: str) -> str:
    """The mode the relay says it is actually running (`local`|`extension`).

    `launch` is the relay's legacy name for driving a local Chrome; normalise it
    so callers only ever see the two-value vocabulary.
    """
    reported = (relay or {}).get("mode")
    if reported == "launch":
        return "local"
    if reported in ("local", "extension"):
        return reported
    return fallback


async def ensure_browser(client, container_key: str, mode: str) -> dict:
    """Bring up whichever browser `mode` asks for, falling back when it cannot.

    mode is the RELAY vocabulary: "auto" | "local" | "extension".
    Returns at least: {"mode": <effective mode actually running>, "relay": {...}, "chrome": {...}|None}
    where "mode" is one of "local" | "extension".

    `extension`/`auto` prefer the user's own browser but degrade to the cloud
    desktop's Chrome whenever the extension is not attached — a missing user
    browser is the normal case, not an error, so only a failure of BOTH paths
    raises.
    """
    if mode not in _VALID_MODES:
        raise ValueError(f"mode must be one of {_VALID_MODES}, got {mode!r}")

    if mode == "local":
        chrome = await ensure_chrome(client, container_key)
        relay = await ensure_relay(client, container_key, "local")
        return {"mode": _effective_mode(relay, "local"), "relay": relay, "chrome": chrome}

    # extension / auto: try the user's own browser first, tolerating a relay
    # that cannot even start (fall through to local rather than surfacing it).
    try:
        relay = await ensure_relay(client, container_key, mode)
    except RelayUnavailable:
        relay = None

    if relay and relay.get("extensionConnected"):
        return {"mode": _effective_mode(relay, "extension"), "relay": relay, "chrome": None}

    # No user browser attached — fall back to the desktop's own Chrome so the
    # agent still has something to drive. Any failure here is a real one.
    chrome = await ensure_chrome(client, container_key)
    relay = await ensure_relay(client, container_key, "local")
    return {"mode": _effective_mode(relay, "local"), "relay": relay, "chrome": chrome}
