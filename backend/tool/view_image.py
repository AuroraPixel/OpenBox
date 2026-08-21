"""view_image: let the model actually SEE an image from the sandbox.

The model runs in the backend; a screenshot or chart produced on the cloud
desktop is just a path to it. This tool pushes the file desktop → OSS with
`obx-file put` (no tunnel bytes), records it in file_assets, pins a file part
on the assistant message (the chat renders a preview card), and marks the
tool part so the next LLM call carries the image as real multimodal content
(see loop._to_llm_messages).
"""
import shlex
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from core.identifier import ascending
from core.log import create_logger
from tool.tool import ToolResult, ToolContext, define_tool

log = create_logger("tool.view_image")

_MAX_BYTES = 10 * 1024 * 1024
_IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


class ViewImageArgs(BaseModel):
    file_path: str = Field(description="Absolute path to the image file in the workspace")


async def execute(args: ViewImageArgs, ctx: ToolContext) -> ToolResult:
    from core.oss import OssNotConfigured, get_oss
    from sandbox.assets import attach_sandbox_image

    path = args.file_path
    if not path.startswith("/"):
        path = f"{ctx.workdir.rstrip('/')}/{path}"

    try:
        oss = get_oss()
    except OssNotConfigured as e:
        return ToolResult(title="view_image unavailable", output=f"OSS transfer is not configured: {e}")

    probe = await ctx.sandbox.execute(
        f"stat -c %s {shlex.quote(path)} && file --brief --mime-type {shlex.quote(path)}", timeout=15
    )
    if probe.exit_code != 0:
        return ToolResult(title=f"Cannot read {path}", output=probe.stderr.strip() or "No such file")
    lines = probe.stdout.strip().splitlines()
    size = int(lines[0]) if lines and lines[0].isdigit() else 0
    mime = lines[1].strip() if len(lines) > 1 else ""
    if mime not in _IMAGE_MIMES:
        return ToolResult(
            title=f"Not a viewable image: {path}",
            output=f"Detected type {mime or 'unknown'}; supported: {', '.join(sorted(_IMAGE_MIMES))}",
        )
    if size > _MAX_BYTES:
        return ToolResult(title=f"Image too large: {path}", output=f"{size} bytes (max {_MAX_BYTES})")

    name = path.split("/")[-1]
    try:
        asset_id, verified = await attach_sandbox_image(ctx, path, mime, size, name=name)
    except Exception as e:
        return ToolResult(title=f"Upload failed: {path}", output=str(e)[:300])

    return ToolResult(
        title=name,
        output=f"Image attached for viewing: {path} ({mime}, {size} bytes). It will be visible in your next turn.",
        metadata={"asset_id": asset_id, "mime": mime, "path": path, "size": verified},
    )


VIEW_IMAGE_DESCRIPTION = """\
Look at an image file from the workspace (screenshot, rendered chart, photo, \
downloaded picture). The image is attached to the conversation so you can \
actually see its pixels in your next turn — reading image bytes with the read \
tool does NOT work. Use after taking a screenshot or generating an image to \
verify it. Supports png/jpeg/gif/webp up to 10 MB."""

view_image_tool = define_tool(
    "view_image",
    description=VIEW_IMAGE_DESCRIPTION,
    parameters=ViewImageArgs,
    execute=execute,
)
