"""Auth module — JWT authentication, ticket system, middleware."""
from auth.jwt import init_auth
from auth.ticket import init_ticket_store
from auth.middleware import init_blacklist
from auth.routes import init_auth_routes
from auth.preview_token import init_preview_store


def setup_auth(config, cache):
    """Initialize all auth subsystems. Call during app startup."""
    if config.jwt_secret:
        init_auth(config.jwt_secret, config.jwt_access_expire_minutes, config.jwt_refresh_expire_days)
        init_ticket_store(cache)
        init_blacklist(cache)
        init_auth_routes(cache)
        init_preview_store(cache)
