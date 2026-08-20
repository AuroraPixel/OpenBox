"""SandboxProvider abstract interface — unifies Docker and Kubernetes sandbox backends."""
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

import httpx

from models.container import ContainerInfo, ContainerStatus


def _slug(value: str, *, max_length: int = 24) -> str:
    """Create a stable, lowercase identifier safe for Docker/K8s names."""
    safe = re.sub(r"[^a-zA-Z0-9-]+", "-", value).strip("-").lower()
    return (safe[:max_length] or "default").strip("-") or "default"


def build_sandbox_name(user_id: str, project_id: str = "default") -> str:
    """Build a stable sandbox name for a user-level sandbox."""
    return f"user-{_slug(user_id)}"


def _safe_user_alias(user_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9-]+", "-", user_id).strip("-").lower()
    return safe[:63] or "default"


class SandboxProvider(ABC):
    """Abstract base class for sandbox container providers.

    Both DockerManager and KubernetesProvider implement this interface,
    allowing the rest of the codebase to be agnostic about the runtime.
    """

    supports_build: bool = False

    # Providers that address the action server by URL (rather than by the
    # host/port pair on ContainerInfo) set this; SandboxManager prefers it when
    # building the client. Needed for tunnelled or TLS endpoints.
    client_base_url: str | None = None

    _containers: dict[str, ContainerInfo]
    _api_keys: dict[str, str]

    @abstractmethod
    async def create_container(
        self, name: str, image: str | None = None, project_id: str | None = None, user_id: str | None = None,
    ) -> ContainerInfo: ...

    @abstractmethod
    async def delete_container(self, container_id: str, user_id: str | None = None) -> None: ...

    @abstractmethod
    async def start_container(self, container_id: str, user_id: str | None = None) -> None: ...

    @abstractmethod
    async def stop_container(self, container_id: str, user_id: str | None = None) -> None: ...

    @abstractmethod
    async def get_container(self, container_id: str, user_id: str | None = None) -> ContainerInfo: ...

    @abstractmethod
    async def list_containers(self) -> list[ContainerInfo]: ...

    @abstractmethod
    async def forward_to_container(
        self, container_id: str, method: str, path: str, user_id: str | None = None, **kwargs,
    ) -> httpx.Response: ...

    @abstractmethod
    async def reconcile(self) -> None:
        """Restore in-memory state from the actual runtime (K8s pods / Docker containers)."""

    @abstractmethod
    async def cleanup_all(self) -> None:
        """Clean up all sandbox resources (Docker: remove containers, K8s: clear memory state)."""

    # Optional: image build support (Docker only)
    def image_exists(self, image: str | None = None) -> bool:
        return False

    async def build_sandbox_image(self) -> AsyncGenerator[dict, None]:
        yield {"step": "error", "message": "Image build not supported in this provider"}

    def _user_matches(self, owner: str | None, user_id: str) -> bool:
        if not owner:
            return False
        return owner == user_id or owner == _safe_user_alias(user_id)

    def get_user_container(self, user_id: str, project_id: str | None = None) -> ContainerInfo | None:
        owners = getattr(self, "_container_owners", {})
        fallback: ContainerInfo | None = None
        for container_id, info in self._containers.items():
            if not self._user_matches(owners.get(container_id), user_id):
                continue
            if info.status == ContainerStatus.RUNNING:
                return info
            if fallback is None:
                fallback = info
        return fallback

    def get_container_owner(self, container_id: str) -> str | None:
        owners = getattr(self, "_container_owners", {})
        return owners.get(container_id)

    def get_container_project(self, container_id: str) -> str | None:
        projects = getattr(self, "_container_projects", {})
        return projects.get(container_id)

    def ensure_container_access(self, container_id: str, user_id: str | None = None) -> None:
        if not user_id or user_id == "default":
            return

        owner = self.get_container_owner(container_id)
        if owner and not self._user_matches(owner, user_id):
            raise PermissionError(f"Container {container_id} does not belong to user {user_id}")

    def get_containers_for_user(self, user_id: str) -> list[ContainerInfo]:
        owners = getattr(self, "_container_owners", {})
        return [
            info
            for container_id, info in self._containers.items()
            if self._user_matches(owners.get(container_id), user_id)
        ]

    async def ensure_user_container(self, user_id: str, project_id: str = "default") -> ContainerInfo:
        existing = self.get_user_container(user_id)
        if existing:
            if existing.status != ContainerStatus.RUNNING:
                await self.start_container(existing.id, user_id=user_id)
                return await self.get_container(existing.id, user_id=user_id)
            return existing

        return await self.create_container(
            name=build_sandbox_name(user_id),
            image=None,
            project_id=None,
            user_id=user_id,
        )
