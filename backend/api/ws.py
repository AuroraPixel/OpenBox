"""Main WebSocket endpoint — replaces SSE for real-time bidirectional communication.

Server → Client: session events, message deltas, tool status, permission/question requests
Client → Server: permission replies, question replies, abort, build trigger
"""
import asyncio
import json
from asyncio import QueueEmpty

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from auth.ticket import consume_ticket
from auth.middleware import is_auth_enabled
from bus import bus
from core.log import create_logger

log = create_logger("api.ws")

router = APIRouter()

# Events a client cannot recover from by watching the next one. todo.updated
# is here because the task card is the frame the rest of the turn renders
# inside: drop one and the card shows the wrong step until something else
# forces a refetch.
CRITICAL_EVENT_TYPES = {
    "session.status", "session.finalizing", "session.error", "message.created",
    "todo.updated",
}
BROADCAST_WHITELIST = {"build.progress", "build.complete", "build.error", "server.announcement"}


# ---------------------------------------------------------------------------
# WebSocket Connection Manager
# ---------------------------------------------------------------------------

class WSConnectionManager:
    """Manages per-user WebSocket connections with send queues."""

    def __init__(self):
        # user_id -> {websocket: asyncio.Queue}
        self._connections: dict[str, dict[WebSocket, asyncio.Queue]] = {}
        self._cleanup_timers: dict[str, asyncio.Task] = {}  # user_id -> cleanup task

    def register(self, user_id: str, ws: WebSocket) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        if user_id not in self._connections:
            self._connections[user_id] = {}
        self._connections[user_id][ws] = queue
        log.info(f"WS registered: user={user_id} (total connections: {self._total()})")
        return queue

    def unregister(self, user_id: str, ws: WebSocket):
        conns = self._connections.get(user_id, {})
        conns.pop(ws, None)
        if not conns:
            self._connections.pop(user_id, None)
        log.info(f"WS unregistered: user={user_id} (total connections: {self._total()})")

    def has_connections(self, user_id: str) -> bool:
        """Return True if the user still has at least one WebSocket connection."""
        return bool(self._connections.get(user_id))

    def schedule_cleanup(self, user_id: str):
        """Schedule container cleanup 30 min after last WS disconnect.

        Skips cleanup if user has high-frequency cron jobs (keepalive).
        """
        self.cancel_cleanup(user_id)

        async def _cleanup():
            await asyncio.sleep(30 * 60)  # 30 minutes

            # Skip if user has cron keepalive (high-frequency jobs need container)
            try:
                from cron.warmup import is_keepalive_user
                if is_keepalive_user(user_id):
                    return
            except Exception:
                pass

            # Re-check: user may have reconnected while we were sleeping.
            # cancel_cleanup() cancels the task, but there's a tiny window
            # where the sleep finishes before cancel() is called.
            if self.has_connections(user_id):
                log.info(f"User {user_id} reconnected during cleanup wait, skipping cleanup")
                return

            log.info(f"User {user_id} inactive for 30min, cleaning up containers")
            from sandbox import provider
            containers = provider.get_containers_for_user(user_id)
            for info in containers:
                # Double-check before each deletion in case user reconnects mid-cleanup
                if self.has_connections(user_id):
                    log.info(f"User {user_id} reconnected during cleanup, aborting")
                    return
                try:
                    await provider.delete_container(info.id, user_id=user_id)
                    log.info(f"Cleaned up container {info.name} ({info.id}) for inactive user {user_id}")
                except Exception as e:
                    log.warning(f"Failed to cleanup container {info.id} for user {user_id}: {e}")

            # Also clean up sandbox manager state
            from sandbox import sandbox_manager
            for k in list(sandbox_manager._project_map.keys()):
                sb = sandbox_manager._project_map.get(k)
                if sb and sb.user_id == user_id:
                    sandbox_manager._project_map.pop(k, None)
                    sandbox_manager._clients.pop(k, None)

        self._cleanup_timers[user_id] = asyncio.create_task(_cleanup())

    def cancel_cleanup(self, user_id: str):
        """Cancel a pending cleanup timer for a user."""
        task = self._cleanup_timers.pop(user_id, None)
        if task and not task.done():
            task.cancel()

    async def send_to_user(self, user_id: str, event: dict):
        conns = self._connections.get(user_id, {})
        for ws, queue in conns.items():
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                event_type = str(event.get("type", ""))
                if event_type not in CRITICAL_EVENT_TYPES:
                    log.warning(f"WS queue full for user={user_id}, dropping non-critical event {event_type}")
                    continue
                # Preserve critical events by evicting the first non-critical item.
                buffered: list[dict] = []
                evicted = False
                try:
                    while True:
                        old = queue.get_nowait()
                        old_type = str(old.get("type", ""))
                        if not evicted and old_type not in CRITICAL_EVENT_TYPES:
                            evicted = True
                            continue
                        buffered.append(old)
                except QueueEmpty:
                    pass

                # Rebuild queue and enqueue critical event.
                for item in buffered:
                    try:
                        queue.put_nowait(item)
                    except asyncio.QueueFull:
                        break
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Queue contains only critical events; drop oldest to keep latest status.
                    try:
                        _ = queue.get_nowait()
                        queue.put_nowait(event)
                        log.warning(f"WS queue full of critical events for user={user_id}, replaced oldest with {event_type}")
                    except Exception:
                        log.error(f"WS critical event dropped for user={user_id}: {event_type}")

    async def broadcast(self, event: dict):
        for user_id, conns in self._connections.items():
            for ws, queue in conns.items():
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    def _total(self) -> int:
        return sum(len(conns) for conns in self._connections.values())


ws_manager = WSConnectionManager()


# ---------------------------------------------------------------------------
# Bus → WebSocket bridge
# ---------------------------------------------------------------------------

async def _on_bus_event(event: dict):
    """Forward bus events to the appropriate user's WebSocket connections."""
    data = event.get("data", {})
    user_id = data.get("userId")
    if user_id:
        await ws_manager.send_to_user(user_id, event)
    else:
        event_type = event.get("type", "")
        if event_type in BROADCAST_WHITELIST:
            await ws_manager.broadcast(event)
        elif event_type not in ("server.heartbeat",):
            log.warning(f"Dropping event without userId: {event_type}")


# Subscribe to all bus events
bus.subscribe_all(_on_bus_event)


# ---------------------------------------------------------------------------
# Client → Server message handling
# ---------------------------------------------------------------------------

async def _handle_client_message(user_id: str, user_role: str, msg: dict):
    """Process a message received from the client via WebSocket."""
    msg_type = msg.get("type")

    if msg_type == "permission.reply":
        from permission import permission as perm_mod
        await perm_mod.reply(msg.get("id", ""), msg.get("action", "reject"), msg.get("message"), user_id=user_id)

    elif msg_type == "question.reply":
        from question import question as q_mod
        await q_mod.reply(msg.get("id", ""), msg.get("answers", []), user_id=user_id)

    elif msg_type == "question.reject":
        from question import question as q_mod
        await q_mod.reject(msg.get("id", ""), user_id=user_id)

    elif msg_type == "session.abort":
        session_id = msg.get("sessionId", "")
        # Verify ownership: load session, check it exists
        # In single-user mode, always allow
        from session.session import get_session
        session = await get_session(session_id, user_id=user_id)
        if session:
            from session.status import trigger_abort
            trigger_abort(session_id)

    elif msg_type == "build.start":
        if user_role != "admin":
            return
        asyncio.create_task(_stream_build_to_user(user_id))

    else:
        log.warning(f"Unknown WS message type: {msg_type}")


async def _stream_build_to_user(user_id: str):
    """Stream Docker build progress to a user's WebSocket connections."""
    from sandbox import provider
    try:
        async for event in provider.build_sandbox_image():
            step = event.get("step", "building")
            event_type = f"build.{step}" if step != "building" else "build.progress"
            await ws_manager.send_to_user(user_id, {
                "type": event_type,
                "data": {"userId": user_id, **event},
            })
    except Exception as e:
        await ws_manager.send_to_user(user_id, {
            "type": "build.error",
            "data": {"userId": user_id, "message": str(e)},
        })


async def _ensure_user_container(user_id: str) -> None:
    """Ensure each connected user has exactly one sandbox container."""
    try:
        from sandbox import provider
        await provider.ensure_user_container(user_id=user_id, project_id="default")
    except Exception as e:
        log.warning(f"Failed to ensure container for user={user_id}: {e}")


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket, ticket: str = Query(default="")):
    """Main WebSocket endpoint for real-time communication.

    Authentication: ticket query parameter (one-time use, 30s TTL).
    In single-user mode (no JWT_SECRET), accepts without ticket.
    """
    # Authenticate
    user_id = "default"
    user_role = "admin"

    if is_auth_enabled():
        if not ticket:
            await websocket.close(code=4001, reason="Ticket required")
            return
        user_data = await consume_ticket(ticket)
        if not user_data:
            await websocket.close(code=4001, reason="Invalid or expired ticket")
            return
        user_id = user_data["user_id"]
        user_role = user_data.get("role", "user")

    await websocket.accept()

    # Cancel any pending cleanup timer on reconnect
    ws_manager.cancel_cleanup(user_id)

    send_queue = ws_manager.register(user_id, websocket)

    # Send connection confirmation
    await send_queue.put({"type": "server.connected", "data": {}})
    asyncio.create_task(_ensure_user_container(user_id))

    try:
        await asyncio.gather(
            _receive_loop(user_id, user_role, websocket),
            _send_loop(websocket, send_queue),
            _heartbeat_loop(send_queue),
        )
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error(f"WS error for user={user_id}: {e}")
    finally:
        ws_manager.unregister(user_id, websocket)
        # If user has no more connections, schedule cleanup
        if not ws_manager.has_connections(user_id):
            ws_manager.schedule_cleanup(user_id)


async def _receive_loop(user_id: str, user_role: str, ws: WebSocket):
    """Receive and process client messages."""
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                await _handle_client_message(user_id, user_role, msg)
            except json.JSONDecodeError:
                log.warning(f"Invalid JSON from WS user={user_id}")
    except WebSocketDisconnect:
        raise
    except Exception as e:
        log.error(f"WS receive error: {e}")
        raise


async def _send_loop(ws: WebSocket, send_queue: asyncio.Queue):
    """Serial send loop — takes events from queue and sends them one at a time."""
    try:
        while True:
            event = await send_queue.get()
            await ws.send_json(event)
    except Exception:
        raise


async def _heartbeat_loop(send_queue: asyncio.Queue):
    """Send heartbeat every 25 seconds (below typical 30s proxy timeout)."""
    try:
        while True:
            await asyncio.sleep(25)
            await send_queue.put({"type": "server.heartbeat", "data": {}})
    except Exception:
        raise
