"""FastAPI authentication dependencies."""
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.jwt import decode_access_token
from core.log import create_logger

log = create_logger("auth.middleware")

_bearer = HTTPBearer(auto_error=False)

# JWT blacklist check (set by init)
_cache = None
_auth_enabled = False  # Set to True when JWT_SECRET is configured


def init_blacklist(cache):
    global _cache, _auth_enabled
    _cache = cache
    _auth_enabled = True


def is_auth_enabled() -> bool:
    """Check if auth is enabled. Use this instead of importing _auth_enabled directly."""
    return _auth_enabled


# Default user for single-user mode (no auth)
_SINGLE_USER = {"user_id": "default", "role": "admin"}


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Extract and verify the current user from JWT access token.

    In single-user mode (no JWT_SECRET): returns default user without auth.
    In multi-user mode: requires valid JWT.

    Returns: {"user_id": str, "role": str}
    """
    if not is_auth_enabled():
        return _SINGLE_USER

    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Check blacklist
    if _cache:
        jti = payload.get("jti")
        if jti and await _cache.exists(f"jwt_bl:{jti}"):
            raise HTTPException(status_code=401, detail="Token has been revoked")

    return {"user_id": user_id, "role": payload.get("role", "user")}


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Require admin role."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
