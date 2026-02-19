"""
Trinity — Streaming Pipeline

Extracts the core streaming logic from the former 1086-line ``agent.py``
god module into a focused, composable pipeline.

The pipeline follows one path for every query:
  1. Fast-path smalltalk → instant response (no LLM)
  2. Detect tools needed
  3. If tools → ReAct loop (streaming)
     Else → direct chat_stream with think-block filtering

Public API
----------
* ``StreamingPipeline`` — main class (accepts any LLMProvider)
* ``PipelineResponse`` — result dataclass
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Generator, List, Optional

from middleware.observability import record_complexity, record_routing

from .llm_provider import LLMProvider
from .loading_messages import format_phase_update
from .search import format_search_context, is_search_available, search_web
from .think_filter import (
    contains_fenced_code,
    filter_think_blocks,
)
from .query_classifier import (
    smalltalk_fast_response,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_TOKENS = 16384
TIMEOUT = 300
SEARCH_TIMEOUT = 30

# Search trigger keywords
_SEARCH_KEYWORDS = frozenset([
    "latest", "current", "today", "news", "price", "weather",
    "recent", "update", "2024", "2025", "2026", "who won", "score",
    "search", "look up", "find out", "how much", "what day",
    "what time", "right now", "bitcoin", "stock", "crypto",
])


# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------

@dataclass
class PipelineResponse:
    """Final metadata from a streaming pipeline run."""

    answer: str
    passes_used: int = 1
    search_performed: bool = False
    search_query: Optional[str] = None
    total_time_seconds: float = 0.0
    tools_used: List[str] = field(default_factory=list)
    model_used: Optional[str] = None

    def to_dict(self) -> Dict:
        result = {
            "answer": self.answer,
            "complexity": "single_pass",
            "passes_used": self.passes_used,
            "total_time_seconds": self.total_time_seconds,
            "search_performed": self.search_performed,
        }
        if self.search_query:
            result["search_query"] = self.search_query
        if self.tools_used:
            result["tools_used"] = self.tools_used
        if self.model_used:
            result["model_used"] = self.model_used
        return result


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class StreamingPipeline:
    """Single-pass reasoning pipeline with streaming output.

    Every query follows one path:
      1. Detect tools needed
      2. Web search if applicable
      3. If tools → ReAct loop (streaming)
         Else → direct chat_stream with think-block filtering

    Accepts any ``LLMProvider`` — the caller decides which backend to use.
    """

    def __init__(self, provider: Optional[LLMProvider] = None):
        if provider is not None:
            self.client = provider
        else:
            from .provider_factory import get_provider
            self.client = get_provider()

    # ------------------------------------------------------------------
    # ReAct integration
    # ------------------------------------------------------------------

    def _get_react_loop(self, principal_id: str = None):
        """Create a ReactLoop scoped to this request."""
        try:
            from .react_loop import ReactLoop
            context = {}
            if principal_id:
                context["principal_id"] = principal_id
            return ReactLoop(self.client, context=context)
        except ImportError:
            return None

    # ------------------------------------------------------------------
    # Web search
    # ------------------------------------------------------------------

    @staticmethod
    def _maybe_web_search(question: str) -> tuple[str, bool]:
        """Check if web search should be triggered. Returns (context, did_search)."""
        if not is_search_available():
            return "", False

        q_lower = question.lower()
        if not any(kw in q_lower for kw in _SEARCH_KEYWORDS):
            return "", False

        result = search_web(question, count=5, timeout=SEARCH_TIMEOUT)
        if result.error or not result.results:
            return "", False

        return format_search_context(result), True

    # ------------------------------------------------------------------
    # Main streaming entry point
    # ------------------------------------------------------------------

    def process_streaming(
        self,
        question: str,
        messages: List[Dict],
        *,
        search_context: str = "",
        principal_id: str = None,
        fast_path: bool = False,
        disclosure_path: bool = False,
        tools_needed: Optional[List[str]] = None,
        chat_id: str = None,
        max_tokens: int = MAX_TOKENS,
        timeout: int = TIMEOUT,
        **kwargs,
    ) -> Generator[Dict, None, None]:
        """Stream a response for a single user turn.

        The caller (context_loader) has already classified the query.
        The pipeline trusts those decisions and does not re-classify.

        Yields
        ------
        dict
            ``{"phase": ...}`` — progress updates,
            ``{"token": ...}`` — streamed text,
            ``{"done": True, ...}`` — final metadata.
        """
        start_time = time.time()
        full_response = ""
        search_performed = bool(search_context)
        last_done_reason = "stop"
        response_mode = "normal"

        record_complexity("single_pass")
        record_routing("agent")

        # ----- Fast-path: trivial smalltalk -----
        if fast_path:
            logger.info("⚡ Pipeline fast-path: trivial smalltalk")
            yield format_phase_update("executing")
            full_response = smalltalk_fast_response(question)
            yield {"token": full_response}
            yield self._done_event(full_response, False, start_time)
            return

        # ----- Tool decision (trusted from context_loader) -----
        use_tools = bool(tools_needed)

        logger.info(
            "🧠 Pipeline: single-pass, tools=%s, disclosure=%s",
            use_tools,
            disclosure_path,
        )

        # ----- Web search (non-tool path only) -----
        if not use_tools and not search_context:
            yield format_phase_update("searching")
            search_context, search_performed = self._maybe_web_search(question)
            if search_performed:
                yield {
                    "phase": "searching",
                    "message": "Found web sources...",
                }

        try:
            yield format_phase_update("executing")

            if use_tools:
                # ------ ReAct loop ------
                react = self._get_react_loop(principal_id)
                if react is None:
                    yield {"error": "ReAct loop unavailable"}
                    return

                for event in react.execute_streaming(
                    question=question,
                    messages=messages,
                    search_context=search_context,
                    max_tokens=max_tokens,
                    timeout=timeout,
                ):
                    if "token" in event:
                        full_response += event["token"]
                    yield event

            else:
                # ------ Direct streaming generation ------
                filtered_parts: list[str] = []
                for token in filter_think_blocks(
                    self.client.chat_stream(
                        messages,
                        max_tokens,
                        timeout=timeout,
                        think=False,
                    ),
                    filtered_parts,
                ):
                    if isinstance(token, dict) and "__done_reason" in token:
                        last_done_reason = token["__done_reason"]
                        continue
                    yield {"token": token}
                full_response = "".join(filtered_parts)

        except Exception as e:
            logger.error("Pipeline streaming error: %s", e)
            yield {"error": str(e)}

        if response_mode == "normal" and contains_fenced_code(full_response):
            response_mode = "inline_code"

        total_time = time.time() - start_time
        resp = PipelineResponse(
            answer=full_response,
            search_performed=search_performed,
            search_query=question if search_performed else None,
            total_time_seconds=round(total_time, 2),
        )
        yield {
            "done": True,
            "response": resp.to_dict(),
            "done_reason": last_done_reason,
            "response_mode": response_mode,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _done_event(
        full_response: str,
        search_performed: bool,
        start_time: float,
    ) -> Dict:
        resp = PipelineResponse(
            answer=full_response,
            search_performed=search_performed,
            total_time_seconds=round(time.time() - start_time, 2),
        )
        return {
            "done": True,
            "response": resp.to_dict(),
            "done_reason": "stop",
            "response_mode": "normal",
        }


# ---------------------------------------------------------------------------
# Singleton management (backwards compat)
# ---------------------------------------------------------------------------

_instance: Optional[StreamingPipeline] = None


def get_pipeline(provider=None) -> StreamingPipeline:
    """Get or create the pipeline singleton."""
    global _instance
    if _instance is None:
        _instance = StreamingPipeline(provider=provider)
    return _instance


def reset_pipeline():
    """Reset the singleton (for testing)."""
    global _instance
    _instance = None
