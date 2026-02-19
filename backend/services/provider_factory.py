"""
Provider Factory — create an OllamaProvider for the configured model.

Usage:
    from services.provider_factory import create_provider, get_provider
    provider = create_provider()
    provider = get_provider()             # Singleton (cached)
"""

import logging
from typing import Dict, Optional, Tuple

from .llm_provider import LLMProvider

logger = logging.getLogger(__name__)

# Provider instances keyed by backend/host/model/ctx.
_provider_instances: Dict[Tuple[str, str, str, int], LLMProvider] = {}


def create_provider(model_name: Optional[str] = None) -> LLMProvider:
    """Create a new LLMProvider instance.

    Returns:
        An OllamaProvider instance.
    """
    from config import MODEL_BACKEND, NUM_CTX, OLLAMA_CHAT_HOST, OLLAMA_CHAT_MODEL

    from .ollama_provider import OllamaProvider

    resolved_model = model_name or OLLAMA_CHAT_MODEL
    provider = OllamaProvider(
        host=OLLAMA_CHAT_HOST,
        model=resolved_model,
        num_ctx=NUM_CTX,
    )
    logger.info(f"🔧 Created provider ({MODEL_BACKEND}) → {OLLAMA_CHAT_HOST} ({resolved_model})")

    return provider


def get_provider(
    prompt: str = "",
    use_case: Optional[str] = None,
    model_name: Optional[str] = None,
) -> LLMProvider:
    """Get or create a cached provider instance for the selected model."""
    from config import (
        MODEL_BACKEND,
        MODEL_ROUTING_ENABLED,
        NUM_CTX,
        OLLAMA_CHAT_HOST,
        OLLAMA_CHAT_MODEL,
    )

    selected_model = model_name or OLLAMA_CHAT_MODEL
    if model_name is None and MODEL_ROUTING_ENABLED:
        try:
            from .model_router import choose_model_for_prompt

            selected_model = choose_model_for_prompt(prompt or "", use_case=use_case)
        except Exception as e:
            logger.debug(f"Model routing fallback to default model: {e}")
            selected_model = OLLAMA_CHAT_MODEL

    key = (MODEL_BACKEND, OLLAMA_CHAT_HOST, selected_model, NUM_CTX)
    provider = _provider_instances.get(key)
    if provider is None:
        provider = create_provider(model_name=selected_model)
        _provider_instances[key] = provider
    return provider


def reset_provider():
    """Reset cached providers (for testing or config changes)."""
    _provider_instances.clear()
