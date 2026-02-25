"""
Trinity Backend — Query Classifier

Provides disclosure detection, memory-recall detection, and temperature
routing. The tiny ByteTransformer classifier assists tool detection
(in tools.py) — that's its primary job now.

Context-level classification has been removed. Every query gets full
context (messages, knowledge, embedding). The LLM handles routing
naturally; we don't need a 50K-param model to decide whether "hello"
deserves a database lookup.

Public API:
  - is_personal_disclosure(question) → bool
  - requests_personal_memory(question) → bool
  - classify_temperature(prompt, tools_needed) → float
  - ContextLevel (kept for backwards-compat imports, but unused in pipeline)
"""

import logging
import re
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)

# Confidence threshold — below this, fall back to regex heuristics
_CONFIDENCE_THRESHOLD = 0.75

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_NORMALIZE_RE = re.compile(r"[^\w\s']")

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

_PERSONAL_MEMORY_PATTERNS = [
    re.compile(r"\bwhat do you know about me\b"),
    re.compile(r"\bwhat do you remember about me\b"),
    re.compile(r"\bdo you remember\b"),
    re.compile(r"\bwho am i\b"),
    re.compile(r"\bwhat(?:'s| is| was| are) my (?:name|job|role|company|goal|preference|preferences|favorite|colour|color|birthday|hobby|hobbies|interest|interests|team|project|stack|language|work)\b"),
    re.compile(r"\bwhere do i (?:live|work)\b"),
    re.compile(r"\btell me about me\b"),
    re.compile(r"\bwhat do i (?:do|like|prefer|work|study)\b"),
    re.compile(r"\bwhat did i\b"),
    re.compile(r"\bdo you know (?:my|me|who i)\b"),
]

_CODE_PATTERNS = [
    re.compile(r"\b(write|create|generate|build|make|implement)\b.*\b(code|script|function|program|file)\b"),
    re.compile(r"\b(show|give)\b.*\b(code|implementation|example)\b"),
    re.compile(r"\b(python|javascript|typescript|html|css|sql|bash|shell|rust|go|java|c\+\+|c#)\b"),
]


def _normalize(text: str) -> str:
    """Normalize text for regex matching."""
    normalized = (text or "").strip().lower().replace("\u2019", "'")
    normalized = _NORMALIZE_RE.sub(" ", normalized)
    return " ".join(normalized.split())


# ---------------------------------------------------------------------------
# ContextLevel — kept for backwards compatibility (imports still reference it)
# The pipeline no longer branches on this; every query gets FULL treatment.
# ---------------------------------------------------------------------------


class ContextLevel(Enum):
    NONE = "none"
    MINIMAL = "minimal"
    DISCLOSURE = "disclosure"
    FULL = "full"


# ---------------------------------------------------------------------------
# Classifier helper
# ---------------------------------------------------------------------------


def _classify(text: str):
    """Get classifier prediction. Returns (label, confidence)."""
    try:
        from services.tiny_classifier import classify_query
        return classify_query(text)
    except Exception as e:
        logger.debug("Classifier unavailable: %s", e)
        return ("general", 0.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_personal_disclosure(question: str) -> bool:
    """Return True for first-person self-disclosure statements.

    Used by context_loader to set is_disclosure flag, which controls
    whether identity/preference facts are included in the prompt.
    """
    try:
        label, confidence = _classify(question)
        if label == "disclosure" and confidence >= _CONFIDENCE_THRESHOLD:
            return True
    except Exception:
        pass

    normalized = _normalize(question)
    if not normalized:
        return False
    if "?" in (question or ""):
        return False
    if any(p.search(normalized) for p in _PERSONAL_DISCLOSURE_NEGATIVE_PATTERNS):
        return False
    return any(p.search(normalized) for p in _PERSONAL_DISCLOSURE_PATTERNS)


def requests_personal_memory(question: str) -> bool:
    """Return True when the user explicitly asks for personal/profile recall.

    Used by memory_eval.py to decide whether to include identity facts.
    """
    try:
        label, confidence = _classify(question)
        if label == "memory_recall" and confidence >= _CONFIDENCE_THRESHOLD:
            return True
    except Exception:
        pass

    normalized = _normalize(question)
    if not normalized:
        return False
    return any(p.search(normalized) for p in _PERSONAL_MEMORY_PATTERNS)


def classify_temperature(
    prompt: str,
    tools_needed: list = None,
    # Deprecated params kept for backwards-compat call sites:
    context_level=None,
    is_code: bool = False,
) -> float:
    """Determine sampling temperature.

    Simple routing:
      - Code → 0.1 (deterministic)
      - Tool use → 0.3 (precise)
      - Everything else → 0.7 (conversational)
    """
    from config import TEMPERATURE_CODE, TEMPERATURE_FACTUAL, TEMPERATURE_CONVERSATIONAL

    try:
        label, confidence = _classify(prompt)
    except Exception:
        label, confidence = "general", 0.0

    if is_code or label == "code":
        return TEMPERATURE_CODE

    # Regex fallback for code detection
    if confidence < _CONFIDENCE_THRESHOLD:
        normalized = _normalize(prompt)
        if any(p.search(normalized) for p in _CODE_PATTERNS):
            return TEMPERATURE_CODE

    if tools_needed:
        return TEMPERATURE_FACTUAL

    if label == "memory_recall" and confidence >= _CONFIDENCE_THRESHOLD:
        return TEMPERATURE_FACTUAL

    return TEMPERATURE_CONVERSATIONAL


# ---------------------------------------------------------------------------
# Deprecated — kept as stubs for backwards compatibility
# ---------------------------------------------------------------------------


def is_trivial_smalltalk(question: str, context_messages: Optional[List] = None) -> bool:
    """DEPRECATED: No longer drives any pipeline behavior."""
    return False


def smalltalk_fast_response(question: str) -> str:
    """DEPRECATED: All queries go through the LLM."""
    return ""


def classify_context_level(prompt: str) -> ContextLevel:
    """DEPRECATED: Every query gets FULL context now."""
    return ContextLevel.FULL


def is_code_generation_request(question: str) -> bool:
    """DEPRECATED: Only used for temperature routing now (handled internally)."""
    normalized = _normalize(question)
    if not normalized:
        return False
    try:
        label, confidence = _classify(question)
        if label == "code" and confidence >= _CONFIDENCE_THRESHOLD:
            return True
    except Exception:
        pass
    return any(p.search(normalized) for p in _CODE_PATTERNS)


def is_preference_query(query: str) -> bool:
    """DEPRECATED: No longer drives pipeline behavior."""
    try:
        label, confidence = _classify(query)
        return label == "preference" and confidence >= _CONFIDENCE_THRESHOLD
    except Exception:
        return False
