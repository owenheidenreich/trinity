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
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Generator, List, Optional

import requests

from middleware.observability import record_complexity, record_routing, track_agent_pass

from .agent_prompts import build_chat_messages, build_system_prompt
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

MAX_TOKENS = 16384       # Visible answer only (think=False default)
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
    "what up",
    "what up friend",
    "what up my friend",
    "whats up",
    "what's up",
    "how are you",
    "how are you doing",
    "thanks",
    "thank you",
    "thx",
}
_SMALLTALK_GREETING_TOKENS = {
    "hi",
    "hello",
    "hey",
    "yo",
    "sup",
    "what",
    "up",
    "my",
    "friend",
    "morning",
    "afternoon",
    "evening",
    "thanks",
    "thank",
    "you",
    "thx",
    "trinity",
    "there",
}

_CODE_REQUEST_PATTERNS = [
    re.compile(r"\b(write|create|generate|build|make|implement)\b.*\b(code|script|function|program|file)\b"),
    re.compile(r"\b(show|give)\b.*\b(code|implementation|example)\b"),
    re.compile(r"\b(can you|could you)\b.*\b(code|script|function|program|file)\b"),
    re.compile(r"\b(python|javascript|typescript|html|css|sql|bash|shell|rust|go|java|c\+\+|c#)\b"),
]
_EXECUTION_INTENT_PATTERNS = [
    re.compile(r"\b(run|execute|debug|fix|test|benchmark|profile)\b"),
]
_CODE_LANGUAGE_PATTERNS = [
    (re.compile(r"\btypescript\b|\b\.ts\b"), "typescript"),
    (re.compile(r"\bjavascript\b|\b\.js\b"), "javascript"),
    (re.compile(r"\bpython\b|\b\.py\b"), "python"),
    (re.compile(r"\bhtml\b|\b\.html\b"), "html"),
    (re.compile(r"\bcss\b|\b\.css\b"), "css"),
    (re.compile(r"\bsql\b"), "sql"),
    (re.compile(r"\brust\b|\b\.rs\b"), "rust"),
    (re.compile(r"\bgo\b|\b\.go\b"), "go"),
    (re.compile(r"\bjava\b|\b\.java\b"), "java"),
    (re.compile(r"\bbash\b|\bshell\b|\b\.sh\b"), "bash"),
]
_FAKE_FILE_CLAIM_PATTERN = re.compile(
    r"\b(file|script|program)\b[\w\s\"'`:/\\.-]{0,120}\b(created|written|saved|generated)\b",
    re.IGNORECASE,
)

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

_CATEGORY_REPRESENTATIVES = {
    "identity": "user name age location background timezone language identity personal profile",
    "work": "user work job role company project startup engineering stack coding professional",
    "interests": "user interests hobbies learning reading sports music goals topics curiosity",
    "preferences": "user preferences preferred style format tone tools language response settings",
    "relationships": "user relationships partner cofounder friend colleague family team collaborators",
    "general": "durable facts about the user",
}
_CATEGORY_EMBEDDINGS: Dict[str, "object"] = {}
_CATEGORY_EMBEDDINGS_LOCK = threading.Lock()
_PREFERENCE_QUERY_HINTS = {
    "style",
    "tone",
    "format",
    "respond",
    "reply",
    "wording",
    "color",
    "green",
    "concise",
    "verbose",
    "bullet",
}


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


def _query_targets_response_preferences(query: str) -> bool:
    normalized = _normalize_smalltalk_text(query)
    if not normalized:
        return False
    words = set(normalized.split())
    return any(hint in words for hint in _PREFERENCE_QUERY_HINTS)


def is_trivial_smalltalk(question: str, context_messages: Optional[List[Dict]] = None) -> bool:
    """Return True for low-value phatic messages that should use a fast path."""
    normalized = _normalize_smalltalk_text(question)
    if not normalized:
        return False

    if len(normalized.split()) > _SMALLTALK_MAX_WORDS:
        return False

    # Keep this conservative: only clear greetings/acknowledgements.
    if normalized in _SMALLTALK_CANONICAL:
        return True

    words = normalized.split()
    if 1 <= len(words) <= 3 and all(w in _SMALLTALK_GREETING_TOKENS for w in words):
        return True

    return False


def _smalltalk_fast_response(question: str) -> str:
    """Generate a concise non-LLM response for trivial greetings."""
    normalized = _normalize_smalltalk_text(question)

    if normalized in {"thanks", "thank you", "thx"}:
        return "You're welcome. What do you want to work on next?"
    if normalized in {"how are you", "how are you doing"}:
        return "Doing well and ready to help. What are we tackling?"
    return "Hey. I'm here and ready when you are."


def _is_code_generation_request(question: str) -> bool:
    text = _normalize_smalltalk_text(question)
    if not text:
        return False
    if any(pattern.search(text) for pattern in _EXECUTION_INTENT_PATTERNS):
        return False
    return any(pattern.search(text) for pattern in _CODE_REQUEST_PATTERNS)


def _infer_code_language(question: str) -> str:
    text = _normalize_smalltalk_text(question)
    for pattern, language in _CODE_LANGUAGE_PATTERNS:
        if pattern.search(text):
            return language
    return "text"


def _contains_fenced_code(text: str) -> bool:
    return bool(text and text.count("```") >= 2)


def _looks_like_code(text: str) -> bool:
    if not text:
        return False
    code_markers = (
        "def ",
        "class ",
        "function ",
        "const ",
        "let ",
        "var ",
        "import ",
        "console.log",
        "print(",
        "{",
        "}",
        "<html",
        "SELECT ",
        "#include",
        "public static",
    )
    snippet = text.strip()
    if any(marker in snippet for marker in code_markers):
        return True
    lines = [line for line in snippet.splitlines() if line.strip()]
    return len(lines) >= 3 and any(("=" in line or ":" in line) for line in lines[:6])


def _wrap_code_block(text: str, language: str) -> str:
    body = (text or "").strip()
    return f"```{language}\n{body}\n```" if body else f"```{language}\n\n```"


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


def _compute_category_boosts(
    query: str,
    query_embedding,
    embed_text,
    cosine_similarity,
) -> Dict[str, float]:
    """Compute query-adaptive category boosts from embedding similarity."""
    import numpy as np

    boosts = {cat: 0.0 for cat in _CATEGORY_REPRESENTATIVES}
    if query_embedding is None:
        return boosts
    if not isinstance(query_embedding, np.ndarray):
        query_embedding = np.array(query_embedding)

    personal_query = _question_requests_personal_memory(query)
    if personal_query:
        multipliers = {
            "identity": 0.22,
            "relationships": 0.22,
            "work": 0.08,
            "interests": 0.08,
            "preferences": 0.08,
            "general": 0.05,
        }
    else:
        multipliers = {
            "identity": 0.05,
            "relationships": 0.05,
            "work": 0.18,
            "interests": 0.18,
            "preferences": 0.14,
            "general": 0.10,
        }

    for category, representative in _CATEGORY_REPRESENTATIVES.items():
        rep_emb = None
        with _CATEGORY_EMBEDDINGS_LOCK:
            rep_emb = _CATEGORY_EMBEDDINGS.get(category)
            if rep_emb is None:
                generated = embed_text(representative)
                if generated is not None:
                    rep_emb = np.array(generated)
                    _CATEGORY_EMBEDDINGS[category] = rep_emb

        if rep_emb is None:
            continue

        try:
            similarity = float(cosine_similarity(query_embedding, rep_emb))
        except Exception:
            similarity = 0.0
        boosts[category] = max(0.0, similarity) * multipliers.get(category, 0.0)

    return boosts


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
    embed_text = None
    cosine_similarity = None
    category_boosts = {cat: 0.0 for cat in _CATEGORY_REPRESENTATIVES}

    if query:
        try:
            from .embeddings import cosine_similarity as cosine_similarity_fn, embed_text as embed_text_fn

            cosine_similarity = cosine_similarity_fn
            embed_text = embed_text_fn
            query_embedding = embed_text(query)
            category_boosts = _compute_category_boosts(
                query=query,
                query_embedding=query_embedding,
                embed_text=embed_text,
                cosine_similarity=cosine_similarity,
            )
        except Exception:
            pass

    prefers_style_memory = _query_targets_response_preferences(query)
    personal_recall_query = _question_requests_personal_memory(query)

    for fact in facts:
        # Handle plain string facts (legacy format)
        if isinstance(fact, str):
            text = fact
            if not text.strip():
                continue
            if not include_personal:
                continue
            score = 0.5 * 0.5 + (3 / 5.0) * 0.3 + 1.0 * 0.2 + category_boosts.get("general", 0.0)
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

        category = fact.get("category", "general")
        score += category_boosts.get(category, 0.0)

        if query and category == "preferences":
            # Style/format preferences should only be injected when the user is
            # explicitly asking for response style guidance or profile recall.
            if not (prefers_style_memory or personal_recall_query):
                continue

        if not include_personal and category in {"identity", "relationships"}:
            continue

        if not include_personal:
            if query_embedding is not None and score < PROFILE_RELEVANCE_FLOOR:
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

    header = "## What you know about this user\n"
    footer = "\n\n*(This is everything you know. If it's not listed here, you don't know it — say so.)*"
    return header + "\n".join(sections) + footer


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
        # Track how many chars have been consumed inside a think block.
        # If the model never closes the tag we flush after a generous limit
        # so the user isn't left with a blank screen.
        think_chars = 0
        _THINK_CHAR_LIMIT = 80_000  # ~20k tokens; triggers safety flush early
        #                            enough that the model still has output budget

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
                        think_chars = 0
                        continue
                    else:
                        # Keep the tail large enough that a split </think>
                        # tag is never lost.  Previous value of 8 was too
                        # small — "</think>" is 8 chars, so we need at
                        # least that much overlap.
                        think_chars += max(0, len(buf) - 16)
                        if len(buf) > 16:
                            buf = buf[-16:]

                        # Safety: if we've been inside <think> for way too
                        # long, the close tag was probably never emitted.
                        # Break out so the remaining text reaches the user.
                        if think_chars > _THINK_CHAR_LIMIT:
                            logger.warning(
                                "Think block exceeded %d chars without closing — "
                                "flushing remaining text to user.",
                                _THINK_CHAR_LIMIT,
                            )
                            inside_think = False
                            think_chars = 0
                            # Don't discard buf — it may contain the start
                            # of the real answer.
                            continue
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
                        think_chars = 0
                        continue
                    else:
                        if len(buf) > 7:
                            safe = buf[:-7]
                            buf = buf[-7:]
                            accumulator.append(safe)
                            yield safe
                        break

        # Flush remaining buffer — even if we're technically still inside
        # an unclosed think block, yield it so the user sees *something*.
        if buf:
            if inside_think:
                logger.warning(
                    "Stream ended inside unclosed <think> block — flushing %d chars.",
                    len(buf),
                )
            accumulator.append(buf)
            yield buf

    @staticmethod
    def _yield_text_chunks(text: str, chunk_size: int = 320) -> Generator[str, None, None]:
        body = text or ""
        if not body:
            return
        for start in range(0, len(body), chunk_size):
            yield body[start:start + chunk_size]

    def _repair_inline_code_response(
        self,
        *,
        question: str,
        draft_response: str,
        language: str,
    ) -> str:
        """
        One-shot repair pass when a code request returned prose without fenced code.
        """
        try:
            repair_messages = [
                {
                    "role": "system",
                    "content": (
                        "You format code answers. Return ONLY runnable code in ONE fenced markdown block. "
                        "No prose, no explanations, no tool tags, no claims about file creation."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"User request:\n{question}\n\n"
                        f"Draft answer (may be invalid):\n{draft_response}\n\n"
                        f"Return corrected code only. Preferred language: {language}."
                    ),
                },
            ]
            repaired = self.client.chat(
                repair_messages,
                max_tokens=min(MAX_TOKENS, 3000),
                temperature=0.1,
                timeout=TIMEOUT,
                think=False,
            )
            repaired_text = (repaired or "").strip()
            if not repaired_text:
                return ""
            if _contains_fenced_code(repaired_text):
                return repaired_text
            if _looks_like_code(repaired_text):
                return _wrap_code_block(repaired_text, language)
            return ""
        except Exception as e:
            logger.debug("Code-response repair skipped: %s", e)
            return ""

    def _finalize_response_contract(self, question: str, response_text: str) -> tuple[str, str]:
        """
        Enforce deterministic inline-code contract for code-generation requests.
        """
        normalized = (response_text or "").strip()
        if not _is_code_generation_request(question):
            return normalized, "normal"

        language = _infer_code_language(question)

        if _contains_fenced_code(normalized):
            return normalized, "inline_code"

        if normalized and _looks_like_code(normalized):
            return _wrap_code_block(normalized, language), "inline_code"

        sanitized_draft = normalized
        if _FAKE_FILE_CLAIM_PATTERN.search(sanitized_draft):
            sanitized_draft = ""

        repaired = self._repair_inline_code_response(
            question=question,
            draft_response=sanitized_draft or normalized,
            language=language,
        )
        if repaired:
            return repaired, "inline_code"

        fallback = sanitized_draft or normalized
        return _wrap_code_block(fallback or "# No code returned.", language), "inline_code"

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
        response_mode = "normal"

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
            yield {
                "done": True,
                "response": response.to_dict(),
                "done_reason": "stop",
                "response_mode": "normal",
            }
            return

        tools_needed = self._should_use_react(question)
        disclosure_path = bool(kwargs.get("disclosure_path")) or is_personal_disclosure(question)
        include_personal_memory = _question_requests_personal_memory(question) or disclosure_path
        formatted_user_memory = ""
        conversation_summary = ""
        last_summarized_index = -1
        chat_id = kwargs.get("chat_id")
        current_message_index = kwargs.get("message_index")
        formatted_user_memory = _format_user_memory(
            user_memory,
            query=question,
            include_personal=include_personal_memory,
        )
        if isinstance(user_memory, dict) and chat_id:
            summaries = user_memory.get("conversation_summaries", {})
            if isinstance(summaries, dict):
                summary_record = summaries.get(chat_id, {})
                if isinstance(summary_record, dict):
                    conversation_summary = str(summary_record.get("summary", "")).strip()
                    try:
                        last_summarized_index = int(
                            summary_record.get("last_summarized_index", -1)
                        )
                    except (TypeError, ValueError):
                        last_summarized_index = -1

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
                               "recent", "update", "2024", "2025", "2026", "who won", "score",
                               "search", "look up", "find out", "how much", "what day",
                               "what time", "right now", "bitcoin", "stock", "crypto"]
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
                messages = build_chat_messages(
                    question,
                    context_messages,
                    formatted_user_memory,
                    search_context,
                    include_tools=False,
                    chat_id=kwargs.get("chat_id"),
                    conversation_summary=conversation_summary,
                    last_summarized_index=last_summarized_index,
                    current_message_index=current_message_index,
                )
                code_intent = _is_code_generation_request(question)
                if code_intent:
                    # Deterministic inline-code contract path.
                    generated = self.client.chat(
                        messages,
                        kwargs.get("max_tokens", MAX_TOKENS),
                        timeout=TIMEOUT,
                        think=False,
                    )
                    finalized, response_mode = self._finalize_response_contract(question, generated or "")
                    full_response = finalized
                    for chunk in self._yield_text_chunks(full_response):
                        yield {"token": chunk}
                    last_done_reason = "stop"
                else:
                    # Direct single-pass chat (think=False to avoid
                    # proxy timeouts — think blocks produce no SSE events
                    # and the 60s Akash read_timeout kills the connection).
                    # Uses /api/chat with structured messages for proper
                    # turn-taking awareness (games, role-play, multi-turn).
                    filtered_parts = []
                    for token in self._filter_think_blocks(
                        self.client.chat_stream(
                            messages,
                            kwargs.get("max_tokens", MAX_TOKENS),
                            timeout=TIMEOUT,
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
            logger.error(f"Agent streaming error: {e}")
            yield {"error": str(e)}

        total_time = time.time() - start_time
        if response_mode == "normal" and _contains_fenced_code(full_response):
            response_mode = "inline_code"

        response = AgentResponse(
            answer=full_response,
            search_performed=search_performed,
            search_query=question if search_performed else None,
            total_time_seconds=round(total_time, 2),
        )

        yield {
            "done": True,
            "response": response.to_dict(),
            "done_reason": last_done_reason,
            "response_mode": response_mode,
        }


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
