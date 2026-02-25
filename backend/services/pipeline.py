"""
Trinity — Streaming Pipeline

Extracts the core streaming logic from the former 1086-line ``agent.py``
god module into a focused, composable pipeline.

The pipeline follows one path for every query:
  1. If tools needed → ReAct loop (streaming)
  2. Else → direct chat_stream with think-block filtering

All queries go through the LLM. There are no hardcoded responses.

Public API
----------
* ``StreamingPipeline`` — main class (accepts any LLMProvider)
* ``PipelineResponse`` — result dataclass
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, Generator, List, Optional

from middleware.observability import record_complexity, record_routing

from .llm_provider import LLMProvider
from .loading_messages import format_phase_update
from .search import format_search_context, is_search_available, search_web
from .think_filter import (
    contains_fenced_code,
    detect_prompt_leakage,
    filter_think_blocks,
    looks_like_code,
    wrap_code_block,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

from config import DEFAULT_MAX_TOKENS as MAX_TOKENS  # noqa: E402 — synced with prompt assembler

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
# Tool-call rescue: catches tool-call JSON/XML on the direct-chat path
# ---------------------------------------------------------------------------

# Characters that could start a tool-call response (JSON, XML, markdown bold, code fence)
_TOOL_CALL_START_CHARS = frozenset('{<*`')
# Buffer threshold: accumulate this many chars before deciding tool-call vs normal
_TOOL_RESCUE_BUFFER_CHARS = 50

_KNOWN_TOOL_NAMES_RE = re.compile(
    r'\b(calculator|code_display|document_search|web_search|fact_check|'
    r'save_memory|recall_memory|search_memory|update_memory|forget_memory|'
    r'read_file|write_file|list_directory|search_codebase|run_command|'
    r'current_datetime)\b',
    re.IGNORECASE,
)


def _is_tool_call_output(text: str) -> bool:
    """Check if LLM output looks like a raw tool call rather than a natural response.

    Detects JSON, XML, and markdown-bold tool-call formats that Qwen3 emits
    when it wants to call a tool but the pipeline is on the direct-chat path.
    """
    stripped = text.strip()
    if not stripped:
        return False

    # Strip code fences for normalisation
    clean = re.sub(r'^```(?:json)?\s*', '', stripped)
    clean = re.sub(r'```\s*$', '', clean).strip()

    # JSON tool call: {"tool": "..."} or {"name": "..."}
    if clean.startswith('{') and re.search(r'"(tool|name)"\s*:', clean):
        return True

    # XML tool call: <tool_call ...>
    if re.match(r'<tool_call', stripped, re.IGNORECASE):
        return True

    # Markdown bold tool name: **save_memory**
    bold_match = re.match(r'\*\*(\w+)\*\*', stripped)
    if bold_match and _KNOWN_TOOL_NAMES_RE.match(bold_match.group(1)):
        return True

    # Bare tool name followed by newline + JSON/XML
    bare_match = re.match(r'^(\w+)\s*\n\s*[<{]', stripped)
    if bare_match and _KNOWN_TOOL_NAMES_RE.match(bare_match.group(1)):
        return True

    return False


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
        tools_needed: Optional[List[str]] = None,
        chat_id: str = None,
        max_tokens: int = MAX_TOKENS,
        timeout: int = TIMEOUT,
        temperature: float = 0.7,
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

        # ----- Tool decision (trusted from context_loader) -----
        use_tools = bool(tools_needed)

        logger.info(
            "🧠 Pipeline: single-pass, tools=%s",
            use_tools,
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
                    temperature=temperature,
                ):
                    if "token" in event:
                        full_response += event["token"]
                    yield event

            else:
                # ------ Direct streaming with tool-call rescue ------
                # Buffer initial tokens to detect if the model is outputting
                # a raw tool-call (JSON/XML) instead of a natural answer.
                # If detected, execute the tool and re-prompt for a real answer.
                filtered_parts: list[str] = []
                _buf: list[str] = []
                _buf_n = 0
                _decided = False
                _rescue = False

                for token in filter_think_blocks(
                    self.client.chat_stream(
                        messages,
                        max_tokens,
                        temperature=temperature,
                        timeout=timeout,
                        think=False,
                    ),
                    filtered_parts,
                ):
                    if isinstance(token, dict) and "__done_reason" in token:
                        last_done_reason = token["__done_reason"]
                        continue

                    # Non-string metadata tokens: yield immediately, don't buffer
                    if not isinstance(token, str):
                        if not (_decided and _rescue):
                            yield {"token": token}
                        continue

                    if _decided:
                        if not _rescue:
                            yield {"token": token}
                        # else: consume silently (filtered_parts still captures it)
                    else:
                        _buf.append(token)
                        _buf_n += len(token)

                        # Fast exit: first real char is not a tool-call starter
                        buf_text = "".join(_buf).lstrip()
                        if buf_text and buf_text[0] not in _TOOL_CALL_START_CHARS:
                            _decided = True
                            for bt in _buf:
                                yield {"token": bt}
                        elif _buf_n >= _TOOL_RESCUE_BUFFER_CHARS:
                            if _is_tool_call_output(buf_text):
                                _decided = True
                                _rescue = True
                                logger.info(
                                    "🔧 Tool rescue: detected tool-call in direct-chat output"
                                )
                            else:
                                _decided = True
                                for bt in _buf:
                                    yield {"token": bt}

                # Handle short responses that ended before buffer threshold
                if not _decided:
                    buf_text = "".join(_buf)
                    if _is_tool_call_output(buf_text):
                        _rescue = True
                        logger.info(
                            "🔧 Tool rescue: detected tool-call in short direct-chat output"
                        )
                    else:
                        for bt in _buf:
                            yield {"token": bt}

                full_response = "".join(filtered_parts)

                # --- Tool-call rescue execution ---
                if _rescue:
                    from .code_executor import execute_tool
                    from .tools import parse_tool_calls

                    tool_calls = parse_tool_calls(full_response)
                    if tool_calls:
                        tc = tool_calls[0]
                        logger.info("🔧 Tool rescue: executing %s", tc.name)

                        yield format_phase_update(
                            "tool_execution", f"Using {tc.name}..."
                        )

                        context = {}
                        if principal_id:
                            context["principal_id"] = principal_id
                        try:
                            success, output = execute_tool(
                                tc.name, tc.params, context=context
                            )
                        except Exception as exc:
                            logger.error("Tool rescue exec error: %s", exc)
                            success, output = False, str(exc)

                        status = "done" if success else "error"
                        yield format_phase_update(
                            "tool_result", f"{tc.name}: {status}"
                        )

                        # Re-prompt with tool result for a natural answer
                        result_text = (
                            output if success else f"Error: {output}"
                        )
                        rescue_msgs = list(messages) + [
                            {
                                "role": "assistant",
                                "content": f"I'll use the {tc.name} tool.",
                            },
                            {
                                "role": "user",
                                "content": (
                                    f"[Tool Result: {tc.name}]\n{result_text}\n\n"
                                    f"Now give your final answer based on this result."
                                ),
                            },
                        ]

                        rescue_parts: list[str] = []
                        for rescue_tok in filter_think_blocks(
                            self.client.chat_stream(
                                rescue_msgs,
                                max_tokens,
                                temperature=temperature,
                                timeout=timeout,
                                think=False,
                            ),
                            rescue_parts,
                        ):
                            if isinstance(rescue_tok, dict) and "__done_reason" in rescue_tok:
                                last_done_reason = rescue_tok["__done_reason"]
                                continue
                            yield {"token": rescue_tok}

                        full_response = "".join(rescue_parts)
                    else:
                        # Detection triggered but parse failed — emit raw output
                        logger.warning(
                            "🔧 Tool rescue: parse returned empty, emitting raw"
                        )
                        yield {"token": full_response}

        except Exception as e:
            logger.error("Pipeline streaming error: %s", e)
            yield {"error": str(e)}

        # Auto-fence unfenced code blocks (deterministic post-processor)
        if looks_like_code(full_response) and not contains_fenced_code(full_response):
            full_response = wrap_code_block(full_response, "")

        # --- Prompt leakage detection (canary + n-gram) ---
        system_content = ""
        canaries: list[str] = []
        if messages:
            system_content = messages[0].get("content", "")
            # Extract canary tokens embedded during assembly
            import re as _re

            canary_match = _re.search(
                r"\[Internal reference: (CANARY_\w+(?: CANARY_\w+)*)\]",
                system_content,
            )
            if canary_match:
                canaries = canary_match.group(1).split()
        if canaries and detect_prompt_leakage(full_response, canaries, system_content):
            full_response = (
                "I'm not able to share that information. "
                "How can I help you with something else?"
            )

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
