"""
Trinity Agentic Pipeline — Single-Pass Orchestrator

Routes every query through one path:
  1. Detect if tools are needed
  2. If yes → ReAct loop (iterative tool calling with streaming)
  3. If no  → direct chat_stream through Ollama

No complexity classification. No multi-pass. One prompt, one response.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, Generator, List, Optional

import requests

from middleware.observability import record_complexity, record_routing, track_agent_pass

from .agent_prompts import build_system_prompt
from .loading_messages import format_phase_update
from .search import format_search_context, is_search_available, search_web
from .tools import detect_tools_needed

# Import ReAct loop (with graceful fallback)
try:
    from config import REACT_ENABLED
    from .react_loop import ReactLoop

    REACT_AVAILABLE = True
except ImportError as e:
    logging.warning(f"ReAct loop not available: {e}")
    REACT_AVAILABLE = False
    REACT_ENABLED = False

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

MAX_TOKENS = 24000       # Generous token limit for thorough responses
TIMEOUT = 300            # 5 min connection timeout (streaming keeps alive)
SEARCH_TIMEOUT = 30      # Web search timeout


# Regex to strip <think>...</think> blocks from streaming tokens
_THINK_OPEN = re.compile(r"<think>", re.IGNORECASE)
_THINK_CLOSE = re.compile(r"</think>", re.IGNORECASE)


def _format_user_memory(user_memory: Dict) -> str:
    """Format user memory dict into clean text for LLM consumption.

    Handles both legacy fact formats:
      - {"fact": "..."} (from REST API)
      - {"text": "...", "embedding": [...]} (from memory tools)
      - plain strings
    Strips embeddings so they never pollute the prompt.
    """
    if not user_memory or not isinstance(user_memory, dict):
        return ""
    facts = user_memory.get("facts", [])
    if not facts:
        return ""
    lines = []
    for fact in facts[:10]:
        if isinstance(fact, dict):
            text = fact.get("text") or fact.get("fact") or ""
            if not text:
                continue
            category = fact.get("category", "")
            if category and category != "general":
                lines.append(f"- [{category}] {text}")
            else:
                lines.append(f"- {text}")
        elif isinstance(fact, str):
            lines.append(f"- {fact}")
    if not lines:
        return ""
    return "## What you know about this user\n" + "\n".join(lines)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class AgentResponse:
    """Final response from the agent pipeline."""

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


# ============================================================================
# OLLAMA INTERFACE
# ============================================================================


class OllamaClient:
    """Client for Ollama API calls."""

    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.host = host
        self.model = model

    def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 30,
        **kwargs,
    ) -> str:
        """Generate a response (non-streaming)."""
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens, "temperature": temperature, "num_ctx": 32768},
                },
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"Ollama error: {response.status_code}")
                return ""

            return response.json().get("response", "")

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama timeout after {timeout}s")
            return ""
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return ""

    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 60,
        **kwargs,
    ) -> Generator[str, None, None]:
        """Generate a response with streaming."""
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {"num_predict": max_tokens, "temperature": temperature, "num_ctx": 32768},
                },
                stream=True,
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"Ollama error: {response.status_code}")
                return

            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            yield {"__done_reason": chunk.get("done_reason", "stop")}
                            break
                    except json.JSONDecodeError:
                        continue

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama stream timeout after {timeout}s")
        except Exception as e:
            logger.error(f"Ollama stream error: {e}")

    def chat(
        self,
        messages: List[Dict],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 60,
        tools: List[Dict] = None,
        raw_message: bool = False,
        **kwargs,
    ) -> str:
        """Call Ollama /api/chat with messages array (non-streaming)."""
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": temperature, "num_ctx": 32768},
            }
            if tools:
                payload["tools"] = tools

            response = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"Ollama chat error: {response.status_code}")
                return {} if raw_message else ""

            message = response.json().get("message", {})
            return message if raw_message else message.get("content", "")

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama chat timeout after {timeout}s")
            return {} if raw_message else ""
        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
            return {} if raw_message else ""

    def chat_stream(
        self,
        messages: List[Dict],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 60,
        **kwargs,
    ) -> Generator[str, None, None]:
        """Call Ollama /api/chat with messages array (streaming)."""
        try:
            response = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "options": {"num_predict": max_tokens, "temperature": temperature, "num_ctx": 32768},
                },
                stream=True,
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"Ollama chat stream error: {response.status_code}")
                return

            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            yield {"__done_reason": chunk.get("done_reason", "stop")}
                            break
                    except json.JSONDecodeError:
                        continue

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama chat stream timeout after {timeout}s")
        except Exception as e:
            logger.error(f"Ollama chat stream error: {e}")


# ============================================================================
# AGENT PIPELINE
# ============================================================================


class AgentPipeline:
    """
    Single-pass reasoning pipeline.

    Every query follows one path:
      1. Detect tools needed
      2. Web search if applicable
      3. If tools → ReAct loop (streaming)
         Else → direct generate_stream
    """

    def __init__(self, ollama_host: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.client = OllamaClient(ollama_host, model)

    def _get_react_loop(self, principal_id: str = None) -> "ReactLoop":
        """Create a ReactLoop with user context for this request."""
        if not REACT_AVAILABLE:
            return None
        context = {}
        if principal_id:
            context["principal_id"] = principal_id
        return ReactLoop(self.client, context=context)

    def _should_use_react(self, question: str) -> bool:
        """Check if this query should use the ReAct loop."""
        if not REACT_AVAILABLE or not REACT_ENABLED:
            return False
        tools = detect_tools_needed(question)
        return len(tools) > 0

    def _filter_think_blocks(
        self, token_stream: Generator, accumulator: list
    ) -> Generator[str, None, None]:
        """Filter <think>...</think> blocks from a streaming token generator.

        Qwen3 (and some other models) emit <think>reasoning</think> before
        the actual answer. These must be stripped so the frontend never sees
        raw XML tags.

        Args:
            token_stream: Generator yielding str tokens or dict metadata.
            accumulator: Mutable list — clean text appended for caller to read.
        Yields:
            str tokens with think blocks removed.
            dict metadata tokens (e.g. __done_reason) are yielded unchanged.
        """
        inside_think = False
        buf = ""

        for token in token_stream:
            if isinstance(token, dict):
                yield token
                continue

            buf += token

            while buf:
                if inside_think:
                    close_match = _THINK_CLOSE.search(buf)
                    if close_match:
                        buf = buf[close_match.end():]
                        inside_think = False
                        continue
                    else:
                        if len(buf) > 8:
                            buf = buf[-8:]
                        break
                else:
                    open_match = _THINK_OPEN.search(buf)
                    if open_match:
                        before = buf[:open_match.start()]
                        if before:
                            accumulator.append(before)
                            yield before
                        buf = buf[open_match.end():]
                        inside_think = True
                        continue
                    else:
                        if len(buf) > 7:
                            safe = buf[:-7]
                            buf = buf[-7:]
                            accumulator.append(safe)
                            yield safe
                        break

        # Flush remaining buffer
        if buf and not inside_think:
            accumulator.append(buf)
            yield buf

    def process_streaming(
        self,
        question: str,
        context_messages: List[Dict] = None,
        user_memory: Dict = None,
        semantic_context: List[Dict] = None,
        principal_id: str = None,
        **kwargs,
    ) -> Generator[Dict, None, None]:
        """
        Single-pass streaming pipeline.

        Yields:
            {"phase": "...", "message": "..."} — progress updates
            {"token": "..."} — streamed response tokens
            {"done": True, "response": {...}} — final metadata
        """
        start_time = time.time()
        context_messages = context_messages or []
        user_memory = user_memory or {}
        full_response = ""
        search_context = ""
        search_performed = False
        last_done_reason = "stop"

        record_complexity("single_pass")
        record_routing("agent")

        tools_needed = self._should_use_react(question)

        logger.info(
            f"🧠 Agent streaming: single-pass, tools={tools_needed}"
        )

        # === WEB SEARCH (if applicable) ===
        # Web search for tool-using queries is handled by the ReAct loop.
        # For direct queries, check if search keywords are present.
        if not tools_needed and is_search_available():
            search_keywords = ["latest", "current", "today", "news", "price", "weather",
                               "recent", "update", "2024", "2025", "2026", "who won", "score"]
            question_lower = question.lower()
            if any(kw in question_lower for kw in search_keywords):
                yield format_phase_update("searching")
                search_result = search_web(question, count=5, timeout=SEARCH_TIMEOUT)
                if not search_result.error and search_result.results:
                    search_context = format_search_context(search_result)
                    search_performed = True
                    yield {
                        "phase": "searching",
                        "message": f"Found {len(search_result.results)} sources...",
                    }

        try:
            yield format_phase_update("executing")

            if tools_needed:
                # ReAct loop for tool-using queries
                for event in self._get_react_loop(principal_id).execute_streaming(
                    question=question,
                    context_messages=context_messages,
                    user_memory=_format_user_memory(user_memory),
                    search_context=search_context,
                    max_tokens=MAX_TOKENS,
                    timeout=TIMEOUT,
                ):
                    if "token" in event:
                        full_response += event["token"]
                    yield event
            else:
                # Direct single-pass generation
                prompt = build_system_prompt(
                    question, context_messages, _format_user_memory(user_memory), search_context
                )
                filtered_parts = []
                for token in self._filter_think_blocks(
                    self.client.generate_stream(
                        prompt, MAX_TOKENS, timeout=TIMEOUT
                    ),
                    filtered_parts,
                ):
                    if isinstance(token, dict) and "__done_reason" in token:
                        last_done_reason = token["__done_reason"]
                        continue
                    yield {"token": token}
                full_response = "".join(filtered_parts)

        except Exception as e:
            logger.error(f"Agent streaming error: {e}")
            yield {"error": str(e)}

        total_time = time.time() - start_time

        response = AgentResponse(
            answer=full_response,
            search_performed=search_performed,
            search_query=question if search_performed else None,
            total_time_seconds=round(total_time, 2),
        )

        yield {"done": True, "response": response.to_dict(), "done_reason": last_done_reason}


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_pipeline_instance: Optional[AgentPipeline] = None


def get_agent_pipeline(ollama_host: str = None, model: str = None) -> AgentPipeline:
    """Get or create the agent pipeline singleton."""
    global _pipeline_instance

    if _pipeline_instance is None:
        import os
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config import MODEL_NAME as DEFAULT_MODEL
        from config import OLLAMA_HOST as DEFAULT_HOST

        _pipeline_instance = AgentPipeline(
            ollama_host=ollama_host or DEFAULT_HOST, model=model or DEFAULT_MODEL
        )

    return _pipeline_instance


def reset_agent_pipeline():
    """Reset the pipeline (for testing or config changes)."""
    global _pipeline_instance
    _pipeline_instance = None
