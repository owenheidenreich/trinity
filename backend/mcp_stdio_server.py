#!/usr/bin/env python3
"""
Trinity MCP Server — stdio transport entry point

Exposes Trinity's 8 tools (calculator, web_search, fact_check,
document_search, code_display, save_memory, recall_memory, search_memory)
via MCP stdio transport.

Usage:
    python mcp_stdio_server.py

Configure in Claude Desktop (claude_desktop_config.json):
    {
      "mcpServers": {
        "trinity": {
          "command": "python3",
          "args": ["/path/to/backend/mcp_stdio_server.py"],
          "env": {
            "BRAVE_SEARCH_API_KEY": "your-key-here"
          }
        }
      }
    }
"""

import asyncio
import os
import sys

# Add backend to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def main():
    from mcp.server.stdio import stdio_server

    from services.mcp_server import create_async_mcp_server

    server = create_async_mcp_server()
    if server is None:
        print("Error: mcp package not installed. Run: pip install mcp", file=sys.stderr)
        sys.exit(1)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
