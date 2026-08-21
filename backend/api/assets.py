"""Asset uploads: browser → OSS direct transfer, with a DB ledger.

The backend never carries the bytes. It issues a presigned PUT (the browser
uploads straight to OSS), verifies the object landed, and records the upload
in `file_assets`. The cloud desktop later pulls the object with `obx-file`
(sandbox/assets.py) — solving the tunnel-bandwidth problem the old chunked
base64 upload had. 503 here tells the frontend to fall back to that legacy
sandbox upload (e.g. local docker dev without OSS configured).
"""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from auth.middleware import get_current_user
from core.identifier import ascending
from core.oss import OssNotConfigured, get_oss
from db.base import get_db_session
from db.models.file_asset import FileAsset

router = APIRouter(prefix="/api/assets", tags=["assets"], dependencies=[Depends(get_current_user)])

_MAX_SIZE = 512 * 1024 * 1024  # 512 MB; OSS handles it, the tunnel never sees it


class CreateAssetBody(BaseModel):
    name: str
    mime: str = "application/octet-stream"
    size: int = 0
    session_id: str | None = None


def _clean_name(name: str) -> str:
    cleaned = re.sub(r"[^\w.一-鿿-]", "_", name or "file").strip("._") or "file"
    return cleaned[:200]


def _oss_or_503():
    try:
        return get_oss()
    except OssNotConfigured as e:
        raise HTTPException(503, detail=str(e))


@router.post("")
async def create_asset(body: CreateAssetBody, current_user: dict = Depends(get_current_user)):
    """Open an upload: record it and hand the browser a presigned PUT URL."""
    oss = _oss_or_503()
    if body.size > _MAX_SIZE:
        raise HTTPException(413, detail="File too large (max 512 MB)")
    user_id = current_user["user_id"]
    name = _clean_name(body.name)
    asset_id = ascending("asset")
    key = f"assets/{user_id}/{asset_id}/{name}"
    mime = (body.mime or "application/octet-stream")[:128]

    async with get_db_session() as db:
        db.add(
            FileAsset(
                id=asset_id,
                user_id=user_id,
                session_id=body.session_id,
                name=name,
                oss_key=key,
                mime=mime,
                size=body.size,
                status="pending",
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        await db.commit()

    return {
        "id": asset_id,
        "name": name,
        "sandboxPath": f"/workspace/uploads/{name}",
        "putUrl": oss.presign_put(key, mime),
        # The PUT must send exactly what was signed (bossip's hard-won rule).
        "headers": {"Content-Type": mime},
    }


async def _owned_asset(db, asset_id: str, user_id: str) -> FileAsset:
    row = (
        await db.execute(select(FileAsset).where(FileAsset.id == asset_id, FileAsset.user_id == user_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, detail="Asset not found")
    return row


@router.post("/{asset_id}/complete")
async def complete_asset(asset_id: str, current_user: dict = Depends(get_current_user)):
    """Verify the object actually landed in OSS, then mark the record ready."""
    oss = _oss_or_503()
    async with get_db_session() as db:
        row = await _owned_asset(db, asset_id, current_user["user_id"])
        head = await oss.head(row.oss_key)
        if not head:
            raise HTTPException(409, detail="Object not found in OSS — upload did not complete")
        row.size = head["size"] or row.size
        row.status = "ready"
        await db.commit()
        return {
            "id": row.id,
            "name": row.name,
            "mime": row.mime,
            "size": row.size,
            "sandboxPath": f"/workspace/uploads/{row.name}",
            "url": oss.presign_get(row.oss_key),
        }


@router.get("/{asset_id}/url")
async def asset_url(asset_id: str, download: bool = False, current_user: dict = Depends(get_current_user)):
    """Fresh presigned GET for previews (they expire; the UI refetches)."""
    oss = _oss_or_503()
    async with get_db_session() as db:
        row = await _owned_asset(db, asset_id, current_user["user_id"])
        if row.status != "ready":
            raise HTTPException(409, detail="Upload not completed")
        return {
            "url": oss.presign_get(row.oss_key, download_name=row.name if download else None),
            "mime": row.mime,
            "name": row.name,
            "size": row.size,
        }
