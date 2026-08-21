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

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from auth.middleware import get_current_user
from core.aliyun import AliyunCredentialsError, load_credentials
from core.config import get_config
from core.log import create_logger

log = create_logger("api.desktop")

router = APIRouter(prefix="/api/desktop", tags=["desktop"], dependencies=[Depends(get_current_user)])

_POLL_INTERVAL = 2.0
_POLL_BUDGET = 14.0  # keep well under typical proxy/request timeouts


def _ecd_client(region_id: str):
    from alibabacloud_ecd20200930.client import Client
    from alibabacloud_tea_openapi import models as open_api_models

    creds = load_credentials()
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
    except AliyunCredentialsError as e:
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
