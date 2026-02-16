"""
Trinity Agentic Pipeline — Single-Pass Orchestrator

Routes every query through one path:
  1. Detect if tools are needed
  2. If yes → ReAct loop (iterative tool calling with streaming)
  3. If no  → direct chat_stream through LLMProvider

Provider-agnostic: works with OllamaProvider or any future LLMProvider subclass.

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
from .llm_provider import LLMProvider
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

_SMALLTALK_NORMALIZE = re.compile(r"[^\w\s']")
_SMALLTALK_MAX_WORDS = 6
_SMALLTALK_CANONICAL = {
    "hi",
    "hello",
    "hello there",
    "hey",
    "hey there",
    "hi there",
    "good morning",
    "good afternoon",
    "good evening",
    "morning",
    "afternoon",
    "evening",
    "sup",
    "whats up",
    "what's up",
    "how are you",
    "how are you doing",
    "thanks",
    "thank you",
    "thx",
}

_PERSONAL_MEMORY_PATTERNS = [
    re.compile(r"\bwhat do you know about me\b"),
    re.compile(r"\bwhat do you remember about me\b"),
    re.compile(r"\bdo you remember\b"),
    re.compile(r"\bwho am i\b"),
    re.compile(r"\bwhat(?:'s| is) my (?:name|job|role|company|goal|preference|preferences)\b"),
    re.compile(r"\bwhere do i (?:live|work)\b"),
    re.compile(r"\btell me about me\b"),
]

_PERSONAL_DISCLOSURE_PATTERNS = [
    re.compile(r"\bmy name is\b"),
    re.compile(r"\bmy favorite\b"),
    re.compile(r"\bi(?:'m| am)\b"),
    re.compile(r"\bi (?:like|love|enjoy|prefer)\b"),
    re.compile(r"\bi (?:live|work|study)\b"),
    re.compile(r"\bmy (?:goal|hobby|job|role|company|project)\b"),
]

_PERSONAL_DISCLOSURE_NEGATIVE_PATTERNS = [
    re.compile(r"\bcan you\b"),
    re.compile(r"\bcould you\b"),
    re.compile(r"\bwould you\b"),
    re.compile(r"\bhelp me\b"),
    re.compile(r"\bhow do i\b"),
    re.compile(r"\bwhat is\b"),
    re.compile(r"\bwhy is\b"),
]


def _question_requests_personal_memory(question: str) -> bool:
    """Return True only when the user explicitly asks for personal/profile recall."""
    normalized = _normalize_smalltalk_text(question)
    if not normalized:
        return False

    return any(pattern.search(normalized) for pattern in _PERSONAL_MEMORY_PATTERNS)


def is_personal_disclosure(question: str) -> bool:
    """Return True for first-person self-disclosure statements (not requests)."""
    normalized = _normalize_smalltalk_text(question)
    if not normalized:
        return False
    if "?" in (question or ""):
        return False
    if any(pattern.search(normalized) for pattern in _PERSONAL_DISCLOSURE_NEGATIVE_PATTERNS):
        return False
    return any(pattern.search(normalized) for pattern in _PERSONAL_DISCLOSURE_PATTERNS)


def _normalize_smalltalk_text(text: str) -> str:
    normalized = (text or "").strip().lower().replace("\u2019", "'")
    normalized = _SMALLTALK_NORMALIZE.sub(" ", normalized)
    return " ".join(normalized.split())


def is_trivial_smalltalk(question: str, context_messages: Optional[List[Dict]] = None) -> bool:
    """Return True for low-value phatic messages that should use a fast path."""
    normalized = _normalize_smalltalk_text(question)
    if not normalized:
        return False

    if len(normalized.split()) > _SMALLTALK_MAX_WORDS:
        return False

    # Keep this conservative: only clear greetings/acknowledgements.
    return normalized in _SMALLTALK_CANONICAL


def _smalltalk_fast_response(question: str) -> str:
    """Generate a concise non-LLM response for trivial greetings."""
    normalized = _normalize_smalltalk_text(question)

    if normalized in {"thanks", "thank you", "thx"}:
        return "You're welcome. What do you want to work on next?"
    if normalized in {"how are you", "how are you doing"}:
        return "Doing well and ready to help. What are we tackling?"
    return "Hey. I'm here and ready when you are."


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


def _format_user_memory(
    user_memory: Dict,
    query: str = "",
    include_personal: bool = True,
) -> str:
    """Format user memory into a token-budget-aware profile section for the LLM.

    Args:
        user_memory: User profile payload from storage.
        query: Current user message used for relevance scoring.
        include_personal: If False, suppress identity/relationship facts unless query relevance is high.

    Returns:
        Markdown section for prompt injection.
    """
    from config import PROFILE_MAX_FACTS, PROFILE_RELEVANCE_FLOOR, PROFILE_TOKEN_BUDGET

    if not user_memory or not isinstance(user_memory, dict):
        return ""

    # Import here to avoid circular imports
    try:
        from storage import get_active_facts
        facts = get_active_facts(user_memory)
    except ImportError:
        facts = [
            f for f in user_memory.get("facts", [])
            if isinstance(f, str) or (isinstance(f, dict) and not f.get("deleted", False))
        ]

    if not facts:
        return ""

    # Score each fact
    now_ms = int(time.time() * 1000)
    scored_facts = []
    query_embedding = None

    if query:
        try:
            from .embeddings import cosine_similarity, embed_text
            query_embedding = embed_text(query)
        except Exception:
            pass

    for fact in facts:
        # Handle plain string facts (legacy format)
        if isinstance(fact, str):
            text = fact
            if not text.strip():
                continue
            if not include_personal:
                continue
            score = 0.5 * 0.5 + (3 / 5.0) * 0.3 + 1.0 * 0.2
            scored_facts.append((score, fact, text, "general"))
            continue

        text = fact.get("text") or fact.get("fact") or ""
        if not text:
            continue

        # Relevance to query (0-1)
        relevance = 0.5  # default if no query
        if query_embedding is not None:
            emb = fact.get("embedding")
            if emb is not None:
                try:
                    import numpy as np
                    relevance = float(cosine_similarity(query_embedding, np.array(emb)))
                except Exception:
                    relevance = 0.5

        # Importance (normalized 0-1)
        importance = fact.get("importance", 3) / 5.0

        # Recency (0-1, decays over 30 days)
        # Use valid_at for temporal accuracy, fall back to last_mentioned or created_at
        created_at = fact.get("valid_at") or fact.get("last_mentioned") or fact.get("created_at", now_ms)
        age_days = max(0, (now_ms - created_at) / (1000 * 86400))
        recency = max(0.0, 1.0 - (age_days / 30.0))

        # Combined score
        score = relevance * 0.5 + importance * 0.3 + recency * 0.2

        # Identity facts get a big boost — always include the user's name
        category = fact.get("category", "general")
        if category == "identity" and include_personal:
            score += 0.35

        if not include_personal and category in {"identity", "relationships"}:
            continue

        if not include_personal:
            if category == "preferences":
                pass
            elif query_embedding is not None and score < PROFILE_RELEVANCE_FLOOR:
                continue
            elif query_embedding is None:
                continue

        scored_facts.append((score, fact, text, category))

    if not scored_facts:
        return ""

    # Sort by score (highest first)
    scored_facts.sort(key=lambda x: x[0], reverse=True)

    # Pack into token budget
    lines_by_category = {}
    token_count = 50  # header overhead

    selected_count = 0
    for score, fact, text, category in scored_facts:
        if selected_count >= PROFILE_MAX_FACTS:
            break

        line = f"- {text}"
        line_tokens = _estimate_tokens(line)

        if token_count + line_tokens > PROFILE_TOKEN_BUDGET:
            continue

        if category not in lines_by_category:
            lines_by_category[category] = []
        lines_by_category[category].append(line)
        token_count += line_tokens
        selected_count += 1

    if not lines_by_category:
        return ""

    # Format with category headers
    sections = []
    category_order = ["identity", "work", "interests", "preferences", "relationships", "general"]
    for cat in category_order:
        if cat in lines_by_category:
            label = cat.title()
            sections.append(f"### {label}")
            sections.extend(lines_by_category[cat])

    return "## What you know about this user\n" + "\n".join(sections)


def _format_semantic_context(semantic_context: Optional[List[Dict]]) -> str:
    """Format semantic retrieval results for prompt injection."""
    if not semantic_context:
        return ""

    lines = ["## Relevant past conversation"]

    for item in semantic_context[:8]:
        role = item.get("role", "unknown")
        content = (item.get("content") or "").strip()
        if not content:
            continue
        if len(content) > 280:
            content = content[:277] + "..."

        chat_id = item.get("chat_id")
        if chat_id:
            lines.append(f"- ({role}, chat {chat_id[:8]}) {content}")
        else:
            lines.append(f"- ({role}) {content}")

    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _format_graph_context(graph_context: Optional[List[Dict]]) -> str:
    """Format graph triples for compact prompt injection."""
    if not graph_context:
        return ""

    lines = ["## Relevant long-term relationships"]
    for triple in graph_context[:6]:
        subject = triple.get("subject", "user")
        predicate = triple.get("predicate", "related_to")
        obj = triple.get("object", "")
        if not obj:
            continue
        lines.append(f"- {subject} {predicate} {obj}")

    if len(lines) == 1:
        return ""
    return "\n".join(lines)


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
# AGENT PIPELINE
# ============================================================================


# Backwards-compat alias so any test doing ``from services.agent import OllamaClient``
# still works — it gets the provider-based equivalent.
try:
    from .ollama_provider import OllamaProvider as OllamaClient  # noqa: F401
except ImportError:
    OllamaClient = None  # type: ignore[assignment,misc]


class AgentPipeline:
    """
    Single-pass reasoning pipeline.

    Every query follows one path:
      1. Detect tools needed
      2. Web search if applicable
      3. If tools → ReAct loop (streaming)
         Else → direct generate_stream

    Accepts any LLMProvider — the caller decides which backend to use.
    """

    def __init__(self, provider=None, ollama_host=None, model=None):
        """Create an AgentPipeline.

        Args:
            provider: An LLMProvider instance (preferred).
            ollama_host: Legacy — creates an OllamaProvider if no provider given.
            model: Legacy — model name for OllamaProvider fallback.
        """
        if provider is not None:
            self.client = provider
        elif ollama_host is not None:
            from .ollama_provider import OllamaProvider
            self.client = OllamaProvider(host=ollama_host, model=model or "qwen2.5-coder:32b")
        else:
            from .provider_factory import get_provider
            self.client = get_provider()

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
        graph_context: List[Dict] = None,
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

        fast_path = bool(kwargs.get("fast_path")) or is_trivial_smalltalk(question, context_messages)
        if fast_path:
            logger.info("⚡ Agent fast-path: trivial smalltalk")
            yield format_phase_update("executing")
            full_response = _smalltalk_fast_response(question)
            yield {"token": full_response}
            total_time = time.time() - start_time
            response = AgentResponse(
                answer=full_response,
                search_performed=False,
                search_query=None,
                total_time_seconds=round(total_time, 2),
            )
            yield {"done": True, "response": response.to_dict(), "done_reason": "stop"}
            return

        tools_needed = self._should_use_react(question)
        disclosure_path = bool(kwargs.get("disclosure_path")) or is_personal_disclosure(question)
        include_personal_memory = _question_requests_personal_memory(question)
        formatted_user_memory = ""

        if not disclosure_path:
            formatted_user_memory = _format_user_memory(
                user_memory,
                query=question,
                include_personal=include_personal_memory,
            )
            formatted_semantic = _format_semantic_context(semantic_context)
            formatted_graph = _format_graph_context(graph_context)
            if formatted_semantic:
                if formatted_user_memory:
                    formatted_user_memory = f"{formatted_user_memory}\n\n{formatted_semantic}"
                else:
                    formatted_user_memory = formatted_semantic
            if formatted_graph:
                if formatted_user_memory:
                    formatted_user_memory = f"{formatted_user_memory}\n\n{formatted_graph}"
                else:
                    formatted_user_memory = formatted_graph

        logger.info(
            "🧠 Agent streaming: single-pass, tools=%s, disclosure=%s",
            tools_needed,
            disclosure_path,
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
                    user_memory=formatted_user_memory,
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
                    question, context_messages, formatted_user_memory, search_context
                )
                filtered_parts = []
                for token in self._filter_think_blocks(
                    self.client.generate_stream(
                        prompt, kwargs.get("max_tokens", MAX_TOKENS), timeout=TIMEOUT
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


def get_agent_pipeline(provider=None, ollama_host=None, model=None):
    """Get or create the agent pipeline singleton.

    Args:
        provider: An LLMProvider instance (preferred).
        ollama_host: Legacy — creates OllamaProvider.
        model: Legacy — model name for OllamaProvider.
    """
    global _pipeline_instance

    if _pipeline_instance is None:
        if provider is not None:
            _pipeline_instance = AgentPipeline(provider=provider)
        elif ollama_host is not None:
            _pipeline_instance = AgentPipeline(ollama_host=ollama_host, model=model)
        else:
            # Default: use the configured provider from factory
            from .provider_factory import get_provider
            _pipeline_instance = AgentPipeline(provider=get_provider())

    return _pipeline_instance


def reset_agent_pipeline():
    """Reset the pipeline (for testing or config changes)."""
    global _pipeline_instance
    _pipeline_instance = None
