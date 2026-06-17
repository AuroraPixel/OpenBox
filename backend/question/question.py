"""Question system: LLM asks user structured questions, waits for answers."""
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from bus import bus
from bus.events import QUESTION_ASKED, QUESTION_REPLIED, QUESTION_REJECTED
from core.identifier import generate_id
from core.log import create_logger

log = create_logger("question")


class QuestionOption(BaseModel):
    label: str
    description: str = ""


class Question(BaseModel):
    question: str
    header: str = ""
    options: list[QuestionOption] = []
    multiple: bool = False  # Allow selecting multiple choices
    custom: bool = True  # Allow typing a custom "Other" answer (default: true)


class QuestionRequest(BaseModel):
    id: str
    user_id: str = "default"
    session_id: str
    questions: list[Question]
    tool: dict | None = None  # { "messageID": str, "callID": str }
    created_at: str = ""


class QuestionReply(BaseModel):
    id: str
    answers: list[list[str]]  # One string[] per question (selected labels)


@dataclass
class PendingQuestion:
    """A question waiting for user response."""
    request: QuestionRequest
    event: asyncio.Event = field(default_factory=asyncio.Event)
    answers: list[list[str]] | None = None  # One string[] per question
    rejected: bool = False


class QuestionRejectedError(Exception):
    """Raised when the user dismisses/rejects a question."""
    pass


# State
_pending: dict[str, PendingQuestion] = {}


def _get_redis_client():
    """Get the Redis client from the bus module, if available."""
    return bus._redis_client


async def _wait_via_redis(request_id: str, pending: PendingQuestion) -> None:
    """Wait for a question reply via Redis Pub/Sub channel."""
    redis_client = _get_redis_client()
    channel_name = f"question_reply:{request_id}"
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel_name)
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if message is not None and message["type"] == "message":
                try:
                    reply_data = json.loads(message["data"])
                    if reply_data.get("rejected"):
                        pending.rejected = True
                    else:
                        pending.answers = reply_data.get("answers")
                    return
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    log.warning(f"Invalid question reply message: {e}")
            else:
                await asyncio.sleep(0.01)
    finally:
        try:
            await pubsub.unsubscribe(channel_name)
            await pubsub.aclose()
        except Exception:
            pass


async def ask(
    session_id: str,
    questions: list[Question],
    tool: dict | None = None,
    user_id: str = "default",
) -> list[list[str]]:
    """Ask the user questions and wait for answers.

    Returns list of answers, one string[] per question (selected labels).
    """
    request_id = generate_id()
    request = QuestionRequest(
        id=request_id,
        user_id=user_id,
        session_id=session_id,
        questions=questions,
        tool=tool,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    pending = PendingQuestion(request=request)
    _pending[request_id] = pending

    redis_client = _get_redis_client()

    if redis_client is not None:
        # Store request data in Redis for cross-worker access
        try:
            await redis_client.setex(
                f"question_req:{request_id}",
                300,  # TTL 300s
                json.dumps(request.model_dump()),
            )
        except Exception as e:
            log.warning(f"Failed to store question request in Redis: {e}")

    # Publish SSE event
    bus.publish(QUESTION_ASKED, {**request.model_dump(), "userId": user_id})

    if redis_client is not None:
        # Wait via Redis Pub/Sub for cross-worker support
        try:
            await _wait_via_redis(request_id, pending)
        except Exception as e:
            log.warning(f"Redis wait failed, falling back to local: {e}")
            await pending.event.wait()
    else:
        # Fallback: local asyncio.Event wait
        await pending.event.wait()

    # Clean up pending
    _pending.pop(request_id, None)

    if pending.rejected:
        raise QuestionRejectedError("User dismissed this question.")

    return pending.answers or []


async def reply(request_id: str, answers: list[list[str]], user_id: str = "default") -> None:
    """Handle user reply to a question."""
    redis_client = _get_redis_client()

    # Try to load request from Redis (cross-worker scenario)
    request_data = None
    if redis_client is not None:
        try:
            raw = await redis_client.get(f"question_req:{request_id}")
            if raw:
                request_data = json.loads(raw)
                await redis_client.delete(f"question_req:{request_id}")
        except Exception as e:
            log.warning(f"Failed to read question request from Redis: {e}")

    # Check local pending dict
    pending = _pending.pop(request_id, None)

    owner_id = pending.request.user_id if pending is not None else (request_data or {}).get("user_id")
    if owner_id and owner_id != user_id:
        if pending is not None:
            _pending[request_id] = pending
        raise PermissionError("Question request does not belong to current user")
    if pending is None and request_data is None:
        raise KeyError("Question request not found")

    if pending is not None:
        # Local worker owns this request
        pending.answers = answers
        pending.event.set()

    # Publish reply via Redis channel for cross-worker delivery
    if redis_client is not None:
        reply_payload = json.dumps({"answers": answers})
        try:
            await redis_client.publish(f"question_reply:{request_id}", reply_payload)
        except Exception as e:
            log.warning(f"Failed to publish question reply to Redis: {e}")

    # Determine session_id for the bus event
    session_id = None
    if pending is not None:
        session_id = pending.request.session_id
    elif request_data is not None:
        session_id = request_data.get("session_id")

    bus.publish(QUESTION_REPLIED, {
        "userId": user_id,
        "id": request_id,
        "session_id": session_id or "",
    })


async def reject(request_id: str, user_id: str = "default") -> None:
    """Handle user rejection/dismissal of a question."""
    redis_client = _get_redis_client()

    # Try to load request from Redis (cross-worker scenario)
    request_data = None
    if redis_client is not None:
        try:
            raw = await redis_client.get(f"question_req:{request_id}")
            if raw:
                request_data = json.loads(raw)
                await redis_client.delete(f"question_req:{request_id}")
        except Exception as e:
            log.warning(f"Failed to read question request from Redis: {e}")

    # Check local pending dict
    pending = _pending.pop(request_id, None)

    owner_id = pending.request.user_id if pending is not None else (request_data or {}).get("user_id")
    if owner_id and owner_id != user_id:
        if pending is not None:
            _pending[request_id] = pending
        raise PermissionError("Question request does not belong to current user")
    if pending is None and request_data is None:
        raise KeyError("Question request not found")

    if pending is not None:
        # Local worker owns this request
        pending.rejected = True
        pending.event.set()

    # Publish rejection via Redis channel for cross-worker delivery
    if redis_client is not None:
        reply_payload = json.dumps({"rejected": True})
        try:
            await redis_client.publish(f"question_reply:{request_id}", reply_payload)
        except Exception as e:
            log.warning(f"Failed to publish question rejection to Redis: {e}")

    # Determine session_id for the bus event
    session_id = None
    if pending is not None:
        session_id = pending.request.session_id
    elif request_data is not None:
        session_id = request_data.get("session_id")

    bus.publish(QUESTION_REJECTED, {
        "userId": user_id,
        "id": request_id,
        "session_id": session_id or "",
    })


def list_pending(user_id: str | None = None) -> list[QuestionRequest]:
    """List all pending questions."""
    requests = [p.request for p in _pending.values()]
    if user_id is None:
        return requests
    return [r for r in requests if r.user_id == user_id]
