"""Config and metadata routes."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from auth.middleware import get_current_user, require_admin
from pydantic import BaseModel

router = APIRouter(dependencies=[Depends(get_current_user)])


class InstallSkillBody(BaseModel):
    url: str | None = None
    name: str | None = None
    content: str | None = None


class AddMcpServerBody(BaseModel):
    name: str
    type: str = "stdio"
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    timeout: int = 60


@router.get("/config")
async def get_config():
    """Get application configuration."""
    from core.config import get_config
    config = get_config()

    # The context window and vision support are resolved here rather than
    # passed through raw, so the frontend always receives a real number and a
    # real boolean — it has no business re-deriving either from a model id.
    from agent.compaction import get_model_context_limit
    from agent.vision import supports_vision

    # Build model list: use explicit models list if configured, else fall back to single model
    if config.models:
        models = []
        for m in config.models:
            models.append({
                "id": m.id,
                "name": m.name or m.id.split("/")[-1],
                "provider": m.provider or (m.id.split("/")[0] if "/" in m.id else ""),
                "max_tokens": m.max_tokens,
                "context_limit": get_model_context_limit(m.id),
                "vision": supports_vision(m.id),
            })
    else:
        models = [{
            "id": config.model,
            "name": config.model.split("/")[-1],
            "provider": config.model.split("/")[0] if "/" in config.model else "",
            "max_tokens": 200000,
            "context_limit": get_model_context_limit(config.model),
            "vision": supports_vision(config.model),
        }]

    return {
        "models": models,
        "default_model": config.model,
        "default_agent": "build",
    }


@router.get("/agent")
async def list_agents():
    """List available agents."""
    from agent.agent import list_agents
    agents = list_agents()
    return [
        {
            "name": a.name,
            "description": a.description,
            "model": a.model or "",
            "temperature": a.temperature,
            "tools": a.tools,
        }
        for a in agents
    ]


@router.get("/skill")
async def list_skills(current_user: dict = Depends(get_current_user)):
    """List available skills (from container + local fallback)."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    # Try container first
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if client:
            return await client.list_skills()
    except Exception:
        pass
    # Fall back to local skills
    try:
        from skill.skill import list_skills
        skills = await list_skills()
        return [{"name": s.name, "description": s.description, "source": s.source} for s in skills]
    except ImportError:
        return []


@router.get("/skill/{name}")
async def get_skill(name: str, current_user: dict = Depends(get_current_user)):
    """Get skill details."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if client:
            return await client.get_skill(name)
    except Exception:
        pass
    raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")


@router.post("/skill/install")
async def install_skill(body: InstallSkillBody, current_user: dict = Depends(get_current_user)):
    """Install a skill into the container."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if not client:
            raise HTTPException(status_code=503, detail="No sandbox available. Send a message first to create one.")
        return await client.install_skill(
            url=body.url,
            name=body.name,
            content=body.content,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/skill/{name}")
async def uninstall_skill(name: str, current_user: dict = Depends(get_current_user)):
    """Uninstall a skill from the container."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if not client:
            raise HTTPException(status_code=503, detail="No sandbox available")
        return await client.uninstall_skill(name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/skill/upload")
async def upload_skill_archive(
    file: UploadFile = File(...),
    name: str = Form(""),
    current_user: dict = Depends(get_current_user),
):
    """Install a skill from an uploaded archive (zip/tar/tar.gz/tgz/rar)."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if not client:
            raise HTTPException(status_code=503, detail="No sandbox available")
        file_bytes = await file.read()
        return await client.upload_skill_archive(file_bytes, file.filename or "archive.zip", name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/command")
async def list_commands():
    """List available slash commands."""
    try:
        from command.command import list_commands
        return await list_commands()
    except ImportError:
        return []


@router.get("/mcp")
async def get_mcp_status(current_user: dict = Depends(get_current_user)):
    """Get MCP server status (from container)."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if client:
            return await client.list_mcp_servers()
    except Exception:
        pass
    return []


@router.post("/mcp")
async def add_mcp_server(body: AddMcpServerBody, current_user: dict = Depends(get_current_user)):
    """Add a new MCP server configuration to the container."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if not client:
            raise HTTPException(status_code=503, detail="No sandbox available")
        config = body.model_dump(exclude={"name"}, exclude_none=True)
        return await client.add_mcp_server(name=body.name, config=config)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/mcp/{name}")
async def remove_mcp_server(name: str, current_user: dict = Depends(get_current_user)):
    """Remove an MCP server from the container."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if not client:
            raise HTTPException(status_code=503, detail="No sandbox available")
        return await client.remove_mcp_server(name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/{name}/connect")
async def connect_mcp(name: str, current_user: dict = Depends(get_current_user)):
    """Connect to an MCP server in the container."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if not client:
            raise HTTPException(status_code=503, detail="No sandbox available")
        return await client.connect_mcp(name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/{name}/disconnect")
async def disconnect_mcp(name: str, current_user: dict = Depends(get_current_user)):
    """Disconnect from an MCP server in the container."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if not client:
            raise HTTPException(status_code=503, detail="No sandbox available")
        return await client.disconnect_mcp(name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/{name}/refresh")
async def refresh_mcp(name: str, current_user: dict = Depends(get_current_user)):
    """Refresh tools/resources/prompts for a connected MCP server."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if not client:
            raise HTTPException(status_code=503, detail="No sandbox available")
        result = await client.refresh_mcp_server(name)
        if result.get("tools_changed"):
            from bus import bus
            bus.publish("mcp.tools_changed", {"userId": user_id, "server": name, "tools": result.get("tools", 0)})
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mcp/resources")
async def list_mcp_resources(current_user: dict = Depends(get_current_user)):
    """List all MCP resources from connected servers."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if client:
            return await client.list_mcp_resources()
    except Exception:
        pass
    return []


class ReadResourceBody(BaseModel):
    server: str
    uri: str


@router.post("/mcp/resources/read")
async def read_mcp_resource(body: ReadResourceBody, current_user: dict = Depends(get_current_user)):
    """Read a specific MCP resource."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if not client:
            raise HTTPException(status_code=503, detail="No sandbox available")
        return await client.read_mcp_resource(body.server, body.uri)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mcp/prompts")
async def list_mcp_prompts(current_user: dict = Depends(get_current_user)):
    """List all MCP prompts from connected servers."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if client:
            return await client.list_mcp_prompts()
    except Exception:
        pass
    return []


class GetPromptBody(BaseModel):
    server: str
    name: str
    arguments: dict | None = None


@router.post("/mcp/prompts/get")
async def get_mcp_prompt(body: GetPromptBody, current_user: dict = Depends(get_current_user)):
    """Get a specific MCP prompt."""
    from sandbox.manager import sandbox_manager
    user_id = current_user["user_id"]
    try:
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if not client:
            raise HTTPException(status_code=503, detail="No sandbox available")
        return await client.get_mcp_prompt(body.server, body.name, body.arguments)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── MCP OAuth (F8) ── PKCE + Dynamic Registration + Auto-Discovery ──

# In-memory state for pending OAuth flows
_oauth_pending: dict[str, dict] = {}  # state -> {server_name, user_id, code_verifier, oauth_config}


class McpOAuthStartBody(BaseModel):
    server_name: str


@router.post("/mcp/oauth/start")
async def start_mcp_oauth(
    body: McpOAuthStartBody,
    current_user: dict = Depends(get_current_user),
):
    """Initiate OAuth flow for an MCP server. Returns the authorize URL.

    Supports:
    - Manual OAuth config (client_id, client_secret, etc.)
    - Auto-discovery via /.well-known/oauth-authorization-server (RFC 8414)
    - Dynamic client registration (RFC 7591) if discovery reveals registration_endpoint
    - PKCE (RFC 7636) for enhanced security
    """
    from core.config import get_config
    from core.identifier import generate_id
    from mcp.oauth_provider import (
        OAuthConfig, build_authorize_url, generate_pkce,
        discover_oauth_metadata, dynamic_register,
    )

    config = get_config()
    mcp_config = config.mcp.get(body.server_name)
    if not mcp_config:
        raise HTTPException(404, f"MCP server '{body.server_name}' not configured")

    redirect_uri = f"http://localhost:{config.port}/api/agent/mcp/oauth/callback"
    oauth_cfg = getattr(mcp_config, "oauth", None)

    # If no OAuth config but server has a URL, try auto-discovery
    if (not oauth_cfg or not isinstance(oauth_cfg, dict)) and mcp_config.url:
        metadata = await discover_oauth_metadata(mcp_config.url)
        if metadata and "authorization_endpoint" in metadata:
            reg_endpoint = metadata.get("registration_endpoint")
            if reg_endpoint:
                # Dynamic client registration (RFC 7591)
                reg_result = await dynamic_register(reg_endpoint, redirect_uri)
                oauth_cfg = {
                    "client_id": reg_result["client_id"],
                    "client_secret": reg_result.get("client_secret", ""),
                    "authorize_url": metadata["authorization_endpoint"],
                    "token_url": metadata["token_endpoint"],
                    "scope": " ".join(metadata.get("scopes_supported", [])),
                }
            else:
                raise HTTPException(400,
                    f"Server requires OAuth but no client_id configured and no registration endpoint available")
        elif not metadata:
            raise HTTPException(400, f"MCP server '{body.server_name}' has no OAuth configuration")

    if not oauth_cfg or not isinstance(oauth_cfg, dict):
        raise HTTPException(400, f"MCP server '{body.server_name}' has no OAuth configuration")

    # Generate PKCE pair
    code_verifier, code_challenge = generate_pkce()

    state = generate_id()
    _oauth_pending[state] = {
        "server_name": body.server_name,
        "user_id": current_user["user_id"],
        "code_verifier": code_verifier,
        "oauth_config": oauth_cfg,  # Store for callback (may be from dynamic registration)
    }

    oa = OAuthConfig(
        client_id=oauth_cfg["client_id"],
        client_secret=oauth_cfg.get("client_secret", ""),
        authorize_url=oauth_cfg["authorize_url"],
        token_url=oauth_cfg["token_url"],
        redirect_uri=oauth_cfg.get("redirect_uri", redirect_uri),
        scope=oauth_cfg.get("scope", ""),
    )
    url = build_authorize_url(oa, state, code_challenge=code_challenge)
    return {"authorize_url": url, "state": state}


@router.get("/mcp/oauth/callback")
async def mcp_oauth_callback(code: str, state: str):
    """Handle OAuth callback, exchange code for token (with PKCE verifier)."""
    from core.config import get_config
    from mcp.oauth_provider import OAuthConfig, exchange_code

    pending = _oauth_pending.pop(state, None)
    if not pending:
        raise HTTPException(400, "Invalid or expired OAuth state")

    server_name = pending["server_name"]
    user_id = pending["user_id"]
    code_verifier = pending.get("code_verifier")
    oauth_cfg = pending.get("oauth_config")

    config = get_config()

    # Use stored oauth_cfg (may be from dynamic registration)
    if not oauth_cfg:
        mcp_config = config.mcp.get(server_name)
        if not mcp_config:
            raise HTTPException(404, f"MCP server '{server_name}' not found")
        oauth_cfg = getattr(mcp_config, "oauth", None) or {}

    redirect_uri = f"http://localhost:{config.port}/api/agent/mcp/oauth/callback"
    oa = OAuthConfig(
        client_id=oauth_cfg["client_id"],
        client_secret=oauth_cfg.get("client_secret", ""),
        authorize_url=oauth_cfg["authorize_url"],
        token_url=oauth_cfg["token_url"],
        redirect_uri=oauth_cfg.get("redirect_uri", redirect_uri),
        scope=oauth_cfg.get("scope", ""),
    )

    token = await exchange_code(oa, code, server_name, user_id, code_verifier=code_verifier)

    try:
        from bus.bus import publish_toast
        publish_toast(user_id, "success", f"MCP server '{server_name}' authorized via OAuth")
    except Exception:
        pass

    return {
        "ok": True,
        "server_name": server_name,
        "message": "OAuth authorization successful. You can close this window.",
    }
