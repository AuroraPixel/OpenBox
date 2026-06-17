"""In-process async pub/sub event bus with optional Redis cross-worker broadcasting."""
import asyncio
import json
from typing import Any, Callable
from uuid import uuid4

from core.log import create_logger

log = create_logger("bus")

# Type for event handlers
EventHandler = Callable[[dict[str, Any]], Any]

# Unique identifier for this worker process
worker_id: str = uuid4().hex[:8]

# Global state
_subscribers: dict[str, list[EventHandler]] = {}
_all_subscribers: list[EventHandler] = []

# Redis state (optional)
_redis_client = None  # redis.asyncio.Redis instance
_redis_listener_task: asyncio.Task | None = None

REDIS_BUS_CHANNEL = "bus:events"


def _dispatch_local(event: dict[str, Any]) -> None:
    """Dispatch an event to local (in-process) subscribers only."""
    event_type = event.get("type", "")

    # Notify type-specific subscribers
    for handler in _subscribers.get(event_type, []):
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(result)
                except RuntimeError:
                    pass
        except Exception as e:
            log.error(f"Event handler error for {event_type}: {e}")

    # Notify all-event subscribers
    for handler in _all_subscribers:
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(result)
                except RuntimeError:
                    log.warning(f"No running loop for async handler, event={event_type}")
        except Exception as e:
            log.error(f"Global event handler error: {e}")


def publish(event_type: str, data: dict[str, Any] | None = None) -> None:
    """Publish an event to all subscribers (local + remote workers if Redis is available)."""
    event = {"type": event_type, "data": data or {}}

    # Always dispatch locally
    n_type = len(_subscribers.get(event_type, []))
    n_all = len(_all_subscribers)
    if n_all == 0 and event_type not in ("server.heartbeat",):
        log.warning(f"publish({event_type}): 0 subscribers! (type={n_type}, all={n_all})")
    _dispatch_local(event)

    # Also broadcast via Redis if available
    if _redis_client is not None:
        envelope = json.dumps({
            "worker_id": worker_id,
            "event": event,
        })
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(_redis_publish(envelope))
        except RuntimeError:
            # No event loop running; skip Redis broadcast
            log.debug("No event loop for Redis broadcast, skipping")


async def _redis_publish(envelope: str) -> None:
    """Publish envelope to Redis bus channel."""
    try:
        await _redis_client.publish(REDIS_BUS_CHANNEL, envelope)
    except Exception as e:
        log.warning(f"Failed to publish to Redis bus: {e}")


async def _redis_listener() -> None:
    """Background task that listens for events from other workers via Redis Pub/Sub."""
    pubsub = _redis_client.pubsub()
    await pubsub.subscribe(REDIS_BUS_CHANNEL)
    log.info(f"Redis bus listener started (worker_id={worker_id})")
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if message is not None and message["type"] == "message":
                try:
                    envelope = json.loads(message["data"])
                    sender_id = envelope.get("worker_id")
                    event = envelope.get("event")
                    # Only dispatch events from OTHER workers
                    if sender_id != worker_id and event:
                        _dispatch_local(event)
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    log.warning(f"Invalid Redis bus message: {e}")
            else:
                # No message received; yield control briefly
                await asyncio.sleep(0.01)
    except asyncio.CancelledError:
        log.info("Redis bus listener shutting down")
    except Exception as e:
        log.error(f"Redis bus listener error: {e}")
    finally:
        try:
            await pubsub.unsubscribe(REDIS_BUS_CHANNEL)
            await pubsub.aclose()
        except Exception:
            pass


async def init_redis_bus(redis_url: str) -> None:
    """Initialize Redis-based cross-worker event bus.

    Call this during application startup to enable multi-worker event broadcasting.
    If Redis is unavailable, the bus continues to work in local-only mode.
    """
    global _redis_client, _redis_listener_task
    try:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(redis_url, decode_responses=True)
        # Verify connection
        await _redis_client.ping()
        # Start background listener
        _redis_listener_task = asyncio.create_task(_redis_listener())
        log.info(f"Redis bus initialized (worker_id={worker_id})")
    except Exception as e:
        log.warning(f"Failed to init Redis bus, falling back to local-only: {e}")
        _redis_client = None
        _redis_listener_task = None


async def close_redis_bus() -> None:
    """Shut down the Redis bus listener and close the connection."""
    global _redis_client, _redis_listener_task
    if _redis_listener_task is not None:
        _redis_listener_task.cancel()
        try:
            await _redis_listener_task
        except asyncio.CancelledError:
            pass
        _redis_listener_task = None
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception:
            pass
        _redis_client = None
    log.info("Redis bus closed")


def subscribe(event_type: str, handler: EventHandler) -> Callable[[], None]:
    """Subscribe to a specific event type. Returns unsubscribe function."""
    if event_type not in _subscribers:
        _subscribers[event_type] = []
    _subscribers[event_type].append(handler)

    def unsubscribe():
        try:
            _subscribers[event_type].remove(handler)
        except ValueError:
            pass

    return unsubscribe


def subscribe_all(handler: EventHandler) -> Callable[[], None]:
    """Subscribe to all events. Returns unsubscribe function."""
    _all_subscribers.append(handler)

    def unsubscribe():
        try:
            _all_subscribers.remove(handler)
        except ValueError:
            pass

    return unsubscribe


def publish_toast(user_id: str, level: str, message: str) -> None:
    """Publish a toast notification to a user's frontend."""
    from bus.events import TOAST
    publish(TOAST, {"userId": user_id, "level": level, "message": message})


def clear() -> None:
    """Clear all subscribers (for testing)."""
    _subscribers.clear()
    _all_subscribers.clear()
