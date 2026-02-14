"""
Trinity MCP Client

Connects to external MCP servers and makes their tools available
to Trinity's ReAct loop and LangGraph agents.

External tools are prefixed with their server name to avoid collisions:
  e.g., "github:search_repos", "slack:send_message"

Configuration via MCP_SERVERS env var:
  [{"name": "github", "url": "http://localhost:3001/sse"}]
"""

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an external MCP server."""

    name: str
    url: str  # SSE endpoint URL


@dataclass
class MCPExternalTool:
    """A tool discovered from an external MCP server."""

    server_name: str
    name: str
    qualified_name: str  # "server:tool"
    description: str
    input_schema: dict


class MCPClientManager:
    """
    Manages connections to external MCP servers.

    Provides sync wrappers around the async MCP client SDK.
    Tools from external servers are available via execute_tool()
    and get_tool_definitions().
    """

    def __init__(self):
        self._tools: Dict[str, MCPExternalTool] = {}
        self._sessions: Dict[str, Any] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._initialized = False
        self._mcp_available = False

        # Check if mcp client SDK is available
        try:
            from mcp import ClientSession  # noqa: F401

            self._mcp_available = True
        except ImportError:
            logger.info("mcp package not installed — MCP client disabled")

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create the background event loop for async operations."""
        if self._loop is None or not self._loop.is_running():
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever, daemon=True, name="mcp-client-loop"
            )
            self._thread.start()
        return self._loop

    def _run_async(self, coro, timeout: float = 30.0):
        """Run an async coroutine from sync context."""
        loop = self._get_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    def initialize(self, server_configs: List[MCPServerConfig]) -> int:
        """
        Connect to configured MCP servers and discover their tools.

        Args:
            server_configs: List of server configurations

        Returns:
            Number of tools discovered
        """
        if not self._mcp_available:
            logger.info("MCP client SDK not available, skipping initialization")
            self._initialized = True
            return 0

        if not server_configs:
            self._initialized = True
            return 0

        total_tools = 0
        for config in server_configs:
            try:
                tools = self._run_async(self._connect_and_discover(config))
                for tool in tools:
                    self._tools[tool.qualified_name] = tool
                total_tools += len(tools)
                logger.info(
                    f"MCP: Discovered {len(tools)} tools from '{config.name}'"
                )
            except Exception as e:
                logger.warning(
                    f"MCP: Failed to connect to '{config.name}' ({config.url}): {e}"
                )

        self._initialized = True
        return total_tools

    async def _connect_and_discover(
        self, config: MCPServerConfig
    ) -> List[MCPExternalTool]:
        """Connect to a single MCP server and discover its tools."""
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        async with sse_client(config.url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.list_tools()
                tools = []
                for tool in result.tools:
                    qualified = f"{config.name}:{tool.name}"
                    tools.append(
                        MCPExternalTool(
                            server_name=config.name,
                            name=tool.name,
                            qualified_name=qualified,
                            description=tool.description or "",
                            input_schema=tool.inputSchema or {},
                        )
                    )

                # Cache session for later tool calls
                self._sessions[config.name] = session
                return tools

    def execute_tool(self, qualified_name: str, params: dict) -> Tuple[bool, str]:
        """
        Execute a tool on its external MCP server.

        Args:
            qualified_name: "server:tool" format
            params: Tool parameters

        Returns:
            (success, result_text) tuple
        """
        tool = self._tools.get(qualified_name)
        if not tool:
            return False, f"Unknown MCP tool: {qualified_name}"

        if not self._mcp_available:
            return False, "MCP client SDK not available"

        try:
            result = self._run_async(self._call_tool_async(tool, params))
            return True, result
        except Exception as e:
            logger.error(f"MCP tool call failed ({qualified_name}): {e}")
            return False, f"MCP tool error: {e}"

    async def _call_tool_async(self, tool: MCPExternalTool, params: dict) -> str:
        """Call a tool on its MCP server."""
        session = self._sessions.get(tool.server_name)
        if not session:
            raise RuntimeError(f"No active session for server '{tool.server_name}'")

        result = await session.call_tool(tool.name, params)

        texts = []
        for content in result.content:
            if hasattr(content, "text"):
                texts.append(content.text)

        return "\n".join(texts) if texts else "No output"

    def has_tool(self, name: str) -> bool:
        """Check if a tool name belongs to an external MCP server."""
        return name in self._tools

    def get_tool_definitions(self) -> Dict[str, dict]:
        """
        Get external MCP tools in Trinity's TOOL_DEFINITIONS format.

        Returns:
            Dict mapping qualified tool names to definition dicts
        """
        definitions = {}
        for qname, tool in self._tools.items():
            params = {}
            schema = tool.input_schema
            if isinstance(schema, dict):
                for prop_name, prop_def in schema.get("properties", {}).items():
                    params[prop_name] = prop_def.get("description", prop_name)

            definitions[qname] = {
                "description": f"[MCP:{tool.server_name}] {tool.description}",
                "params": params,
                "examples": [],
            }
        return definitions

    @property
    def tool_count(self) -> int:
        """Number of external MCP tools available."""
        return len(self._tools)

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def shutdown(self):
        """Clean up background event loop."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=5)
        self._sessions.clear()
        self._tools.clear()


# =============================================================================
# SINGLETON + HELPERS
# =============================================================================

_mcp_client: Optional[MCPClientManager] = None


def get_mcp_client() -> MCPClientManager:
    """Get or create the MCP client manager singleton."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClientManager()
    return _mcp_client


def initialize_mcp_client() -> int:
    """
    Initialize the MCP client from config.

    MCP client feature is currently disabled.
    Returns number of tools discovered (always 0).
    """
    return 0


# Module availability flag
MCP_CLIENT_AVAILABLE = True
