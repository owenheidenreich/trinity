"""
Trinity Backend - Route Blueprints
===================================
Extracted from inference_server.py (Phase 3.1)

Blueprints:
  - health_bp:      /health, /health/icp, /metrics, /stats
  - generate_bp:    /generate/agent
  - chat_bp:        /chat/*
  - memory_bp:      /user/memory*
  - user_bp:        /user/status, /user/stats, /user/export
  - tools_bp:       /tools/*
  - passphrase_bp:  /api/passphrase/*
"""

from .health import health_bp
from .generate import generate_bp
from .chat import chat_bp
from .memory import memory_bp
from .user import user_bp
from .tools import tools_bp
from .passphrase import passphrase_bp

ALL_BLUEPRINTS = [
    health_bp,
    generate_bp,
    chat_bp,
    memory_bp,
    user_bp,
    tools_bp,
    passphrase_bp,
]

__all__ = [
    "health_bp",
    "generate_bp",
    "chat_bp",
    "memory_bp",
    "user_bp",
    "tools_bp",
    "passphrase_bp",
    "ALL_BLUEPRINTS",
]
