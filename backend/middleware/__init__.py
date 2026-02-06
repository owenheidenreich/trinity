"""
Trinity Backend - Middleware Package
Rate limiting, ICP caching, observability, A/B testing, and request utilities
"""

from .rate_limit import (
    rate_limit, storage_rate_limit,
    request_counts, RATE_LIMIT, RATE_WINDOW,
    storage_request_counts, STORAGE_RATE_LIMIT, STORAGE_RATE_WINDOW
)
from .icp_cache import icp_idempotent, icp_cache
from .observability import (
    PROMETHEUS_AVAILABLE,
    track_request, track_inference, track_storage, track_auth,
    observe_endpoint, track_error,
    get_metrics_response, update_system_metrics,
    set_model_loaded, set_uptime,
    REQUEST_COUNTER, REQUEST_LATENCY, ERROR_COUNTER,
    INFERENCE_DURATION, TOKENS_GENERATED, AUTH_ATTEMPTS,
    # Phase 4: Experiment metrics
    EXPERIMENT_ASSIGNMENTS, EXPERIMENT_EXPOSURES,
    PARALLEL_EXECUTIONS, PARALLEL_LATENCY,
    # Phase 5: Cost optimization metrics
    EMBEDDING_CACHE_HITS, EMBEDDING_CACHE_MISSES, EMBEDDING_CACHE_SIZE,
    SEMANTIC_CACHE_HITS, SEMANTIC_CACHE_MISSES, SEMANTIC_CACHE_SIZE,
    SEMANTIC_CACHE_SIMILARITY,
    TOKENS_PROMPT, TOKENS_COMPLETION, ESTIMATED_COST_USD,
    TOKEN_RATE, USER_TOKENS
)
from .ab_test import (
    experiment, experiments,
    get_session_id, get_experiment_config, get_variant_name,
    is_in_variant, record_exposure, get_all_experiment_assignments
)

__all__ = [
    'rate_limit',
    'storage_rate_limit',
    'request_counts',
    'RATE_LIMIT',
    'RATE_WINDOW',
    'storage_request_counts',
    'STORAGE_RATE_LIMIT',
    'STORAGE_RATE_WINDOW',
    'icp_idempotent',
    'icp_cache',
    # Observability exports
    'PROMETHEUS_AVAILABLE',
    'track_request',
    'track_inference', 
    'track_storage',
    'track_auth',
    'observe_endpoint',
    'track_error',
    'get_metrics_response',
    'update_system_metrics',
    'set_model_loaded',
    'set_uptime',
    'REQUEST_COUNTER',
    'REQUEST_LATENCY',
    'ERROR_COUNTER',
    'INFERENCE_DURATION',
    'TOKENS_GENERATED',
    'AUTH_ATTEMPTS',
    # Phase 4: Experiment exports
    'EXPERIMENT_ASSIGNMENTS',
    'EXPERIMENT_EXPOSURES',
    'PARALLEL_EXECUTIONS',
    'PARALLEL_LATENCY',
    'experiment',
    'experiments',
    'get_session_id',
    'get_experiment_config',
    'get_variant_name',
    'is_in_variant',
    'record_exposure',
    'get_all_experiment_assignments',
    # Phase 5: Cost optimization exports
    'EMBEDDING_CACHE_HITS',
    'EMBEDDING_CACHE_MISSES',
    'EMBEDDING_CACHE_SIZE',
    'SEMANTIC_CACHE_HITS',
    'SEMANTIC_CACHE_MISSES',
    'SEMANTIC_CACHE_SIZE',
    'SEMANTIC_CACHE_SIMILARITY',
    'TOKENS_PROMPT',
    'TOKENS_COMPLETION',
    'ESTIMATED_COST_USD',
    'TOKEN_RATE',
    'USER_TOKENS',
]
