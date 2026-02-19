"""
Trinity Backend — Query Classifier

Extracted from agent.py (1086 lines). Contains all query classification logic:
  - is_trivial_smalltalk() — detect greetings/acknowledgements
  - is_personal_disclosure() — detect self-disclosure statements
  - is_code_generation_request() — detect code requests
  - classify_context_level() — determine NONE / MINIMAL / FULL context loading

Each function is evaluated ONCE per request in context_loader.py.
No re-evaluation in agent.py or generate.py.
"""

import re
from enum import Enum
from typing import List, Optional

# ---------------------------------------------------------------------------
# Context level enum (used by context_loader.py)
# ---------------------------------------------------------------------------


class ContextLevel(Enum):
    NONE = "none"
    MINIMAL = "minimal"
    DISCLOSURE = "disclosure"
    FULL = "full"


# ContextLevel is defined here (canonical location) and imported by
# context_loader.py — no re-import needed.


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SMALLTALK_NORMALIZE = re.compile(r"[^\w\s']")


def _normalize_text(text: str) -> str:
    """Normalize text for classification: lowercase, strip punctuation, collapse whitespace."""
    normalized = (text or "").strip().lower().replace("\u2019", "'")
    normalized = _SMALLTALK_NORMALIZE.sub(" ", normalized)
    return " ".join(normalized.split())


# ---------------------------------------------------------------------------
# Smalltalk detection
# ---------------------------------------------------------------------------

_SMALLTALK_MAX_WORDS = 6

_SMALLTALK_CANONICAL = {
    "hi", "hello", "hello there", "hey", "hey there", "hi there",
    "good morning", "good afternoon", "good evening",
    "morning", "afternoon", "evening",
    "sup", "what up", "what up friend", "what up my friend",
    "whats up", "what's up",
    "how are you", "how are you doing",
    "thanks", "thank you", "thx",
}

_SMALLTALK_GREETING_TOKENS = {
    "hi", "hello", "hey", "yo", "sup", "what", "up", "my", "friend",
    "morning", "afternoon", "evening", "thanks", "thank", "you", "thx",
    "trinity", "there",
}


def is_trivial_smalltalk(question: str, context_messages: Optional[List] = None) -> bool:
    """
    Return True for low-value phatic messages that should use a fast path.

    Conservative: only clear greetings/acknowledgements.
    """
    normalized = _normalize_text(question)
    if not normalized:
        return False
    if len(normalized.split()) > _SMALLTALK_MAX_WORDS:
        return False
    if normalized in _SMALLTALK_CANONICAL:
        return True
    words = normalized.split()
    if 1 <= len(words) <= 3 and all(w in _SMALLTALK_GREETING_TOKENS for w in words):
        return True
    return False


def smalltalk_fast_response(question: str) -> str:
    """Generate a concise non-LLM response for trivial greetings."""
    normalized = _normalize_text(question)
    if normalized in {"thanks", "thank you", "thx"}:
        return "You're welcome. What do you want to work on next?"
    if normalized in {"how are you", "how are you doing"}:
        return "Doing well and ready to help. What are we tackling?"
    return "Hey. I'm here and ready when you are."


# ---------------------------------------------------------------------------
# Personal disclosure detection
# ---------------------------------------------------------------------------

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


def is_personal_disclosure(question: str) -> bool:
    """Return True for first-person self-disclosure statements (not requests)."""
    normalized = _normalize_text(question)
    if not normalized:
        return False
    if "?" in (question or ""):
        return False
    if any(p.search(normalized) for p in _PERSONAL_DISCLOSURE_NEGATIVE_PATTERNS):
        return False
    return any(p.search(normalized) for p in _PERSONAL_DISCLOSURE_PATTERNS)


# ---------------------------------------------------------------------------
# Personal memory recall detection
# ---------------------------------------------------------------------------

_PERSONAL_MEMORY_PATTERNS = [
    re.compile(r"\bwhat do you know about me\b"),
    re.compile(r"\bwhat do you remember about me\b"),
    re.compile(r"\bdo you remember\b"),
    re.compile(r"\bwho am i\b"),
    re.compile(r"\bwhat(?:'s| is) my (?:name|job|role|company|goal|preference|preferences)\b"),
    re.compile(r"\bwhere do i (?:live|work)\b"),
    re.compile(r"\btell me about me\b"),
]


def requests_personal_memory(question: str) -> bool:
    """Return True when the user explicitly asks for personal/profile recall."""
    normalized = _normalize_text(question)
    if not normalized:
        return False
    return any(p.search(normalized) for p in _PERSONAL_MEMORY_PATTERNS)


# ---------------------------------------------------------------------------
# Code generation detection
# ---------------------------------------------------------------------------

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


def is_code_generation_request(question: str) -> bool:
    """Return True for pure code-generation requests (not run/debug)."""
    text = _normalize_text(question)
    if not text:
        return False
    if any(p.search(text) for p in _EXECUTION_INTENT_PATTERNS):
        return False
    return any(p.search(text) for p in _CODE_REQUEST_PATTERNS)


def infer_code_language(question: str) -> str:
    """Guess the target programming language from the question."""
    text = _normalize_text(question)
    for pattern, language in _CODE_LANGUAGE_PATTERNS:
        if pattern.search(text):
            return language
    return "text"


# ---------------------------------------------------------------------------
# Lightweight prompt detection (from generate.py)
# ---------------------------------------------------------------------------

_MEMORY_SIGNALS = (
    "remember", "recall", "about me", "my name", "i'm ", "i am ",
    "my project", "my startup", "my company", "i moved", "i live",
    "i work", "actually",
)

_RETRIEVAL_SIGNALS = (
    "latest", "today", "news", "price", "weather", "search",
    "look up", "find out", "code", "function", "script", "file",
    "debug", "fix",
)


def _is_lightweight_prompt(prompt: str) -> bool:
    """Return True for short prompts that don't need memory or retrieval."""
    text = (prompt or "").strip().lower()
    if not text:
        return False
    words = text.split()
    if len(words) > 6:
        return False
    if any(sig in text for sig in _MEMORY_SIGNALS):
        return False
    if any(sig in text for sig in _RETRIEVAL_SIGNALS):
        return False
    if "?" in text:
        return False
    return True


# ---------------------------------------------------------------------------
# Preference query detection
# ---------------------------------------------------------------------------

_PREFERENCE_QUERY_HINTS = {
    "style", "tone", "format", "respond", "reply", "wording",
    "color", "green", "concise", "verbose", "bullet",
}


def is_preference_query(query: str) -> bool:
    """Return True when the query targets response/style preferences."""
    normalized = _normalize_text(query)
    if not normalized:
        return False
    words = set(normalized.split())
    return any(hint in words for hint in _PREFERENCE_QUERY_HINTS)


# ---------------------------------------------------------------------------
# Unified classifier
# ---------------------------------------------------------------------------


def classify_context_level(prompt: str) -> "ContextLevel":
    """
    Classify how much context a prompt needs.

    Returns:
        ContextLevel.NONE: Smalltalk — hardcoded response, no DB.
        ContextLevel.MINIMAL: Short non-memory prompt — last 5 messages only.
        ContextLevel.DISCLOSURE: Self-introduction — last 5 msgs, no embedding/knowledge.
        ContextLevel.FULL: Everything — messages, summary, knowledge, embedding.
    """
    if is_trivial_smalltalk(prompt):
        return ContextLevel.NONE
    if _is_lightweight_prompt(prompt):
        return ContextLevel.MINIMAL
    if is_personal_disclosure(prompt):
        return ContextLevel.DISCLOSURE
    return ContextLevel.FULL
