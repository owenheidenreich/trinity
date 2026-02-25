"""
Trinity Backend - Route Blueprints
===================================
Extracted from inference_server.py (Phase 3.1)

Blueprints:
  - health_bp:      /health, /health/icp, /metrics, /stats
  - admin_bp:       /admin/*
  - generate_bp:    /generate/agent
  - chat_bp:        /chat/*
  - memory_bp:      /user/memory*
  - user_bp:        /user/status, /user/stats, /user/export
  - tools_bp:       /tools/*
  - session_bp:     /session/*, /funding/*
  - mcp_bp:         /mcp
  - passphrase_bp:  /api/passphrase/*
"""

from .health import health_bp
from .admin import admin_bp
from .generate import generate_bp
from .chat import chat_bp
from .memory import memory_bp
from .user import user_bp
from .tools import tools_bp
from .session import session_bp
from .mcp import mcp_bp
from .passphrase import passphrase_bp

ALL_BLUEPRINTS = [
    health_bp,
    admin_bp,
    generate_bp,
    chat_bp,
    memory_bp,
    user_bp,
    tools_bp,
    session_bp,
    mcp_bp,
    passphrase_bp,
]

__all__ = [
    "health_bp",
    "admin_bp",
    "generate_bp",
    "chat_bp",
    "memory_bp",
    "user_bp",
    "tools_bp",
    "session_bp",
    "mcp_bp",
    "passphrase_bp",
    "ALL_BLUEPRINTS",
]
