"""
Provider Factory — create an LLMProvider for the configured backend.

Supported backends (MODEL_BACKEND env var):
    "llama-server"  → LlamaServerProvider (OpenAI-compatible /v1/chat/completions)

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
    """Create a new LlamaServerProvider instance.

    Returns:
        LlamaServerProvider configured for the chat endpoint.
    """
    from config import LLAMA_SERVER_CHAT_PORT, NUM_CTX, CHAT_MODEL

    from .llama_server_provider import LlamaServerProvider

    resolved_model = model_name or CHAT_MODEL
    host = f"http://localhost:{LLAMA_SERVER_CHAT_PORT}"
    provider = LlamaServerProvider(
        host=host,
        model=resolved_model,
        num_ctx=NUM_CTX,
    )
    logger.info(f"🔧 Created provider (llama-server) → {host} ({resolved_model})")
    return provider


def get_provider(
    prompt: str = "",
    use_case: Optional[str] = None,
    model_name: Optional[str] = None,
) -> LLMProvider:
    """Get or create a cached provider instance for the selected model."""
    from config import (
        NUM_CTX,
        CHAT_MODEL,
    )

    selected_model = model_name or CHAT_MODEL
    if model_name is None:
        try:
            from config import MODEL_ROUTING_ENABLED

            if MODEL_ROUTING_ENABLED:
                from .model_router import choose_model_for_prompt

                selected_model = choose_model_for_prompt(prompt or "", use_case=use_case)
        except Exception as e:
            logger.debug(f"Model routing fallback to default model: {e}")
            selected_model = CHAT_MODEL

    from config import LLAMA_SERVER_CHAT_PORT

    host_key = f"http://localhost:{LLAMA_SERVER_CHAT_PORT}"
    key = ("llama-server", host_key, selected_model, NUM_CTX)
    provider = _provider_instances.get(key)
    if provider is None:
        provider = create_provider(model_name=selected_model)
        _provider_instances[key] = provider
    return provider


def create_ingest_provider() -> LLMProvider:
    """Create an LLMProvider for ingestion (profile extraction, summarization).

    Uses a separate port so ingestion work doesn't compete with chat.
    """
    from config import LLAMA_SERVER_INGEST_PORT, NUM_CTX, INGEST_MODEL

    from .llama_server_provider import LlamaServerProvider

    host = f"http://localhost:{LLAMA_SERVER_INGEST_PORT}"
    provider = LlamaServerProvider(
        host=host,
        model=INGEST_MODEL,
        num_ctx=min(NUM_CTX, 8192),
    )
    logger.info(f"🔧 Created ingest provider (llama-server) → {host} ({INGEST_MODEL})")
    return provider


def get_ingest_provider() -> LLMProvider:
    """Get or create a cached ingest provider singleton."""
    from config import LLAMA_SERVER_INGEST_PORT, NUM_CTX, INGEST_MODEL

    host_key = f"http://localhost:{LLAMA_SERVER_INGEST_PORT}"
    key = ("llama-server", host_key, INGEST_MODEL, min(NUM_CTX, 8192))
    provider = _provider_instances.get(key)
    if provider is None:
        provider = create_ingest_provider()
        _provider_instances[key] = provider
    return provider


def reset_provider():
    """Reset cached providers (for testing or config changes)."""
    _provider_instances.clear()
