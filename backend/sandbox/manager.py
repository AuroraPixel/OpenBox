"""Sandbox lifecycle management: User-level container reuse with session-level directory isolation."""
import asyncio
from dataclasses import dataclass, field

from core.log import create_logger
from models.container import ContainerStatus
from sandbox.client import SandboxClient
from sandbox.provider import build_sandbox_name

log = create_logger("sandbox.manager")


def _map_key(user_id: str, project_id: str = "default") -> str:
    """Build a stable in-memory mapping key for a user's sandbox."""
    return user_id


@dataclass
class SandboxInfo:
    """Information about a user-level sandbox container shared across sessions."""
    container_id: str
    user_id: str
    host: str
    port: int
    api_key: str
    project_id: str
    session_ids: set[str] = field(default_factory=set)
    base_url: str | None = None   # set by URL-addressed providers (wuying)

    @property
    def alive_url(self) -> str:
        return f"{(self.base_url or f'http://{self.host}:{self.port}').rstrip('/')}/alive"


class SandboxManager:
    """Manages user-level sandbox containers with session-level directory isolation.

    All sessions for the same user share ONE container.
    Each session gets its own working directory: /workspace/sessions/{session_id}/
    This avoids creating a new container per session while keeping data isolated.
    """

    def __init__(self):
        self._project_map: dict[str, SandboxInfo] = {}    # user_id -> sandbox
        self._session_project: dict[str, str] = {}        # session_id -> user_id
        self._clients: dict[str, SandboxClient] = {}      # user_id -> client
        self._lock = asyncio.Lock()

    async def _verify_sandbox_alive(self, sandbox: SandboxInfo, key: str) -> bool:
        """Return True when the tracked sandbox still responds to /alive."""
        import httpx

        try:
            # trust_env=False — the sandbox endpoint is direct infrastructure and
            # must not be routed through a developer's HTTP(S)_PROXY.
            async with httpx.AsyncClient(timeout=5.0, trust_env=False) as http:
                resp = await http.get(sandbox.alive_url)
            if resp.status_code == 200:
                return True
        except Exception:
            pass

        log.warning(f"Sandbox {sandbox.container_id} not responsive for key {key}")
        return False

    async def _cleanup_stale_sandbox(
        self,
        sandbox: SandboxInfo,
        key: str,
        session_id: str | None = None,
    ) -> None:
        """Clear stale sandbox state from both manager and provider caches."""
        from sandbox import provider

        self._project_map.pop(key, None)
        self._clients.pop(key, None)
        stale_sessions = [sid for sid, mapped_key in self._session_project.items() if mapped_key == key]
        for sid in stale_sessions:
            self._session_project.pop(sid, None)
        if session_id:
            self._session_project.pop(session_id, None)

        provider._containers.pop(sandbox.container_id, None)
        provider._api_keys.pop(sandbox.container_id, None)
        if hasattr(provider, "_container_owners"):
            provider._container_owners.pop(sandbox.container_id, None)
        if hasattr(provider, "_container_projects"):
            provider._container_projects.pop(sandbox.container_id, None)

    async def check_health(self, project_id: str = "default", user_id: str = "default") -> dict:
        """Check if a sandbox is available and healthy for the given user."""
        key = _map_key(user_id)
        sandbox = self._project_map.get(key)
        if sandbox:
            if await self._verify_sandbox_alive(sandbox, key):
                return {
                    "available": True,
                    "container_id": sandbox.container_id,
                    "container_name": build_sandbox_name(user_id),
                    "status": "running",
                }
            await self._cleanup_stale_sandbox(sandbox, key)

        from sandbox import provider
        containers = provider.get_containers_for_user(user_id)
        return {
            "available": False,
            "containers": [
                {
                    "id": c.id,
                    "name": c.name,
                    "status": c.status.value,
                    "host": c.host,
                    "port": c.port,
                }
                for c in containers
            ],
        }

    async def acquire(self, session_id: str, project_id: str = "default", user_id: str = "default") -> SandboxInfo:
        """Acquire a sandbox for a session. Reuses the user's existing container if available."""
        key = _map_key(user_id)

        async with self._lock:
            existing_key = self._session_project.get(session_id)
            if existing_key:
                sandbox = self._project_map.get(existing_key)
                if sandbox and existing_key == key:
                    if await self._verify_sandbox_alive(sandbox, key):
                        sandbox.session_ids.add(session_id)
                        return sandbox
                    await self._cleanup_stale_sandbox(sandbox, key, session_id)

            sandbox = self._project_map.get(key)
            if sandbox:
                if await self._verify_sandbox_alive(sandbox, key):
                    sandbox.session_ids.add(session_id)
                    self._session_project[session_id] = key
                    client = self._clients[key]
                    log.info(f"Reusing sandbox {sandbox.container_id} for session {session_id} (user {user_id})")
                    await self._ensure_session_dir(client, session_id)
                    return sandbox
                await self._cleanup_stale_sandbox(sandbox, key, session_id)

        from sandbox import provider

        try:
            info = provider.get_user_container(user_id)
            if info:
                if info.status != ContainerStatus.RUNNING:
                    await provider.start_container(info.id, user_id=user_id)
                    info = await provider.get_container(info.id, user_id=user_id)
            else:
                info = await provider.create_container(
                    name=build_sandbox_name(user_id),
                    image=None,
                    project_id=None,
                    user_id=user_id,
                )

            sandbox = SandboxInfo(
                container_id=info.id,
                user_id=user_id,
                host=info.host,
                port=info.port,
                api_key=info.api_key or "",
                project_id=project_id,
                session_ids={session_id},
                base_url=getattr(provider, "client_base_url", None),
            )

            client = SandboxClient(
                host=info.host,
                port=info.port,
                api_key=info.api_key or "",
                base_url=getattr(provider, "client_base_url", None),
            )

            async with self._lock:
                self._project_map[key] = sandbox
                self._session_project[session_id] = key
                self._clients[key] = client

            await self._ensure_session_dir(client, session_id)

            log.info(f"Created sandbox {info.id} for user {user_id}, session {session_id}")
            return sandbox

        except Exception as e:
            log.error(f"Failed to acquire sandbox for session {session_id}: {e}")
            raise

    async def _ensure_session_dir(self, client: SandboxClient, session_id: str) -> None:
        """Create the directory this session will run in.

        That is the project's directory, not one per session: sessions in a
        project share a working tree the way two terminals open on the same
        checkout do, so the agent can pick up where the last conversation left
        off instead of starting in an empty folder every time.
        """
        from project.workspace import (
            INTERNAL_ROOT, project_directory, slug_for, WORKSPACE_ROOT,
        )
        slug = "default"
        try:
            from session.session import project_id_for
            slug = await slug_for(await project_id_for(session_id))
        except Exception as e:
            log.debug(f"Could not resolve project for session {session_id}: {e}")

        workdir = project_directory(slug)
        try:
            await client.execute(
                command=f"mkdir -p {workdir} {INTERNAL_ROOT}",
                timeout=10,
                workdir=WORKSPACE_ROOT,
            )
        except Exception as e:
            log.warning(f"Failed to create project dir {workdir}: {e}")

    async def get_session_workdir(self, session_id: str) -> str:
        """The directory a session's tools run in — its project's directory."""
        from project.workspace import project_directory, slug_for
        try:
            from session.session import project_id_for
            return project_directory(await slug_for(await project_id_for(session_id)))
        except Exception as e:
            log.debug(f"Could not resolve workdir for {session_id}: {e}")
        return project_directory("default")

    async def release(self, session_id: str) -> None:
        """Release a session from its sandbox. Only destroys container when no sessions remain."""
        async with self._lock:
            key = self._session_project.pop(session_id, None)
            if not key:
                log.warning(f"No sandbox found for session {session_id}")
                return

            sandbox = self._project_map.get(key)
            if not sandbox:
                return

            sandbox.session_ids.discard(session_id)

            if sandbox.session_ids:
                log.info(f"Session {session_id} released, {len(sandbox.session_ids)} sessions still using sandbox")
                return

            self._project_map.pop(key, None)
            self._clients.pop(key, None)

        from sandbox import provider

        try:
            await provider.delete_container(sandbox.container_id, user_id=sandbox.user_id)
            log.info(
                f"Destroyed sandbox {sandbox.container_id} "
                f"(user {sandbox.user_id}, project {sandbox.project_id}, last session released)"
            )
        except Exception as e:
            log.warning(f"Failed to destroy sandbox {sandbox.container_id}: {e}")

    async def get_client(self, session_id: str, user_id: str = "default") -> SandboxClient:
        """Get the SandboxClient for a session. Acquires sandbox if needed."""
        key = self._session_project.get(session_id)
        if not key:
            await self.acquire(session_id, user_id=user_id)
            key = self._session_project.get(session_id)

        if key and key in self._clients:
            sandbox = self._project_map.get(key)
            if sandbox and not await self._verify_sandbox_alive(sandbox, key):
                await self._cleanup_stale_sandbox(sandbox, key, session_id)
                await self.acquire(session_id, user_id=user_id)
                key = self._session_project.get(session_id)
            if key and key in self._clients:
                return self._clients[key]

        raise RuntimeError(f"No sandbox client for session {session_id}")

    async def get_client_any(self, user_id: str = "default") -> SandboxClient | None:
        """Get any available SandboxClient (not session-specific).

        Used by management endpoints (skills, MCP) that operate at the container level.
        Returns the first available client. If none exists, auto-acquires a default sandbox.
        """
        for key, client in self._clients.items():
            sandbox = self._project_map.get(key)
            if sandbox and sandbox.user_id == user_id:
                if await self._verify_sandbox_alive(sandbox, key):
                    return client
                await self._cleanup_stale_sandbox(sandbox, key)
        try:
            await self.acquire("__management__", "default", user_id=user_id)
            key = self._session_project.get("__management__")
            if key:
                return self._clients.get(key)
        except Exception as e:
            log.warning(f"Failed to auto-acquire sandbox: {e}")
        return None

    def get_info(self, session_id: str) -> SandboxInfo | None:
        """Get sandbox info for a session (non-async, may return None)."""
        key = self._session_project.get(session_id)
        if key:
            return self._project_map.get(key)
        return None

    async def release_all(self, destroy: bool = True) -> None:
        """Release all sandboxes (used during shutdown)."""
        if destroy:
            keys = list(self._project_map.keys())
            for key in keys:
                sandbox = self._project_map.get(key)
                if sandbox:
                    from sandbox import provider
                    try:
                        await provider.delete_container(sandbox.container_id, user_id=sandbox.user_id)
                    except Exception as e:
                        log.warning(f"Error releasing sandbox for {key}: {e}")
        self._project_map.clear()
        self._session_project.clear()
        self._clients.clear()


sandbox_manager = SandboxManager()
