"""Delivery abstraction layer — dispatch cron results to external channels.

Current: only "none" mode (results stay in DB + inject to session).
Extensible: webhook, channel (Telegram/Slack/Feishu etc.)
"""
from __future__ import annotations

from pydantic import BaseModel

from core.log import create_logger

log = create_logger("cron.delivery")


class DeliveryResult(BaseModel):
    success: bool
    error: str | None = None


async def dispatch_delivery(
    delivery_config: dict,
    job_name: str,
    job_id: str,
    status: str,
    summary_text: str | None,
    duration_ms: int,
) -> DeliveryResult:
    """Dispatch cron result to configured delivery target.

    Currently supports:
    - "none": No external delivery (default)
    - "webhook": HTTP POST to configured URL (future)
    - "channel": Push to messaging channel (future)
    """
    mode = delivery_config.get("mode", "none") if delivery_config else "none"

    if mode == "none":
        return DeliveryResult(success=True)

    if mode == "webhook":
        return await _deliver_webhook(delivery_config, job_name, job_id, status, summary_text, duration_ms)

    if mode == "channel":
        # Future: Telegram, Slack, Feishu, etc.
        log.warning(f"Channel delivery not yet implemented for job {job_id}")
        return DeliveryResult(success=False, error="Channel delivery not implemented")

    return DeliveryResult(success=False, error=f"Unknown delivery mode: {mode}")


async def _deliver_webhook(
    config: dict,
    job_name: str,
    job_id: str,
    status: str,
    summary_text: str | None,
    duration_ms: int,
) -> DeliveryResult:
    """Deliver cron result via HTTP webhook POST."""
    url = config.get("webhook_url")
    if not url:
        return DeliveryResult(success=False, error="No webhook_url configured")

    token = config.get("webhook_token")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    from datetime import datetime, timezone
    payload = {
        "job_id": job_id,
        "job_name": job_name,
        "status": status,
        "summary": summary_text,
        "duration_ms": duration_ms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.is_success:
                return DeliveryResult(success=True)
            else:
                return DeliveryResult(success=False, error=f"Webhook returned {resp.status_code}")
    except Exception as e:
        return DeliveryResult(success=False, error=str(e))
