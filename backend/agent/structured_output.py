"""Structured output: making the model answer in a caller-supplied JSON shape.

Implemented as a synthetic tool rather than a provider `response_format`,
following opencode. The reason is reach: every provider that supports tool
calling supports this, while native JSON-schema response formats are supported
by a much smaller set and behave inconsistently across the OpenAI-compatible
gateways people actually deploy behind.

The model is told it must call the tool; the arguments it passes *are* the
answer. Nothing needs parsing out of prose.
"""
from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ConfigDict

from core.log import create_logger
from tool.tool import ToolInfo, ToolResult, define_tool

log = create_logger("agent.structured_output")

TOOL_NAME = "StructuredOutput"

DESCRIPTION = (
    "Use this tool to return your final response in the requested structured "
    "format. Call it once, with your complete answer as the arguments."
)

SYSTEM_PROMPT = (
    "IMPORTANT: The user has requested structured output. You MUST use the "
    f"{TOOL_NAME} tool to provide your final response. Do NOT respond with "
    f"plain text — you MUST call the {TOOL_NAME} tool with your answer "
    "formatted according to the schema."
)


class _Passthrough(BaseModel):
    """Carrier for whatever the caller's schema declares.

    define_tool validates arguments against this before handing them to
    execute(), so it must accept unknown fields — the real shape is only known
    at runtime and is advertised separately via raw_schema. A plain BaseModel
    here would validate cleanly and silently discard the entire answer.
    """

    model_config = ConfigDict(extra="allow")


def requested_schema(message) -> dict | None:
    """The JSON schema a user message is asking for, if any.

    Accepts opencode's shape — {"type": "json_schema", "schema": {...}} — and
    tolerates a bare schema dict, since that is the obvious thing for an API
    client to send.
    """
    fmt = getattr(message, "format", None)
    if not isinstance(fmt, dict):
        return None
    if fmt.get("type") == "json_schema":
        schema = fmt.get("schema")
        return schema if isinstance(schema, dict) else None
    # A bare schema, e.g. {"type": "object", "properties": {...}}
    if fmt.get("type") == "object" and "properties" in fmt:
        return fmt
    return None


def create_structured_output_tool(schema: dict, on_success: Callable[[Any], None]) -> ToolInfo:
    """A tool whose parameters are the caller's schema.

    Arguments are already validated against the schema by the time execute()
    runs, so capturing them is the whole job.
    """
    # $schema is a document-level annotation; providers reject it inside a
    # tool's parameter schema.
    advertised = {k: v for k, v in schema.items() if k != "$schema"}

    async def execute(args, ctx) -> ToolResult:
        payload = args.model_dump() if hasattr(args, "model_dump") else args
        on_success(payload)
        return ToolResult(
            title="Structured Output",
            output="Structured output captured.",
            metadata={"structured": True},
        )

    return define_tool(
        TOOL_NAME,
        description=DESCRIPTION,
        parameters=_Passthrough,
        execute=execute,
        sandbox_required=False,
        never_prune=True,
        raw_schema=advertised,
    )
