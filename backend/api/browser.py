"""Browser view: which browser the agent drives, and its live availability.

The agent can reach the web two ways. **local** is Chrome on the cloud desktop
(the sandbox), always there but carrying none of the user's logins. **remote**
is the user's own Chrome, driven through a browser extension that connects back
here — it has the real sessions, but only while the extension is connected.
**auto** (the default) prefers remote and falls back to local the moment the
extension drops.

The chosen mode is a per-user preference. Reads and writes go through
``session.browser_pref`` (it lives in the ``extra`` bag of the existing
preferences row); ``status`` reports the *effective* mode against what is
actually reachable right now, so the UI can show the live picture.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.dev_browser import _active_ws
from auth.middleware import get_current_user
from core.log import create_logger
from session.browser_pref import get_browser_mode, set_browser_mode

log = create_logger("api.browser")

router = APIRouter(prefix="/api/browser", tags=["browser"], dependencies=[Depends(get_current_user)])

_MODES = ("auto", "local", "remote")


class PreferenceUpdate(BaseModel):
    mode: str


def _existing_client(user_id: str):
    """A client for this user's sandbox, without creating one.

    Deliberately not `get_client_any`, which acquires a sandbox when none is
    running: the settings page polls this endpoint, and merely looking at a
    status must never spin a machine up.

    A cached client is used when the manager already has one. Otherwise the
    provider is asked whether a container is simply *there* — with a long-lived
    desktop that is the normal case, and refusing to look at it just because no
    session has touched it in this process would report the browser as missing
    when it is running fine.
    """
    from sandbox.client import SandboxClient
    from sandbox.manager import sandbox_manager

    for key, client in sandbox_manager._clients.items():
        sandbox = sandbox_manager._project_map.get(key)
        if sandbox and sandbox.user_id == user_id:
            return client

    try:
        from sandbox import provider
        container = provider.get_user_container(user_id)
        if not container or not container.port:
            return None
        return SandboxClient(
            host=container.host or "127.0.0.1",
            port=container.port,
            api_key=container.api_key or "",
        )
    except Exception as e:
        log.debug(f"No existing sandbox to inspect: {e}")
        return None


async def _local_status(user_id: str) -> dict:
    """Availability of the cloud desktop's Chrome for this user.

    The probe reports the two endpoints; this flattens them into the
    `available` flag the UI renders, plus enough detail to say WHY when the
    answer is no. `available` means Chrome is answering — a missing relay is
    not fatal, since it is started on demand when the skill loads.
    """
    from sandbox.browser import browser_status

    client = _existing_client(user_id)
    if client is None:
        return {"available": False, "reason": "no_sandbox"}

    try:
        state = await browser_status(client)
    except Exception as e:
        log.warning(f"browser_status failed: {e}")
        return {"available": False, "reason": "error"}

    chrome = state.get("chrome") or {}
    relay = state.get("relay") or {}
    if not chrome:
        return {"available": False, "reason": "not_started"}
    return {
        "available": True,
        "version": chrome.get("Browser"),
        "relayRunning": bool(relay),
        "relayMode": relay.get("mode"),
    }


async def _build_status(user_id: str) -> dict:
    """The effective mode plus the live state of each side."""
    preference = await get_browser_mode(user_id)
    remote_connected = bool(_active_ws.get(user_id))
    local = await _local_status(user_id)

    # local is pinned; auto and remote ride the extension and fall back to local.
    effective = "remote" if (preference != "local" and remote_connected) else "local"

    return {
        "mode": effective,
        "preference": preference,
        "local": local,
        "remote": {"connected": remote_connected},
    }


@router.get("/status")
async def get_status(current_user: dict = Depends(get_current_user)):
    """What browser the agent would drive right now, and why."""
    return await _build_status(current_user["user_id"])


@router.put("/preference")
async def set_preference(body: PreferenceUpdate, current_user: dict = Depends(get_current_user)):
    """Persist the browser mode and return the refreshed status."""
    user_id = current_user["user_id"]
    try:
        await set_browser_mode(user_id, (body.mode or "").strip())
    except ValueError:
        return JSONResponse({"error": "invalid_mode", "allowed": list(_MODES)}, status_code=400)
    return await _build_status(user_id)
