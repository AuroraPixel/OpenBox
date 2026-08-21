"""Cloud-desktop view: connection tickets for the Wuying Web SDK.

The frontend's 云桌面 tab streams the Wuying desktop through Alibaba's Web SDK,
which needs a one-time connection ticket from ECD ``GetConnectionTicket``.
That call is an async task server-side: the first request may only return a
``taskId`` while Wuying logs the end user onto the desktop, and the ticket
appears once the task reaches FINISHED. We poll within a small budget and
return 202 (with the task id for the next attempt) when it isn't ready yet —
the frontend retries on 202, mirroring the reference integration in bossip.

Credentials come from ALIBABA_CLOUD_ACCESS_KEY_ID/SECRET, falling back to the
aliyun CLI profile (~/.aliyun/config.json) on dev machines.
"""
import asyncio
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from auth.middleware import get_current_user
from core.config import get_config
from core.log import create_logger

log = create_logger("api.desktop")

router = APIRouter(prefix="/api/desktop", tags=["desktop"], dependencies=[Depends(get_current_user)])

_POLL_INTERVAL = 2.0
_POLL_BUDGET = 14.0  # keep well under typical proxy/request timeouts


class _CredentialsError(Exception):
    pass


def _load_credentials() -> dict:
    key_id = (os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID") or os.environ.get("ALICLOUD_ACCESS_KEY_ID") or "").strip()
    key_secret = (
        os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET") or os.environ.get("ALICLOUD_ACCESS_KEY_SECRET") or ""
    ).strip()
    if key_id and key_secret:
        return {"access_key_id": key_id, "access_key_secret": key_secret}

    config_path = Path(os.environ.get("ALIYUN_CLI_CONFIG") or Path.home() / ".aliyun" / "config.json")
    try:
        parsed = json.loads(config_path.read_text())
    except FileNotFoundError:
        raise _CredentialsError("No Alibaba Cloud credentials (env or aliyun CLI profile)")
    profiles = parsed.get("profiles") or []
    wanted = os.environ.get("ALIBABA_CLOUD_PROFILE") or parsed.get("current") or "default"
    profile = next((p for p in profiles if p.get("name") == wanted), None)
    if not profile or not profile.get("access_key_id") or not profile.get("access_key_secret"):
        raise _CredentialsError(f"aliyun CLI profile '{wanted}' has no usable access key")
    creds = {"access_key_id": profile["access_key_id"], "access_key_secret": profile["access_key_secret"]}
    if profile.get("sts_token"):
        creds["security_token"] = profile["sts_token"]
    return creds


def _ecd_client(region_id: str):
    from alibabacloud_ecd20200930.client import Client
    from alibabacloud_tea_openapi import models as open_api_models

    creds = _load_credentials()
    config = open_api_models.Config(
        access_key_id=creds["access_key_id"],
        access_key_secret=creds["access_key_secret"],
        security_token=creds.get("security_token"),
        endpoint=f"ecd.{region_id}.aliyuncs.com",
        region_id=region_id,
    )
    return Client(config)


@router.get("/ticket")
async def desktop_ticket(task_id: str | None = None):
    """One-time Wuying connection ticket for the current sandbox desktop.

    202 + {taskId} while the desktop session is still being prepared; the
    client retries with that task id. The response carries the desktop and
    region only because the Web SDK's connect payload needs them — the UI
    never renders them.
    """
    config = get_config()
    if config.sandbox_provider != "wuying" or not config.wuying_desktop_id:
        return JSONResponse({"available": False, "reason": "provider"}, status_code=503)
    if not config.wuying_end_user_id:
        return JSONResponse({"available": False, "reason": "no_end_user"}, status_code=503)

    from alibabacloud_ecd20200930 import models as ecd_models

    region = config.wuying_region_id
    try:
        client = _ecd_client(region)
    except _CredentialsError as e:
        log.warning(f"Desktop ticket unavailable: {e}")
        return JSONResponse({"available": False, "reason": "credentials"}, status_code=503)

    deadline = asyncio.get_event_loop().time() + _POLL_BUDGET
    current_task = (task_id or "").strip() or None
    while True:
        try:
            resp = await client.get_connection_ticket_async(
                ecd_models.GetConnectionTicketRequest(
                    desktop_id=config.wuying_desktop_id,
                    end_user_id=config.wuying_end_user_id,
                    region_id=region,
                    task_id=current_task,
                )
            )
        except Exception as e:
            # Transient network wobble inside the budget keeps polling; a
            # hard API error is the caller's 502.
            message = str(e)
            if any(x in message for x in ("ConnectTimeout", "timed out", "ECONNRESET", "Connection reset")):
                if asyncio.get_event_loop().time() + _POLL_INTERVAL > deadline:
                    return JSONResponse(
                        {"pending": True, "taskId": current_task},
                        status_code=202,
                        headers={"Retry-After": "3"},
                    )
                await asyncio.sleep(_POLL_INTERVAL)
                continue
            log.warning(f"GetConnectionTicket failed: {message}")
            return JSONResponse({"available": False, "reason": "api_error"}, status_code=502)

        body = resp.body
        ticket = (body.ticket or "").strip() if body else ""
        current_task = (body.task_id or "").strip() or current_task if body else current_task
        status = (body.task_status or "").strip() if body else ""

        if ticket:
            return {
                "ticket": ticket,
                "desktopId": config.wuying_desktop_id,
                "regionId": region,
            }
        if status == "FAILED":
            log.warning(f"GetConnectionTicket task failed: {body.task_message if body else ''}")
            return JSONResponse({"available": False, "reason": "task_failed"}, status_code=502)
        if asyncio.get_event_loop().time() + _POLL_INTERVAL > deadline:
            return JSONResponse(
                {"pending": True, "taskId": current_task},
                status_code=202,
                headers={"Retry-After": "3"},
            )
        await asyncio.sleep(_POLL_INTERVAL)
