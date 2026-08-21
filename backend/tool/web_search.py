"""Web search tool: search the web using DuckDuckGo or configurable endpoint."""
import json

from pydantic import BaseModel, Field

from tool.tool import ToolResult, ToolContext, define_tool
from core.log import create_logger

log = create_logger("tool.web_search")


class WebSearchArgs(BaseModel):
    query: str = Field(description="Search query")
    max_results: int = Field(default=5, description="Maximum number of results to return")
    search_depth: str = Field(
        default="basic",
        description="Search depth: 'basic' (balanced), 'advanced' (highest relevance, 2x cost), 'fast' (lower latency), 'ultra-fast' (minimum latency). Only used with Tavily provider.",
    )
    topic: str = Field(
        default="general",
        description="Search topic: 'general', 'news' (real-time events), or 'finance'. Only used with Tavily provider.",
    )
    time_range: str | None = Field(
        default=None,
        description="Filter results by recency: 'day', 'week', 'month', or 'year'. Only used with Tavily provider.",
    )
    include_answer: bool = Field(
        default=False,
        description="Include an LLM-generated answer summarizing results. Only used with Tavily provider.",
    )


async def execute(args: WebSearchArgs, ctx: ToolContext) -> ToolResult:
    """Search the web using configured provider.

    Priority: Tavily (if configured) → custom endpoint → DuckDuckGo (default).
    """
    try:
        from core.config import get_config
        import os
        config = get_config()
        provider = config.provider
        search_config = provider.get("search", None)

        if search_config:
            search_type = search_config.options.get("type", "").lower() if search_config.options else ""
            api_key = search_config.api_key or search_config.options.get("api_key", "")

            # Tavily: explicit type or api_key starts with "tvly-"
            if search_type == "tavily" or (api_key and api_key.startswith("tvly-")):
                if api_key:
                    return await _search_tavily(args, api_key)
                else:
                    log.warning("Tavily search configured but no API key provided")

            # Custom endpoint
            endpoint = search_config.options.get("endpoint", "") if search_config.options else ""
            if endpoint:
                if "tavily.com" in endpoint:
                    return await _search_tavily(args, api_key)
                return await _search_custom(args.query, args.max_results, endpoint, api_key)

        # Also check TAVILY_API_KEY env var
        tavily_key = os.environ.get("TAVILY_API_KEY", "")
        if tavily_key:
            return await _search_tavily(args, tavily_key)

    except Exception:
        pass

    # Default: use DuckDuckGo HTML scraping
    return await _search_duckduckgo(args.query, args.max_results)


async def _search_tavily(args: WebSearchArgs, api_key: str) -> ToolResult:
    """Search using Tavily API (POST https://api.tavily.com/search)."""
    try:
        import httpx

        body: dict = {
            "query": args.query,
            "max_results": min(args.max_results, 20),
            "search_depth": args.search_depth,
            "topic": args.topic,
            "include_answer": args.include_answer,
            "include_raw_content": False,
            "include_images": False,
        }
        if args.time_range:
            body["time_range"] = args.time_range

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        output_lines = [f"Search results for: {args.query}\n"]

        # Include LLM-generated answer if requested
        answer = data.get("answer")
        if answer:
            output_lines.append(f"Answer: {answer}\n")

        if not results:
            if not answer:
                return ToolResult(
                    title=f"Search: {args.query}",
                    output=f"No results found for: {args.query}",
                )
        else:
            for i, result in enumerate(results[:args.max_results], 1):
                output_lines.append(f"{i}. {result.get('title', '')}")
                if result.get("url"):
                    output_lines.append(f"   URL: {result['url']}")
                if result.get("content"):
                    output_lines.append(f"   {result['content']}")
                if result.get("score"):
                    output_lines.append(f"   Score: {result['score']:.2f}")
                output_lines.append("")

        return ToolResult(
            title=f"Search: {args.query} ({len(results)} results)",
            output="\n".join(output_lines),
            metadata={
                "query": args.query,
                "results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", ""),
                    }
                    for r in results[: args.max_results]
                ],
            },
        )

    except Exception as e:
        log.warning(f"Tavily search failed: {e}")
        log.info("Falling back to DuckDuckGo search")
        return await _search_duckduckgo(args.query, args.max_results)


async def _search_duckduckgo(query: str, max_results: int) -> ToolResult:
    """Search using DuckDuckGo HTML endpoint."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            # Use DuckDuckGo Lite (HTML version)
            resp = await client.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query},
                headers={"User-Agent": "OpenAgent/1.0"},
            )
            resp.raise_for_status()

            results = _parse_ddg_html(resp.text, max_results)

            if not results:
                return ToolResult(
                    title=f"Search: {query}",
                    output=f"No results found for: {query}",
                )

            output_lines = [f"Search results for: {query}\n"]
            for i, result in enumerate(results, 1):
                output_lines.append(f"{i}. {result['title']}")
                if result.get("url"):
                    output_lines.append(f"   URL: {result['url']}")
                if result.get("snippet"):
                    output_lines.append(f"   {result['snippet']}")
                output_lines.append("")

            return ToolResult(
                title=f"Search: {query} ({len(results)} results)",
                output="\n".join(output_lines),
                metadata={
                    "query": query,
                    "results": [
                        {
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "snippet": r.get("snippet", ""),
                        }
                        for r in results
                    ],
                },
            )

    except ImportError:
        return ToolResult(
            title=f"Search: {query}",
            output="httpx is required for web search. Install with: pip install httpx",
        )
    except Exception as e:
        log.warning(f"DuckDuckGo search failed: {e}")
        return ToolResult(
            title=f"Search: {query}",
            output=f"Search failed: {e}",
        )


async def _search_custom(query: str, max_results: int, endpoint: str, api_key: str | None) -> ToolResult:
    """Search using a custom API endpoint (e.g., SearXNG, Brave, Serper)."""
    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                endpoint,
                params={"q": query, "format": "json", "count": max_results},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

            # Try common response formats
            results = data.get("results", data.get("organic", data.get("items", [])))

            output_lines = [f"Search results for: {query}\n"]
            for i, result in enumerate(results[:max_results], 1):
                title = result.get("title", result.get("name", ""))
                url = result.get("url", result.get("link", ""))
                snippet = result.get("content", result.get("snippet", result.get("description", "")))
                output_lines.append(f"{i}. {title}")
                if url:
                    output_lines.append(f"   URL: {url}")
                if snippet:
                    output_lines.append(f"   {snippet}")
                output_lines.append("")

            return ToolResult(
                title=f"Search: {query} ({min(len(results), max_results)} results)",
                output="\n".join(output_lines),
            )

    except Exception as e:
        log.warning(f"Custom search failed: {e}")
        return ToolResult(
            title=f"Search: {query}",
            output=f"Search failed: {e}",
        )


def _parse_ddg_html(html: str, max_results: int) -> list[dict]:
    """Parse DuckDuckGo Lite HTML response to extract results."""
    results = []

    # Simple HTML parsing without external dependencies
    # DuckDuckGo Lite returns results in <a class="result-link"> tags
    import re

    # Pattern for result links
    link_pattern = re.compile(
        r'<a[^>]*class="result-link"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    # Pattern for result snippets
    snippet_pattern = re.compile(
        r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>',
        re.DOTALL,
    )

    links = link_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i, (url, title) in enumerate(links):
        if i >= max_results:
            break

        # Clean HTML tags from title and snippet
        clean_title = re.sub(r"<[^>]+>", "", title).strip()
        clean_snippet = ""
        if i < len(snippets):
            clean_snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()

        if clean_title:
            results.append({
                "title": clean_title,
                "url": url,
                "snippet": clean_snippet,
            })

    # Fallback: try parsing table-based results (DDG Lite alternative format)
    if not results:
        # Look for links in result rows
        row_pattern = re.compile(
            r'<a[^>]*rel="nofollow"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        for i, (url, title) in enumerate(row_pattern.findall(html)):
            if i >= max_results:
                break
            clean_title = re.sub(r"<[^>]+>", "", title).strip()
            if clean_title and url.startswith("http"):
                results.append({
                    "title": clean_title,
                    "url": url,
                    "snippet": "",
                })

    return results


web_search_tool = define_tool(
    "web_search",
    description="""\
Search the web for information. Returns search results with titles, URLs, and snippets.

Usage tips:
- Use search_depth="basic" (default) for everyday queries. Use "advanced" for complex research needing high relevance (costs 2x).
- Set topic="news" for real-time events (politics, sports, breaking news). Use "finance" for market/financial data.
- Set time_range="day" or "week" to find only recent results.
- Set include_answer=true when you need a quick summarized answer in addition to source links.
- For simple factual lookups, include_answer=true with max_results=3 is usually sufficient.
- For deep research, use search_depth="advanced" with max_results=10 and review the full results.""",
    parameters=WebSearchArgs,
    execute=execute,
    sandbox_required=False,
)
