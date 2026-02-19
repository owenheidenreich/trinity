"""
Trinity Inference Server — App Factory
========================================
Production backend using Ollama for model inference.

Phase 3.1 refactor: all route handlers live in routes/ blueprints.
This file creates the Flask app, registers blueprints, hooks, and scheduler.
"""

import time
import atexit
import threading
from pathlib import Path
from urllib.parse import urlparse

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, request
from flask_compress import Compress
from flask_cors import CORS

from config import (
    CHAT_INACTIVE_DAYS,
    CHATS_DIR,
    MAX_QUEUE_SIZE,
    MODEL_BACKEND,
    MODEL_NAME,
    PROVIDER_ID,
    GPU_TYPE,
    logger,
)
from services.provider_factory import get_provider
from services.state_checkpoint import checkpoint_all_state_stores

# Route blueprints
from routes import ALL_BLUEPRINTS

# ===========================================================================
# Runtime feature flags
# ===========================================================================

# Keep legacy-named config keys for API compatibility, but source them from
# canonical runtime behavior instead of import-probing sidecar modules.
V4_IMPORT_ERROR = None
V4_FEATURES = {
    "embeddings": True,          # canonical embeddings tables in state.db
    "vector_store": False,       # sidecar vectors.db is retired from runtime path
    "semantic_memory": True,
    "tools": True,
    "code_executor": True,
    "structured": True,
}
V4_FEATURES_AVAILABLE = True

MCP_SERVER_AVAILABLE = False
MCP_CLIENT_TOOLS = 0
try:
    from services.mcp_server import MCP_SERVER_AVAILABLE  # noqa: F811
    logger.info(f"✅ MCP server: {'ENABLED' if MCP_SERVER_AVAILABLE else 'DISABLED'}")
except Exception as e:
    logger.warning(f"⚠️ MCP server not available: {e}")

try:
    from services.mcp_client import initialize_mcp_client
    MCP_CLIENT_TOOLS = initialize_mcp_client()
    if MCP_CLIENT_TOOLS > 0:
        logger.info(f"✅ MCP client: {MCP_CLIENT_TOOLS} external tools discovered")
except Exception as e:
    logger.debug(f"MCP client init: {e}")


# ===========================================================================
# Flask App Creation
# ===========================================================================

app = Flask(__name__)

Compress(app)

# CORS origins
ALLOWED_ORIGINS = [
    "https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io",
    "https://zc67k-kiaaa-aaaal-qtmiq-cai.raw.icp0.io",
    "https://dubya.ai",
    "https://www.dubya.ai",
    "https://api.dubya.ai",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]

CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

# Store feature flags on app.config so blueprints can access them
app.config["V4_FEATURES_AVAILABLE"] = V4_FEATURES_AVAILABLE
app.config["V4_IMPORT_ERROR"] = V4_IMPORT_ERROR
app.config["V4_FEATURES"] = V4_FEATURES
app.config["MCP_SERVER_AVAILABLE"] = MCP_SERVER_AVAILABLE
app.config["MCP_CLIENT_TOOLS"] = MCP_CLIENT_TOOLS


def _startup_state_integrity_scan(max_users: int = 500):
    """
    Validate canonical state.db schema for existing principals before serving.
    Any corrupt/mismatched DB is self-healed by get_state_store().
    """
    try:
        from services.state_store import get_state_store

        root = Path(CHATS_DIR)
        if not root.exists():
            return

        scanned = 0
        healed = 0
        for child in root.iterdir():
            if scanned >= max_users:
                break
            if not child.is_dir():
                continue
            principal_id = child.name
            try:
                store = get_state_store(principal_id)
                store.ensure_required_schema()
                scanned += 1
            except Exception as e:
                healed += 1
                logger.warning(
                    "⚠️ Startup integrity scan self-healed %s: %s",
                    principal_id[:16],
                    e,
                )
        if scanned or healed:
            logger.info(
                "✅ Startup integrity scan complete: scanned=%s healed=%s",
                scanned,
                healed,
            )
    except Exception as e:
        logger.warning("⚠️ Startup state integrity scan skipped: %s", e)


# ===========================================================================
# Register Blueprints
# ===========================================================================

_startup_state_integrity_scan()

for bp in ALL_BLUEPRINTS:
    app.register_blueprint(bp)
    logger.info(f"  📦 Registered blueprint: {bp.name}")

# ===========================================================================
# Request Hooks
# ===========================================================================


@app.before_request
def log_request():
    """Log all incoming requests for debugging"""
    logger.debug(f"{request.method} {request.path} from {request.remote_addr}")


@app.before_request
def validate_origin():
    """
    CSRF protection via Origin/Referer checking.
    Ed25519 signatures already prevent CSRF on authenticated endpoints,
    but this adds defense-in-depth for state-changing requests.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    if request.path in ("/health", "/health/icp", "/metrics"):
        return

    origin = request.headers.get("Origin") or request.headers.get("Referer")
    if not origin:
        return

    parsed = urlparse(origin)
    origin_base = f"{parsed.scheme}://{parsed.netloc}"

    if origin_base not in ALLOWED_ORIGINS:
        logger.warning(f"🚨 Origin validation failed: {origin_base} from {request.remote_addr}")
        return jsonify({
            "error": {
                "code": 403,
                "message": "Request origin not allowed",
            }
        }), 403


@app.after_request
def add_rate_limit_response_headers(response):
    """Add X-RateLimit-* headers to all responses."""
    ip = request.remote_addr or "unknown"
    try:
        from middleware.rate_limit import add_rate_limit_headers
        add_rate_limit_headers(response, ip)
    except Exception:
        pass
    return response


# ===========================================================================
# Error Handlers
# ===========================================================================


@app.errorhandler(404)
def not_found(e):
    return (
        jsonify(
            {
                "error": "Endpoint not found",
                "provider_id": PROVIDER_ID,
                "available_endpoints": [
                    "/health",
                    "/generate/agent",
                    "/stats",
                    "/chat/start",
                    "/chat/list",
                    "/chat/{chatId}",
                    "/chat/{chatId} [PATCH|DELETE]",
                    "/user/memory",
                    "/user/memory/fact",
                ],
            }
        ),
        404,
    )


@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {e}", exc_info=True)
    return jsonify({"error": "Internal server error", "provider_id": PROVIDER_ID}), 500


# ===========================================================================
# Background Scheduler — 7-day chat auto-delete
# ===========================================================================


def cleanup_inactive_chats():
    """Delete inactive chats from canonical state store (except archived/pinned)."""
    try:
        logger.info("Running 7-day cleanup job...")
        chats_root = Path(CHATS_DIR)
        current_time = time.time()
        inactive_seconds = CHAT_INACTIVE_DAYS * 24 * 60 * 60
        deleted_count = 0
        from services.state_store import get_state_store

        for principal_dir in chats_root.iterdir():
            if not principal_dir.is_dir():
                continue

            principal_id = principal_dir.name
            state_db_path = principal_dir / "state.db"
            if not state_db_path.exists():
                continue

            try:
                store = get_state_store(principal_id)
                chats = store.list_chats(include_archived=True, limit=1000)
                for chat in chats:
                    if chat.get("archived") or chat.get("pinned"):
                        continue
                    last_updated = float(chat.get("lastUpdated", 0)) / 1000.0
                    if current_time - last_updated <= inactive_seconds:
                        continue
                    chat_id = str(chat.get("chatId", ""))
                    if not chat_id:
                        continue
                    if store.delete_chat(chat_id):
                        deleted_count += 1
                        logger.info("Deleted inactive chat from canonical store: %s", chat_id[:16])
            except Exception as e:
                logger.error(f"Error processing user {principal_id}: {e}")
                continue

        logger.info(f"Cleanup complete: deleted {deleted_count} inactive chats")

    except Exception as e:
        logger.error(f"Cleanup job error: {e}", exc_info=True)


scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_inactive_chats, "cron", hour=2, minute=0, id="chat_cleanup")
scheduler.add_job(
    checkpoint_all_state_stores,
    "interval",
    minutes=15,
    id="state_db_checkpoint",
    kwargs={"max_users": 200},
)
atexit.register(lambda: checkpoint_all_state_stores(max_users=500))


def _bootstrap_state_checkpoints_async(max_users: int = 200):
    """
    Best-effort startup restore for principals missing local canonical state.
    Does not block boot path.
    """
    def _run():
        try:
            from services.state_checkpoint import restore_state_checkpoint_from_ipfs

            root = Path(CHATS_DIR)
            if not root.exists():
                return
            processed = 0
            for child in root.iterdir():
                if processed >= max_users:
                    break
                if not child.is_dir():
                    continue
                state_db = child / "state.db"
                if state_db.exists() and state_db.stat().st_size > 0:
                    continue
                principal_id = child.name
                try:
                    restore_state_checkpoint_from_ipfs(principal_id)
                except Exception as e:
                    logger.debug("Startup checkpoint restore skipped for %s: %s", principal_id[:16], e)
                processed += 1
        except Exception as e:
            logger.debug("Startup checkpoint bootstrap failed: %s", e)

    threading.Thread(target=_run, daemon=True, name="state-checkpoint-bootstrap").start()


_bootstrap_state_checkpoints_async()


# ===========================================================================
# Startup
# ===========================================================================


if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("🚀 Trinity Inference Server — Unified Backend")
    logger.info("=" * 70)
    logger.info(f"Backend: {MODEL_BACKEND}")
    logger.info(f"Model: {MODEL_NAME}")
    logger.info(f"Provider ID: {PROVIDER_ID}")
    logger.info(f"GPU Type: {GPU_TYPE}")
    logger.info(f"Max Queue Size: {MAX_QUEUE_SIZE}")
    logger.info(f"Chats Directory: {CHATS_DIR}")
    logger.info("=" * 70)

    # Initialize the LLM provider and verify connection
    provider = get_provider()
    logger.info(f"🔧 Provider: {provider}")

    if provider.check_connection():
        logger.info(f"✅ Successfully connected to {provider.backend_name} ({MODEL_NAME})")
        provider.warmup()
    else:
        logger.warning(f"⚠️  Could not connect to {provider.backend_name} — server will start anyway")
        logger.warning("   Make sure Ollama is running: ollama serve")
        logger.warning(f"   Make sure model is available: ollama pull {MODEL_NAME}")

    if not scheduler.running:
        scheduler.start()
        logger.info("✅ Cleanup scheduler started (runs daily at 2 AM)")

    logger.info("🌐 Starting Flask server on port 8000")
    logger.info("=" * 70)

    app.run(host="0.0.0.0", port=8000, threaded=True, debug=False)
