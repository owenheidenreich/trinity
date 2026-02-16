"""
Trinity Profile Extractor — Automatic Fact Extraction from Conversations

Runs lightweight heuristic extraction on user messages to detect
profile-worthy information ("My name is X", "I'm a developer", etc.)
without burning an LLM tool call.

Also extracts facts from assistant messages when the assistant echoes
back confirmed user information ("Since you're a developer in NYC...").

The extraction result is a list of candidate facts that can be fed
into tool_save_memory for dedup + storage. This supplements (but does
not replace) the LLM's own ability to call save_memory explicitly.
"""

import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# EXTRACTION PATTERNS
# ============================================================================

# Each pattern is (compiled_regex, category, importance, fact_template)
# The template uses \1, \2 etc. for regex groups

_PATTERNS = [
    # Identity
    (re.compile(r"\bmy name is (\w[\w\s]{0,30})", re.I), "identity", 5,
     "User's name is {0}"),
    (re.compile(r"\bi(?:'m| am) (\w[\w\s]{0,30})(?:\.|,|$)", re.I), "identity", 4,
     "User is {0}"),
    (re.compile(r"\bi live in ([\w\s,]{2,40})", re.I), "identity", 4,
     "User lives in {0}"),
    (re.compile(r"\bi(?:'m| am) from ([\w\s,]{2,40})", re.I), "identity", 3,
     "User is from {0}"),
    (re.compile(r"\bi speak ([\w\s,]+?)(?:\.|,|$)", re.I), "identity", 3,
     "User speaks {0}"),

    # Work
    (re.compile(r"\bi work (?:at|for) ([\w\s&.]{2,40})", re.I), "work", 4,
     "User works at {0}"),
    (re.compile(r"\bmy (?:job|role|title) is ([\w\s]{2,40})", re.I), "work", 4,
     "User's role is {0}"),
    (re.compile(r"\bi(?:'m| am) (?:a |an )([\w\s]{2,40})(?:developer|engineer|designer|manager|architect|founder|scientist|researcher|analyst|consultant)", re.I), "work", 4,
     "User is a {0}"),
    (re.compile(r"\bi(?:'m| am) (?:building|working on|developing) ([\w\s]{2,60})", re.I), "work", 4,
     "User is building {0}"),
    (re.compile(r"\bmy (?:project|app|product|startup|company) (?:is called |is |called )([\w\s]{2,40})", re.I), "work", 4,
     "User's project is {0}"),
    (re.compile(r"\bour tech stack (?:is|includes) ([\w\s,/+]{2,80})", re.I), "work", 3,
     "User's tech stack includes {0}"),

    # Interests
    (re.compile(r"\bi(?:'m| am) (?:interested in|passionate about|studying|learning) ([\w\s]{2,60})", re.I), "interests", 3,
     "User is interested in {0}"),
    (re.compile(r"\bi (?:like|love|enjoy) ([\w\s]{2,60})(?:\.|,|$)", re.I), "interests", 3,
     "User enjoys {0}"),
    (re.compile(r"\bmy (?:goal|aim) is (?:to )?([\w\s]{2,80})", re.I), "interests", 4,
     "User's goal is to {0}"),

    # Preferences
    (re.compile(r"\bi prefer ([\w\s]{2,60})(?: over| to| instead)", re.I), "preferences", 3,
     "User prefers {0}"),
    (re.compile(r"\bplease (?:always |)(respond|answer|write|code|explain) (?:in |with |using )?([\w\s]{2,40})", re.I), "preferences", 4,
     "User prefers responses in {0} {1}"),
    (re.compile(r"\bi (?:don't|do not) like ([\w\s]{2,40})(?:\.|,|$)", re.I), "preferences", 3,
     "User doesn't like {0}"),

    # Relationships
    (re.compile(r"\bmy (?:friend|colleague|partner|wife|husband|boss|cofounder|co-founder) (\w[\w\s]{0,30})", re.I), "relationships", 3,
     "User's relationship: {0}"),
]

# Phrases that indicate the user is NOT making a personal statement
# (e.g., "I am not sure", "I'm happy to help" in a code context)
_NEGATIVE_PATTERNS = [
    re.compile(r"\bi(?:'m| am) (?:not sure|sorry|confused|wondering|asking|trying|looking|having trouble)", re.I),
    re.compile(r"\bi(?:'m| am) (?:happy to|glad to|here to)", re.I),
    re.compile(r"\bi(?:'m| am) (?:getting|seeing|receiving) (?:an? )?error", re.I),
    re.compile(r"\bcan you|could you|would you|please help", re.I),
]

# Patterns for extracting user facts from assistant messages.
# These catch when the assistant echoes back confirmed user info.
_ASSISTANT_PATTERNS = [
    (re.compile(r"\byou(?:'re| are) (?:a |an )?([\w\s]{2,40}?)(?:,| who| based| living| from| working| and)", re.I), "identity", 3,
     "User is {0}"),
    (re.compile(r"\byou live in ([\w\s,]{2,40})", re.I), "identity", 3,
     "User lives in {0}"),
    (re.compile(r"\byou work (?:at|for|with) ([\w\s&.]{2,40})", re.I), "work", 3,
     "User works at {0}"),
    (re.compile(r"\byou(?:'re| are) (?:building|developing|working on) ([\w\s]{2,60})", re.I), "work", 3,
     "User is building {0}"),
    (re.compile(r"\byour (?:project|app|product|startup|company),? ([\w\s]{2,40})", re.I), "work", 3,
     "User's project is {0}"),
    (re.compile(r"\byou(?:'re| are) (?:interested in|learning|studying) ([\w\s]{2,60})", re.I), "interests", 3,
     "User is interested in {0}"),
    (re.compile(r"\byou prefer ([\w\s]{2,60})", re.I), "preferences", 3,
     "User prefers {0}"),
    (re.compile(r"\byour name is (\w[\w\s]{0,30})", re.I), "identity", 5,
     "User's name is {0}"),
]

# Negative patterns for assistant messages — skip generic/templated text
_ASSISTANT_NEGATIVE_PATTERNS = [
    re.compile(r"\byou(?:'re| are) (?:welcome|right|correct|asking|looking|trying)", re.I),
    re.compile(r"\byou(?:'re| are) (?:experiencing|encountering|getting|seeing|having)", re.I),
    re.compile(r"\bif you(?:'re| are)", re.I),
    re.compile(r"\bwhen you(?:'re| are)", re.I),
    re.compile(r"\bonce you(?:'re| are)", re.I),
]


def extract_profile_facts(message: str, source: str = "user") -> List[Dict]:
    """
    Extract candidate profile facts from a message.

    Args:
        message: The message text to extract facts from
        source: "user" or "assistant" — controls which patterns are applied

    Returns a list of dicts:
        [{"fact": str, "category": str, "importance": int}, ...]

    These can be fed directly into tool_save_memory's params format.
    Returns empty list if no extractable facts found.
    """
    if not message or len(message) < 5:
        return []

    message_stripped = message.strip()

    if source == "user":
        # Skip messages that are clearly questions or technical help requests
        if message_stripped.endswith("?") and len(message_stripped) < 100:
            return []

        # Check negative patterns
        for neg in _NEGATIVE_PATTERNS:
            if neg.search(message):
                return []

        patterns = _PATTERNS
    else:
        # Assistant source — use assistant-specific patterns
        # Check assistant negative patterns
        for neg in _ASSISTANT_NEGATIVE_PATTERNS:
            if neg.search(message):
                return []

        patterns = _ASSISTANT_PATTERNS

    candidates = []
    seen_texts = set()  # prevent duplicates within one extraction

    for pattern, category, importance, template in patterns:
        match = pattern.search(message)
        if match:
            groups = [g.strip().rstrip(".,!") for g in match.groups() if g]
            if not groups:
                continue

            # Build fact text from template
            try:
                fact_text = template.format(*groups)
            except (IndexError, KeyError):
                fact_text = groups[0]

            # Clean up
            fact_text = fact_text.strip()
            if len(fact_text) < 5 or len(fact_text) > 200:
                continue

            # Dedup within this extraction
            text_lower = fact_text.lower()
            if text_lower in seen_texts:
                continue
            seen_texts.add(text_lower)

            candidates.append({
                "fact": fact_text,
                "category": category,
                "importance": str(importance),
            })

    return candidates


def auto_extract_and_save(message: str, principal_id: str, source: str = "user") -> int:
    """
    Extract profile facts from a message and save them to user memory.

    Uses tool_save_memory which handles dedup/merge, so it's safe to
    call on every message — redundant facts are silently skipped.

    Args:
        message: The message text to extract facts from
        principal_id: User's principal ID
        source: "user" or "assistant" — controls extraction patterns

    Returns:
        Number of new facts saved (0 if nothing extracted or all duped).
    """
    candidates = extract_profile_facts(message, source=source)
    if not candidates:
        return 0

    saved = 0
    try:
        from .memory_tools import tool_save_memory
        for candidate in candidates:
            success, result = tool_save_memory(candidate, principal_id)
            if success and "Saved:" in result:
                saved += 1
                logger.info(f"📝 Auto-extracted ({source}): {candidate['fact']}")
            elif success and "Updated" in result:
                saved += 1
                logger.info(f"📝 Auto-updated ({source}): {result}")
    except Exception as e:
        logger.warning(f"⚠️ Auto-extraction error: {e}")

    return saved
