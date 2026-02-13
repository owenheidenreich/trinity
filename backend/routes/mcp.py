"""
Trinity MCP HTTP Route

Exposes Trinity's tools via MCP JSON-RPC 2.0 over HTTP POST.
This implements the Streamable HTTP transport (MCP spec 2025-03-26).

Endpoints:
    POST /mcp  — Handle JSON-RPC 2.0 messages (initialize, tools/list, tools/call)
    GET  /mcp  — Server info and capabilities

Authentication: Uses Trinity's standard Ed25519 auth when available,
falls back to unauthenticated access for local development.
"""

import logging

from flask import Blueprint, Response, jsonify, request

from config import MCP_SERVER_ENABLED

logger = logging.getLogger(__name__)

mcp_bp = Blueprint("mcp", __name__)


@mcp_bp.route("/mcp", methods=["GET"])
def mcp_info():
    """Return MCP server info and capabilities."""
    if not MCP_SERVER_ENABLED:
        return jsonify({"error": "MCP server is disabled"}), 503

    from services.mcp_server import (
        MCP_PROTOCOL_VERSION,
        MCP_SERVER_NAME,
        MCP_SERVER_VERSION,
    )

    return jsonify({
        "name": MCP_SERVER_NAME,
        "version": MCP_SERVER_VERSION,
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "transport": "streamable-http",
        "capabilities": {
            "tools": {"listChanged": False},
        },
    })


@mcp_bp.route("/mcp", methods=["POST"])
def mcp_endpoint():
    """
    Handle MCP JSON-RPC 2.0 messages.

    Supports:
        initialize     — Protocol handshake
        tools/list     — List available tools
        tools/call     — Execute a tool
        ping           — Health check
    """
    if not MCP_SERVER_ENABLED:
        return jsonify({
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32000, "message": "MCP server is disabled"},
        }), 503

    message = request.get_json(silent=True)
    if not message:
        return jsonify({
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error: invalid JSON"},
        }), 400

    # Extract principal_id from auth header if available
    context = _get_context_from_request()

    from services.mcp_server import handle_mcp_message

    response = handle_mcp_message(message, context=context)

    # Notifications don't get responses
    if response is None:
        return Response(status=204)

    return jsonify(response)


def _get_context_from_request() -> dict:
    """Extract context (principal_id) from the request if authenticated."""
    context = {}

    # Try to get principal from Trinity's auth system
    principal_id = request.headers.get("X-Principal-Id")
    if principal_id:
        context["principal_id"] = principal_id

    return context
