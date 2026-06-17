import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sse_starlette.sse import EventSourceResponse

from auth.middleware import get_current_user, require_admin
from sandbox import provider
from models.container import (
    ContainerInfo,
    ContainerListResponse,
    CreateContainerRequest,
    ImageStatusResponse,
    SuccessResponse,
)

router = APIRouter(prefix="/api/containers", tags=["containers"], dependencies=[Depends(get_current_user)])

# Preview proxy: separate router with preview token auth (no JWT — browser accesses via URL)
preview_router = APIRouter(prefix="/api/containers", tags=["preview"])


@router.get("/sandbox-image/status", response_model=ImageStatusResponse)
async def check_sandbox_image(current_user: dict = Depends(require_admin)):
    image = provider.config.sandbox_image
    exists = provider.image_exists(image)
    return ImageStatusResponse(exists=exists, image=image)


@router.post("/sandbox-image/build")
async def build_sandbox_image(current_user: dict = Depends(require_admin)):
    if not provider.supports_build:
        async def not_supported():
            yield {"data": json.dumps({"step": "error", "message": "Image build not supported in this provider"})}
        return EventSourceResponse(not_supported())

    async def event_stream():
        async for event in provider.build_sandbox_image():
            yield {"data": json.dumps(event)}

    return EventSourceResponse(event_stream())


@router.post("", response_model=ContainerInfo, status_code=201)
async def create_container(req: CreateContainerRequest, current_user: dict = Depends(get_current_user)):
    from auth.quota import check_container_quota
    from core.config import get_config
    user_id = current_user["user_id"]
    config = get_config()

    existing_list = provider.get_containers_for_user(user_id)
    if existing_list:
        raise HTTPException(status_code=409, detail="Each user can only have one container")

    await check_container_quota(user_id, config)
    try:
        return await provider.create_container(req.name, req.image, req.project_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=ContainerListResponse)
async def list_containers(current_user: dict = Depends(get_current_user)):
    containers = provider.get_containers_for_user(current_user["user_id"])
    return ContainerListResponse(containers=containers, total=len(containers))


@router.get("/admin/all")
async def list_all_containers(current_user: dict = Depends(require_admin)):
    """List all containers across all users (admin only)."""
    from db.base import get_db_session
    from db.models.container import Container as ContainerORM
    from sqlalchemy import select
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(ContainerORM)
                .where(ContainerORM.is_deleted == False)  # noqa: E712
                .order_by(ContainerORM.created_at.desc())
            )
            rows = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "project_id": r.project_id,
                    "docker_id": r.docker_id,
                    "host": r.host,
                    "name": r.name,
                    "status": r.status,
                    "image": r.image,
                    "port": r.port,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query containers: {e}")


@router.get("/{container_id}", response_model=ContainerInfo)
async def get_container(container_id: str, current_user: dict = Depends(get_current_user)):
    try:
        return await provider.get_container(container_id, user_id=current_user["user_id"])
    except ValueError:
        raise HTTPException(status_code=404, detail="Container not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.delete("/{container_id}", response_model=SuccessResponse)
async def delete_container(container_id: str, current_user: dict = Depends(get_current_user)):
    try:
        await provider.delete_container(container_id, user_id=current_user["user_id"])
        return SuccessResponse(message="Container deleted")
    except ValueError:
        raise HTTPException(status_code=404, detail="Container not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/{container_id}/stop", response_model=SuccessResponse)
async def stop_container(container_id: str, current_user: dict = Depends(get_current_user)):
    try:
        await provider.stop_container(container_id, user_id=current_user["user_id"])
        return SuccessResponse(message="Container stopped")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/{container_id}/start", response_model=SuccessResponse)
async def start_container(container_id: str, current_user: dict = Depends(get_current_user)):
    try:
        await provider.start_container(container_id, user_id=current_user["user_id"])
        return SuccessResponse(message="Container started")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/{container_id}/ports")
async def get_listening_ports(container_id: str, current_user: dict = Depends(get_current_user)):
    """Detect TCP ports with services listening inside the container."""
    try:
        resp = await provider.forward_to_container(
            container_id, "GET", "/listening_ports", user_id=current_user["user_id"], timeout=5.0,
        )
        return resp.json()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to query ports: {e}")


@router.post("/{container_id}/preview-token")
async def create_preview_access_token(container_id: str, port: int, current_user: dict = Depends(get_current_user)):
    """Create short-lived preview token bound to user + container + port."""
    user_id = current_user["user_id"]
    try:
        await provider.get_container(container_id, user_id=user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Container not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")

    from auth.preview_token import create_preview_token
    token = await create_preview_token(user_id, container_id, port)
    return {
        "token": token,
        "url": f"/api/containers/{container_id}/preview/{port}/?_pt={token}",
    }


# ── Preview Proxy (no auth — container is ephemeral) ──

@preview_router.api_route(
    "/{container_id}/preview/{port:int}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
@preview_router.api_route(
    "/{container_id}/preview/{port:int}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def preview_proxy(request: Request, container_id: str, port: int, path: str = ""):
    """Proxy requests to a user application running inside the container on the given port.

    NOTE: Preview proxy is intentionally open — NO authentication, NO token required.
    Do NOT add auth here. Browser loads these URLs directly (iframes, stylesheets,
    scripts, fonts, source maps, HMR) and cannot attach Authorization headers.
    Container sandboxes are ephemeral and network-isolated per-user, so the risk is low.
    """
    try:
        info = await provider.get_container(container_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Container not found")

    proxy_url = f"http://{info.host}:{info.port}/proxy/{port}/{path}"
    if request.url.query:
        proxy_url += f"?{request.url.query}"

    body = await request.body()
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "connection")}
    headers["X-API-Key"] = info.api_key or ""

    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method=request.method,
                url=proxy_url,
                headers=headers,
                content=body,
            )
        excluded = {"transfer-encoding", "connection", "content-encoding", "content-length"}
        resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}

        content = resp.content
        content_type = resp.headers.get("content-type", "")

        if "text/html" in content_type and resp.status_code == 200:
            base_href = f"/api/containers/{container_id}/preview/{port}/"
            base_tag = f'<base href="{base_href}">'
            html = content.decode("utf-8", errors="replace")

            html = re.sub(
                r'''((?:src|href|action)\s*=\s*["'])/(?!/|https?:)''',
                r'\1./',
                html,
                flags=re.IGNORECASE,
            )

            html = re.sub(
                r'''url\(\s*(["']?)/(?!/|https?:)''',
                r'url(\1./',
                html,
                flags=re.IGNORECASE,
            )

            ws_stub = (
                '<script>'
                '(function(){'
                'var _WS=window.WebSocket;'
                'window.WebSocket=function(u,p){'
                'try{var o=new URL(u,location.href);'
                'if(o.hostname===location.hostname){'
                'var f={readyState:3,CONNECTING:0,OPEN:1,CLOSING:2,CLOSED:3,'
                'send:function(){},close:function(){},'
                'addEventListener:function(){},removeEventListener:function(){}};'
                'return f;'
                '}}catch(e){}'
                'return p!==void 0?new _WS(u,p):new _WS(u);'
                '};'
                'window.WebSocket.CONNECTING=0;window.WebSocket.OPEN=1;'
                'window.WebSocket.CLOSING=2;window.WebSocket.CLOSED=3;'
                '})();'
                '</script>'
            )
            inject = ws_stub + base_tag
            if "<head>" in html:
                html = html.replace("<head>", f"<head>{inject}", 1)
            elif "<HEAD>" in html:
                html = html.replace("<HEAD>", f"<HEAD>{inject}", 1)
            elif "<html" in html.lower():
                html = re.sub(r"(<html[^>]*>)", rf"\1<head>{inject}</head>", html, count=1, flags=re.IGNORECASE)
            else:
                html = inject + html

            content = html.encode("utf-8")

        elif "text/css" in content_type and resp.status_code == 200:
            css = content.decode("utf-8", errors="replace")
            css = re.sub(
                r'''url\(\s*(["']?)/(?!/|https?:)''',
                r'url(\1./',
                css,
                flags=re.IGNORECASE,
            )
            content = css.encode("utf-8")

        elif ("javascript" in content_type or "text/javascript" in content_type) and resp.status_code == 200:
            base_href = f"/api/containers/{container_id}/preview/{port}"
            js = content.decode("utf-8", errors="replace")
            js = re.sub(
                r'''((?:from|import\()\s*)(["'])/(?!/|https?:)''',
                rf'\1\2{base_href}/',
                js,
                flags=re.IGNORECASE,
            )
            js = re.sub(
                r'''(\bimport\s+)(["'])/(?!/|https?:)''',
                rf'\1\2{base_href}/',
                js,
            )
            js = re.sub(
                r'''((?:fetch|new\s+URL)\s*\(\s*)(["'])/(?!/|https?:)''',
                rf'\1\2{base_href}/',
                js,
                flags=re.IGNORECASE,
            )
            content = js.encode("utf-8")

        return Response(
            content=content,
            status_code=resp.status_code,
            headers=resp_headers,
            media_type=content_type or None,
        )
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail=f"No service on port {port} in container")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Timeout connecting to port {port}")
