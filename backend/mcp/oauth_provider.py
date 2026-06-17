"""OAuth 2.0 flow handler for MCP servers.

Implements:
- Authorization code grant flow with PKCE (RFC 7636)
- OAuth metadata discovery (RFC 8414)
- Dynamic client registration (RFC 7591)
- Token exchange and refresh
"""
import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from core.log import create_logger
from mcp.oauth import OAuthToken, store_token, persist_token

log = create_logger("mcp.oauth_provider")


@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    redirect_uri: str = "http://localhost:8080/api/agent/mcp/oauth/callback"
    scope: str = ""


# ── PKCE (RFC 7636) ──

def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256).

    Returns (code_verifier, code_challenge).
    """
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


# ── OAuth Metadata Discovery (RFC 8414) ──

async def discover_oauth_metadata(server_url: str) -> dict | None:
    """Discover OAuth metadata from /.well-known/oauth-authorization-server.

    Returns metadata dict or None if not available.
    """
    from urllib.parse import urlparse
    parsed = urlparse(server_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    well_known_url = f"{base}/.well-known/oauth-authorization-server"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(well_known_url)
            if resp.status_code == 200:
                data = resp.json()
                log.info(f"Discovered OAuth metadata at {well_known_url}")
                return data
    except Exception as e:
        log.debug(f"OAuth metadata discovery failed for {server_url}: {e}")
    return None


# ── Dynamic Client Registration (RFC 7591) ──

async def dynamic_register(
    registration_url: str,
    redirect_uri: str,
    client_name: str = "OpenBox",
) -> dict:
    """Dynamically register an OAuth client.

    Returns dict with client_id, client_secret (optional), etc.
    """
    payload = {
        "client_name": client_name,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_post",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(registration_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    log.info(f"Dynamic client registration successful: client_id={data.get('client_id', '?')}")
    return data


# ── Authorization URL ──

def build_authorize_url(config: OAuthConfig, state: str, code_challenge: str | None = None) -> str:
    """Build the OAuth authorization URL, optionally with PKCE."""
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "state": state,
    }
    if config.scope:
        params["scope"] = config.scope
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    return f"{config.authorize_url}?{urlencode(params)}"


# ── Token Exchange ──

async def exchange_code(
    config: OAuthConfig,
    code: str,
    server_name: str,
    user_id: str,
    code_verifier: str | None = None,
) -> OAuthToken:
    """Exchange authorization code for tokens, with optional PKCE verifier."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.redirect_uri,
        "client_id": config.client_id,
    }
    if config.client_secret:
        data["client_secret"] = config.client_secret
    if code_verifier:
        data["code_verifier"] = code_verifier

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(config.token_url, data=data)
        resp.raise_for_status()
        resp_data = resp.json()

    token = OAuthToken(
        access_token=resp_data["access_token"],
        refresh_token=resp_data.get("refresh_token"),
        expires_at=time.time() + resp_data.get("expires_in", 3600),
        token_type=resp_data.get("token_type", "Bearer"),
        scope=resp_data.get("scope", ""),
    )
    store_token(user_id, server_name, token)
    await persist_token(user_id, server_name, token)
    log.info(f"OAuth token obtained for MCP server '{server_name}'")
    return token


# ── Token Refresh ──

async def refresh_token(
    config: OAuthConfig,
    refresh_tok: str,
    server_name: str,
    user_id: str,
) -> OAuthToken | None:
    """Refresh an expired token."""
    try:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_tok,
            "client_id": config.client_id,
        }
        if config.client_secret:
            data["client_secret"] = config.client_secret

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(config.token_url, data=data)
            resp.raise_for_status()
            resp_data = resp.json()

        token = OAuthToken(
            access_token=resp_data["access_token"],
            refresh_token=resp_data.get("refresh_token", refresh_tok),
            expires_at=time.time() + resp_data.get("expires_in", 3600),
            token_type=resp_data.get("token_type", "Bearer"),
            scope=resp_data.get("scope", ""),
        )
        store_token(user_id, server_name, token)
        await persist_token(user_id, server_name, token)
        log.info(f"OAuth token refreshed for MCP server '{server_name}'")
        return token
    except Exception as e:
        log.error(f"Token refresh failed for {server_name}: {e}")
        return None
