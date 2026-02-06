"""
A/B Testing Framework for Trinity

Provides deterministic experiment assignment based on session/user ID.
Supports multiple variants with configurable weights.

Phase 4: Experimentation Framework

Key Features:
- Stateless hash-based assignment (no database needed)
- Deterministic: same user always gets same variant
- Uniform distribution across variants
- Easy to add/modify experiments
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class Variant:
    """
    A single variant in an experiment.

    Attributes:
        name: Unique identifier for this variant (e.g., 'control', 'treatment')
        weight: Probability weight (0.0 to 1.0), all variants must sum to 1.0
        config: Configuration dict passed to the feature when this variant is active
    """

    name: str
    weight: float
    config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate variant configuration."""
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"Variant weight must be between 0 and 1, got {self.weight}")
        if not self.name:
            raise ValueError("Variant name cannot be empty")


@dataclass
class Experiment:
    """
    An A/B test experiment definition.

    Attributes:
        name: Unique identifier for this experiment
        description: Human-readable description of what's being tested
        variants: List of Variant objects (must sum to 1.0 weight)
        enabled: Whether this experiment is active
        created_at: When this experiment was defined
    """

    name: str
    description: str
    variants: List[Variant]
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self):
        """Validate experiment configuration."""
        if not self.name:
            raise ValueError("Experiment name cannot be empty")
        if not self.variants:
            raise ValueError("Experiment must have at least one variant")

        total_weight = sum(v.weight for v in self.variants)
        if not 0.99 <= total_weight <= 1.01:  # Allow small floating point error
            raise ValueError(f"Variant weights must sum to 1.0, got {total_weight}")


# =============================================================================
# EXPERIMENT DEFINITIONS
# =============================================================================

EXPERIMENTS: Dict[str, Experiment] = {
    "agent_mode": Experiment(
        name="agent_mode",
        description="Test LangGraph vs legacy pipeline for complex queries",
        variants=[
            Variant("control", 0.5, {"mode": "legacy"}),
            Variant("langgraph", 0.5, {"mode": "langgraph"}),
        ],
        enabled=True,
    ),
    "parallel_execution": Experiment(
        name="parallel_execution",
        description="Run both pipelines in parallel and vote on best result",
        variants=[
            Variant("control", 0.5, {"parallel": False}),
            Variant("parallel", 0.5, {"parallel": True}),
        ],
        enabled=False,  # Enable when parallel pipeline is ready
    ),
    "complexity_threshold": Experiment(
        name="complexity_threshold",
        description="Test different word count thresholds for LangGraph activation",
        variants=[
            Variant("control", 0.34, {"threshold": 50}),  # Current default
            Variant("lower", 0.33, {"threshold": 35}),  # More queries to LangGraph
            Variant("higher", 0.33, {"threshold": 65}),  # Fewer queries to LangGraph
        ],
        enabled=True,
    ),
    "reasoning_depth": Experiment(
        name="reasoning_depth",
        description="Test different max iteration counts for LangGraph reasoning",
        variants=[
            Variant("control", 0.5, {"max_iterations": 5}),
            Variant("deeper", 0.5, {"max_iterations": 8}),
        ],
        enabled=True,
    ),
}


# =============================================================================
# ASSIGNMENT LOGIC
# =============================================================================


def get_experiment(name: str) -> Optional[Experiment]:
    """
    Get an experiment by name.

    Args:
        name: Experiment name

    Returns:
        Experiment object or None if not found
    """
    return EXPERIMENTS.get(name)


def list_experiments(enabled_only: bool = False) -> Dict[str, Dict[str, Any]]:
    """
    List all experiments with their current status.

    Args:
        enabled_only: If True, only return enabled experiments

    Returns:
        Dict mapping experiment names to their details
    """
    result = {}
    for name, exp in EXPERIMENTS.items():
        if enabled_only and not exp.enabled:
            continue
        result[name] = {
            "description": exp.description,
            "enabled": exp.enabled,
            "created_at": exp.created_at,
            "variants": [
                {"name": v.name, "weight": v.weight, "config": v.config} for v in exp.variants
            ],
        }
    return result


def assign_variant(experiment_name: str, session_id: str) -> Optional[Variant]:
    """
    Deterministically assign a variant using hash-based assignment.

    This is a stateless assignment mechanism that guarantees:
    1. Same session always gets same variant (deterministic)
    2. Uniform distribution across variants (fair)
    3. No state needed (no database lookups)

    Args:
        experiment_name: Name of the experiment
        session_id: Unique identifier for the user/session

    Returns:
        Assigned Variant object, or None if experiment doesn't exist or is disabled

    Example:
        >>> variant = assign_variant('agent_mode', 'user-123')
        >>> if variant:
        ...     print(f"User assigned to: {variant.name}")
        ...     mode = variant.config.get('mode', 'legacy')
    """
    experiment = EXPERIMENTS.get(experiment_name)
    if not experiment:
        logger.warning(f"Experiment not found: {experiment_name}")
        return None

    if not experiment.enabled:
        logger.debug(f"Experiment disabled: {experiment_name}")
        return None

    # Create deterministic hash from experiment name + session ID
    # This ensures same user always gets same variant for same experiment
    hash_input = f"{experiment_name}:{session_id}"
    hash_bytes = hashlib.sha256(hash_input.encode()).digest()

    # Convert first 8 bytes to float between 0.0 and 1.0
    hash_value = int.from_bytes(hash_bytes[:8], "big") / (2**64)

    # Assign based on cumulative weights
    cumulative = 0.0
    for variant in experiment.variants:
        cumulative += variant.weight
        if hash_value < cumulative:
            logger.debug(f"Assigned {session_id} to {experiment_name}:{variant.name}")
            return variant

    # Fallback to last variant (handles floating point edge cases)
    return experiment.variants[-1]


def get_all_assignments(session_id: str) -> Dict[str, Dict[str, Any]]:
    """
    Get all experiment assignments for a session.

    Useful for debugging or getting a complete picture of a user's experiment state.

    Args:
        session_id: Unique identifier for the user/session

    Returns:
        Dict mapping experiment names to variant info
    """
    assignments = {}
    for name in EXPERIMENTS:
        variant = assign_variant(name, session_id)
        if variant:
            assignments[name] = {"variant": variant.name, "config": variant.config}
    return assignments


# =============================================================================
# EXPERIMENT MANAGEMENT
# =============================================================================


def enable_experiment(name: str) -> bool:
    """
    Enable an experiment.

    Args:
        name: Experiment name

    Returns:
        True if experiment was enabled, False if not found
    """
    exp = EXPERIMENTS.get(name)
    if exp:
        exp.enabled = True
        logger.info(f"Enabled experiment: {name}")
        return True
    return False


def disable_experiment(name: str) -> bool:
    """
    Disable an experiment.

    Args:
        name: Experiment name

    Returns:
        True if experiment was disabled, False if not found
    """
    exp = EXPERIMENTS.get(name)
    if exp:
        exp.enabled = False
        logger.info(f"Disabled experiment: {name}")
        return True
    return False


def add_experiment(experiment: Experiment) -> bool:
    """
    Add a new experiment at runtime.

    Args:
        experiment: Experiment object to add

    Returns:
        True if added, False if name already exists
    """
    if experiment.name in EXPERIMENTS:
        logger.warning(f"Experiment already exists: {experiment.name}")
        return False

    EXPERIMENTS[experiment.name] = experiment
    logger.info(f"Added experiment: {experiment.name}")
    return True


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def validate_assignment_distribution(
    experiment_name: str, sample_size: int = 10000
) -> Dict[str, float]:
    """
    Validate that experiment assignment is uniformly distributed.

    Useful for testing that weights are being respected.

    Args:
        experiment_name: Experiment to validate
        sample_size: Number of random session IDs to test

    Returns:
        Dict mapping variant names to observed percentages
    """
    import uuid

    experiment = EXPERIMENTS.get(experiment_name)
    if not experiment:
        return {}

    counts = {v.name: 0 for v in experiment.variants}

    for _ in range(sample_size):
        session_id = str(uuid.uuid4())
        variant = assign_variant(experiment_name, session_id)
        if variant:
            counts[variant.name] += 1

    return {name: count / sample_size for name, count in counts.items()}
