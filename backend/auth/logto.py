"""Logto OIDC integration.

The browser runs the Authorization Code + PKCE flow directly against Logto as a
public client, so no client secret ever reaches this process. It then hands the
resulting ID token here; we verify it against Logto's JWKS, upsert a local user
keyed on the `sub` claim, and issue OpenBox's own JWT so the rest of the
codebase keeps using a single session representation.
"""
from __future__ import annotations

import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from core.log import create_logger

log = create_logger("auth.logto")

PROVIDER = "logto"
_JWKS_TTL = 3600

_jwk_client: PyJWKClient | None = None
_jwk_loaded_at: float = 0.0
_discovery: dict[str, Any] | None = None


class LogtoError(Exception):
    """Raised when a Logto token cannot be verified."""


def _settings():
    from core.config import get_config

    config = get_config()
    endpoint = (getattr(config, "logto_endpoint", "") or "").rstrip("/")
    return {
        "endpoint": endpoint,
        "issuer": (getattr(config, "logto_issuer", "") or (f"{endpoint}/oidc" if endpoint else "")),
        "jwks_uri": (getattr(config, "logto_jwks_uri", "") or (f"{endpoint}/oidc/jwks" if endpoint else "")),
        "app_id": getattr(config, "logto_app_id", "") or "",
        "app_secret": getattr(config, "logto_app_secret", "") or "",
    }


def is_enabled() -> bool:
    s = _settings()
    return bool(s["endpoint"] and s["app_id"])


def public_config() -> dict[str, Any]:
    """Non-secret values the browser needs to start the PKCE flow."""
    s = _settings()
    return {
        "enabled": is_enabled(),
        "endpoint": s["endpoint"],
        "issuer": s["issuer"],
        "app_id": s["app_id"],
    }


def _jwks() -> PyJWKClient:
    global _jwk_client, _jwk_loaded_at
    now = time.time()
    if _jwk_client is None or now - _jwk_loaded_at > _JWKS_TTL:
        uri = _settings()["jwks_uri"]
        if not uri:
            raise LogtoError("Logto is not configured (missing LOGTO_ENDPOINT)")
        # PyJWKClient keeps its own small cache; we rotate the client itself so a
        # rotated signing key is picked up within the TTL.
        _jwk_client = PyJWKClient(uri, cache_keys=True, lifespan=_JWKS_TTL)
        _jwk_loaded_at = now
    return _jwk_client


def verify_id_token(token: str) -> dict[str, Any]:
    """Verify a Logto ID token and return its claims.

    Audience is the Logto application ID for an ID token. Signature, issuer,
    audience and expiry are all enforced; a failure raises LogtoError.
    """
    s = _settings()
    if not is_enabled():
        raise LogtoError("Logto is not configured")
    try:
        signing_key = _jwks().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256", "ES384"],
            audience=s["app_id"],
            issuer=s["issuer"],
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise LogtoError("Logto token has expired") from e
    except jwt.InvalidAudienceError as e:
        raise LogtoError(f"Logto token audience does not match app_id {s['app_id']}") from e
    except jwt.InvalidIssuerError as e:
        raise LogtoError(f"Logto token issuer does not match {s['issuer']}") from e
    except Exception as e:  # signature, malformed token, JWKS fetch failure
        raise LogtoError(f"Logto token verification failed: {e}") from e

    if not claims.get("sub"):
        raise LogtoError("Logto token has no subject claim")
    return claims


async def exchange_code(code: str, code_verifier: str, redirect_uri: str) -> dict[str, Any]:
    """Complete Authorization Code + PKCE server-side.

    Done here rather than in the browser on purpose: Logto only allows a fixed
    set of CORS origins, and a server-to-server POST sidesteps that entirely.

    Client authentication depends on how the app is registered in Logto:

    * Traditional Web app (confidential) — has a secret, and the token endpoint
      rejects an unauthenticated request with `invalid_client` before it even
      looks at the code. Set LOGTO_APP_SECRET.
    * SPA / Native (public) — no secret; PKCE alone is the proof.

    Logto accepts both `client_secret_basic` and `client_secret_post`, and which
    one a given app is registered for is not discoverable, so we try Basic and
    fall back to POST on an `invalid_client` rejection.
    """
    s = _settings()
    if not is_enabled():
        raise LogtoError("Logto is not configured")

    form = {
        "grant_type": "authorization_code",
        "client_id": s["app_id"],
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
    }
    secret = s["app_secret"]

    # (auth kwargs, extra form fields) — first entry that isn't invalid_client wins.
    if secret:
        attempts = [
            ({"auth": (s["app_id"], secret)}, {}),          # client_secret_basic
            ({}, {"client_secret": secret}),                # client_secret_post
        ]
    else:
        attempts = [({}, {})]                                # public client, PKCE only

    last = ""
    async with httpx.AsyncClient(timeout=15.0) as client:
        for auth_kwargs, extra in attempts:
            try:
                resp = await client.post(
                    f"{s['endpoint']}/oidc/token",
                    data={**form, **extra},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    **auth_kwargs,
                )
            except Exception as e:
                raise LogtoError(f"Could not reach Logto token endpoint: {e}") from e

            if resp.status_code == 200:
                tokens = resp.json()
                if not tokens.get("id_token"):
                    raise LogtoError("Logto returned no id_token (is 'openid' in the scope?)")
                return tokens

            last = resp.text[:300]
            if "invalid_client" not in last:
                break  # a real failure (bad/expired code, redirect_uri mismatch) — don't retry

    log.warning(f"Logto token exchange failed: {last}")
    if "invalid_client" in last:
        if not secret:
            raise LogtoError(
                "Logto rejected the client. This app is registered as a confidential "
                "client, so PKCE alone is not enough — set LOGTO_APP_SECRET to the "
                "app's Default secret (or change the app type to SPA in Logto)."
            )
        raise LogtoError("Logto rejected the client credentials — check LOGTO_APP_SECRET")
    raise LogtoError(f"Logto rejected the authorization code: {last}")


async def fetch_userinfo(access_token: str) -> dict[str, Any]:
    """Best-effort profile lookup; ID token claims alone are often enough."""
    s = _settings()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{s['endpoint']}/oidc/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code == 200:
            return resp.json()
        log.warning(f"Logto userinfo returned HTTP {resp.status_code}")
    except Exception as e:
        log.warning(f"Logto userinfo lookup failed: {e}")
    return {}


def derive_username(claims: dict[str, Any]) -> str:
    """Pick a stable, human-readable username from OIDC claims."""
    for key in ("username", "preferred_username", "name"):
        value = claims.get(key)
        if value:
            return str(value)[:64]
    email = claims.get("email")
    if email:
        return str(email).split("@")[0][:64]
    return f"logto-{str(claims['sub'])[:16]}"
