"""
Health & metrics endpoints.
Routes: /health, /health/icp, /metrics, /stats
"""

from datetime import datetime

from flask import Blueprint, Response, current_app, jsonify

from config import (
    BRAVE_SEARCH_API_KEY,
    BUILD_TIMESTAMP,
    GPU_TYPE,
    MAX_QUEUE_SIZE,
    MODEL_NAME,
    OLLAMA_HOST,
    PROVIDER_ID,
    logger,
)
from middleware import (
    get_active_requests,
    get_metrics_response,
    get_prometheus_summary,
    get_system_info,
    icp_idempotent,
)
from services import check_ollama_connection

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    """Health check endpoint for load balancers and monitoring."""
    ollama_healthy = check_ollama_connection()
    system_info = get_system_info()
    stats = get_prometheus_summary()
    active_reqs = get_active_requests()

    # Import feature flags from app config
    v4 = current_app.config.get("V4_FEATURES_AVAILABLE", False)
    langgraph = current_app.config.get("LANGGRAPH_AVAILABLE", False)
    v4_features = current_app.config.get("V4_FEATURES", {})
    v4_memory = v4_features.get("semantic_memory", False)

    is_healthy = (
        ollama_healthy
        and active_reqs < MAX_QUEUE_SIZE
        and system_info["memory_percent"] < 95
    )

    return jsonify({
        "status": "healthy" if is_healthy else "degraded",
        "provider_id": PROVIDER_ID,
        "model": MODEL_NAME,
        "gpu_type": GPU_TYPE,
        "ollama_connected": ollama_healthy,
        "timestamp": datetime.utcnow().isoformat(),
        "build_timestamp": BUILD_TIMESTAMP,
        "system": system_info,
        "metrics": stats,
        "queue_size": active_reqs,
        "max_queue_size": MAX_QUEUE_SIZE,
        "features": {
            "v4_intelligence": v4,
            "langgraph_agents": langgraph,
            "semantic_memory": v4_memory,
            "web_search": bool(BRAVE_SEARCH_API_KEY),
        },
    }), (200 if is_healthy else 503)


@health_bp.route("/health/icp")
@icp_idempotent
def health_icp():
    """Deterministic health check for ICP HTTP Outcalls (all 13 replicas must agree)."""
    ollama_healthy = check_ollama_connection()

    return jsonify({
        "status": "healthy" if ollama_healthy else "degraded",
        "provider_id": PROVIDER_ID,
        "model": MODEL_NAME,
        "gpu_type": GPU_TYPE,
        "ollama_connected": ollama_healthy,
        "build_timestamp": BUILD_TIMESTAMP,
        "version": "2.1.0",
        "icp_compatible": True,
    }), (200 if ollama_healthy else 503)


@health_bp.route("/metrics")
def prometheus_metrics():
    """Prometheus metrics endpoint for monitoring and alerting."""
    content, content_type = get_metrics_response()
    return Response(content, mimetype=content_type)


@health_bp.route("/stats")
def stats():
    """Get detailed statistics in JSON format."""
    return jsonify({
        "provider_id": PROVIDER_ID,
        "model": MODEL_NAME,
        "gpu_type": GPU_TYPE,
        "metrics": get_prometheus_summary(),
        "system": get_system_info(),
        "config": {
            "ollama_host": OLLAMA_HOST,
            "max_queue_size": MAX_QUEUE_SIZE,
        },
        "timestamp": datetime.utcnow().isoformat(),
    })
