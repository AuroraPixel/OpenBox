import base64
import re

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from auth.middleware import get_current_user
from sandbox import provider
from models.container import ListFilesRequest

_UPLOAD_MAX_BYTES = 8 * 1024 * 1024
_UPLOAD_CHUNK = 48 * 1024  # keeps each base64 shell command well under ARG_MAX

router = APIRouter(
    prefix="/api/containers/{container_id}/files",
    tags=["files"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/list")
async def list_files(
    container_id: str,
    req: ListFilesRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        resp = await provider.forward_to_container(
            container_id, "POST", "/list_files", user_id=current_user["user_id"], json=req.model_dump()
        )
        return resp.json()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_file(
    container_id: str,
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
):
    """Upload one attachment into the sandbox (frontend-v2 composer).

    Lands in /workspace/uploads/<name> via chunked base64 through the
    container's /execute — the action server has no binary endpoint.
    """
    raw = await file.read()
    if len(raw) > _UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 8 MB)")

    name = re.sub(r"[^\w.一-鿿-]", "_", file.filename or "file")
    dest = f"/workspace/uploads/{name}"

    async def run(cmd: str):
        resp = await provider.forward_to_container(
            container_id, "POST", "/execute",
            user_id=current_user["user_id"],
            json={"command": cmd, "timeout": 30},
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        data = resp.json()
        if data.get("exit_code") not in (0, None):
            raise HTTPException(status_code=500, detail=data.get("stderr") or "upload failed")

    try:
        await run(f"mkdir -p /workspace/uploads && : > '{dest}'")
        for i in range(0, len(raw), _UPLOAD_CHUNK):
            b64 = base64.b64encode(raw[i : i + _UPLOAD_CHUNK]).decode()
            await run(f"printf %s {b64} | base64 -d >> '{dest}'")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"path": dest, "name": name, "size": len(raw)}


@router.get("/search")
async def search_files(
    container_id: str,
    q: str = "",
    limit: int = 30,
    path: str = "/workspace",
    current_user: dict = Depends(get_current_user),
):
    """Fuzzy file lookup for the composer's @-mention menu.

    Globs the sandbox once and filters by substring here — the action server
    has no search endpoint, and a single glob is cheaper than walking /list.
    """
    try:
        resp = await provider.forward_to_container(
            container_id, "POST", "/glob",
            user_id=current_user["user_id"],
            json={"pattern": "**/*", "path": path},
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        data = resp.json()
        files = data.get("files") or data.get("matches") or []
        if isinstance(files, dict):
            files = files.get("files", [])
        needle = q.strip().lower()
        hits = [f for f in files if not needle or needle in str(f).lower()]
        hits = [f for f in hits if "/node_modules/" not in f and "/.git/" not in f]
        return {"files": hits[:limit], "total": len(hits)}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/content")
async def file_content(
    container_id: str,
    path: str,
    current_user: dict = Depends(get_current_user),
):
    """Raw file content for the workbench file viewer (frontend-v2).

    The container's /read_file returns cat -n numbered lines; strip the
    numbering here so the viewer gets the file as-is.
    """
    try:
        resp = await provider.forward_to_container(
            container_id, "POST", "/read_file",
            user_id=current_user["user_id"],
            json={"path": path, "offset": 0, "limit": 5000},
        )
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"File not found: {path}")
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        data = resp.json()
        numbered = data.get("content", "")
        raw = "\n".join(
            line.split("\t", 1)[1] if "\t" in line else line
            for line in numbered.split("\n")
        )
        total = data.get("total_lines") or 0
        end = data.get("end_line") or 0
        return {"path": path, "content": raw, "total_lines": total, "truncated": end < total}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system_info")
async def system_info(container_id: str, current_user: dict = Depends(get_current_user)):
    try:
        resp = await provider.forward_to_container(
            container_id, "GET", "/system_info", user_id=current_user["user_id"]
        )
        return resp.json()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
