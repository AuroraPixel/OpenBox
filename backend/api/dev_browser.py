import asyncio
import logging

import websockets
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query, HTTPException

from auth.ticket import consume_ticket
from auth.middleware import is_auth_enabled, get_current_user
from models.container import ContainerStatus
from sandbox import provider

logger = logging.getLogger(__name__)

# HTTP routes require user auth
_http_router = APIRouter(
    prefix="/api/containers",
    tags=["dev-browser"],
    dependencies=[Depends(get_current_user)],
)

_ws_router = APIRouter()

router = APIRouter()

# Active WS connections: user_id -> {client_id, ws}
_active_ws: dict[str, dict] = {}


# ── HTTP API: container-specific endpoints (authenticated) ──

@_http_router.post("/{container_id}/dev-browser/start")
async def start_dev_browser(container_id: str, current_user: dict = Depends(get_current_user)):
    try:
        resp = await provider.forward_to_container(
            container_id, "POST", "/dev-browser/start", user_id=current_user["user_id"]
        )
        return resp.json()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_http_router.post("/{container_id}/dev-browser/stop")
async def stop_dev_browser(container_id: str, current_user: dict = Depends(get_current_user)):
    try:
        resp = await provider.forward_to_container(
            container_id, "POST", "/dev-browser/stop", user_id=current_user["user_id"]
        )
        return resp.json()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_http_router.get("/{container_id}/dev-browser/status")
async def get_dev_browser_status_authed(container_id: str, current_user: dict = Depends(get_current_user)):
    try:
        resp = await provider.forward_to_container(
            container_id, "GET", "/dev-browser/status", user_id=current_user["user_id"]
        )
        return resp.json()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Extension connection info (authenticated) ──

@_http_router.get("/dev-browser/link-info")
async def get_extension_status(current_user: dict = Depends(get_current_user)):
    """Get current user's extension connection status."""
    user_id = current_user["user_id"]

    active = _active_ws.get(user_id)
    if active:
        return {
            "has_link": True,
            "connected": True,
            "client_id": active["client_id"][:8],
        }

    return {"has_link": False, "connected": False}


# ── WebSocket: auto endpoint (ticket auth, auto-resolve container) ──

@_ws_router.websocket("/ws/dev-browser/auto")
async def dev_browser_ws_auto(
    websocket: WebSocket,
    ticket: str = Query(default=""),
    client_id: str = Query(default=""),
):
    """WebSocket relay with ticket auth. Auto-resolves user's running container.

    Close codes: 4001=replaced, 4003=auth failed, 4004=no container.
    """
    user_id = "default"

    if is_auth_enabled():
        if not ticket:
            await websocket.accept()
            await websocket.close(code=4003, reason="Ticket required")
            return

        user_data = await consume_ticket(ticket)
        if not user_data:
            await websocket.accept()
            await websocket.close(code=4003, reason="Invalid or expired ticket")
            return
        user_id = user_data["user_id"]

    container = provider.get_user_container(user_id)
    if not container or container.status != ContainerStatus.RUNNING or not container.port:
        await websocket.accept()
        await websocket.close(code=4004, reason="No running container")
        return

    await websocket.accept()

    # Kick any existing connection for this user
    if client_id:
        active = _active_ws.get(user_id)
        if active and active["client_id"] != client_id:
            logger.info(f"Kicking client {active['client_id'][:8]}... replaced by {client_id[:8]}...")
            try:
                await active["ws"].close(code=4001, reason="Replaced by new client")
            except Exception:
                pass
        _active_ws[user_id] = {"client_id": client_id, "ws": websocket}

    container_id = container.id
    container_ws_url = (
        f"ws://{container.host}:{container.port}/dev-browser/ws"
        f"?api_key={container.api_key or provider._api_keys.get(container_id, '')}"
    )

    try:
        async with websockets.connect(
            container_ws_url, max_size=2**20, ping_interval=20, ping_timeout=10,
        ) as container_ws:

            async def ext_to_ctr():
                try:
                    while True:
                        msg = await websocket.receive()
                        if msg["type"] == "websocket.disconnect":
                            break
                        if "text" in msg and msg["text"]:
                            await container_ws.send(msg["text"])
                        elif "bytes" in msg and msg["bytes"]:
                            await container_ws.send(msg["bytes"])
                except (WebSocketDisconnect, Exception):
                    pass

            async def ctr_to_ext():
                try:
                    async for m in container_ws:
                        if isinstance(m, bytes):
                            await websocket.send_bytes(m)
                        else:
                            await websocket.send_text(m)
                except Exception:
                    pass

            done, pending = await asyncio.wait(
                [asyncio.create_task(ext_to_ctr()), asyncio.create_task(ctr_to_ext())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
    except Exception as e:
        logger.error(f"Failed to connect to container relay: {e}")
        try:
            await websocket.send_json({"type": "error", "data": str(e)})
        except Exception:
            pass
    finally:
        if client_id:
            active = _active_ws.get(user_id)
            if active and active["client_id"] == client_id:
                _active_ws.pop(user_id, None)
        try:
            await websocket.close()
        except Exception:
            pass


# Combine all routers
router.include_router(_http_router)
router.include_router(_ws_router)
