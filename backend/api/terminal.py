import asyncio
import logging

import websockets
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from auth.middleware import is_auth_enabled
from auth.ticket import consume_ticket
from sandbox import provider

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/terminal/{container_id}")
async def terminal_websocket(websocket: WebSocket, container_id: str, ticket: str = Query(default="")):
    user_id = "default"
    if is_auth_enabled():
        if not ticket:
            await websocket.close(code=4001, reason="Ticket required")
            return
        user_data = await consume_ticket(ticket)
        if not user_data:
            await websocket.close(code=4001, reason="Invalid or expired ticket")
            return
        user_id = user_data["user_id"]

    await websocket.accept()

    try:
        info = await provider.get_container(container_id, user_id=user_id)
    except ValueError:
        await websocket.send_json({"type": "error", "data": "Container not found"})
        await websocket.close()
        return
    except PermissionError:
        await websocket.send_json({"type": "error", "data": "Forbidden"})
        await websocket.close(code=4003)
        return

    if not info.port:
        await websocket.send_json({"type": "error", "data": "Container port not available"})
        await websocket.close()
        return

    # Build container WebSocket URL
    container_ws_url = f"ws://{info.host}:{info.port}/terminal?api_key={info.api_key or ''}"

    try:
        async with websockets.connect(
            container_ws_url,
            max_size=2**20,
            ping_interval=20,
            ping_timeout=10,
        ) as container_ws:

            async def frontend_to_container():
                """Relay messages from frontend WebSocket to container WebSocket."""
                try:
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            break
                        if "bytes" in message and message["bytes"]:
                            await container_ws.send(message["bytes"])
                        elif "text" in message and message["text"]:
                            await container_ws.send(message["text"])
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    logger.debug(f"frontend_to_container ended: {e}")

            async def container_to_frontend():
                """Relay messages from container WebSocket to frontend WebSocket."""
                try:
                    async for msg in container_ws:
                        if isinstance(msg, bytes):
                            await websocket.send_bytes(msg)
                        else:
                            await websocket.send_text(msg)
                except Exception as e:
                    logger.debug(f"container_to_frontend ended: {e}")

            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(frontend_to_container()),
                    asyncio.create_task(container_to_frontend()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

    except Exception as e:
        logger.error(f"Failed to connect to container terminal: {e}")
        try:
            await websocket.send_json({"type": "error", "data": f"Failed to connect to container terminal: {e}"})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
