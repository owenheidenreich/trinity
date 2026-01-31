"""
Trinity Backend - Health Check Routes
Status endpoints for monitoring and load balancing
"""

from flask import jsonify
from datetime import datetime
from . import health_bp
from config import (
    PROVIDER_ID, MODEL_NAME, GPU_TYPE, MAX_QUEUE_SIZE, BUILD_TIMESTAMP
)
from services import metrics, get_system_info, check_ollama_connection
from middleware import icp_idempotent


@health_bp.route('/health')
def health():
    """
    Health check endpoint for load balancers and monitoring
    
    Returns:
        - status: 'healthy' or 'degraded'
        - provider_id: unique identifier for this provider
        - model: which AI model is loaded
        - gpu_type: hardware type (CPU/GPU)
        - system: CPU and memory usage
        - metrics: performance statistics
        - ollama_connected: whether Ollama is responsive
    """
    ollama_healthy = check_ollama_connection()
    system_info = get_system_info()
    stats = metrics.get_stats()
    
    # Determine overall health
    is_healthy = (
        ollama_healthy and
        metrics.active_requests < MAX_QUEUE_SIZE and
        system_info['memory_percent'] < 95
    )
    
    return jsonify({
        'status': 'healthy' if is_healthy else 'degraded',
        'provider_id': PROVIDER_ID,
        'model': MODEL_NAME,
        'gpu_type': GPU_TYPE,
        'ollama_connected': ollama_healthy,
        'timestamp': datetime.utcnow().isoformat(),
        'build_timestamp': BUILD_TIMESTAMP,
        'system': system_info,
        'metrics': stats,
        'queue_size': metrics.active_requests,
        'max_queue_size': MAX_QUEUE_SIZE,
    }), 200 if is_healthy else 503


@health_bp.route('/health/icp')
@icp_idempotent
def health_icp():
    """
    Deterministic health check endpoint for ICP HTTP Outcalls.
    
    ICP requires all 13 subnet replicas to receive identical responses
    for consensus. This endpoint returns ONLY static/deterministic data.
    
    Uses @icp_idempotent decorator for X-Request-ID based caching.
    """
    ollama_healthy = check_ollama_connection()
    
    # Only return STATIC values - no timestamps, no dynamic metrics
    return jsonify({
        'status': 'healthy' if ollama_healthy else 'degraded',
        'provider_id': PROVIDER_ID,
        'model': MODEL_NAME,
        'gpu_type': GPU_TYPE,
        'ollama_connected': ollama_healthy,
        'build_timestamp': BUILD_TIMESTAMP,  # Static - set at startup
        'version': '2.1.0',
        'icp_compatible': True
    }), 200 if ollama_healthy else 503


@health_bp.route('/stats')
def stats():
    """
    Get detailed statistics in JSON format
    Useful for monitoring dashboards and debugging
    """
    from config import OLLAMA_HOST
    
    return jsonify({
        'provider_id': PROVIDER_ID,
        'model': MODEL_NAME,
        'gpu_type': GPU_TYPE,
        'metrics': metrics.get_stats(),
        'system': get_system_info(),
        'config': {
            'ollama_host': OLLAMA_HOST,
            'max_queue_size': MAX_QUEUE_SIZE,
        },
        'timestamp': datetime.utcnow().isoformat(),
    })
