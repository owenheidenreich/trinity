"""
A/B Test Middleware for Trinity

Provides Flask middleware and decorators for automatic experiment assignment.
Integrates with the experiments framework for deterministic variant assignment.

Phase 4: Experimentation Framework
"""

import functools
import logging
from typing import Callable, Optional

from flask import g, request

logger = logging.getLogger(__name__)

# Try to import experiments module
try:
    from services.experiments import assign_variant

    EXPERIMENTS_AVAILABLE = True
except ImportError:
    EXPERIMENTS_AVAILABLE = False
    logger.warning("Experiments module not available")

# Import metrics from observability (already registered there)
try:
    from middleware.observability import EXPERIMENT_ASSIGNMENTS as experiment_assignments
    from middleware.observability import EXPERIMENT_EXPOSURES as experiment_exposures
    from middleware.observability import (
        PROMETHEUS_AVAILABLE,
    )
except ImportError:
    PROMETHEUS_AVAILABLE = False
    experiment_assignments = None
    experiment_exposures = None


# =============================================================================
# SESSION ID EXTRACTION
# =============================================================================


def get_session_id() -> str:
    """
    Extract a session identifier for experiment assignment.

    Priority:
    1. Principal ID (authenticated ICP users) - most reliable
    2. X-Session-ID header (frontend provided)
    3. IP + User-Agent hash (fallback for anonymous)

    Returns:
        Session identifier string
    """
    # Prefer principal ID for authenticated users
    principal = request.headers.get("X-ICP-Principal")
    if principal:
        return f"principal:{principal}"

    # Check for explicit session ID header
    session_id = request.headers.get("X-Session-ID")
    if session_id:
        return f"session:{session_id}"

    # Check request JSON for principal
    if request.is_json:
        data = request.get_json(silent=True) or {}
        principal = data.get("principal")
        if principal:
            return f"principal:{principal}"

    # Fallback: Hash IP + User-Agent for anonymous users
    ip = request.remote_addr or "unknown"
    ua = request.headers.get("User-Agent", "unknown")[:100]  # Limit UA length

    import hashlib

    anon_hash = hashlib.sha256(f"{ip}:{ua}".encode()).hexdigest()[:16]
    return f"anon:{anon_hash}"


# =============================================================================
# EXPERIMENT DECORATOR
# =============================================================================


def experiment(experiment_name: str):
    """
    Decorator to automatically assign experiment variant to a request.

    Adds experiment assignment to Flask's `g` object for access in the handler.

    Usage:
        @app.route('/generate')
        @experiment('agent_mode')
        def generate():
            if hasattr(g, 'experiments') and 'agent_mode' in g.experiments:
                mode = g.experiments['agent_mode']['config'].get('mode', 'legacy')
            else:
                mode = 'legacy'  # Default when experiment not assigned

    Args:
        experiment_name: Name of the experiment to assign
    """

    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if not EXPERIMENTS_AVAILABLE:
                return f(*args, **kwargs)

            session_id = get_session_id()

            # Initialize experiments dict on g if needed
            if not hasattr(g, "experiments"):
                g.experiments = {}

            # Assign variant
            variant = assign_variant(experiment_name, session_id)
            if variant:
                g.experiments[experiment_name] = {"variant": variant.name, "config": variant.config}

                # Record assignment metric
                if experiment_assignments:
                    experiment_assignments.labels(
                        experiment=experiment_name, variant=variant.name
                    ).inc()

                logger.debug(
                    f"Experiment {experiment_name}: assigned {variant.name} "
                    f"to session {session_id[:20]}..."
                )

            return f(*args, **kwargs)

        return wrapper

    return decorator


def experiments(*experiment_names: str):
    """
    Decorator to assign multiple experiments at once.

    Usage:
        @app.route('/generate')
        @experiments('agent_mode', 'complexity_threshold', 'reasoning_depth')
        def generate():
            # Access any experiment from g.experiments
            pass

    Args:
        experiment_names: Names of experiments to assign
    """

    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if not EXPERIMENTS_AVAILABLE:
                return f(*args, **kwargs)

            session_id = get_session_id()

            if not hasattr(g, "experiments"):
                g.experiments = {}

            for experiment_name in experiment_names:
                variant = assign_variant(experiment_name, session_id)
                if variant:
                    g.experiments[experiment_name] = {
                        "variant": variant.name,
                        "config": variant.config,
                    }

                    if experiment_assignments:
                        experiment_assignments.labels(
                            experiment=experiment_name, variant=variant.name
                        ).inc()

            return f(*args, **kwargs)

        return wrapper

    return decorator


# =============================================================================
# EXPERIMENT ACCESS HELPERS
# =============================================================================


def get_experiment_config(experiment_name: str, key: str, default=None):
    """
    Get a config value from an assigned experiment.

    Safe to call even if experiment wasn't assigned.

    Args:
        experiment_name: Name of the experiment
        key: Config key to retrieve
        default: Default value if not found

    Returns:
        Config value or default
    """
    if not hasattr(g, "experiments"):
        return default

    exp = g.experiments.get(experiment_name)
    if not exp:
        return default

    return exp.get("config", {}).get(key, default)


def get_variant_name(experiment_name: str) -> Optional[str]:
    """
    Get the assigned variant name for an experiment.

    Args:
        experiment_name: Name of the experiment

    Returns:
        Variant name or None if not assigned
    """
    if not hasattr(g, "experiments"):
        return None

    exp = g.experiments.get(experiment_name)
    return exp.get("variant") if exp else None


def is_in_variant(experiment_name: str, variant_name: str) -> bool:
    """
    Check if the current request is in a specific variant.

    Args:
        experiment_name: Name of the experiment
        variant_name: Variant to check for

    Returns:
        True if in the specified variant
    """
    return get_variant_name(experiment_name) == variant_name


def record_exposure(experiment_name: str):
    """
    Record that an experiment variant was actually used/exposed.

    Call this when the experiment's behavior actually affects the response,
    not just when the variant is assigned. Useful for accurate conversion tracking.

    Args:
        experiment_name: Name of the experiment
    """
    if not hasattr(g, "experiments"):
        return

    exp = g.experiments.get(experiment_name)
    if exp and experiment_exposures:
        experiment_exposures.labels(experiment=experiment_name, variant=exp["variant"]).inc()


# =============================================================================
# REQUEST CONTEXT HELPERS
# =============================================================================


def get_all_experiment_assignments() -> dict:
    """
    Get all experiment assignments for the current request.

    Returns:
        Dict of all assigned experiments
    """
    if hasattr(g, "experiments"):
        return dict(g.experiments)
    return {}


def inject_experiments_to_response(response_dict: dict) -> dict:
    """
    Inject experiment assignments into an API response.

    Useful for debugging or for frontends that need to know the assignment.

    Args:
        response_dict: The response to augment

    Returns:
        Response with _experiments field added
    """
    assignments = get_all_experiment_assignments()
    if assignments:
        response_dict["_experiments"] = {
            name: {"variant": data["variant"]} for name, data in assignments.items()
        }
    return response_dict
