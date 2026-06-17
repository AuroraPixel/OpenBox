"""Preview token — short-lived signed URL token for container preview proxy.

Usage:
  1. Frontend: POST /api/containers/{id}/preview-token?port=3000 → {"token": "abc123", "url": "/api/containers/.../preview/3000/?_pt=abc123"}
  2. Browser loads the URL with ?_pt=abc123, preview proxy validates the token.
"""
import secrets
import json

from core.log import create_logger

log = create_logger("auth.preview")

_cache = None
PREVIEW_TOKEN_TTL = 3600  # 1 hour


def init_preview_store(cache):
    global _cache
    _cache = cache


async def create_preview_token(user_id: str, container_id: str, port: int) -> str:
    """Create a preview token bound to a specific container + port."""
    if _cache is None:
        raise RuntimeError("Preview token store not initialized")
    token = secrets.token_urlsafe(24)
    await _cache.set(
        f"pt:{token}",
        json.dumps({"user_id": user_id, "container_id": container_id, "port": port}),
        ttl=PREVIEW_TOKEN_TTL,
    )
    return token


async def verify_preview_token(token: str, container_id: str, port: int) -> dict | None:
    """Verify a preview token. Returns {user_id, container_id, port} or None."""
    if _cache is None or not token:
        return None
    key = f"pt:{token}"
    data = await _cache.get(key)
    if data is None:
        return None
    if isinstance(data, str):
        data = json.loads(data)
    # Verify token is bound to this container + port
    if data.get("container_id") != container_id or data.get("port") != port:
        return None
    return data
