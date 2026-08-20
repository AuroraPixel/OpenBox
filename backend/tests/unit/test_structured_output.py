"""Structured output: the synthetic tool that carries a schema-shaped answer.

Implemented as a tool rather than a provider response_format so it works on any
provider that can call tools. The tool's arguments *are* the answer, which puts
all the risk in one place: anything that filters those arguments silently
discards the whole result.
"""
import asyncio

import pytest

from agent.structured_output import (
    TOOL_NAME,
    create_structured_output_tool,
    requested_schema,
)

SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "count": {"type": "integer"}},
    "required": ["name"],
}


class Msg:
    def __init__(self, fmt=None):
        self.format = fmt


# ── recognising the request ──

def test_opencode_shape_is_recognised():
    assert requested_schema(Msg({"type": "json_schema", "schema": SCHEMA})) == SCHEMA


def test_bare_schema_is_accepted():
    """The obvious thing for an API client to send."""
    assert requested_schema(Msg(SCHEMA)) == SCHEMA


@pytest.mark.parametrize("fmt", [
    None,
    "text",                                   # the legacy string column
    {"type": "text"},
    {"type": "json_schema"},                  # no schema
    {"type": "json_schema", "schema": "nope"},  # not a dict
])
def test_non_requests_return_none(fmt):
    assert requested_schema(Msg(fmt)) is None


def test_message_without_a_format_attribute():
    class Bare:
        pass

    assert requested_schema(Bare()) is None


# ── the tool ──

def test_tool_advertises_the_callers_schema():
    tool = create_structured_output_tool(SCHEMA, lambda v: None)
    assert tool.id == TOOL_NAME
    assert tool.raw_schema == SCHEMA


def test_document_level_schema_key_is_stripped():
    """Providers reject $schema inside a tool's parameter schema."""
    tool = create_structured_output_tool({"$schema": "http://json-schema.org/draft-07/schema#", **SCHEMA},
                                         lambda v: None)
    assert "$schema" not in tool.raw_schema
    assert tool.raw_schema["properties"] == SCHEMA["properties"]


def test_tool_needs_no_sandbox():
    assert create_structured_output_tool(SCHEMA, lambda v: None).sandbox_required is False


def test_output_is_never_pruned():
    """The captured answer must survive context trimming."""
    assert create_structured_output_tool(SCHEMA, lambda v: None).never_prune is True


# ── capture ──

def test_arguments_reach_the_callback_intact():
    """The regression this guards: validating against a field-less model
    accepts the call and silently discards every field, so the run finishes
    'successfully' with an empty answer."""
    captured = {}
    tool = create_structured_output_tool(SCHEMA, lambda v: captured.update(v))
    asyncio.run(tool.execute({"name": "openbox", "count": 3}, None))
    assert captured == {"name": "openbox", "count": 3}


def test_types_survive_the_round_trip():
    captured = {}
    tool = create_structured_output_tool(SCHEMA, lambda v: captured.update(v))
    asyncio.run(tool.execute({"name": "x", "count": 42}, None))
    assert captured["count"] == 42 and isinstance(captured["count"], int)


def test_nested_values_survive():
    captured = {}
    tool = create_structured_output_tool(
        {"type": "object", "properties": {"items": {"type": "array"}}},
        lambda v: captured.update(v),
    )
    payload = {"items": [{"a": 1}, {"b": [2, 3]}]}
    asyncio.run(tool.execute(payload, None))
    assert captured == payload


def test_execute_reports_success_to_the_model():
    tool = create_structured_output_tool(SCHEMA, lambda v: None)
    result = asyncio.run(tool.execute({"name": "x"}, None))
    assert result.metadata.get("structured") is True
    assert result.output
