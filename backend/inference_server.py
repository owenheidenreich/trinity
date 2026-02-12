"""
Trinity Inference Server — App Factory
========================================
Production backend using Ollama for model inference.

Phase 3.1 refactor: all route handlers live in routes/ blueprints.
This file creates the Flask app, registers blueprints, hooks, and scheduler.
"""

import json
import time
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
    OLLAMA_HOST,
    PROVIDER_ID,
    GPU_TYPE,
    logger,
)
from services import check_ollama_connection, warmup_model

# Route blueprints
from routes import ALL_BLUEPRINTS

# ===========================================================================
# V4 / LangGraph feature detection (stored on app.config for blueprints)
# ===========================================================================

V4_IMPORT_ERROR = None
V4_EMBEDDINGS_AVAILABLE = False
V4_VECTOR_STORE_AVAILABLE = False
V4_MEMORY_AVAILABLE = False
V4_TOOLS_AVAILABLE = False
V4_CODE_EXECUTOR_AVAILABLE = False
V4_VOTING_AVAILABLE = False
V4_STRUCTURED_AVAILABLE = False

try:
    from services.embeddings import V4_EMBEDDINGS_AVAILABLE
    logger.info(f"✅ embeddings: V4_EMBEDDINGS_AVAILABLE={V4_EMBEDDINGS_AVAILABLE}")
except Exception as e:
    V4_IMPORT_ERROR = f"embeddings: {e}"
    logger.error(f"❌ embeddings import failed: {e}")

try:
    from services.vector_store import V4_VECTOR_STORE_AVAILABLE
    logger.info(f"✅ vector_store: V4_VECTOR_STORE_AVAILABLE={V4_VECTOR_STORE_AVAILABLE}")
except Exception as e:
    V4_IMPORT_ERROR = f"vector_store: {e}"
    logger.error(f"❌ vector_store import failed: {e}")

try:
    from services.memory import V4_MEMORY_AVAILABLE
    logger.info(f"✅ memory: V4_MEMORY_AVAILABLE={V4_MEMORY_AVAILABLE}")
except Exception as e:
    V4_IMPORT_ERROR = f"memory: {e}"
    logger.error(f"❌ memory import failed: {e}")

try:
    from services.tools import V4_TOOLS_AVAILABLE
    logger.info(f"✅ tools: V4_TOOLS_AVAILABLE={V4_TOOLS_AVAILABLE}")
except Exception as e:
    V4_IMPORT_ERROR = f"tools: {e}"
    logger.error(f"❌ tools import failed: {e}")

try:
    from services.code_executor import V4_CODE_EXECUTOR_AVAILABLE
    logger.info(f"✅ code_executor: V4_CODE_EXECUTOR_AVAILABLE={V4_CODE_EXECUTOR_AVAILABLE}")
except Exception as e:
    V4_IMPORT_ERROR = f"code_executor: {e}"
    logger.error(f"❌ code_executor import failed: {e}")

try:
    from services.voting import V4_VOTING_AVAILABLE
    logger.info(f"✅ voting: V4_VOTING_AVAILABLE={V4_VOTING_AVAILABLE}")
except Exception as e:
    V4_IMPORT_ERROR = f"voting: {e}"
    logger.error(f"❌ voting import failed: {e}")

try:
    from services.structured import V4_STRUCTURED_AVAILABLE
    logger.info(f"✅ structured: V4_STRUCTURED_AVAILABLE={V4_STRUCTURED_AVAILABLE}")
except Exception as e:
    V4_IMPORT_ERROR = f"structured: {e}"
    logger.error(f"❌ structured import failed: {e}")

V4_FEATURES_AVAILABLE = all([
    V4_EMBEDDINGS_AVAILABLE,
    V4_VECTOR_STORE_AVAILABLE,
    V4_MEMORY_AVAILABLE,
    V4_TOOLS_AVAILABLE,
    V4_CODE_EXECUTOR_AVAILABLE,
])
logger.info(f"🧠 V4.0 Intelligence features: {'ENABLED' if V4_FEATURES_AVAILABLE else 'PARTIAL'}")

LANGGRAPH_AVAILABLE = False
try:
    from services.graph import execute_graph  # noqa: F401
    from services.graph.edges import should_use_langgraph  # noqa: F401
    LANGGRAPH_AVAILABLE = True
    logger.info("✅ LangGraph multi-agent system: ENABLED")
except Exception as e:
    logger.warning(f"⚠️ LangGraph not available: {e}")


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
app.config["V4_FEATURES"] = {
    "embeddings": V4_EMBEDDINGS_AVAILABLE,
    "vector_store": V4_VECTOR_STORE_AVAILABLE,
    "semantic_memory": V4_MEMORY_AVAILABLE,
    "tools": V4_TOOLS_AVAILABLE,
    "code_executor": V4_CODE_EXECUTOR_AVAILABLE,
    "voting": V4_VOTING_AVAILABLE,
    "structured": V4_STRUCTURED_AVAILABLE,
}
app.config["LANGGRAPH_AVAILABLE"] = LANGGRAPH_AVAILABLE

# ===========================================================================
# Register Blueprints
# ===========================================================================

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
                    "/generate",
                    "/stats",
                    "/chat/autosave",
                    "/chat/list",
                    "/chat/{chatId}",
                    "/chat/{chatId}/archive",
                    "/chat/recover-archives",
                    "/chat/archive/{cid}",
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
    """Delete chats that haven't been updated in 7 days (except archived)"""
    try:
        logger.info("Running 7-day cleanup job...")
        chats_root = Path(CHATS_DIR)
        current_time = time.time()
        inactive_seconds = CHAT_INACTIVE_DAYS * 24 * 60 * 60
        deleted_count = 0

        for principal_dir in chats_root.iterdir():
            if not principal_dir.is_dir():
                continue

            principal_id = principal_dir.name
            metadata_path = principal_dir / "metadata.json"

            if not metadata_path.exists():
                continue

            try:
                with open(metadata_path, "r") as f:
                    metadata = json.load(f)

                chats_to_keep = []

                for chat in metadata.get("chats", []):
                    last_updated = chat.get("lastUpdated", 0) / 1000
                    is_archived = chat.get("isArchived", False)
                    is_pinned = chat.get("pinned", False)

                    if is_archived or is_pinned:
                        chats_to_keep.append(chat)
                        continue

                    if current_time - last_updated > inactive_seconds:
                        chat_file = principal_dir / f"{chat['chatId']}.json"
                        if chat_file.exists():
                            chat_file.unlink()
                            deleted_count += 1
                            logger.info(f'Deleted inactive chat: {chat["chatId"]}')
                    else:
                        chats_to_keep.append(chat)

                metadata["chats"] = chats_to_keep
                with open(metadata_path, "w") as f:
                    json.dump(metadata, f, indent=2)

            except Exception as e:
                logger.error(f"Error processing user {principal_id}: {e}")
                continue

        logger.info(f"Cleanup complete: deleted {deleted_count} inactive chats")

    except Exception as e:
        logger.error(f"Cleanup job error: {e}", exc_info=True)


scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_inactive_chats, "cron", hour=2, minute=0, id="chat_cleanup")


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
    logger.info(f"Ollama Host: {OLLAMA_HOST}")
    logger.info("=" * 70)

    if check_ollama_connection():
        logger.info(f"✅ Successfully connected to Ollama ({MODEL_NAME})")
        warmup_model()
    else:
        logger.warning("⚠️  Could not connect to Ollama - server will start anyway")
        logger.warning("   Make sure Ollama is running: ollama serve")
        logger.warning(f"   Make sure model is available: ollama pull {MODEL_NAME}")

    if not scheduler.running:
        scheduler.start()
        logger.info("✅ Cleanup scheduler started (runs daily at 2 AM)")

    logger.info("🌐 Starting Flask server on port 8000")
    logger.info("=" * 70)

    app.run(host="0.0.0.0", port=8000, threaded=True, debug=False)
