"""MCP (Model Context Protocol) client for stdio and remote servers."""
import asyncio
from dataclasses import dataclass, field
from typing import Any

from core.log import create_logger

log = create_logger("mcp")


@dataclass
class McpTool:
    name: str
    description: str
    input_schema: dict = field(default_factory=dict)


@dataclass
class McpServer:
    name: str
    type: str  # "stdio" or "remote"
    status: str = "disconnected"  # "connected", "disconnected", "error"
    tools: list[McpTool] = field(default_factory=list)
    error: str | None = None
    _session: Any = field(default=None, repr=False)


class McpClient:
    """MCP client for communicating with MCP servers."""

    def __init__(self):
        self._servers: dict[str, McpServer] = {}

    async def connect(self, name: str, config: dict) -> McpServer:
        """Connect to an MCP server."""
        server_type = config.get("type", "local")

        server = McpServer(
            name=name,
            type=server_type,
        )

        try:
            if server_type == "local":
                await self._connect_stdio(server, config)
            else:
                await self._connect_remote(server, config)

            server.status = "connected"
            self._servers[name] = server
            log.info(f"Connected to MCP server: {name}")

        except Exception as e:
            server.status = "error"
            server.error = str(e)
            self._servers[name] = server
            log.error(f"Failed to connect to MCP server {name}: {e}")

        return server

    async def disconnect(self, name: str) -> None:
        """Disconnect from an MCP server."""
        server = self._servers.pop(name, None)
        if server:
            server.status = "disconnected"
            log.info(f"Disconnected from MCP server: {name}")

    async def _connect_stdio(self, server: McpServer, config: dict) -> None:
        """Connect via stdio transport."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            command = config.get("command", [])
            if not command:
                raise ValueError("No command specified for stdio MCP server")

            params = StdioServerParameters(
                command=command[0],
                args=command[1:] if len(command) > 1 else [],
                env=config.get("env", {}),
            )

            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # List tools
                    response = await session.list_tools()
                    server.tools = [
                        McpTool(
                            name=t.name,
                            description=t.description or "",
                            input_schema=t.inputSchema if hasattr(t, "inputSchema") else {},
                        )
                        for t in response.tools
                    ]
        except ImportError:
            log.warning("MCP SDK not installed. Install with: pip install mcp")
            raise

    async def _connect_remote(self, server: McpServer, config: dict, user_id: str = "default") -> None:
        """Connect via HTTP/SSE transport.

        Uses the MCP SDK's sse_client for remote HTTP-based MCP servers.
        Injects OAuth Authorization header if token is available (F8).
        """
        url = config.get("url")
        if not url:
            raise ValueError("No URL specified for remote MCP server")

        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client

            headers = dict(config.get("headers", {}))

            # F8: Inject OAuth token if available
            try:
                from mcp.oauth import get_token, load_token
                token = get_token(user_id, server.name) or await load_token(user_id, server.name)
                if token:
                    if token.expired and token.refresh_token:
                        oauth_cfg_data = config.get("oauth")
                        if oauth_cfg_data:
                            from mcp.oauth_provider import OAuthConfig, refresh_token
                            oa = OAuthConfig(**oauth_cfg_data)
                            token = await refresh_token(oa, token.refresh_token, server.name, user_id)
                    if token and not token.expired:
                        headers["Authorization"] = f"{token.token_type} {token.access_token}"
            except Exception as e:
                log.debug(f"OAuth token injection skipped for {server.name}: {e}")

            async with sse_client(url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # List available tools
                    response = await session.list_tools()
                    server.tools = [
                        McpTool(
                            name=t.name,
                            description=t.description or "",
                            input_schema=t.inputSchema if hasattr(t, "inputSchema") else {},
                        )
                        for t in response.tools
                    ]
                    server._session = session

                    log.info(f"Remote MCP server {server.name}: {len(server.tools)} tools discovered")

        except ImportError:
            log.warning("MCP SDK not installed. Install with: pip install mcp")
            raise
        except Exception as e:
            raise ConnectionError(f"Failed to connect to remote MCP server at {url}: {e}")

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """Call a tool on a connected MCP server."""
        server = self._servers.get(server_name)
        if not server or server.status != "connected":
            raise RuntimeError(f"MCP server {server_name} is not connected")

        if not server._session:
            raise RuntimeError(f"MCP server {server_name} has no active session")

        try:
            result = await server._session.call_tool(tool_name, arguments)
            return result
        except Exception as e:
            log.error(f"MCP tool call failed: {server_name}/{tool_name}: {e}")
            raise

    def list_servers(self) -> list[McpServer]:
        """List all MCP servers."""
        return list(self._servers.values())

    def get_all_tools(self) -> dict[str, McpTool]:
        """Get all tools from all connected servers."""
        tools = {}
        for server in self._servers.values():
            if server.status == "connected":
                for tool in server.tools:
                    key = f"{server.name}_{tool.name}"
                    tools[key] = tool
        return tools


# Singleton
mcp_client = McpClient()
