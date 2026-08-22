"""WUYING (无影云电脑) sandbox provider.

Unlike the Docker and Kubernetes providers, this one does not own a container
lifecycle. The sandbox is a long-lived Alibaba Cloud WUYING cloud desktop that
was provisioned out of band; the action server runs there as a systemd unit and
is reached over a tunnel endpoint (``wuying_endpoint``).

Consequences that matter:

* ``create_container`` is idempotent — it returns the one desktop we know about.
* ``delete_container`` / ``stop_container`` are deliberate no-ops. The session
  manager destroys a container once its last session is released; doing that to
  someone's cloud desktop would be destructive and is never what we want here.
* Isolation between sessions is by working directory only
  (``/workspace/sessions/<id>``), the same as the shared-container path the
  Docker provider already takes. There is no per-session boundary beyond that.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from core.log import create_logger
from models.container import ContainerInfo, ContainerStatus
from sandbox.provider import SandboxProvider

log = create_logger("sandbox.wuying")

CONTAINER_ID = "wuying-desktop"


class WuyingProvider(SandboxProvider):
    """Points every session at a single pre-provisioned WUYING cloud desktop."""

    supports_build = False
    owns_containers = False

    def __init__(self) -> None:
        from core.config import get_config

        config = get_config()
        self.endpoint: str = (getattr(config, "wuying_endpoint", "") or "http://127.0.0.1:18000").rstrip("/")
        self.desktop_id: str = getattr(config, "wuying_desktop_id", "") or CONTAINER_ID
        api_key: str = getattr(config, "wuying_api_key", "") or ""

        parsed = urlparse(self.endpoint)
        self._host = parsed.hostname or "127.0.0.1"
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        # SandboxManager builds its client from this rather than host/port, so a
        # tunnelled or TLS endpoint survives the round trip intact.
        self.client_base_url = self.endpoint

        self._api_key = api_key
        self._containers: dict[str, ContainerInfo] = {CONTAINER_ID: self._build_desktop()}
        self._api_keys: dict[str, str] = {CONTAINER_ID: api_key}
        # Shared desktop: every user maps onto the same sandbox.
        self._container_owners: dict[str, str] = {}
        self._container_projects: dict[str, str] = {}

        if not api_key:
            log.warning("WUYING_API_KEY is empty — the action server will reject every request")
        log.info(f"WUYING sandbox provider -> {self.endpoint} (desktop {self.desktop_id})")

    def _build_desktop(self) -> ContainerInfo:
        """The registry entry standing for the cloud desktop."""
        return ContainerInfo(
            id=CONTAINER_ID,
            name=self.desktop_id,
            status=ContainerStatus.RUNNING,
            image=f"wuying:{self.desktop_id}",
            created_at=datetime.now(timezone.utc),
            host=self._host,
            port=self._port,
            api_key=self._api_key,
        )

    def _desktop(self) -> ContainerInfo:
        """The one desktop, rebuilt if something evicted it.

        The registry holds exactly one entry and OpenBox does not own it: the
        desktop exists whether or not this process believes it does. Callers
        that recycle a dead sandbox clear it from the provider's caches —
        correct for containers OpenBox creates, fatal here, because nothing
        outside __init__ ever put it back. One failed liveness check used to
        strand every later request on KeyError until the process restarted.
        """
        info = self._containers.get(CONTAINER_ID)
        if info is None:
            log.warning("desktop entry was evicted from the registry; restoring it")
            info = self._build_desktop()
            self._containers[CONTAINER_ID] = info
            self._api_keys.setdefault(CONTAINER_ID, info.api_key or "")
        return info

    # -- lifecycle: the desktop already exists, so these are mostly inert --

    async def create_container(
        self, name: str, image: str | None = None,
        project_id: str | None = None, user_id: str | None = None,
    ) -> ContainerInfo:
        return self._desktop()

    async def delete_container(self, container_id: str, user_id: str | None = None) -> None:
        log.info("delete_container ignored — the WUYING desktop is not managed by OpenBox")

    async def start_container(self, container_id: str, user_id: str | None = None) -> None:
        return None

    async def stop_container(self, container_id: str, user_id: str | None = None) -> None:
        log.info("stop_container ignored — the WUYING desktop is not managed by OpenBox")

    async def get_container(self, container_id: str, user_id: str | None = None) -> ContainerInfo:
        return self._desktop()

    async def list_containers(self) -> list[ContainerInfo]:
        return list(self._containers.values())

    # -- ownership: one shared desktop, so every user resolves to it --

    def get_user_container(self, user_id: str, project_id: str | None = None) -> ContainerInfo | None:
        return self._desktop()

    def get_containers_for_user(self, user_id: str) -> list[ContainerInfo]:
        return list(self._containers.values())

    def ensure_container_access(self, container_id: str, user_id: str | None = None) -> None:
        return None

    async def ensure_user_container(self, user_id: str, project_id: str = "default") -> ContainerInfo:
        return self._desktop()

    # -- transport --

    async def forward_to_container(
        self, container_id: str, method: str, path: str,
        user_id: str | None = None, **kwargs,
    ) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers["X-API-Key"] = self._api_keys.get(CONTAINER_ID) or (self._desktop().api_key or "")
        timeout = kwargs.pop("timeout", 35.0)
        # trust_env=False: see SandboxClient._client — a developer proxy must not
        # intercept traffic to the tunnel endpoint.
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            return await client.request(method, f"{self.endpoint}{path}", headers=headers, **kwargs)

    async def reconcile(self) -> None:
        """Confirm the action server answers; log loudly rather than failing startup."""
        try:
            async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
                resp = await client.get(f"{self.endpoint}/alive")
            if resp.status_code == 200:
                log.info(f"WUYING sandbox reachable: {resp.json()}")
                return
            log.error(f"WUYING sandbox returned HTTP {resp.status_code} from {self.endpoint}/alive")
        except Exception as e:
            log.error(
                f"WUYING sandbox unreachable at {self.endpoint} ({e}). "
                "Is the SSH tunnel up? See scripts/wuying_tunnel.sh"
            )

    async def cleanup_all(self) -> None:
        return None
