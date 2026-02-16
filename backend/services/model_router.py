"""
Model Router
============
Lightweight intent routing between conversational and coder models.
"""

import re
from typing import Optional

_CODE_HINTS = [
    re.compile(r"\bpython\b|\bjavascript\b|\btypescript\b|\brust\b|\bgo\b", re.I),
    re.compile(r"\bcode\b|\bfunction\b|\bclass\b|\bapi\b|\bsql\b|\bregex\b", re.I),
    re.compile(r"\bdebug\b|\berror\b|\btraceback\b|\bstack trace\b", re.I),
    re.compile(r"```"),
]

_CONVERSATION_HINTS = [
    re.compile(r"\bhow are you\b|\bwhat do you think\b|\bhelp me decide\b", re.I),
    re.compile(r"\bexplain\b|\bteach me\b|\bwhat is\b", re.I),
]


def is_coding_intent(prompt: str) -> bool:
    """Heuristic coding-intent detector."""
    text = (prompt or "").strip()
    if not text:
        return False

    code_hits = sum(1 for p in _CODE_HINTS if p.search(text))
    convo_hits = sum(1 for p in _CONVERSATION_HINTS if p.search(text))
    return code_hits > max(0, convo_hits)


def choose_model_for_prompt(prompt: str, use_case: Optional[str] = None) -> str:
    """
    Select a model name for the request.

    Args:
        prompt: User query text.
        use_case: Optional explicit hint ('coding' or 'conversation').
    """
    from config import CODER_MODEL_NAME, CONVERSATION_MODEL_NAME

    explicit = (use_case or "").strip().lower()
    if explicit == "coding":
        return CODER_MODEL_NAME
    if explicit == "conversation":
        return CONVERSATION_MODEL_NAME
    return CODER_MODEL_NAME if is_coding_intent(prompt) else CONVERSATION_MODEL_NAME
