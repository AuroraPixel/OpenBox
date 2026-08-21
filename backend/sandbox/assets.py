"""Deliver OSS assets into the sandbox — and the `obx-file` tool that does it.

Attachment bytes go browser → OSS → sandbox: the desktop pulls straight from
OSS over Alibaba's network, so nothing streams through the backend or the
SSH tunnel. The puller is `obx-file`, a small system-level CLI this module
installs into the sandbox (so the agent can also run it by hand in the
terminal, grep-style):

    obx-file get <presigned-url> <dest>   # OSS → sandbox
    obx-file put <src> <presigned-url>    # sandbox → OSS (empty-CT signing)
"""
import base64
import shlex

from core.log import create_logger
from core.oss import OssClient

log = create_logger("sandbox.assets")

UPLOAD_DIR = "/workspace/uploads"

OBX_FILE_SCRIPT = """#!/bin/sh
# obx-file - move files between OSS and this sandbox via presigned URLs.
#   obx-file get <url> <dest>
#   obx-file put <src> <url> [content-type]
# The content-type must match what the URL was signed with: empty when
# omitted, exactly the given value otherwise.
set -e
case "$1" in
  get)
    [ -n "$2" ] && [ -n "$3" ] || { echo "usage: obx-file get <url> <dest>" >&2; exit 2; }
    mkdir -p "$(dirname "$3")"
    curl -fsSL --retry 3 --retry-delay 1 -o "$3" "$2"
    ;;
  put)
    [ -f "$2" ] || { echo "no such file: $2" >&2; exit 2; }
    [ -n "$3" ] || { echo "usage: obx-file put <src> <url> [content-type]" >&2; exit 2; }
    curl -fsSL --retry 3 --retry-delay 1 -X PUT -H "Content-Type:${4:+ $4}" --upload-file "$2" "$3"
    ;;
  *)
    echo "usage: obx-file get <url> <dest> | obx-file put <src> <url> [content-type]" >&2
    exit 2
    ;;
esac
"""

#: Container ids that already have the tool this process lifetime.
_installed: set[str] = set()


async def ensure_cli(client, container_key: str) -> None:
    """Install obx-file into the sandbox (idempotent, cached per container).

    /usr/local/bin when passwordless sudo allows it, else ~/.local/bin; the
    caller runs it through `PATH="$HOME/.local/bin:$PATH"` so both work.
    """
    if container_key in _installed:
        return
    b64 = base64.b64encode(OBX_FILE_SCRIPT.encode()).decode()
    cmd = (
        f"printf %s {b64} | base64 -d > /tmp/.obx-file && chmod +x /tmp/.obx-file && "
        "(sudo -n install -m755 /tmp/.obx-file /usr/local/bin/obx-file 2>/dev/null || "
        '(mkdir -p "$HOME/.local/bin" && install -m755 /tmp/.obx-file "$HOME/.local/bin/obx-file"))'
    )
    result = await client.execute(cmd, timeout=30)
    if result.exit_code != 0:
        raise RuntimeError(f"obx-file install failed: {result.stderr[:200]}")
    _installed.add(container_key)


async def deliver(client, container_key: str, oss: OssClient, assets: list) -> list[str]:
    """Pull each ready asset into /workspace/uploads. Returns landed paths.

    A failed download is logged and skipped — the agent still gets the other
    files plus the message text, which beats failing the whole prompt.
    """
    await ensure_cli(client, container_key)
    landed: list[str] = []
    for asset in assets:
        url = oss.presign_get(asset.oss_key, expires_sec=1800)
        dest = f"{UPLOAD_DIR}/{asset.name}"
        cmd = f'PATH="$HOME/.local/bin:$PATH" obx-file get {shlex.quote(url)} {shlex.quote(dest)}'
        try:
            result = await client.execute(cmd, timeout=120)
            if result.exit_code == 0:
                landed.append(dest)
            else:
                log.warning(f"Asset {asset.id} download failed: {result.stderr[:200]}")
        except Exception as e:
            log.warning(f"Asset {asset.id} download failed: {e}")
    return landed


async def attach_sandbox_image(
    ctx, path: str, mime: str, size: int, name: str | None = None, transient: bool = False
) -> tuple[str, int]:
    """Push a sandbox image to OSS and pin a file part on the current message.

    Shared by view_image and the computer tool's screenshot: the model runs
    in the backend, so the only way it sees a picture that lives on the cloud
    desktop is to move it to OSS (no tunnel bytes) and hand back a presigned
    URL, which loop._to_llm_messages turns into real image content next turn.

    Returns (asset_id, verified_size). Raises RuntimeError on any failure —
    callers translate that into a ToolResult error.
    """
    from datetime import datetime, timezone
    from core.identifier import ascending
    from core.oss import get_oss
    from db.base import get_db_session
    from db.models.file_asset import FileAsset
    from models.message import FilePart
    from session.session import save_part

    oss = get_oss()
    obj_name = name or path.split("/")[-1]
    asset_id = ascending("asset")
    key = f"assets/{ctx.user_id}/{asset_id}/{obj_name}"

    # Keyed by the machine, not the conversation: obx-file is a property of
    # the container, so a new chat must not reinstall it.
    await ensure_cli(ctx.sandbox, getattr(ctx.sandbox, "base_url", "") or ctx.session_id)
    put_url = oss.presign_put(key, mime, expires_sec=600)
    push = await ctx.sandbox.execute(
        f'PATH="$HOME/.local/bin:$PATH" obx-file put {shlex.quote(path)} {shlex.quote(put_url)} {shlex.quote(mime)}',
        timeout=120,
    )
    if push.exit_code != 0:
        raise RuntimeError(push.stderr.strip()[:300] or "obx-file put failed")
    head = await oss.head(key)
    if not head:
        raise RuntimeError("Object missing in OSS after upload")
    verified = head["size"] or size

    async with get_db_session() as db:
        db.add(
            FileAsset(
                id=asset_id,
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                name=obj_name,
                oss_key=key,
                mime=mime,
                size=verified,
                status="ready",
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        await db.commit()

    await save_part(
        FilePart(
            id=ascending("part"),
            path=path,
            mime_type=mime,
            asset_id=asset_id,
            oss_key=key,
            size=verified,
            transient=transient,
            session_id=ctx.session_id,
            message_id=ctx.message_id,
        ),
        is_new=True,
        user_id=ctx.user_id,
    )
    return asset_id, verified
