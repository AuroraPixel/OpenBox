"""MCP tool wrapper: dynamically create ToolInfo for MCP tools from container."""
from __future__ import annotations

import re
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from core.log import create_logger
from tool.tool import ToolInfo, ToolResult, ToolContext

log = create_logger("tool.mcp")

MAX_TOOL_NAME_LEN = 64


def _sanitize_tool_name(server: str, name: str) -> str:
    """Build a sanitized tool ID: only [a-zA-Z0-9_-], max 64 chars.

    Matches opencode's sanitization: replace non-alphanumeric with '_'.
    """
    safe_server = re.sub(r"[^a-zA-Z0-9_-]", "_", server)
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    tool_id = f"mcp_{safe_server}_{safe_name}"
    if len(tool_id) > MAX_TOOL_NAME_LEN:
        tool_id = tool_id[:MAX_TOOL_NAME_LEN]
    return tool_id


def _sanitize_schema(schema: Any) -> Any:
    """Recursively fix JSON Schema issues that OpenAI/Gemini reject.

    Fixes applied (matching opencode's sanitizeGemini):
    - array type missing 'items' → add { "type": "string" }
    - items is empty object without type → set type to "string"
    - required array references non-existent properties → filter
    """
    if schema is None or not isinstance(schema, dict):
        return schema

    result = {}
    for key, value in schema.items():
        if isinstance(value, dict):
            result[key] = _sanitize_schema(value)
        elif isinstance(value, list):
            result[key] = [_sanitize_schema(v) if isinstance(v, dict) else v for v in value]
        else:
            result[key] = value

    # Fix: array without items
    if result.get("type") == "array":
        if "items" not in result or result["items"] is None:
            result["items"] = {"type": "string"}
        elif isinstance(result["items"], dict) and not result["items"].get("type"):
            result["items"]["type"] = "string"

    # Fix: required references non-existent properties
    if result.get("type") == "object" and "properties" in result and isinstance(result.get("required"), list):
        result["required"] = [f for f in result["required"] if f in result["properties"]]

    return result


def _make_raw_schema_model(input_schema: dict) -> type[BaseModel]:
    """Create a Pydantic BaseModel subclass that returns the raw MCP input_schema
    from model_json_schema().

    This lets the LLM see the full JSON Schema (including const, enum, anyOf,
    default values, etc.) instead of a lossy Pydantic-generated schema.
    The actual validation is done by the MCP server, not locally.
    """
    # Ensure it's a proper object schema and sanitize
    schema = dict(input_schema)
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    schema = _sanitize_schema(schema)

    class McpRawSchemaModel(BaseModel):
        _raw_schema: ClassVar[dict] = schema

        @classmethod
        def model_json_schema(cls, **_kwargs: Any) -> dict:
            """Return the raw MCP input_schema directly."""
            return cls._raw_schema

    return McpRawSchemaModel


def _make_mcp_executor(server_name: str, tool_name: str):
    """Create an executor function for a specific MCP tool.

    Arguments from the LLM are forwarded directly to the MCP server
    without local Pydantic validation — the MCP server handles validation.
    """

    async def executor(args, ctx: ToolContext) -> ToolResult:
        if not ctx.sandbox:
            return ToolResult(
                title=f"MCP tool error: {tool_name}",
                output="No sandbox available for MCP tool execution.",
            )
        try:
            # args is a raw dict from the agent loop
            if hasattr(args, "model_dump"):
                arguments = args.model_dump()
            elif isinstance(args, dict):
                arguments = args
            else:
                arguments = dict(args)

            # Remove None values but keep False, 0, empty string, etc.
            arguments = {k: v for k, v in arguments.items() if v is not None}

            log.info(f"Calling MCP tool {server_name}/{tool_name} with args: {arguments}")
            result = await ctx.sandbox.call_mcp_tool(
                server_name, tool_name, arguments,
            )
            log.info(f"MCP tool {server_name}/{tool_name} returned: isError={result.get('isError')}")

            # Pass raw MCP result to LLM, with truncation.
            # If truncated, save full output ONLY to container (not host).
            import json as _json
            raw_output = _json.dumps(result, ensure_ascii=False, default=str)
            from tool.truncation import MAX_BYTES, MAX_LINES
            raw_bytes = len(raw_output.encode("utf-8"))
            raw_lines = raw_output.count("\n") + 1

            if raw_bytes > MAX_BYTES or raw_lines > MAX_LINES:
                saved_path = f"{ctx.workdir}/.mcp_output_{tool_name}_{int(__import__('time').time())}.json"
                try:
                    await ctx.sandbox.write_file(saved_path, raw_output)
                except Exception:
                    saved_path = None
                # Truncate: keep first portion as preview
                lines = raw_output.split("\n")
                preview_lines = []
                byte_count = 0
                for line in lines:
                    size = len(line.encode("utf-8")) + 1
                    if byte_count + size > MAX_BYTES or len(preview_lines) >= MAX_LINES:
                        break
                    preview_lines.append(line)
                    byte_count += size
                preview = "\n".join(preview_lines)
                hint = f"\n\nFull output saved to: {saved_path}\nUse the read tool with offset/limit to view specific sections." if saved_path else ""
                return ToolResult(
                    title=f"{'Error: ' if result.get('isError') else ''}{tool_name}",
                    output=preview + hint,
                    metadata={"truncated": True},
                )

            return ToolResult(
                title=f"{'Error: ' if result.get('isError') else ''}{tool_name}",
                output=raw_output,
            )
        except Exception as e:
            log.error(f"MCP tool {server_name}/{tool_name} failed: {e}", exc_info=True)
            return ToolResult(
                title=f"MCP tool error: {tool_name}",
                output=f"Failed to call MCP tool: {e}",
            )

    return executor


# When MCP tools exceed this threshold, switch to the two meta-tool pattern
# (mcp_find_tool + mcp_call_tool) instead of registering each tool individually.
# This reduces token usage by ~95% (2 tools vs hundreds).
# Reference: https://docs.litellm.ai/docs/mcp_semantic_filter
#            https://dev.to/stacklok/cut-token-waste-from-your-ai-workflow-with-the-toolhive-mcp-optimizer-3oo6
MCP_META_TOOL_THRESHOLD = 40


async def _llm_filter_tools(query: str, matches: list[tuple[int, dict]]) -> str:
    """Use a lightweight LLM (mcp_filter_model) to select the best tools from many matches.

    Sends a compact tool list to a fast/cheap model and asks it to pick the top 5
    most relevant tools for the user's query. Returns structured output the main
    agent can use to call mcp_call_tool directly.
    """
    from core.config import get_config
    from agent.llm import _get_provider_kwargs

    config = get_config()
    filter_model = config.mcp_filter_model or config.model
    provider_kwargs = _get_provider_kwargs(filter_model)

    # Build compact tool list for the filter model
    tool_lines = []
    for i, (_score, t) in enumerate(matches[:50]):
        desc = (t.get("description") or "")[:100]
        params = list(t.get("input_schema", {}).get("properties", {}).keys())[:5]
        tool_lines.append(f"{i+1}. {t.get('server')}/{t.get('name')}: {desc} (params: {', '.join(params)})")

    prompt = (
        f"User wants to: {query}\n\n"
        f"Available tools ({len(matches)} total, showing top 50):\n"
        + "\n".join(tool_lines)
        + "\n\nPick the TOP 5 most relevant tools for the user's request. "
        "For each tool, output EXACTLY this format:\n"
        "server: \"<server_name>\"\n"
        "tool: \"<tool_name>\"\n"
        "why: <one sentence reason>\n"
        "---\n"
        "Only output the 5 tools, nothing else."
    )

    try:
        import litellm
        log.info(f"Calling MCP filter model ({filter_model}) for query '{query}' with {len(matches)} matches")
        # Filter call: must allow enough tokens for thinking models (Kimi K2.5 etc)
        # that output reasoning_content BEFORE content. With max_tokens=800,
        # thinking uses up all tokens and content is never generated.
        # 4096 = ~2-3K for thinking + ~1K for final answer.
        litellm.drop_params = True
        resp = await litellm.acompletion(
            model=filter_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            **provider_kwargs,
        )
        msg = resp.choices[0].message
        # Always use content (the final answer), not reasoning_content (thinking process)
        llm_output = msg.content or ""
        if not llm_output:
            log.warning(f"MCP filter model content empty (finish_reason={resp.choices[0].finish_reason})")
        log.info(f"MCP filter model response ({len(llm_output)} chars): {llm_output[:200]}")

        # Parse the LLM's selection — must handle multiple output styles:
        # - Structured: tool: "name"
        # - Reasoning/thinking: mentions tool names in free text
        # - Numbered list: 1. server/name
        import re
        selected_names = []

        # Build a set of all valid tool names for matching against free text
        valid_names = {t.get("name", "") for _, t in matches}

        # Pass 1: structured format (tool: "name" or tool: name)
        for line in llm_output.split("\n"):
            line_s = line.strip()
            if line_s.lower().startswith('tool:') or line_s.lower().startswith('- tool:'):
                m = re.search(r'["\']([^"\']+)["\']', line_s)
                if m:
                    selected_names.append(m.group(1))
                else:
                    name = line_s.split(":", 1)[1].strip().strip('"\'').strip()
                    if "/" in name:
                        name = name.split("/")[-1]
                    if name:
                        selected_names.append(name)

        # Pass 2: extract any valid tool names mentioned anywhere in the text
        if len(selected_names) < 3:
            for name in valid_names:
                if name and len(name) > 5 and name in llm_output and name not in selected_names:
                    selected_names.append(name)

        # Pass 3: server/tool patterns
        if not selected_names:
            for m in re.finditer(r'\w+/(\w{6,})', llm_output):
                if m.group(1) in valid_names:
                    selected_names.append(m.group(1))

        # Deduplicate while preserving order
        seen = set()
        unique_names = []
        for n in selected_names:
            if n not in seen:
                seen.add(n)
                unique_names.append(n)
        selected_names = unique_names[:5]

        log.info(f"MCP filter parsed {len(selected_names)} tool names: {selected_names[:5]}")

        # Build full detail output for selected tools
        enriched = []
        for name in selected_names[:5]:
            for _score, t in matches:
                if t.get("name") == name:
                    schema = t.get("input_schema", {})
                    props = schema.get("properties", {})
                    required = schema.get("required", [])
                    param_details = []
                    for pname, pdef in props.items():
                        ptype = pdef.get("type", "?") if isinstance(pdef, dict) else "?"
                        pdesc = pdef.get("description", "")[:60] if isinstance(pdef, dict) else ""
                        req = " (required)" if pname in required else ""
                        param_details.append(f"    {pname}: {ptype}{req}" + (f" - {pdesc}" if pdesc else ""))
                    enriched.append(
                        f"  server: \"{t.get('server')}\"\n"
                        f"  tool: \"{name}\"\n"
                        f"  description: {(t.get('description') or '')[:120]}\n"
                        + ("  parameters:\n" + "\n".join(param_details) if param_details else "  (no parameters)")
                    )
                    break

        if enriched:
            return (
                f"Found {len(matches)} tools. AI filter selected top {len(enriched)} for \"{query}\".\n"
                f"Use mcp_call_tool with the EXACT server and tool values:\n\n"
                + "\n---\n".join(enriched)
            )
        else:
            # Fallback: return raw LLM output
            return f"Found {len(matches)} tools. Filter model recommendation:\n\n{llm_output}"

    except Exception as e:
        log.warning(f"MCP filter model failed: {e}, falling back to compact list")
        # Fallback: simple compact list
        lines = []
        for _score, t in matches[:30]:
            lines.append(f"  - {t.get('server')}/{t.get('name')}: {(t.get('description') or '')[:80]}")
        return (
            f"Found {len(matches)} tools. Search with MORE SPECIFIC keywords to narrow down.\n\n"
            + "\n".join(lines)
        )


def _build_tool_catalog(mcp_tools: list[dict]) -> str:
    """Build a concise text catalog of all MCP tools for the meta-tool description."""
    lines = []
    for t in mcp_tools:
        server = t.get("server", "?")
        name = t.get("name", "?")
        desc = (t.get("description", "") or "")[:100]
        params = t.get("input_schema", {}).get("properties", {})
        param_names = ", ".join(list(params.keys())[:6])
        if len(params) > 6:
            param_names += ", ..."
        lines.append(f"- {server}/{name}: {desc}" + (f" (params: {param_names})" if param_names else ""))
    return "\n".join(lines)


def _create_meta_tools(mcp_tools: list[dict], sandbox_ref) -> dict[str, ToolInfo]:
    """Create two meta-tools (find + call) that replace hundreds of individual tools.

    Pattern from ToolHive MCP Optimizer / Speakeasy Dynamic Toolsets:
    - mcp_find_tool: Search tools by keyword, returns matching tool names + schemas
    - mcp_call_tool: Call any MCP tool by server/name with arguments
    """
    # Build in-memory index
    tool_index: dict[str, dict] = {}  # "server/name" -> full tool dict
    for t in mcp_tools:
        key = f"{t.get('server', '?')}/{t.get('name', '?')}"
        tool_index[key] = t

    catalog = _build_tool_catalog(mcp_tools)
    servers = sorted(set(t.get("server", "?") for t in mcp_tools))

    # --- mcp_find_tool ---
    class FindToolParams(BaseModel):
        query: str = Field(description="Search keyword to find relevant MCP tools")
        server: str = Field(default="", description=f"Optional: filter by server name. Available: {', '.join(servers)}")

    async def find_executor(args, ctx: ToolContext) -> ToolResult:
        params = args.model_dump() if hasattr(args, "model_dump") else dict(args)
        query = params.get("query", "").lower().strip()
        server_filter = params.get("server", "")

        # Split query into keywords for OR matching
        # "tiktok video search" → matches tools containing "tiktok" OR "video" OR "search"
        keywords = [k for k in query.split() if len(k) >= 2]

        # Special: empty/generic queries like "list tools", "all", "help" → show categories
        if not keywords or query in ("list tools", "list", "all", "help", "tools"):
            # Return category summary
            categories: dict[str, int] = {}
            for t in tool_index.values():
                if server_filter and t.get("server", "") != server_filter:
                    continue
                name = t.get("name", "")
                # Extract category from tool name (first part before _)
                parts = name.split("_")
                cat = parts[0] if parts else "other"
                categories[cat] = categories.get(cat, 0) + 1
            sorted_cats = sorted(categories.items(), key=lambda x: -x[1])
            lines = [f"  {cat}: {count} tools" for cat, count in sorted_cats[:30]]
            total_shown = sum(c for _, c in sorted_cats[:30])
            output = (
                f"{len(tool_index)} tools available across {len(categories)} categories.\n"
                f"Search with specific keywords like 'tiktok', 'youtube', 'download', 'search', etc.\n\n"
                f"Top categories:\n" + "\n".join(lines)
            )
            return ToolResult(title=f"{len(tool_index)} MCP tools available", output=output)

        matches = []
        for key, t in tool_index.items():
            if server_filter and t.get("server", "") != server_filter:
                continue
            searchable = f"{t.get('name', '')} {t.get('description', '')}".lower()
            # Score: how many keywords match
            score = sum(1 for k in keywords if k in searchable)
            if score > 0:
                matches.append((score, t))

        # Sort by relevance (most keywords matched first)
        matches.sort(key=lambda x: -x[0])

        if not matches:
            return ToolResult(title="No tools found", output=f"No MCP tools matching '{query}'. Try different keywords like 'tiktok', 'youtube', 'download', etc.")

        # Two-tier response to minimize context usage:
        # - <= 20 matches: return full details (server, tool, description, parameters)
        # - > 20 matches: return compact overview, LLM should refine search with more specific keywords
        if len(matches) <= 20:
            # Full detail mode — LLM can pick and call directly
            results = []
            for _score, t in matches[:10]:
                server_name = t.get("server", "")
                tool_name_exact = t.get("name", "")
                schema = t.get("input_schema", {})
                props = schema.get("properties", {})
                required = schema.get("required", [])
                param_details = []
                for pname, pdef in props.items():
                    ptype = pdef.get("type", "?") if isinstance(pdef, dict) else "?"
                    pdesc = pdef.get("description", "")[:60] if isinstance(pdef, dict) else ""
                    req = " (required)" if pname in required else ""
                    param_details.append(f"    {pname}: {ptype}{req}" + (f" - {pdesc}" if pdesc else ""))
                results.append(
                    f"  server: \"{server_name}\"\n"
                    f"  tool: \"{tool_name_exact}\"\n"
                    f"  description: {t.get('description', '')[:120]}\n"
                    + ("  parameters:\n" + "\n".join(param_details) if param_details else "  (no parameters)")
                )
            header = f"Found {len(matches)} tools. Use mcp_call_tool with the EXACT server and tool values:\n"
            output = header + "\n---\n".join(results)
        else:
            # Too many results — use mcp_filter_model (lightweight LLM) to pick
            # the best tools, saving context for the main agent.
            output = await _llm_filter_tools(query, matches)

        return ToolResult(title=f"Found {len(matches)} MCP tools", output=output)

    find_tool = ToolInfo(
        id="mcp_find_tool",
        description=(
            f"Search {len(mcp_tools)} available MCP tools by keyword. Returns tool names, descriptions, and parameter schemas. "
            f"Servers: {', '.join(servers)}. Use this FIRST to find the right tool, then use mcp_call_tool to execute it."
        ),
        parameters=FindToolParams,
        execute=find_executor,
        sandbox_required=True,
        never_prune=True,
    )

    # --- mcp_call_tool ---
    class CallToolParams(BaseModel):
        server: str = Field(description=f"MCP server name. Available: {', '.join(servers)}")
        tool: str = Field(description="Tool name (from mcp_find_tool results)")
        arguments: dict = Field(default_factory=dict, description="Tool arguments as JSON object")

    async def call_executor(args, ctx: ToolContext) -> ToolResult:
        if not ctx.sandbox:
            return ToolResult(title="Error", output="No sandbox available")
        params = args.model_dump() if hasattr(args, "model_dump") else dict(args)
        server = params.get("server", "")
        tool_name = params.get("tool", "")
        arguments = params.get("arguments", {})

        # LLMs often flatten tool arguments into the top level instead of
        # nesting them inside "arguments". Collect any extra keys as arguments.
        extra = {k: v for k, v in params.items() if k not in ("server", "tool", "arguments") and v is not None}
        if extra:
            if not arguments:
                arguments = extra
            else:
                arguments = {**extra, **arguments}

        # Remove None values
        if isinstance(arguments, dict):
            arguments = {k: v for k, v in arguments.items() if v is not None}

        key = f"{server}/{tool_name}"
        if key not in tool_index:
            # Try progressively looser matching:
            # 1. Exact tool name in any server
            # 2. Tool name as substring
            # 3. Word overlap scoring
            matched = None
            # Pass 1: exact name match across servers
            for k, t in tool_index.items():
                if t.get("name", "") == tool_name:
                    matched = k
                    break
            # Pass 2: substring match
            if not matched:
                for k in tool_index:
                    if tool_name in k or k.split("/", 1)[-1] in tool_name:
                        matched = k
                        break
            # Pass 3: word overlap (split by _ and score)
            if not matched:
                query_words = set(tool_name.lower().replace("-", "_").split("_"))
                best_score, best_key = 0, None
                for k, t in tool_index.items():
                    t_words = set(t.get("name", "").lower().replace("-", "_").split("_"))
                    score = len(query_words & t_words)
                    if score > best_score:
                        best_score = score
                        best_key = k
                if best_score >= 2:
                    matched = best_key

            if matched:
                key = matched
                server, tool_name = key.split("/", 1)
                log.info(f"Fuzzy matched tool '{params.get('tool')}' -> '{key}'")
            else:
                # Suggest similar tools
                query_words = set(tool_name.lower().replace("-", "_").split("_"))
                suggestions = []
                for k, t in tool_index.items():
                    t_words = set(t.get("name", "").lower().replace("-", "_").split("_"))
                    score = len(query_words & t_words)
                    if score >= 1:
                        suggestions.append((score, t.get("name", "")))
                suggestions.sort(key=lambda x: -x[0])
                hint = ""
                if suggestions:
                    top = [name for _, name in suggestions[:5]]
                    hint = f"\n\nDid you mean one of these?\n" + "\n".join(f"  - {n}" for n in top)
                return ToolResult(
                    title="Tool not found",
                    output=f"MCP tool '{params.get('tool')}' not found on server '{server}'.{hint}\n\nUse mcp_find_tool to search for the correct tool name.",
                )

        try:
            log.info(f"Calling MCP tool {server}/{tool_name} with args: {arguments}")
            result = await ctx.sandbox.call_mcp_tool(server, tool_name, arguments)
            import json as _json
            raw_output = _json.dumps(result, ensure_ascii=False, default=str)

            # Truncate large MCP results to prevent context explosion.
            # Save full output ONLY to container (not host) so LLM can read it.
            from tool.truncation import MAX_BYTES, MAX_LINES
            raw_bytes = len(raw_output.encode("utf-8"))
            raw_lines = raw_output.count("\n") + 1

            if raw_bytes > MAX_BYTES or raw_lines > MAX_LINES:
                # Save full output to container only
                saved_path = f"{ctx.workdir}/.mcp_output_{tool_name}_{int(__import__('time').time())}.json"
                try:
                    await ctx.sandbox.write_file(saved_path, raw_output)
                except Exception:
                    saved_path = None

                # Truncate: keep first portion as preview
                lines = raw_output.split("\n")
                preview_lines = []
                byte_count = 0
                for line in lines:
                    size = len(line.encode("utf-8")) + 1
                    if byte_count + size > MAX_BYTES or len(preview_lines) >= MAX_LINES:
                        break
                    preview_lines.append(line)
                    byte_count += size
                preview = "\n".join(preview_lines)

                hint = f"\n\nFull output saved to: {saved_path}\nUse the read tool with offset/limit to view specific sections." if saved_path else ""
                return ToolResult(
                    title=f"{'Error: ' if result.get('isError') else ''}{tool_name}",
                    output=preview + hint,
                    metadata={"truncated": True},
                )

            return ToolResult(
                title=f"{'Error: ' if result.get('isError') else ''}{tool_name}",
                output=raw_output,
            )
        except Exception as e:
            return ToolResult(title=f"MCP call failed: {tool_name}", output=str(e))

    call_tool = ToolInfo(
        id="mcp_call_tool",
        description=(
            f"Call any MCP tool by server name and tool name. Use mcp_find_tool first to discover available tools and their parameters. "
            f"Pass arguments as a JSON object matching the tool's parameter schema."
        ),
        parameters=CallToolParams,
        execute=call_executor,
        sandbox_required=True,
    )

    return {"mcp_find_tool": find_tool, "mcp_call_tool": call_tool}


async def create_mcp_tools(sandbox) -> dict[str, ToolInfo]:
    """Fetch MCP tools from the container and create ToolInfo wrappers.

    Two modes based on tool count:
    - <= MCP_META_TOOL_THRESHOLD: Register each tool individually (full schema)
    - > MCP_META_TOOL_THRESHOLD: Register 2 meta-tools (find + call) to avoid
      token explosion. This reduces token usage by ~95%.
    """
    tools: dict[str, ToolInfo] = {}
    try:
        mcp_tools = await sandbox.list_mcp_tools()
    except Exception as e:
        log.debug(f"Failed to list MCP tools from container: {e}")
        return tools

    total = len(mcp_tools)

    # Large tool sets: use meta-tool pattern (2 tools instead of hundreds)
    if total > MCP_META_TOOL_THRESHOLD:
        log.info(f"MCP has {total} tools (>{MCP_META_TOOL_THRESHOLD}), using meta-tool pattern (find + call)")
        return _create_meta_tools(mcp_tools, sandbox)

    # Small tool sets: register each individually with full schema
    for tool in mcp_tools:
        server = tool.get("server", "unknown")
        name = tool.get("name", "unknown")
        description = tool.get("description", "")
        input_schema = tool.get("input_schema", {})

        tool_id = _sanitize_tool_name(server, name)

        try:
            param_model = _make_raw_schema_model(input_schema)
        except Exception as e:
            log.warning(f"Failed to create schema model for MCP tool {tool_id}: {e}")
            continue

        tools[tool_id] = ToolInfo(
            id=tool_id,
            description=f"[MCP:{server}] {description}",
            parameters=param_model,
            execute=_make_mcp_executor(server, name),
            sandbox_required=True,
        )

    if tools:
        log.info(f"Loaded {len(tools)} MCP tools (direct mode)")

    return tools


def create_mcp_resource_tool() -> ToolInfo:
    """Create a generic tool for reading MCP resources."""

    class ReadResourceParams(BaseModel):
        server: str = Field(description="MCP server name that owns the resource")
        uri: str = Field(description="Resource URI to read")

    async def executor(args, ctx: ToolContext) -> ToolResult:
        if not ctx.sandbox:
            return ToolResult(title="Error", output="No sandbox available")
        try:
            params = args.model_dump() if hasattr(args, "model_dump") else dict(args)
            result = await ctx.sandbox.read_mcp_resource(params["server"], params["uri"])
            contents = result.get("contents", [])
            output_parts = []
            for c in contents:
                if "text" in c:
                    output_parts.append(c["text"])
                elif "blob" in c:
                    output_parts.append(f"[Binary data: {c.get('mimeType', 'unknown')}]")
            return ToolResult(title=f"Resource: {params['uri']}", output="\n".join(output_parts) or "(empty)")
        except Exception as e:
            return ToolResult(title="Resource read error", output=str(e))

    return ToolInfo(
        id="mcp_read_resource",
        description="Read a resource from a connected MCP server by URI. Use this to fetch context from MCP resources.",
        parameters=ReadResourceParams,
        execute=executor,
        sandbox_required=True,
    )
