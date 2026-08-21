"""LLM integration using Pydantic AI + LiteLLM."""
from __future__ import annotations

import asyncio
import hashlib as _hashlib
import json as _json
import re as _re
from typing import Any, AsyncIterator

from agent.agent import AgentDef
from tool.tool import ToolContext, ToolInfo
from core.log import create_logger

log = create_logger("agent.llm")

OUTPUT_TOKEN_MAX = 32000  # Fallback for unknown models

#: Room left for the visible answer once a thinking budget is reserved out of
#: the same allowance. Anthropic requires max_tokens > thinking.budget_tokens.
THINKING_OUTPUT_RESERVE = 8000


#: What the Responses API actually accepts for an item id: `fc_`, then up to 61
#: more characters, the last of which must be alphanumeric. Total length 4..64.
#:
#: This is a POSITIVE pattern on purpose. The rules were previously enumerated
#: as "not too long" and then "no illegal characters", and each time a
#: conversation that had changed providers found a third rule we had not
#: listed. The API's own error message is no help — a trailing underscore is
#: reported as "Expected an ID that contains letters, numbers, underscores, or
#: dashes, but this value contained additional characters", which describes a
#: charset violation the value does not have. The rule below was established by
#: probing the API directly (see tests): `fc_abcDEF_` is rejected while
#: `fc_abcDEF-`, `fc__abcDEF` and `fc_abcDEF` are all accepted.
#:
#: Anything that does not match is replaced wholesale rather than repaired, so
#: a rule we still have not discovered cannot slip through.
_FC_ID_OK = _re.compile(r"fc_[A-Za-z0-9_-]{0,60}[A-Za-z0-9]")


def ensure_fc_id(raw_id: str) -> str:
    """A stable, Responses-API-legal id for a function call.

    Must be a pure function of `raw_id`: the same call reaches this twice —
    once as the assistant's `function_call` and once as its
    `function_call_output` — and the API pairs the two by id. Hashing keeps
    that pairing intact where truncation would collide, since ids from a
    provider that packs a signature into them share long common prefixes.

    The hashed form is `fc_` + 32 hex characters, which satisfies the pattern
    by construction: hex digits are alphanumeric, so it can never end on a
    separator, and 35 characters is well inside the limit.
    """
    fc_id = raw_id if raw_id.startswith("fc_") else f"fc_{raw_id.replace('call_', '')}"
    if _FC_ID_OK.fullmatch(fc_id):
        return fc_id
    return f"fc_{_hashlib.sha256(raw_id.encode()).hexdigest()[:32]}"


def build_responses_input(messages: list[dict], system: list[str] | None = None) -> list[dict]:
    """Convert internal chat history into OpenAI Responses API input items.

    Module-level and pure so it can be tested against directly. It used to live
    inside `_stream_responses_api`, which meant the only way to cover it was to
    re-implement it in the test file — and a test that mirrors the code it
    checks stays green while the real thing drifts. That is exactly how the
    trailing-underscore id bug shipped.

    Every id is re-derived through `ensure_fc_id` rather than trusted: history
    recorded under another provider carries that provider's ids, and Gemini
    packs an encrypted thought signature into them.
    """
    items: list[dict] = []
    if system:
        items.append({"role": "system", "content": "\n\n".join(system)})

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "tool":
            items.append({
                "type": "function_call_output",
                "call_id": ensure_fc_id(msg.get("tool_call_id", "")),
                "output": content if isinstance(content, str) else _json.dumps(content),
            })
            continue

        if role == "assistant" and msg.get("tool_calls"):
            # A turn that said something *and* then called a tool arrives as one
            # message carrying both. Emitting only the calls drops the model's
            # own stated reasoning from the replayed context — silently, since
            # nothing rejects a shorter history. Narration first, in the order
            # it was produced.
            if isinstance(content, str) and content.strip():
                items.append({"role": "assistant", "content": content})
            for tc in msg["tool_calls"]:
                fc_id = ensure_fc_id(tc.get("id", ""))
                items.append({
                    "type": "function_call",
                    "id": fc_id,
                    "call_id": fc_id,
                    "name": tc.get("function", {}).get("name", ""),
                    "arguments": tc.get("function", {}).get("arguments", "{}"),
                })
            continue

        # The Responses API image form differs from Chat Completions.
        images = [u for u in (msg.get("_images") or []) if isinstance(u, str)]
        if role == "user" and images:
            parts: list[dict] = []
            if isinstance(content, str) and content:
                parts.append({"type": "input_text", "text": content})
            parts.extend({"type": "input_image", "image_url": u} for u in images)
            items.append({"role": role, "content": parts})
        else:
            items.append({"role": role, "content": content})

    return items


def _get_max_output_tokens(model_id: str) -> int:
    """Return the max_output_tokens for a model.

    GPT-5.4 / GPT-5.2: 128K output tokens, 1M+ context window
    GPT-5 / GPT-5-mini: 64K output tokens
    Other models: 32K default
    """
    model_lower = model_id.lower()
    if any(x in model_lower for x in ("gpt-5.4", "gpt-5.2", "gpt-5-pro", "gpt-5.2-pro", "gpt-5.4-pro")):
        return 128_000
    if any(x in model_lower for x in ("gpt-5", "gpt-5-mini", "gpt-5-nano")):
        return 64_000
    return OUTPUT_TOKEN_MAX


def _get_provider_kwargs(model_id: str) -> dict:
    """Extract provider-specific kwargs (api_key, api_base) from config.

    Matches provider by model_id prefix (e.g., "openai/gpt-4o" -> "openai").
    LiteLLM accepts api_key and api_base as kwargs to acompletion().
    """
    try:
        from core.config import get_config
        config = get_config()
    except Exception:
        return {}

    if not config.provider:
        return {}

    # Detect provider name from model_id: "provider/model" or "provider"
    provider_name = model_id.split("/")[0] if "/" in model_id else model_id

    provider_cfg = config.provider.get(provider_name)
    if not provider_cfg:
        return {}

    kwargs: dict = {}
    if provider_cfg.api_key:
        kwargs["api_key"] = provider_cfg.api_key
    if provider_cfg.base_url:
        kwargs["api_base"] = provider_cfg.base_url
    # Pass through any extra options
    if provider_cfg.options:
        kwargs.update(provider_cfg.options)

    return kwargs


def _repair_tool_name(tool_name: str, available_tools: dict[str, ToolInfo]) -> str | None:
    """Repair a misnamed tool call (matching opencode's experimental_repairToolCall).

    Tries case-insensitive matching first, returns None if not repairable.
    """
    if tool_name in available_tools:
        return tool_name

    lower = tool_name.lower()
    if lower != tool_name and lower in available_tools:
        log.info(f"Repairing tool call: {tool_name} -> {lower}")
        return lower

    return None


def _inline_refs(schema: dict) -> dict:
    """Inline $ref/$defs in a JSON Schema so all providers can handle it.

    Pydantic v2's model_json_schema() emits $defs + $ref for nested models.
    Some OpenAI-compatible proxies don't support $ref — inline them.
    Also strips Pydantic's 'title' keys and simplifies anyOf nullables.
    """
    defs = schema.pop("$defs", None) or schema.pop("definitions", None)
    if not defs:
        return _simplify_schema(_strip_titles(schema))

    import json
    raw = json.dumps(schema)
    changed = True
    # Iteratively resolve refs (handles nested refs)
    while changed:
        changed = False
        for name, definition in defs.items():
            ref = f'"$ref": "#/$defs/{name}"'
            if ref in raw:
                raw = raw.replace(ref, json.dumps(definition)[1:-1])  # strip outer {}
                changed = True
            ref_alt = f'"$ref": "#/definitions/{name}"'
            if ref_alt in raw:
                raw = raw.replace(ref_alt, json.dumps(definition)[1:-1])
                changed = True

    result = json.loads(raw)
    result.pop("$defs", None)
    result.pop("definitions", None)
    # Remove title keys that Pydantic adds (not part of OpenAI spec)
    return _simplify_schema(_strip_titles(result))


def _strip_titles(obj: Any) -> Any:
    """Remove 'title' keys from a JSON Schema (Pydantic adds these)."""
    if isinstance(obj, dict):
        return {k: _strip_titles(v) for k, v in obj.items() if k != "title"}
    if isinstance(obj, list):
        return [_strip_titles(v) for v in obj]
    return obj


def _simplify_schema(schema: dict) -> dict:
    """Simplify JSON Schema for maximum provider compatibility.

    - Converts anyOf nullable patterns (e.g., anyOf: [{type: string}, {type: null}])
      to simple {type: string} since OpenAI function calling doesn't support anyOf well.
    - Removes 'default': null for nullable fields (keep other defaults).
    """
    if not isinstance(schema, dict):
        return schema

    result = {}
    for key, value in schema.items():
        if key == "anyOf" and isinstance(value, list):
            # Check if this is a nullable pattern: [{type: X}, {type: null}]
            non_null = [v for v in value if not (isinstance(v, dict) and v.get("type") == "null")]
            if len(non_null) == 1 and isinstance(non_null[0], dict):
                # Replace anyOf with the non-null type
                for nk, nv in non_null[0].items():
                    result[nk] = _simplify_schema(nv) if isinstance(nv, (dict, list)) else nv
                continue
        if key == "default" and value is None:
            # Skip null defaults — just make the field optional via not being in 'required'
            continue
        if isinstance(value, dict):
            result[key] = _simplify_schema(value)
        elif isinstance(value, list):
            result[key] = [_simplify_schema(v) if isinstance(v, dict) else v for v in value]
        else:
            result[key] = value
    return result


def _detect_provider(model_id: str) -> str:
    """Detect the LLM provider from model_id prefix.

    Returns 'openai', 'anthropic', 'gemini', 'deepseek', etc.
    For models accessed via OpenAI-compatible proxy (openai/claude-*),
    returns 'openai' so we use OpenAI-compatible parameters.
    """
    prefix = model_id.split("/")[0].lower() if "/" in model_id else ""
    if prefix in ("openai", "azure"):
        return "openai"
    if prefix in ("anthropic",):
        return "anthropic"
    if prefix in ("gemini", "google", "vertex_ai", "vertexai"):
        return "gemini"
    if prefix in ("deepseek",):
        return "deepseek"
    # No prefix — infer from model name
    model_lower = model_id.lower()
    if "claude" in model_lower:
        return "anthropic"
    if "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
        return "openai"
    if "gemini" in model_lower:
        return "gemini"
    if "deepseek" in model_lower:
        return "deepseek"
    return "unknown"


def _is_thinking_model(model_id: str) -> bool:
    """Check if a model is a thinking/reasoning model."""
    model_lower = model_id.lower()
    return any(x in model_lower for x in (
        "opus-4-6", "opus-4.6", "sonnet-4-6", "sonnet-4.6",  # Claude 4.6
        "opus-4", "sonnet-4",  # Claude 4
        "gpt-5",  # GPT-5 family
        "o1", "o3",  # OpenAI reasoning models
        # Note: Kimi K2.x has built-in reasoning but does NOT accept reasoning_effort param.
        # It is handled as a regular model — reasoning_content comes in stream deltas automatically.
    ))


def _get_default_thinking_kwargs(model_id: str) -> dict:
    """Return default thinking/reasoning parameters for thinking-capable models.

    Called when no explicit variant is selected. Matches opencode's
    ProviderTransform.options() — enables thinking by default for models
    that support it.

    IMPORTANT: The provider prefix (openai/, anthropic/) determines which
    parameter format to use. Models accessed via OpenAI-compatible proxy
    (e.g., openai/claude-opus-4-6) use reasoning_effort, not thinking.
    """
    provider = _detect_provider(model_id)
    model_lower = model_id.lower()

    if provider == "openai":
        # Gemini via proxy: the proxy accepts the Anthropic-style thinking
        # param and maps it to thinkingConfig with includeThoughts, so thought
        # summaries stream back as reasoning_content. reasoning_effort alone
        # does NOT bring thoughts back (verified against the live proxy).
        if "gemini" in model_lower:
            return {"thinking": {"type": "enabled", "budget_tokens": 16000}}
        # Claude 4.6 via proxy: enable reasoning
        if any(x in model_lower for x in ("opus-4-6", "opus-4.6", "sonnet-4-6", "sonnet-4.6")):
            return {"reasoning_effort": "medium"}
        # GPT-5.4 / 5.2 / 5.1: default reasoning is "none" per OpenAI docs
        if any(x in model_lower for x in ("gpt-5.4", "gpt-5.2", "gpt-5.1")):
            return {"reasoning_effort": "none"}
        # GPT-5 / 5-mini / 5-nano: default reasoning is "medium"
        if "gpt-5" in model_lower and "gpt-5-pro" not in model_lower and "gpt-5-chat" not in model_lower:
            return {"reasoning_effort": "medium"}
        # o1/o3 models
        if any(x in model_lower for x in ("o1", "o3")):
            return {"reasoning_effort": "medium"}
        return {}

    if provider == "anthropic":
        # Native Anthropic API: use thinking parameter
        if any(x in model_lower for x in ("opus-4-6", "opus-4.6", "sonnet-4-6", "sonnet-4.6")):
            return {"thinking": {"type": "adaptive"}}
        return {}

    if provider == "gemini":
        return {"thinking": {"type": "enabled", "budget_tokens": 16000}}

    if provider == "deepseek":
        return {"reasoning_effort": "medium"}

    return {}


def _get_variant_kwargs(model_id: str, variant: str | None) -> dict:
    """Map variant to provider-specific LLM parameters.

    Supported variant values per model family:
    - GPT-5.4:   none (default), low, medium, high, xhigh
    - GPT-5.2:   none (default), low, medium, high, xhigh
    - GPT-5:     minimal, low, medium (default), high
    - GPT-5-pro: high only
    - Claude:    low, medium, high, max → thinking budget
    - Gemini:    low, medium, high → thinking budget

    When no variant is selected, falls back to _get_default_thinking_kwargs().
    The "max" variant maps to "xhigh" for GPT-5.4/5.2.
    """
    if not variant:
        return _get_default_thinking_kwargs(model_id)

    provider = _detect_provider(model_id)
    model_lower = model_id.lower()

    if provider == "openai":
        # Gemini via proxy: thinking budget, same shape as the default kwargs.
        if "gemini" in model_lower:
            budget = {"low": 4096, "medium": 16000, "high": 24576}.get(variant)
            if budget:
                return {"thinking": {"type": "enabled", "budget_tokens": budget}}
            return {}
        # A variant is chosen for one model and survives a switch to another —
        # it rides on the message, not the model — so it has to be clamped to
        # what THIS family accepts rather than forwarded verbatim. Only 5.4 and
        # 5.2 know "xhigh"; plain GPT-5 rejects both "max" and "xhigh".
        wide = any(x in model_lower for x in ("gpt-5.4", "gpt-5.2"))
        effort = {"max": "xhigh" if wide else "high"}.get(variant, variant)
        if not wide and effort == "xhigh":
            effort = "high"
        if effort not in ("minimal", "none", "low", "medium", "high", "xhigh"):
            log.debug(f"dropping unusable reasoning effort {variant!r} for {model_id}")
            return {}
        return {"reasoning_effort": effort}

    if provider == "anthropic":
        # Native Anthropic API: use thinking parameter
        if any(x in model_lower for x in ("opus-4-6", "opus-4.6", "sonnet-4-6", "sonnet-4.6")):
            return {"thinking": {"type": "adaptive"}}
        if any(x in model_lower for x in ("opus-4", "sonnet-4")):
            budget = {"low": 1024, "medium": 10000, "high": 16000, "max": 32000}.get(variant, 10000)
            return {"thinking": {"type": "enabled", "budget_tokens": budget}}
        budget = {"low": 1024, "medium": 10000, "high": 16000, "max": 32000}.get(variant)
        if budget:
            return {"thinking": {"type": "enabled", "budget_tokens": budget}}
        return {}

    if provider == "gemini":
        budget = {"low": 4096, "medium": 16000, "high": 24576}.get(variant)
        if budget:
            return {"thinking": {"type": "enabled", "budget_tokens": budget}}
        return {}

    if provider == "deepseek":
        # Same clamp as the openai branch, and for the same reason: the variant
        # rides on the message, so a "max" or "xhigh" chosen on a GPT model
        # arrives here intact when the session later resolves to DeepSeek.
        # `reasoning_effort` is a parameter DeepSeek supports, so drop_params
        # will not strip an out-of-range value — it reaches the API and is
        # rejected there.
        effort = {"max": "high", "xhigh": "high"}.get(variant, variant)
        if effort not in ("low", "medium", "high"):
            log.debug(f"dropping unusable reasoning effort {variant!r} for {model_id}")
            return {}
        return {"reasoning_effort": effort}

    return {}


def _needs_responses_api(model_id: str) -> bool:
    """Check if a model needs the OpenAI Responses API for reasoning content.

    GPT-5.x models only expose reasoning summaries through the Responses API,
    NOT through Chat Completions. Claude models return reasoning_content via
    Chat Completions, so they don't need this path.
    """
    model_lower = model_id.lower()
    # GPT-5 family via OpenAI-compatible proxy
    if _detect_provider(model_id) == "openai" and "gpt-5" in model_lower:
        return True
    return False


async def _stream_responses_api(
    model_id: str,
    system: list[str],
    messages: list[dict],
    tools: dict[str, ToolInfo],
    variant: str | None = None,
    tool_choice: str | None = None,
) -> AsyncIterator[dict]:
    """Stream LLM via OpenAI Responses API directly (for GPT-5.x reasoning).

    The Chat Completions API does NOT return reasoning content for GPT-5.x.
    This function calls the Responses API endpoint directly via httpx,
    parsing the SSE event stream into our standard event format.
    """
    import httpx

    provider_kwargs = _get_provider_kwargs(model_id)
    api_key = provider_kwargs.get("api_key", "")
    api_base = provider_kwargs.get("api_base", "")

    if not api_base:
        log.error("No api_base configured for Responses API")
        yield {"type": "error", "error": Exception("No api_base configured")}
        return

    # Build the Responses API URL with required api-version
    # base_url is conventionally written with the /v1 suffix already (that is
    # what every OpenAI-compatible provider documents), so appending another
    # one produced /v1/v1/responses and a 404 that reads like a missing model.
    root = api_base.rstrip("/")
    if not root.endswith("/v1"):
        root = f"{root}/v1"
    url = f"{root}/responses?api-version=2025-03-01-preview"

    # Determine reasoning effort
    variant_kwargs = _get_variant_kwargs(model_id, variant)
    effort = variant_kwargs.get("reasoning_effort", "medium")
    if variant_kwargs:
        log.info(f"Responses API reasoning for {model_id}: effort={effort}")

    input_messages = build_responses_input(messages, system)

    # Build tool definitions for Responses API
    api_tools = []
    for tool_id, tool_info in tools.items():
        schema = tool_info.raw_schema or tool_info.parameters.model_json_schema()
        schema = _inline_refs(schema)
        api_tools.append({
            "type": "function",
            "name": tool_id,
            "description": tool_info.description,
            "parameters": schema,
        })

    # Strip the provider prefix from model_id (e.g., "openai/gpt-5.2" -> "gpt-5.2")
    bare_model = model_id.split("/", 1)[1] if "/" in model_id else model_id

    payload: dict[str, Any] = {
        "model": bare_model,
        "input": input_messages,
        "reasoning": {"effort": effort, "summary": "detailed"},
        "stream": True,
        "max_output_tokens": _get_max_output_tokens(model_id),
    }
    if api_tools:
        payload["tools"] = api_tools
        # Structured output is enforced by forcing a tool call, not by asking
        # nicely in the prompt. This path used to drop tool_choice entirely, so
        # the same request that was guaranteed on Chat Completions degraded to
        # a suggestion here — and when the model answered in prose instead, the
        # caller got an empty result with no error to explain it.
        if tool_choice:
            payload["tool_choice"] = tool_choice

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        tool_calls: list[dict] = []
        stream_usage: dict = {}
        had_streaming_text = False
        had_streaming_reasoning = False

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    log.error(f"Responses API error {resp.status_code}: {body.decode()[:500]}")
                    yield {"type": "error", "error": Exception(f"Responses API {resp.status_code}: {body.decode()[:200]}")}
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break

                    try:
                        data = _json.loads(data_str)
                    except _json.JSONDecodeError:
                        continue

                    etype = data.get("type", "")

                    # Reasoning summary text (the readable thinking content)
                    if etype == "response.reasoning_summary_text.delta":
                        delta = data.get("delta", "")
                        if delta:
                            had_streaming_reasoning = True
                            yield {"type": "reasoning_delta", "text": delta}

                    # Output text
                    elif etype == "response.output_text.delta":
                        delta = data.get("delta", "")
                        if delta:
                            had_streaming_text = True
                            yield {"type": "text_delta", "text": delta}

                    # Function call: output_item.added creates the entry,
                    # then function_call_arguments.delta accumulates args.
                    # IMPORTANT: delta events use "item_id" (= item.id),
                    # NOT "call_id". We key by item_id for matching.
                    elif etype == "response.output_item.added":
                        item = data.get("item", {})
                        if item.get("type") == "function_call":
                            tc_index = len(tool_calls)
                            tool_calls.append({
                                "item_id": item.get("id", ""),
                                "call_id": item.get("call_id", ""),
                                "name": item.get("name", ""),
                                "args": "",
                            })
                            # Emit tool_call_start so frontend shows card immediately
                            if item.get("name"):
                                yield {"type": "tool_call_start", "index": tc_index, "tool": item["name"], "call_id": item.get("call_id", "")}

                    elif etype == "response.function_call_arguments.delta":
                        item_id = data.get("item_id", "")
                        delta = data.get("delta", "")
                        existing = None
                        tc_index = -1
                        for i, tc in enumerate(tool_calls):
                            if tc["item_id"] == item_id:
                                existing = tc
                                tc_index = i
                                break
                        if existing:
                            existing["args"] += delta
                        else:
                            # Fallback: create entry if output_item.added was missed
                            tc_index = len(tool_calls)
                            tool_calls.append({
                                "item_id": item_id,
                                "call_id": data.get("call_id", ""),
                                "name": data.get("name", ""),
                                "args": delta,
                            })
                        # Stream argument delta to frontend for live preview
                        if delta:
                            yield {"type": "tool_call_args_delta", "index": tc_index, "delta": delta}

                    # Response completed — extract usage + non-streamed content
                    # GPT-5.4 does NOT stream tool calls or reasoning; everything
                    # arrives in response.completed.output as a batch.
                    elif etype == "response.completed":
                        resp_data = data.get("response", {})
                        u = resp_data.get("usage", {})
                        stream_usage = {
                            "input": u.get("input_tokens", 0),
                            "output": u.get("output_tokens", 0),
                            "total": u.get("total_tokens", 0),
                            "cache": 0,
                        }

                        # Extract content from response.output for models
                        # that don't stream individual events (e.g. GPT-5.4).
                        # Only extract items that weren't already streamed.
                        for output_item in resp_data.get("output", []):
                            item_type = output_item.get("type", "")

                            if item_type == "reasoning" and not had_streaming_reasoning:
                                for summary in output_item.get("summary", []):
                                    text = summary.get("text", "")
                                    if text:
                                        yield {"type": "reasoning_delta", "text": text}

                            elif item_type == "function_call":
                                fc_id = output_item.get("id", "")
                                already_captured = any(
                                    tc.get("item_id") == fc_id for tc in tool_calls
                                )
                                if not already_captured:
                                    tc_index = len(tool_calls)
                                    tool_calls.append({
                                        "item_id": fc_id,
                                        "call_id": output_item.get("call_id", ""),
                                        "name": output_item.get("name", ""),
                                        "args": output_item.get("arguments", ""),
                                    })
                                    if output_item.get("name"):
                                        yield {
                                            "type": "tool_call_start",
                                            "index": tc_index,
                                            "tool": output_item["name"],
                                            "call_id": output_item.get("call_id", ""),
                                        }
                                    args_str = output_item.get("arguments", "")
                                    if args_str:
                                        yield {
                                            "type": "tool_call_args_delta",
                                            "index": tc_index,
                                            "delta": args_str,
                                        }

                            elif item_type == "message" and not had_streaming_text:
                                for content_part in output_item.get("content", []):
                                    if content_part.get("type") == "output_text":
                                        text = content_part.get("text", "")
                                        if text:
                                            yield {"type": "text_delta", "text": text}

        log.info(f"Responses API usage for {model_id}: {stream_usage}")

        # Estimate cost
        if stream_usage:
            try:
                import litellm
                cost = litellm.completion_cost(
                    model=model_id,
                    prompt_tokens=stream_usage.get("input", 0),
                    completion_tokens=stream_usage.get("output", 0),
                )
                stream_usage["cost"] = cost
            except Exception:
                stream_usage["cost"] = 0.0

        # Yield tool calls
        if tool_calls:
            for tc in tool_calls:
                try:
                    args = _json.loads(tc["args"]) if tc["args"] else {}
                except _json.JSONDecodeError:
                    args = {}

                tool_name = tc["name"]
                call_id = tc.get("call_id", tc.get("item_id", ""))
                repaired = _repair_tool_name(tool_name, tools)
                if repaired is None:
                    log.warning(f"Unknown tool call: {tool_name}")
                    yield {
                        "type": "tool_call", "tool": tool_name,
                        "args": args, "call_id": call_id, "invalid": True,
                    }
                else:
                    yield {
                        "type": "tool_call", "tool": repaired,
                        "args": args, "call_id": call_id,
                    }
            yield {"type": "finish", "reason": "tool_calls", "usage": stream_usage}
        else:
            yield {"type": "finish", "reason": "stop", "usage": stream_usage}

    except Exception as e:
        log.error(f"Responses API error: {e}")
        yield {"type": "error", "error": e}


async def stream_llm(
    agent_def: AgentDef,
    system: list[str],
    messages: list[dict],
    tools: dict[str, ToolInfo],
    model_id: str,
    ctx: ToolContext,
    hooks: Any = None,
    variant: str | None = None,
    tool_choice: str | None = None,
) -> AsyncIterator[dict]:
    """Stream LLM responses using LiteLLM.

    Yields events:
    - {"type": "text_delta", "text": "..."}
    - {"type": "reasoning_delta", "text": "..."}
    - {"type": "tool_call", "tool": "...", "args": {...}, "call_id": "..."}
    - {"type": "finish", "reason": "stop"|"tool_calls", "usage": {...}}
    - {"type": "error", "error": Exception}

    Note: tool execution is NOT done here. The caller (loop.py) is responsible
    for executing tools via hooks, so it can pass the correct part_id for SSE events.
    """
    # GPT-5.x models: use Responses API for reasoning content
    if _needs_responses_api(model_id):
        async for event in _stream_responses_api(
            model_id, system, messages, tools, variant=variant, tool_choice=tool_choice
        ):
            yield event
        return

    # All other models: use LiteLLM Chat Completions
    async for event in _stream_litellm_direct(model_id, system, messages, tools, variant=variant, tool_choice=tool_choice):
        yield event


def _to_pydantic_messages(messages: list[dict]) -> list:
    """Convert our message format to Pydantic AI ModelMessage format.

    Pydantic AI expects message_history as a list of ModelMessage objects.
    We try to construct them; if the imports are unavailable, return empty
    (the fallback LiteLLM path handles messages directly).
    """
    try:
        from pydantic_ai.messages import (
            ModelRequest,
            ModelResponse,
            UserPromptPart,
            TextPart as PATextPart,
        )

        history = []
        # Convert all messages except the last user message (which is the prompt)
        for msg in messages[:-1]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                text = " ".join(
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            else:
                text = str(content) if content else ""

            if not text:
                continue

            if role == "user":
                history.append(ModelRequest(parts=[UserPromptPart(content=text)]))
            elif role == "assistant":
                history.append(ModelResponse(parts=[PATextPart(content=text)]))

        return history
    except ImportError:
        # Pydantic AI messages not available
        return []


def _extract_cache_tokens(usage_obj: Any) -> int:
    """Extract total cache tokens (read + write) from a usage object.

    LiteLLM normalizes cache fields across providers:
    - Anthropic: cache_read_input_tokens + cache_creation_input_tokens
    - OpenAI/Azure: prompt_tokens_details.cached_tokens (read only, write is automatic)
    """
    cache_read = 0
    cache_write = 0

    # Anthropic direct: cache_read_input_tokens / cache_creation_input_tokens
    val = getattr(usage_obj, "cache_read_input_tokens", None)
    if val:
        cache_read = int(val)
    val = getattr(usage_obj, "cache_creation_input_tokens", None)
    if val:
        cache_write = int(val)

    # OpenAI / Azure / LiteLLM proxy: prompt_tokens_details.cached_tokens
    if not cache_read:
        ptd = getattr(usage_obj, "prompt_tokens_details", None)
        if ptd:
            cached = getattr(ptd, "cached_tokens", None) if not isinstance(ptd, dict) else ptd.get("cached_tokens")
            if cached:
                cache_read = int(cached)
            creation = getattr(ptd, "cache_creation_tokens", None) if not isinstance(ptd, dict) else ptd.get("cache_creation_tokens")
            if creation:
                cache_write = int(creation)

    return cache_read + cache_write


def _extract_chunk_usage(chunk: Any, target: dict) -> None:
    """Extract usage from a streaming chunk into target dict (mutates target)."""
    usage = getattr(chunk, "usage", None)
    if not usage:
        return
    # Only update if we get non-zero values
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0
    total = getattr(usage, "total_tokens", 0) or 0
    if prompt or completion or total:
        target["input"] = prompt
        target["output"] = completion
        target["total"] = total or (prompt + completion)
        target["cache"] = _extract_cache_tokens(usage)


def _extract_chunk_usage_from_obj(usage: Any, target: dict) -> None:
    """Extract usage from any usage-like object (dict or object with attrs)."""
    if isinstance(usage, dict):
        prompt = usage.get("prompt_tokens", 0) or 0
        completion = usage.get("completion_tokens", 0) or 0
        total = usage.get("total_tokens", 0) or 0
    else:
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        completion = getattr(usage, "completion_tokens", 0) or 0
        total = getattr(usage, "total_tokens", 0) or 0
    if prompt or completion or total:
        target["input"] = prompt
        target["output"] = completion
        target["total"] = total or (prompt + completion)
        target["cache"] = _extract_cache_tokens(usage) if not isinstance(usage, dict) else (usage.get("cache_read_input_tokens", 0) or 0) + (usage.get("cache_creation_input_tokens", 0) or 0)


def _finalize_message(msg: dict) -> dict:
    """Strip loop-internal keys; expand `_images` into multimodal content."""
    internal = {"_images", "_synthetic", "_ignored", "_transient_images"}
    if not any(k in msg for k in internal):
        return msg
    out = {k: v for k, v in msg.items() if k not in internal}
    # Only resolved data URIs are real images. An unresolved reference (a dict
    # left by _image_ref_for_part when nothing called resolve_images) would
    # otherwise be serialised as {"url": {...}} and rejected by the provider —
    # dropping it keeps the turn alive as text.
    images = [u for u in (msg.get("_images") or []) if isinstance(u, str)]
    if images:
        parts: list[dict] = []
        text = out.get("content")
        if isinstance(text, str) and text:
            parts.append({"type": "text", "text": text})
        parts.extend({"type": "image_url", "image_url": {"url": u}} for u in images)
        out["content"] = parts
    return out


async def _stream_litellm_direct(
    model_id: str,
    system: list[str],
    messages: list[dict],
    tools: dict[str, ToolInfo],
    variant: str | None = None,
    tool_choice: str | None = None,
) -> AsyncIterator[dict]:
    """Stream LLM via LiteLLM. Only yields stream events — no tool execution.

    Tool execution is the caller's responsibility (loop.py handles it with
    the correct part_id for SSE events).
    """
    try:
        import litellm

        # Enable LiteLLM compatibility features for thinking models:
        # - modify_params: auto-handle thinking_blocks in multi-turn tool-calling
        #   (drops thinking param if thinking_blocks missing in history)
        # - drop_params: drop unsupported params when switching providers
        # - reasoning_auto_summary: for GPT-5 models, automatically request a
        #   readable reasoning summary (otherwise reasoning is encrypted/hidden)
        litellm.modify_params = True
        litellm.drop_params = True
        litellm.reasoning_auto_summary = True

        provider_kwargs = _get_provider_kwargs(model_id)

        # Build messages
        llm_messages = []
        if system:
            llm_messages.append({"role": "system", "content": "\n\n".join(system)})
        llm_messages.extend(messages)

        # Multimodal: messages carry image URLs out-of-band (_images) so every
        # earlier pass works on plain strings. Convert to OpenAI-style content
        # arrays here, at the last moment, and drop loop-internal keys.
        llm_messages = [_finalize_message(m) for m in llm_messages]

        # Some providers (OpenAI-compatible proxies) reject conversations ending
        # with an assistant message ("assistant prefill not supported").
        # Ensure the conversation ends with a user or tool message.
        if llm_messages and llm_messages[-1].get("role") == "assistant":
            llm_messages.append({"role": "user", "content": "Continue."})

        # LiteLLM/Anthropic proxy compatibility: add _noop tool when
        # message history contains tool calls but no active tools are provided.
        if not tools and _has_tool_calls(llm_messages):
            tool_schemas = [{
                "type": "function",
                "function": {
                    "name": "_noop",
                    "description": "Placeholder for proxy compatibility",
                    "parameters": {"type": "object", "properties": {}},
                },
            }]
        else:
            tool_schemas = []

        for tool_id, tool_info in tools.items():
            schema = tool_info.raw_schema or tool_info.parameters.model_json_schema()
            schema = _inline_refs(schema)
            tool_schemas.append({
                "type": "function",
                "function": {
                    "name": tool_id,
                    "description": tool_info.description,
                    "parameters": schema,
                },
            })

        # Merge variant-specific parameters (thinking budget, reasoning effort, etc.)
        variant_kwargs = _get_variant_kwargs(model_id, variant)
        if variant_kwargs:
            if variant:
                log.info(f"Variant '{variant}' for {model_id}: {variant_kwargs}")
            else:
                log.info(f"Default thinking for {model_id}: {variant_kwargs}")

        # For OpenAI-compatible proxies, pass reasoning params via extra_body
        # so they go through unmodified. LiteLLM's top-level param handling
        # transforms reasoning_effort in ways that some proxies don't recognize.
        provider = _detect_provider(model_id)
        extra_body = {}
        direct_kwargs = {}
        if provider == "openai" and variant_kwargs:
            # OpenAI proxy: send reasoning params in extra_body
            extra_body = dict(variant_kwargs)
            log.info(f"Sending via extra_body for OpenAI proxy: {extra_body}")
        else:
            # Native providers (Anthropic, etc.): use top-level params
            direct_kwargs = variant_kwargs

        call_kwargs = {
            "model": model_id,
            "messages": llm_messages,
            "tools": tool_schemas if tool_schemas else None,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": _get_max_output_tokens(model_id),
            **provider_kwargs,
            **direct_kwargs,
        }
        if extra_body:
            call_kwargs["extra_body"] = extra_body
        # Anthropic draws the thinking budget OUT of the output budget and
        # requires max_tokens to be strictly greater. The generic 32k default
        # happens to equal the "max" budget exactly, so the highest reasoning
        # setting was rejected outright — the two numbers were picked
        # independently and collided.
        budget = ((direct_kwargs.get("thinking") or {}).get("budget_tokens")
                  if isinstance(direct_kwargs.get("thinking"), dict) else None)
        if budget and call_kwargs["max_tokens"] <= budget:
            call_kwargs["max_tokens"] = budget + THINKING_OUTPUT_RESERVE
        # Only meaningful when there is something to choose from; sending it
        # with an empty tool list is rejected by several providers.
        if tool_choice and tool_schemas:
            call_kwargs["tool_choice"] = tool_choice

        response = await litellm.acompletion(**call_kwargs)

        tool_calls = []
        stream_usage: dict = {}  # Captured from the final chunk(s)

        async for chunk in response:
            # Capture usage from any chunk that carries it (typically the final one).
            # With stream_options={"include_usage": True}, the provider sends a
            # final chunk with choices=[] and usage filled.
            _extract_chunk_usage(chunk, stream_usage)

            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            # Reasoning/thinking content
            # LiteLLM standardizes across providers:
            # - Anthropic thinking → delta.reasoning_content
            # - OpenAI reasoning → delta.reasoning_content
            # - DeepSeek R1 → delta.reasoning_content
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                yield {"type": "reasoning_delta", "text": reasoning}

            # Text content
            if delta.content:
                yield {"type": "text_delta", "text": delta.content}

            # Tool calls (accumulate chunks + emit streaming events)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    if tc.index is not None:
                        while len(tool_calls) <= tc.index:
                            tool_calls.append({"id": "", "name": "", "args": "", "_started": False})
                        if tc.id:
                            tool_calls[tc.index]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls[tc.index]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls[tc.index]["args"] += tc.function.arguments
                        # Emit streaming events so frontend can show tool card immediately
                        entry = tool_calls[tc.index]
                        if entry["name"] and not entry["_started"]:
                            entry["_started"] = True
                            yield {"type": "tool_call_start", "index": tc.index, "tool": entry["name"], "call_id": entry["id"]}
                        if tc.function and tc.function.arguments and entry["_started"]:
                            yield {"type": "tool_call_args_delta", "index": tc.index, "delta": tc.function.arguments}

            # Finish reason
            finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
            if finish_reason:
                # Don't break yet — there may be a final usage-only chunk after this
                pass

        # Fallback: LiteLLM's CustomStreamWrapper may strip usage from chunks
        # and store it in _hidden_params after full consumption.
        if not stream_usage:
            hidden = getattr(response, "_hidden_params", {})
            if isinstance(hidden, dict):
                hp_usage = hidden.get("usage", None)
                if hp_usage:
                    _extract_chunk_usage_from_obj(hp_usage, stream_usage)
            # Also try response.usage (some LiteLLM versions set it after iteration)
            if not stream_usage:
                resp_usage = getattr(response, "usage", None)
                if resp_usage:
                    _extract_chunk_usage_from_obj(resp_usage, stream_usage)

        log.info(f"Stream usage for {model_id}: {stream_usage}")

        # Estimate cost using LiteLLM's pricing data
        if stream_usage:
            try:
                cost = litellm.completion_cost(
                    model=model_id,
                    prompt_tokens=stream_usage.get("input", 0),
                    completion_tokens=stream_usage.get("output", 0),
                )
                stream_usage["cost"] = cost
            except Exception:
                stream_usage["cost"] = 0.0

        # Yield tool calls for the caller to execute
        if tool_calls:
            import json
            for tc in tool_calls:
                try:
                    args = json.loads(tc["args"]) if tc["args"] else {}
                except json.JSONDecodeError:
                    args = {}

                tool_name = tc["name"]
                repaired = _repair_tool_name(tool_name, tools)
                if repaired is None:
                    log.warning(f"Unknown tool call: {tool_name}")
                    yield {
                        "type": "tool_call", "tool": tool_name,
                        "args": args, "call_id": tc["id"], "invalid": True,
                    }
                else:
                    yield {
                        "type": "tool_call", "tool": repaired,
                        "args": args, "call_id": tc["id"],
                    }

            yield {"type": "finish", "reason": "tool_calls", "usage": stream_usage}
        else:
            yield {"type": "finish", "reason": "stop", "usage": stream_usage}

    except Exception as e:
        log.error(f"LiteLLM error: {e}")
        yield {"type": "error", "error": e}


def _has_tool_calls(messages: list[dict]) -> bool:
    """Check if any message in history contains tool call/result content.

    Used to determine if a _noop tool should be added for LiteLLM proxy compatibility.
    """
    for msg in messages:
        role = msg.get("role", "")
        if role == "tool":
            return True
        content = msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") in ("tool-call", "tool-result", "tool_use", "tool_result"):
                    return True
        # Check for tool_calls in assistant messages
        if role == "assistant" and msg.get("tool_calls"):
            return True
    return False
