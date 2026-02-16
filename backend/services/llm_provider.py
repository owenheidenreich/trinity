"""
Abstract LLM Provider Interface

All inference backends implement this interface. Business logic in agent.py,
react_loop.py, routes/generate.py calls provider methods — never raw HTTP
to a specific backend.

Architecture:
    LLMProvider (ABC)
    └── OllamaProvider   — wraps Ollama /api/generate & /api/chat
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Generator, List, Optional

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM inference providers.

    Every provider exposes the same interface so callers (AgentPipeline,
    ReactLoop, route handlers) never need to know which backend serves
    inference.  The yield contract for streaming methods is:

        yield str          → a token of content
        yield {"__done_reason": "stop"|"length"}  → stream finished

    Non-streaming methods return str (or dict when raw_message=True).
    """

    # Subclasses should set these in __init__
    host: str = ""
    model: str = ""

    # ── Text-completion (prompt-in → text-out) ────────────────────

    @abstractmethod
    def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 30,
        **kwargs,
    ) -> str:
        """Single-turn text generation. Returns the full response string."""
        ...

    @abstractmethod
    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 60,
        **kwargs,
    ) -> Generator:
        """Streaming text generation.

        Yields:
            str  — token content
            dict — ``{"__done_reason": "stop"}`` when stream ends
        """
        ...

    # ── Chat-completion (messages-in → message-out) ───────────────

    @abstractmethod
    def chat(
        self,
        messages: List[Dict],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 60,
        tools: Optional[List[Dict]] = None,
        raw_message: bool = False,
        **kwargs,
    ) -> str:
        """Chat completion (non-streaming).

        Args:
            messages: OpenAI-style ``[{"role": ..., "content": ...}]``
            tools: Optional tool definitions for function calling
            raw_message: If True, return the full message dict instead of
                         just the content string.

        Returns:
            str content, or full message dict when ``raw_message=True``.
        """
        ...

    @abstractmethod
    def chat_stream(
        self,
        messages: List[Dict],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 60,
        **kwargs,
    ) -> Generator:
        """Streaming chat completion.

        Yields:
            str  — token content
            dict — ``{"__done_reason": "stop"}`` when stream ends
        """
        ...

    # ── Lifecycle ─────────────────────────────────────────────────

    @abstractmethod
    def check_connection(self) -> bool:
        """Verify the inference backend is reachable and a model is loaded."""
        ...

    @abstractmethod
    def warmup(self) -> bool:
        """Warm up the model (e.g. pre-generate a short response).

        Returns True on success.
        """
        ...

    # ── Helpers ───────────────────────────────────────────────────

    @property
    def backend_name(self) -> str:
        """Return a human-readable backend identifier (e.g. 'ollama')."""
        return self.__class__.__name__.replace("Provider", "").lower()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} host={self.host!r} model={self.model!r}>"
