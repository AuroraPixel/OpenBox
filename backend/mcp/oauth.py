"""OAuth 2.0 token management for MCP servers.

Stores tokens in-memory for fast access and persists to kv_store
(PostgreSQL in multi-user mode, FS JSON in single-user mode).
"""
import time
from dataclasses import dataclass
from typing import Optional

from core.log import create_logger

log = create_logger("mcp.oauth")


@dataclass
class OAuthToken:
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: float = 0.0  # Unix timestamp
    token_type: str = "Bearer"
    scope: str = ""

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at - 60  # 60s buffer


# In-memory token cache keyed by (user_id, server_name)
_tokens: dict[tuple[str, str], OAuthToken] = {}


def get_token(user_id: str, server_name: str) -> Optional[OAuthToken]:
    """Get cached token for a server."""
    return _tokens.get((user_id, server_name))


def store_token(user_id: str, server_name: str, token: OAuthToken) -> None:
    """Cache a token in memory."""
    _tokens[(user_id, server_name)] = token


async def persist_token(user_id: str, server_name: str, token: OAuthToken) -> None:
    """Persist token to kv_store (PG or FS)."""
    try:
        from storage import storage
        await storage.write(["oauth_tokens", user_id, server_name], {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "expires_at": token.expires_at,
            "token_type": token.token_type,
            "scope": token.scope,
        })
        log.info(f"Persisted OAuth token for {server_name} (user {user_id})")
    except Exception as e:
        log.warning(f"Failed to persist OAuth token: {e}")


async def load_token(user_id: str, server_name: str) -> Optional[OAuthToken]:
    """Load a persisted token from kv_store."""
    try:
        from storage import storage
        data = await storage.read(["oauth_tokens", user_id, server_name])
        if data and isinstance(data, dict):
            token = OAuthToken(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                expires_at=data.get("expires_at", 0),
                token_type=data.get("token_type", "Bearer"),
                scope=data.get("scope", ""),
            )
            # Cache in memory
            store_token(user_id, server_name, token)
            return token
    except Exception as e:
        log.debug(f"Could not load OAuth token for {server_name}: {e}")
    return None


async def delete_token(user_id: str, server_name: str) -> None:
    """Remove a stored token."""
    _tokens.pop((user_id, server_name), None)
    try:
        from storage import storage
        await storage.remove(["oauth_tokens", user_id, server_name])
    except Exception as e:
        log.debug(f"Could not delete OAuth token: {e}")
