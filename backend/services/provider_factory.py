"""
Provider Factory — create an OllamaProvider for the configured model.

Usage:
    from services.provider_factory import create_provider, get_provider
    provider = create_provider()
    provider = get_provider()             # Singleton (cached)
"""

import logging
from typing import Optional

from .llm_provider import LLMProvider

logger = logging.getLogger(__name__)

# Singleton instance
_provider_instance: Optional[LLMProvider] = None


def create_provider() -> LLMProvider:
    """Create a new LLMProvider instance.

    Returns:
        An OllamaProvider instance.
    """
    from config import MODEL_NAME, NUM_CTX, OLLAMA_HOST

    from .ollama_provider import OllamaProvider

    provider = OllamaProvider(
        host=OLLAMA_HOST,
        model=MODEL_NAME,
        num_ctx=NUM_CTX,
    )
    logger.info(f"🔧 Created OllamaProvider → {OLLAMA_HOST} ({MODEL_NAME})")

    return provider


def get_provider() -> LLMProvider:
    """Get or create the singleton provider instance."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = create_provider()
    return _provider_instance


def reset_provider():
    """Reset the singleton provider (for testing or config changes)."""
    global _provider_instance
    _provider_instance = None
