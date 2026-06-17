from fastapi import APIRouter, Depends, HTTPException

from auth.middleware import get_current_user
from sandbox import provider
from models.container import ListFilesRequest

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
