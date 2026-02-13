"""
Trinity MCP Server

Exposes Trinity's 8 tools via Model Context Protocol (MCP).
Can be used with stdio transport (Claude Desktop) or HTTP (Flask route).

Usage:
  - stdio: python backend/mcp_stdio_server.py
  - HTTP:  POST /mcp  (JSON-RPC 2.0)
"""

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_SERVER_NAME = "trinity"
MCP_SERVER_VERSION = "1.0.0"


def _build_tool_schema(name: str, defn: dict) -> dict:
    """Convert a Trinity TOOL_DEFINITIONS entry to MCP JSON Schema."""
    properties = {}
    required = []
    for param_name, param_desc in defn["params"].items():
        properties[param_name] = {
            "type": "string",
            "description": param_desc,
        }
        required.append(param_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def get_mcp_tool_list() -> List[dict]:
    """
    Get Trinity's tools in MCP Tool format.

    Returns:
        List of MCP Tool dicts with name, description, inputSchema
    """
    from .tools import TOOL_DEFINITIONS

    tools = []
    for name, defn in TOOL_DEFINITIONS.items():
        tools.append({
            "name": name,
            "description": defn["description"],
            "inputSchema": _build_tool_schema(name, defn),
        })
    return tools


def call_mcp_tool(
    name: str, arguments: dict, context: dict = None
) -> Tuple[List[dict], bool]:
    """
    Execute a tool via MCP call_tool protocol.

    Args:
        name: Tool name
        arguments: Tool arguments dict
        context: Optional context with principal_id

    Returns:
        (content_blocks, is_error) tuple
    """
    from .code_executor import execute_tool

    success, result = execute_tool(name, arguments, context=context)
    content = [{"type": "text", "text": result}]
    return content, not success


def handle_mcp_message(message: dict, context: dict = None) -> dict:
    """
    Handle an MCP JSON-RPC 2.0 message and return the response.

    Supports:
        - initialize: Protocol handshake
        - tools/list: List available tools
        - tools/call: Execute a tool
        - ping: Health check

    Args:
        message: JSON-RPC 2.0 request
        context: Optional context with principal_id

    Returns:
        JSON-RPC 2.0 response dict
    """
    msg_id = message.get("id")
    method = message.get("method", "")
    params = message.get("params", {})

    try:
        if method == "initialize":
            result = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {
                    "name": MCP_SERVER_NAME,
                    "version": MCP_SERVER_VERSION,
                },
            }

        elif method == "notifications/initialized":
            # Client acknowledgment — no response needed for notifications
            return None

        elif method == "ping":
            result = {}

        elif method == "tools/list":
            result = {"tools": get_mcp_tool_list()}

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            content, is_error = call_mcp_tool(tool_name, arguments, context=context)
            result = {"content": content, "isError": is_error}

        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            }

        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    except Exception as e:
        logger.error(f"MCP handler error for {method}: {e}")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}",
            },
        }


# ============================================================================
# ASYNC MCP SERVER (for stdio transport via mcp SDK)
# ============================================================================


def create_async_mcp_server(context: dict = None):
    """
    Create an async MCP Server using the mcp SDK.

    Used by mcp_stdio_server.py for stdio transport.
    Returns None if the mcp package is not installed.

    Args:
        context: Optional context dict with principal_id

    Returns:
        mcp.server.Server instance or None
    """
    try:
        from mcp.server import Server
        from mcp.types import TextContent, Tool
    except ImportError:
        logger.warning("mcp package not installed — async MCP server unavailable")
        return None

    from .code_executor import execute_tool
    from .tools import TOOL_DEFINITIONS

    server = Server(MCP_SERVER_NAME)
    tool_context = context or {}

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        tools = []
        for name, defn in TOOL_DEFINITIONS.items():
            tools.append(
                Tool(
                    name=name,
                    description=defn["description"],
                    inputSchema=_build_tool_schema(name, defn),
                )
            )
        return tools

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
        success, result = execute_tool(name, arguments, context=tool_context)
        return [TextContent(type="text", text=result)]

    return server


# Module availability
MCP_SERVER_AVAILABLE = True
