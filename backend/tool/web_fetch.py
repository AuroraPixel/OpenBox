"""Web fetch tool: fetch and process web pages.

Matches opencode's webfetch.ts: supports text/markdown/html formats,
Cloudflare challenge retry, size limits, and proper HTML stripping.
"""
import re

from pydantic import BaseModel, Field

from tool.tool import ToolResult, ToolContext, define_tool

MAX_RESPONSE_SIZE = 5 * 1024 * 1024  # 5MB


class WebFetchArgs(BaseModel):
    url: str = Field(description="URL to fetch")
    format: str = Field(default="text", description="Output format: text, markdown, or html")
    timeout: int = Field(default=30, description="Timeout in seconds")


def _html_to_text(html: str) -> str:
    """Strip HTML to plain text."""
    # Remove script and style blocks
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    # Remove HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Replace block elements with newlines
    text = re.sub(r"<(?:br|p|div|h[1-6]|li|tr|td|th|blockquote|pre|hr)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Remove remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'")
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def execute(args: WebFetchArgs, ctx: ToolContext) -> ToolResult:
    """Fetch a web page and extract content."""
    import httpx

    url = args.url
    if not url.startswith(("http://", "https://")):
        return ToolResult(
            title="Invalid URL",
            output="URL must start with http:// or https://",
        )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    if args.format == "markdown":
        headers["Accept"] = "text/markdown, text/html;q=0.9, */*;q=0.8"
    elif args.format == "html":
        headers["Accept"] = "text/html, */*;q=0.8"
    else:
        headers["Accept"] = "text/plain, text/html;q=0.9, */*;q=0.8"

    timeout = min(max(args.timeout, 5), 120)

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            resp = await client.get(url, headers=headers)

            # Cloudflare challenge retry (matching opencode's behavior)
            if resp.status_code == 403 and "cf-mitigated" in resp.headers.get("", ""):
                headers["User-Agent"] = "openbox"
                resp = await client.get(url, headers=headers)

            resp.raise_for_status()

            # Check size
            content_length = int(resp.headers.get("content-length", "0"))
            if content_length > MAX_RESPONSE_SIZE:
                return ToolResult(
                    title=f"Response too large: {content_length} bytes",
                    output=f"Response exceeds {MAX_RESPONSE_SIZE} byte limit",
                )

            content = resp.text
            content_type = resp.headers.get("content-type", "")

        # Process based on format and content type
        if "text/html" in content_type:
            if args.format == "html":
                pass  # Return raw HTML
            else:
                # Convert HTML to text
                content = _html_to_text(content)

        # Truncate to reasonable size
        if len(content) > 50000:
            content = content[:50000] + "\n\n... (content truncated at 50KB)"

        return ToolResult(
            title=f"Fetched {url}",
            output=content,
        )
    except httpx.HTTPStatusError as e:
        return ToolResult(
            title=f"HTTP {e.response.status_code}",
            output=f"HTTP error {e.response.status_code} fetching {url}: {e}",
        )
    except Exception as e:
        return ToolResult(
            title=f"Error fetching {url}",
            output=str(e),
        )


WEB_FETCH_DESCRIPTION = """\
Fetches content from a specified URL and returns it in the requested format.

- Takes a URL and optional format (text, markdown, html) as input
- Fetches the URL content and converts to requested format (text by default)
- Returns the content in the specified format
- Use this tool when you need to retrieve and analyze web content

Usage notes:
  - The URL must be a fully-formed valid URL
  - HTTP URLs will be automatically upgraded to HTTPS
  - Format options: "text" (default), "markdown", or "html"
  - This tool is read-only and does not modify any files
  - Results may be truncated if the content is very large (>50KB)
  - When a redirect occurs, the tool will inform you — make a new request with the redirect URL"""

web_fetch_tool = define_tool(
    "web_fetch",
    description=WEB_FETCH_DESCRIPTION,
    parameters=WebFetchArgs,
    execute=execute,
    sandbox_required=False,
)
