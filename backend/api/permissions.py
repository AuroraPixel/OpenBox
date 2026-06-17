"""Permission routes."""
from fastapi import APIRouter, Depends, HTTPException
from auth.middleware import get_current_user
from pydantic import BaseModel

from permission import permission as perm_mod

router = APIRouter(dependencies=[Depends(get_current_user)])


class PermissionReplyBody(BaseModel):
    action: str  # "once", "always", "reject"
    message: str | None = None


@router.get("/permission")
async def list_permissions(current_user: dict = Depends(get_current_user)):
    """List all pending permission requests."""
    user_id = current_user["user_id"]
    return perm_mod.list_pending(user_id=user_id)


@router.post("/permission/{request_id}")
async def reply_permission(
    request_id: str,
    body: PermissionReplyBody,
    current_user: dict = Depends(get_current_user),
):
    """Reply to a permission request."""
    if body.action not in ("once", "always", "reject"):
        raise HTTPException(400, "Invalid action. Must be 'once', 'always', or 'reject'.")

    user_id = current_user["user_id"]
    try:
        await perm_mod.reply(request_id, body.action, body.message, user_id=user_id)
    except KeyError:
        raise HTTPException(404, "Permission request not found")
    except PermissionError:
        raise HTTPException(403, "Permission request does not belong to current user")
    return {"ok": True}
