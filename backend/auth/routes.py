"""Authentication API routes — register, login, refresh, logout, ticket."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel

from auth.jwt import create_access_token, create_refresh_token, decode_refresh_token, init_auth
from auth.password import hash_password, verify_password, validate_password_strength
from auth.ticket import create_ticket
from auth.middleware import get_current_user
from core.identifier import generate_id
from core.log import create_logger
from db.repository.user_repo import PgUserRepo
from db.repository.preference_repo import PgPreferenceRepo

log = create_logger("auth.routes")

router = APIRouter(prefix="/api/auth", tags=["Auth"])

_user_repo = PgUserRepo()
_pref_repo = PgPreferenceRepo()
_cache = None  # Set by init


def init_auth_routes(cache):
    global _cache
    _cache = cache


# ── Request/Response models ──

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None

class LoginRequest(BaseModel):
    username: str
    password: str

class ExtensionAuthRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class PreferencesUpdate(BaseModel):
    theme: str | None = None
    default_model: str | None = None
    default_agent: str | None = None
    default_variant: str | None = None
    sidebar_open: bool | None = None
    right_panel_open: bool | None = None
    bottom_panel_height: int | None = None
    extra: dict | None = None


# ── Rate limiting helper ──

async def _check_rate_limit(key: str, limit: int, window: int):
    if _cache is None:
        return
    count = await _cache.incr(f"rl:{key}", ttl=window)
    if count > limit:
        raise HTTPException(status_code=429, detail="Too many requests")


# ── Routes ──

@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest, request: Request, response: Response):
    # Validate password
    err = validate_password_strength(body.password)
    if err:
        raise HTTPException(status_code=400, detail=err)

    # Check username taken
    existing = await _user_repo.get_by_username(body.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    # Create user
    user_id = generate_id()
    hashed = hash_password(body.password)
    await _user_repo.create(id=user_id, username=body.username, password_hash=hashed, email=body.email)

    # Create default project
    from db.repository.session_repo import PgSessionRepo  # avoid circular
    from db.models.project import Project
    from db.base import get_db_session
    project_id = generate_id()
    now = datetime.now(timezone.utc)
    async with get_db_session() as session:
        session.add(Project(id=project_id, user_id=user_id, name="Default", slug="default",
                           created_at=now, updated_at=now))

    # Issue tokens
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    response.set_cookie(
        key="refresh_token", value=refresh, httponly=True, secure=False,
        samesite="lax", max_age=7 * 24 * 3600, path="/api/auth",
    )

    user = await _user_repo.get(user_id)
    return TokenResponse(access_token=access, user=_safe_user(user))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    await _check_rate_limit(f"login:{ip}", limit=5, window=60)

    user = await _user_repo.get_by_username(body.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is disabled")

    # Check lockout
    if user.get("locked_until"):
        locked = datetime.fromisoformat(user["locked_until"])
        if locked > datetime.now(timezone.utc):
            raise HTTPException(status_code=423, detail="Account locked. Try again later.")
        else:
            await _user_repo.reset_failed_login(user["id"])

    if not verify_password(body.password, user.get("password_hash", "")):
        count = await _user_repo.increment_failed_login(user["id"])
        if count >= 5:
            lock_until = datetime.now(timezone.utc) + timedelta(minutes=15)
            await _user_repo.lock_until(user["id"], lock_until.isoformat())
            raise HTTPException(status_code=423, detail="Account locked for 15 minutes")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Reset failed count on success
    if user.get("failed_login_count", 0) > 0:
        await _user_repo.reset_failed_login(user["id"])

    access = create_access_token(user["id"], user.get("role", "user"))
    refresh = create_refresh_token(user["id"])
    response.set_cookie(
        key="refresh_token", value=refresh, httponly=True, secure=False,
        samesite="lax", max_age=7 * 24 * 3600, path="/api/auth",
    )

    return TokenResponse(access_token=access, user=_safe_user(user))


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")

    # Check if refresh token is blacklisted
    if _cache and await _cache.exists(f"jwt_bl:{token[:32]}"):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    payload = decode_refresh_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = payload.get("sub")
    user = await _user_repo.get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access = create_access_token(user_id, user.get("role", "user"))
    new_refresh = create_refresh_token(user_id)
    response.set_cookie(
        key="refresh_token", value=new_refresh, httponly=True, secure=False,
        samesite="lax", max_age=7 * 24 * 3600, path="/api/auth",
    )

    return {"access_token": access, "token_type": "bearer"}


@router.post("/logout")
async def logout(request: Request, response: Response, current_user: dict = Depends(get_current_user)):
    # Blacklist the refresh token if present
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token and _cache:
        from auth.jwt import decode_refresh_token
        payload = decode_refresh_token(refresh_token)
        if payload:
            # Blacklist for remaining validity
            import time
            exp = payload.get("exp", 0)
            ttl = max(int(exp - time.time()), 1)
            await _cache.set(f"jwt_bl:{refresh_token[:32]}", "1", ttl=ttl)

    response.delete_cookie("refresh_token", path="/api/auth")
    return {"ok": True}


@router.post("/ticket")
async def get_ticket(current_user: dict = Depends(get_current_user)):
    ticket = await create_ticket(current_user["user_id"], current_user.get("role", "user"))
    return {"ticket": ticket}


@router.post("/extension-auth")
async def extension_auth(body: ExtensionAuthRequest):
    """Authenticate Chrome extension via refresh_token value (sent in body).

    Returns a one-time ticket for WebSocket connection + user info.
    """
    if _cache and await _cache.exists(f"jwt_bl:{body.refresh_token[:32]}"):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    payload = decode_refresh_token(body.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user_id = payload.get("sub")
    user = await _user_repo.get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    ticket = await create_ticket(user_id, user.get("role", "user"))
    return {"ticket": ticket, "user": _safe_user(user)}


@router.get("/me/prompt-history")
async def get_prompt_history(current_user: dict = Depends(get_current_user)):
    # For now return empty list (will be populated when prompt history tracking is added)
    return []


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    user = await _user_repo.get(current_user["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _safe_user(user)


@router.get("/me/preferences")
async def get_preferences(current_user: dict = Depends(get_current_user)):
    prefs = await _pref_repo.get(current_user["user_id"])
    return prefs or {}


@router.put("/me/preferences")
async def update_preferences(body: PreferencesUpdate, current_user: dict = Depends(get_current_user)):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    result = await _pref_repo.upsert(current_user["user_id"], **fields)
    return result


def _safe_user(user: dict) -> dict:
    """Remove sensitive fields from user dict."""
    return {k: v for k, v in user.items() if k not in ("password_hash",)}
