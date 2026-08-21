"""OpenBox unified configuration loading and validation."""
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.log import create_logger

log = create_logger("config")


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class ProviderConfig(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    options: dict[str, Any] = {}


class CompactionConfig(BaseModel):
    auto: bool = True
    prune: bool = True
    reserved: int | None = None  # Override default buffer
    # How much recent history survives a compaction verbatim instead of being
    # replaced by the summary. None = 25% of usable context, clamped to
    # [8k, 60k] tokens. See agent/compaction_select.
    preserve_recent_tokens: int | None = None
    # Cap on how many recent turns are eligible for that tail. 0 disables the
    # tail entirely (summary-only, the pre-0.2 behaviour).
    tail_turns: int | None = None


class McpServerConfig(BaseModel):
    type: str = "local"  # "local" or "remote"
    command: list[str] = []
    url: str | None = None
    env: dict[str, str] = {}


class ModelConfig(BaseModel):
    id: str
    name: str | None = None       # Display name; defaults to last segment of id
    provider: str | None = None    # Defaults to first segment of id
    max_tokens: int = 200000
    context_limit: int | None = None  # Override context window size (tokens)
    # Whether the model accepts image input. None = fall back to the family
    # heuristic in agent.vision. Set it explicitly when a gateway exposes a
    # text-only variant of an otherwise multimodal family.
    vision: bool | None = None


class AgentOverride(BaseModel):
    model: str | None = None
    temperature: float | None = None
    prompt: str | None = None
    max_steps: int | None = None
    permission: list[dict[str, str]] | None = None


class SkillsConfig(BaseModel):
    paths: list[str] = []
    urls: list[str] = []


# ---------------------------------------------------------------------------
# Unified root config
# ---------------------------------------------------------------------------

class OpenBoxConfig(BaseModel):
    """Unified configuration merging server settings and agent config."""

    # -- Server --
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )

    # -- Sandbox --
    sandbox_provider: str = "docker"               # "docker" | "kubernetes" | "wuying"
    sandbox_image: str = "openbox-sandbox:latest"
    container_name_prefix: str = "openbox-sandbox-"
    container_port_range: tuple[int, int] = (10000, 19999)
    action_server_port: int = 8000
    container_ready_timeout: int = 30
    container_ready_interval: float = 0.5

    # -- Kubernetes (GKE) --
    k8s_namespace: str = "openbox-sandbox"
    k8s_storage_class: str = "standard-rwo"
    k8s_storage_size: str = "10Gi"
    k8s_sandbox_cpu_request: str = "250m"
    k8s_sandbox_cpu_limit: str = "1000m"
    k8s_sandbox_memory_request: str = "256Mi"
    k8s_sandbox_memory_limit: str = "1Gi"
    k8s_sandbox_service_account: str = ""           # SA for sandbox pods (Workload Identity)
    sandbox_idle_timeout: int = 1800                # idle reclaim seconds (30 min)

    # -- WUYING cloud desktop (sandbox_provider="wuying") --
    # A long-lived Alibaba Cloud desktop running the action server, reached over
    # a tunnel. OpenBox never creates or destroys it.
    wuying_endpoint: str = "http://127.0.0.1:18000"
    wuying_api_key: str = ""                        # must match SESSION_API_KEY on the desktop
    wuying_desktop_id: str = ""                     # ecd-... , used by the desktop-view ticket API
    wuying_region_id: str = "cn-hangzhou"           # region the desktop lives in
    wuying_end_user_id: str = ""                    # Wuying end user the web view logs in as

    # -- Browser automation on the cloud desktop --
    # local=drive a headed Chrome on the cloud desktop over CDP; extension=drive
    # the user's own browser through the dev-browser relay; auto=prefer the
    # user's browser but fall back to the cloud one when it disconnects.
    browser_mode: str = "auto"
    browser_chrome_port: int = 9333                 # remote-debugging port of the desktop-local Chrome

    # -- OSS asset transfer (browser -> OSS -> cloud desktop) --
    oss_bucket: str = ""                            # empty = OSS transfer disabled
    oss_region: str = "cn-hangzhou"
    oss_endpoint: str = ""                          # default oss-{region}.aliyuncs.com

    # -- Multi-user infrastructure --
    database_url: str = "postgresql+asyncpg://openbox:openbox@localhost:5432/openbox"
    db_pool_size: int = 10
    db_pool_overflow: int = 20
    redis_url: str = "redis://localhost:6379/0"
    blob_provider: str = "azure"
    blob_azure_connection_string: str = ""
    blob_azure_container: str = "ads-staging"
    blob_local_path: str = "/opt/openbox/blobs"
    gcs_bucket: str = ""

    # -- Authentication / quotas --
    jwt_secret: str = ""
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7
    max_containers_per_user: int = 5
    max_sessions_per_user: int = 200
    # Concurrent agent runs per user. One meant a second conversation could not
    # start while the first was still thinking — the common case of parking a
    # long task and working on something else was simply blocked.
    max_concurrent_agents: int = 5
    monthly_cost_limit: float = 50.0
    rate_limit_login: str = "5/minute"
    rate_limit_api: str = "60/minute"

    # -- Logto OIDC (optional; local username/password still works when unset) --
    # The browser is a public PKCE client, so no client secret is stored here.
    logto_endpoint: str = ""                 # e.g. https://account.example.com
    logto_app_id: str = ""
    # Required only for a confidential app (Logto "Traditional Web"); a SPA /
    # Native app is a public client and leaves this empty.
    logto_app_secret: str = ""
    logto_issuer: str = ""                   # defaults to {endpoint}/oidc
    logto_jwks_uri: str = ""                 # defaults to {endpoint}/oidc/jwks
    logto_redirect_uri: str = "http://localhost:3000/callback"
    logto_post_logout_redirect_uri: str = "http://localhost:3000"

    # -- Agent --
    model: str = "anthropic/claude-sonnet-4-20250514"
    mcp_filter_model: str = ""
    models: list[ModelConfig] = []
    provider: dict[str, ProviderConfig] = {}
    agent: dict[str, AgentOverride] = {}
    permission: dict[str, Any] = {}
    mcp: dict[str, McpServerConfig] = {}
    skills: SkillsConfig = SkillsConfig()
    compaction: CompactionConfig = CompactionConfig()
    instructions: list[str] = []


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_config: OpenBoxConfig | None = None


# ---------------------------------------------------------------------------
# Config file discovery
# ---------------------------------------------------------------------------

def _find_config_files() -> list[Path]:
    """Find config files in priority order (later overrides earlier)."""
    candidates: list[Path] = []

    # 1. Global config
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))

    # Prefer openbox, fall back to openagent
    global_path_new = Path(config_home) / "openbox" / "openbox.json"
    global_path_old = Path(config_home) / "openagent" / "openagent.json"
    if global_path_new.exists():
        candidates.append(global_path_new)
    elif global_path_old.exists():
        candidates.append(global_path_old)

    # 2. Project-level config (current directory)
    cwd = Path.cwd()
    for name in ["openbox.json", "openbox.jsonc", "openagent.json", "openagent.jsonc"]:
        project_path = cwd / name
        if project_path.exists():
            candidates.append(project_path)
            break

    # 3. Custom via environment variable (prefer OPENBOX_CONFIG, fall back to OPENAGENT_CONFIG)
    custom = os.environ.get("OPENBOX_CONFIG") or os.environ.get("OPENAGENT_CONFIG")
    if custom and Path(custom).exists():
        candidates.append(Path(custom))

    return candidates


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _strip_json_comments(text: str) -> str:
    """Strip // and /* */ comments from JSON, respecting quoted strings."""
    result = []
    i = 0
    n = len(text)
    while i < n:
        # String literal: copy verbatim
        if text[i] == '"':
            result.append('"')
            i += 1
            while i < n:
                ch = text[i]
                result.append(ch)
                i += 1
                if ch == '\\' and i < n:
                    result.append(text[i])
                    i += 1
                elif ch == '"':
                    break
        # Line comment
        elif text[i:i+2] == '//':
            while i < n and text[i] != '\n':
                i += 1
        # Block comment
        elif text[i:i+2] == '/*':
            i += 2
            while i < n and text[i-1:i+1] != '*/':
                i += 1
            i += 1
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


def _load_json(path: Path) -> dict:
    """Load JSON with comment stripping (supports // and /* */ in any .json/.jsonc)."""
    content = path.read_text(encoding="utf-8")
    content = _strip_json_comments(content)
    return json.loads(content)


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dicts, override wins for conflicts."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _resolve_env_vars(data: Any) -> Any:
    """Resolve {env:VAR_NAME} placeholders in config values."""
    if isinstance(data, str):
        import re

        def replacer(m):
            var_name = m.group(1)
            return os.environ.get(var_name, "")

        return re.sub(r"\{env:(\w+)\}", replacer, data)
    elif isinstance(data, dict):
        return {k: _resolve_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_resolve_env_vars(v) for v in data]
    return data


# ---------------------------------------------------------------------------
# Environment variable overrides for server fields
# ---------------------------------------------------------------------------

def _apply_env_overrides(data: dict) -> dict:
    """Apply environment variable overrides for server/sandbox/agent fields."""
    # Server & sandbox
    env_map = {
        "host": "HOST",
        "port": "PORT",
        "debug": "DEBUG",
        "sandbox_provider": "SANDBOX_PROVIDER",
        "sandbox_image": "SANDBOX_IMAGE",
        "container_name_prefix": "CONTAINER_NAME_PREFIX",
        "k8s_namespace": "K8S_NAMESPACE",
        "k8s_storage_class": "K8S_STORAGE_CLASS",
        "k8s_storage_size": "K8S_STORAGE_SIZE",
        "k8s_sandbox_cpu_request": "K8S_SANDBOX_CPU_REQUEST",
        "k8s_sandbox_cpu_limit": "K8S_SANDBOX_CPU_LIMIT",
        "k8s_sandbox_memory_request": "K8S_SANDBOX_MEMORY_REQUEST",
        "k8s_sandbox_memory_limit": "K8S_SANDBOX_MEMORY_LIMIT",
        "k8s_sandbox_service_account": "K8S_SANDBOX_SERVICE_ACCOUNT",
        "sandbox_idle_timeout": "SANDBOX_IDLE_TIMEOUT",
        "wuying_endpoint": "WUYING_ENDPOINT",
        "wuying_api_key": "WUYING_API_KEY",
        "wuying_desktop_id": "WUYING_DESKTOP_ID",
        "wuying_region_id": "WUYING_REGION_ID",
        "wuying_end_user_id": "WUYING_END_USER_ID",
        "browser_mode": "BROWSER_MODE",
        "browser_chrome_port": "BROWSER_CHROME_PORT",
        "oss_bucket": "OSS_BUCKET",
        "oss_region": "OSS_REGION",
        "oss_endpoint": "OSS_ENDPOINT",
        "database_url": "DATABASE_URL",
        "db_pool_size": "DB_POOL_SIZE",
        "db_pool_overflow": "DB_POOL_OVERFLOW",
        "redis_url": "REDIS_URL",
        "blob_provider": "BLOB_PROVIDER",
        "blob_azure_connection_string": "BLOB_AZURE_CONNECTION_STRING",
        "blob_azure_container": "BLOB_AZURE_CONTAINER",
        "blob_local_path": "BLOB_LOCAL_PATH",
        "gcs_bucket": "GCS_BUCKET",
        "jwt_secret": "JWT_SECRET",
        "jwt_access_expire_minutes": "JWT_ACCESS_EXPIRE_MINUTES",
        "jwt_refresh_expire_days": "JWT_REFRESH_EXPIRE_DAYS",
        "max_containers_per_user": "MAX_CONTAINERS_PER_USER",
        "max_sessions_per_user": "MAX_SESSIONS_PER_USER",
        "max_concurrent_agents": "MAX_CONCURRENT_AGENTS",
        "monthly_cost_limit": "MONTHLY_COST_LIMIT",
        "rate_limit_login": "RATE_LIMIT_LOGIN",
        "rate_limit_api": "RATE_LIMIT_API",
        "logto_endpoint": "LOGTO_ENDPOINT",
        "logto_app_id": "LOGTO_APP_ID",
        "logto_app_secret": "LOGTO_APP_SECRET",
        "logto_issuer": "LOGTO_ISSUER",
        "logto_jwks_uri": "LOGTO_JWKS_URI",
        "logto_redirect_uri": "LOGTO_REDIRECT_URI",
        "logto_post_logout_redirect_uri": "LOGTO_POST_LOGOUT_REDIRECT_URI",
    }
    for field_name, env_var in env_map.items():
        value = os.environ.get(env_var)
        if value is not None:
            if field_name == "port":
                data[field_name] = int(value)
            elif field_name == "sandbox_idle_timeout":
                data[field_name] = int(value)
            elif field_name in {"db_pool_size", "db_pool_overflow", "jwt_access_expire_minutes",
                                "jwt_refresh_expire_days", "max_containers_per_user", "max_sessions_per_user",
                                "max_concurrent_agents", "browser_chrome_port"}:
                data[field_name] = int(value)
            elif field_name == "monthly_cost_limit":
                data[field_name] = float(value)
            elif field_name == "debug":
                data[field_name] = value.lower() == "true"
            else:
                data[field_name] = value

    # Agent model
    model_env = os.environ.get("OPENBOX_MODEL")
    if model_env:
        data["model"] = model_env

    # Provider: OPENBOX_API_KEY / OPENBOX_BASE_URL apply to the active model's provider
    api_key = os.environ.get("OPENBOX_API_KEY")
    base_url = os.environ.get("OPENBOX_BASE_URL")
    if api_key or base_url:
        model_id = data.get("model", "anthropic/claude-sonnet-4-20250514")
        provider_name = model_id.split("/")[0] if "/" in model_id else model_id
        providers = data.setdefault("provider", {})
        provider_cfg = providers.setdefault(provider_name, {})
        if api_key:
            provider_cfg["api_key"] = api_key
        if base_url:
            provider_cfg["base_url"] = base_url

    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config() -> OpenBoxConfig:
    """Load and merge all config files."""
    merged: dict = {}

    for path in _find_config_files():
        try:
            data = _load_json(path)
            merged = _deep_merge(merged, data)
            log.info(f"Loaded config from {path}")
        except Exception as e:
            log.warning(f"Failed to load config {path}: {e}")

    # Apply inline config from environment (prefer OPENBOX_, fall back to OPENAGENT_)
    inline = os.environ.get("OPENBOX_CONFIG_CONTENT") or os.environ.get("OPENAGENT_CONFIG_CONTENT")
    if inline:
        try:
            data = json.loads(inline)
            merged = _deep_merge(merged, data)
        except Exception as e:
            log.warning(f"Failed to parse inline config content: {e}")

    # Resolve environment variables
    merged = _resolve_env_vars(merged)

    # Apply env var overrides for server fields
    merged = _apply_env_overrides(merged)

    return OpenBoxConfig(**merged)


def get_config() -> OpenBoxConfig:
    """Get the current config (loads on first access). Works both sync and async."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> OpenBoxConfig:
    """Force reload config."""
    global _config
    _config = None
    _config = load_config()
    return _config
