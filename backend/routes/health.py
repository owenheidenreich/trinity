"""
Health & metrics endpoints.
Routes: /health, /health/icp, /metrics, /stats
"""

from datetime import datetime

from flask import Blueprint, Response, jsonify

from config import (
    BRAVE_SEARCH_API_KEY,
    BUILD_TIMESTAMP,
    GRAPH_MEMORY_ENABLED,
    GPU_TYPE,
    MAX_QUEUE_SIZE,
    MEMORY_INGESTION_ENABLED,
    MODEL_BACKEND,
    MODEL_NAME,
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
from services.provider_factory import get_provider

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    """Health check endpoint for load balancers and monitoring."""
    provider = get_provider()
    provider_healthy = provider.check_connection()
    system_info = get_system_info()
    stats = get_prometheus_summary()
    active_reqs = get_active_requests()

    is_healthy = (
        provider_healthy
        and active_reqs < MAX_QUEUE_SIZE
        and system_info["memory_percent"] < 95
    )

    return jsonify({
        "status": "healthy" if is_healthy else "degraded",
        "provider_id": PROVIDER_ID,
        "model": MODEL_NAME,
        "backend": provider.backend_name,
        "gpu_type": GPU_TYPE,
        "ollama_connected": provider_healthy,  # backwards compat key
        "timestamp": datetime.utcnow().isoformat(),
        "build_timestamp": BUILD_TIMESTAMP,
        "system": system_info,
        "metrics": stats,
        "queue_size": active_reqs,
        "max_queue_size": MAX_QUEUE_SIZE,
        "features": {
            "canonical_state_db": True,
            "semantic_memory": True,
            "graph_memory": GRAPH_MEMORY_ENABLED,
            "ingestion_worker": MEMORY_INGESTION_ENABLED,
            "ipfs_checkpoints": True,
            # Legacy key kept for compatibility.
            "v4_intelligence": True,
            "web_search": bool(BRAVE_SEARCH_API_KEY),
        },
    }), (200 if is_healthy else 503)


@health_bp.route("/health/icp")
@icp_idempotent
def health_icp():
    """Deterministic health check for ICP HTTP Outcalls (all 13 replicas must agree)."""
    provider = get_provider()
    provider_healthy = provider.check_connection()

    return jsonify({
        "status": "healthy" if provider_healthy else "degraded",
        "provider_id": PROVIDER_ID,
        "model": MODEL_NAME,
        "gpu_type": GPU_TYPE,
        "ollama_connected": provider_healthy,  # backwards compat key
        "build_timestamp": BUILD_TIMESTAMP,
        "version": "2.1.0",
        "icp_compatible": True,
    }), (200 if provider_healthy else 503)


@health_bp.route("/metrics")
def prometheus_metrics():
    """Prometheus metrics endpoint for monitoring and alerting."""
    content, content_type = get_metrics_response()
    return Response(content, mimetype=content_type)


@health_bp.route("/stats")
def stats():
    """Get detailed statistics in JSON format."""
    provider = get_provider()
    return jsonify({
        "provider_id": PROVIDER_ID,
        "model": MODEL_NAME,
        "backend": provider.backend_name,
        "gpu_type": GPU_TYPE,
        "metrics": get_prometheus_summary(),
        "system": get_system_info(),
        "config": {
            "model_backend": MODEL_BACKEND,
            "max_queue_size": MAX_QUEUE_SIZE,
        },
        "timestamp": datetime.utcnow().isoformat(),
    })
