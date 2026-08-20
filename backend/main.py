"""OpenBox unified server: sandbox management + AI agent platform."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

# Load .env from project root before anything reads os.environ
load_dotenv(Path(__file__).parent / ".env")

from core.log import create_logger

log = create_logger("main")


def _init_agent():
    """Initialize the agent subsystem: register tools and start background tasks."""
    from tool.registry import register_builtin_tools
    register_builtin_tools()

    try:
        from tool.truncation import start_cleanup_task
        start_cleanup_task()
    except Exception as e:
        log.warning(f"Could not start truncation cleanup: {e}")

    log.info("Agent subsystem initialized")


def _init_infrastructure(config):
    """Initialize multi-user infrastructure (DB, Redis, Blob, Auth).

    Only initializes if jwt_secret is configured (multi-user mode).
    Single-user mode (no jwt_secret) skips infrastructure init.
    """
    if not config.jwt_secret:
        log.info("No JWT_SECRET configured — running in single-user mode (no auth)")
        return

    from db.base import init_engine
    init_engine(config.database_url, config.db_pool_size, config.db_pool_overflow)

    from cache.redis_cache import RedisCache
    from cache import set_cache
    cache = RedisCache(config.redis_url)
    set_cache(cache)

    from auth import setup_auth
    setup_auth(config, cache)

    config._cache = cache
    log.info("Multi-user infrastructure initialized")


async def _cleanup_infrastructure(config):
    """Cleanup multi-user infrastructure on shutdown."""
    if not config.jwt_secret:
        return

    try:
        from db.base import close_engine
        await close_engine()
    except Exception as e:
        log.warning(f"Error closing database: {e}")

    try:
        cache = getattr(config, '_cache', None)
        if cache:
            await cache.close()
    except Exception as e:
        log.warning(f"Error closing Redis: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.config import get_config
    config = get_config()

    _init_infrastructure(config)
    _init_agent()

    # Sandbox provider startup: reconcile against the real runtime where the
    # provider owns long-lived resources (K8s pods, an external WUYING desktop);
    # only Docker starts from a clean slate each boot.
    from sandbox import provider
    if config.sandbox_provider in ("kubernetes", "wuying"):
        await provider.reconcile()
        log.info(f"OpenBox starting ({config.sandbox_provider} provider, reconciled)")
    else:
        await provider.cleanup_all()
        log.info("OpenBox starting (docker provider, cleaned up)")

    # Initialize Redis event bus for cross-worker broadcasting (if in multi-user mode)
    if config.jwt_secret:
        from bus.bus import init_redis_bus
        await init_redis_bus(config.redis_url)

    # Initialize Cron scheduler
    try:
        from cron.service import cron_service
        from cron.executor import execute_cron_job
        cron_service.set_executor(execute_cron_job)
        await cron_service.start()
        log.info("Cron scheduler initialized")
    except Exception as e:
        log.warning(f"Failed to start cron scheduler: {e}")

    log.info("OpenBox starting...")
    yield
    log.info("OpenBox shutting down, cleaning up...")

    # Stop cron scheduler
    try:
        from cron.service import cron_service
        await cron_service.stop()
    except Exception as e:
        log.warning(f"Error stopping cron scheduler: {e}")

    # Abort active agent loops
    from session.status import abort_all, active_session_ids
    aborted = abort_all()
    if aborted:
        log.info(f"Sent abort signal to {aborted} active session(s), waiting up to 30s...")
        for _ in range(30):
            remaining = active_session_ids()
            if not remaining:
                break
            await asyncio.sleep(1)
        else:
            remaining = active_session_ids()
            if remaining:
                log.warning(f"{len(remaining)} session(s) still active after 30s timeout")

    # Mark lingering BUSY sessions as ERROR (multi-user mode)
    if config.jwt_secret:
        try:
            from db.base import _engine
            if _engine is not None:
                from db.base import get_db_session
                from db.models.session import Session as SessionModel
                from sqlalchemy import update
                async with get_db_session() as db:
                    await db.execute(
                        update(SessionModel)
                        .where(SessionModel.status == "busy")
                        .values(status="error")
                    )
                log.info("Marked lingering BUSY sessions as ERROR")
        except Exception as e:
            log.warning(f"Could not mark BUSY sessions as ERROR: {e}")

    # Close Redis event bus
    try:
        from bus.bus import close_redis_bus
        await close_redis_bus()
    except Exception as e:
        log.warning(f"Error closing Redis bus: {e}")

    # Container state cleanup
    from sandbox import sandbox_manager
    await sandbox_manager.release_all(destroy=False)
    await provider.cleanup_all()
    await _cleanup_infrastructure(config)


def create_app() -> FastAPI:
    """Application factory: build and configure the FastAPI app."""
    from core.config import get_config
    config = get_config()

    application = FastAPI(
        title="OpenBox API",
        version="0.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Auth routes (no auth required for register/login/refresh) ──
    if config.jwt_secret:
        from auth.routes import router as auth_router
        application.include_router(auth_router)

    # ── WebSocket endpoint (replaces SSE) ──
    from api.ws import router as ws_router
    application.include_router(ws_router)

    # ── Container management routes ──
    from api.containers import router as containers_router, preview_router
    from api.terminal import router as terminal_router
    from api.files import router as files_router
    from api.dev_browser import router as dev_browser_router

    application.include_router(containers_router)
    application.include_router(preview_router)  # No auth — browser accesses directly
    application.include_router(terminal_router)
    application.include_router(files_router)
    application.include_router(dev_browser_router)

    from api.cron import router as cron_router
    application.include_router(cron_router)

    # ── Agent routes ──
    agent_router = APIRouter(prefix="/api/agent", tags=["Agent"])

    from api.projects import router as project_router
    from api.sessions import router as session_router
    from api.permissions import router as perm_router
    from api.questions import router as question_router
    from api.metadata import router as metadata_router

    agent_router.include_router(project_router)
    agent_router.include_router(session_router)
    agent_router.include_router(perm_router)
    agent_router.include_router(question_router)
    agent_router.include_router(metadata_router)

    from api.prompt_history import router as prompt_history_router
    agent_router.include_router(prompt_history_router)

    application.include_router(agent_router)

    # ── Health check ──
    @application.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    return application


app = create_app()
