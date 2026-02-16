"""
Trinity Backend - Route Blueprints
===================================
Extracted from inference_server.py (Phase 3.1)

Blueprints:
  - health_bp:      /health, /health/icp, /metrics, /stats
  - admin_bp:       /admin/*
  - generate_bp:    /generate, /generate/agent
  - chat_bp:        /chat/*, /user/status, /user/memory*
  - tools_bp:       /tools/*
  - v4_bp:          /v4/*
  - session_bp:     /session/*, /funding/*
  - mcp_bp:         /mcp
  - passphrase_bp:  /api/passphrase/*
"""

from .health import health_bp
from .admin import admin_bp
from .generate import generate_bp
from .chat import chat_bp
from .tools import tools_bp
from .v4 import v4_bp
from .session import session_bp
from .mcp import mcp_bp
from .passphrase import passphrase_bp

ALL_BLUEPRINTS = [
    health_bp,
    admin_bp,
    generate_bp,
    chat_bp,
    tools_bp,
    v4_bp,
    session_bp,
    mcp_bp,
    passphrase_bp,
]

__all__ = [
    "health_bp",
    "admin_bp",
    "generate_bp",
    "chat_bp",
    "tools_bp",
    "v4_bp",
    "session_bp",
    "mcp_bp",
    "passphrase_bp",
    "ALL_BLUEPRINTS",
]
