"""
LLM-based profile and graph extraction.

This module replaces regex extraction with a single LLM call per
message and returns both profile facts and graph triples.

Uses the LLMProvider abstraction (via provider_factory) so the
underlying backend (Ollama or llama-server) is transparent.
"""

import json
import logging
import re
import threading
import time
from typing import Dict, List

from config import (
    MEMORY_INGEST_STRICT_ISOLATION,
)

logger = logging.getLogger(__name__)
EXTRACTION_TIMEOUT_SECONDS = 30
EXTRACTION_MAX_TOKENS = 500
ALLOWED_CATEGORIES = {"identity", "work", "interests", "preferences", "relationships", "general"}
_BACKOFF_SECONDS_TIMEOUT = 90
_BACKOFF_SECONDS_ENDPOINT = 90
_BACKOFF_SECONDS_MODEL_MISSING = 300
_BACKOFF_UNTIL: Dict[tuple, float] = {}
_BACKOFF_LOCK = threading.Lock()

_EXTRACTION_SYSTEM_PROMPT = """You extract durable user memory from a single chat message.
Return JSON only with this exact shape:
{
  "facts": [{"fact": "...", "category": "...", "importance": 1-5}],
  "triples": [{"subject": "...", "predicate": "...", "object": "..."}]
}

Rules:
- Facts must be stable personal information about the user, not temporary troubleshooting chatter.
- Include explicit user self-statements about active projects, role, company, stack, goals, collaborators, and long-lived preferences.
- Treat ongoing project/work updates as memory-worthy if they help future assistance (even if they may evolve later).
- If user says "remember ..." treat that as memory-worthy unless clearly temporary.
- Skip generic technical questions unless they reveal a durable user trait.
- Use category from: identity, work, interests, preferences, relationships, general.
- Keep fact text concise and self-contained.
- If nothing should be saved, return {"facts":[],"triples":[]}.
- Triples should be user-centric, e.g. {"subject":"user","predicate":"works_at","object":"Acme"}.
- Prefer at least one fact for clear first-person disclosures that include project, role, company, location, collaborator, or preference details.
- Never include commentary outside JSON."""


def _normalize_category(category: str) -> str:
    value = (category or "general").strip().lower()
    return value if value in ALLOWED_CATEGORIES else "general"


def _normalize_fact(item: Dict) -> Dict:
    text = str(item.get("fact", "")).strip()
    if not text or len(text) < 5 or len(text) > 240:
        return {}
    try:
        importance = max(1, min(5, int(item.get("importance", 3))))
    except (ValueError, TypeError):
        importance = 3
    return {
        "fact": text,
        "category": _normalize_category(str(item.get("category", "general"))),
        "importance": importance,
    }


def _normalize_triple(item: Dict, source: str) -> Dict:
    subject = str(item.get("subject", "")).strip() or "user"
    predicate = str(item.get("predicate", "")).strip().lower()
    obj = str(item.get("object", "")).strip()
    if not predicate or not obj:
        return {}
    return {
        "subject": subject,
        "predicate": predicate.replace(" ", "_"),
        "object": obj,
        "source": source,
        "confidence": 0.75,
    }


def _parse_model_json(raw) -> Dict:
    """Parse model content robustly into a dict payload."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {"facts": raw, "triples": []}
    if not isinstance(raw, str):
        return {"facts": [], "triples": []}

    text = raw.strip()
    if not text:
        return {"facts": [], "triples": []}

    # Primary path: strict JSON.
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None

    # Fallback: strip fenced markdown blocks.
    if parsed is None:
        fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
        try:
            parsed = json.loads(fenced)
        except Exception:
            parsed = None

    # Fallback: extract first JSON object/array.
    if parsed is None:
        first_obj = text.find("{")
        last_obj = text.rfind("}")
        first_arr = text.find("[")
        last_arr = text.rfind("]")
        candidate = None
        if first_obj >= 0 and last_obj > first_obj:
            candidate = text[first_obj:last_obj + 1]
        elif first_arr >= 0 and last_arr > first_arr:
            candidate = text[first_arr:last_arr + 1]
        if candidate:
            parsed = json.loads(candidate)

    if isinstance(parsed, list):
        return {"facts": parsed, "triples": []}
    if isinstance(parsed, dict):
        return parsed
    return {"facts": [], "triples": []}


def _triples_to_facts(triples: List[Dict]) -> List[Dict]:
    """Synthesize minimal fact rows from triples when facts are missing."""
    if not triples:
        return []

    synthesized: List[Dict] = []
    for triple in triples[:10]:
        subject = str(triple.get("subject", "user") or "user").strip()
        predicate = str(triple.get("predicate", "") or "").replace("_", " ").strip()
        obj = str(triple.get("object", "") or "").strip()
        if not predicate or not obj:
            continue

        if subject.lower() == "user":
            text = f"User {predicate} {obj}"
        else:
            text = f"{subject} {predicate} {obj}"

        category = "general"
        pred_lower = predicate.lower()
        if any(token in pred_lower for token in ("work", "project", "company", "role", "build")):
            category = "work"
        elif any(token in pred_lower for token in ("prefer", "style", "like")):
            category = "preferences"
        elif any(token in pred_lower for token in ("friend", "partner", "cofounder", "team", "relationship")):
            category = "relationships"
        elif any(token in pred_lower for token in ("live", "from", "name", "age")):
            category = "identity"

        synthesized.append(
            {
                "fact": text,
                "category": category,
                "importance": 3,
            }
        )
    return synthesized


def _candidate_providers() -> list:
    """
    Ordered extraction providers.
    In strict-isolation mode, extraction only uses ingestion capacity.
    Returns a list of LLMProvider instances.
    """
    from .provider_factory import get_ingest_provider, get_provider

    providers = [get_ingest_provider()]
    if not MEMORY_INGEST_STRICT_ISOLATION:
        chat = get_provider()
        if (chat.host, chat.model) != (providers[0].host, providers[0].model):
            providers.append(chat)

    # Filter out providers currently in backoff
    result = []
    now = time.time()
    for p in providers:
        key = (p.host or "", p.model or "")
        if not key[0] or not key[1]:
            continue
        with _BACKOFF_LOCK:
            blocked_until = float(_BACKOFF_UNTIL.get(key, 0.0) or 0.0)
        if blocked_until > now:
            continue
        result.append(p)
    return result


def _set_target_backoff(host: str, model: str, seconds: int, reason: str):
    key = (host or "", model or "")
    if not key[0] or not key[1]:
        return
    until = time.time() + max(1, int(seconds))
    with _BACKOFF_LOCK:
        previous = float(_BACKOFF_UNTIL.get(key, 0.0) or 0.0)
        if until > previous:
            _BACKOFF_UNTIL[key] = until
    logger.warning(
        "⏳ Extraction target in backoff for %ss (%s @ %s): %s",
        int(seconds),
        model,
        host,
        reason,
    )


def _call_model_once(message: str, source: str, provider) -> Dict:
    messages = [
        {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"source={source}\nmessage={message}",
        },
    ]
    raw = provider.chat(
        messages,
        max_tokens=EXTRACTION_MAX_TOKENS,
        temperature=0.1,
        timeout=EXTRACTION_TIMEOUT_SECONDS,
    )
    if not raw:
        return {"facts": [], "triples": []}

    parsed = _parse_model_json(raw)

    seen_facts = set()
    facts: List[Dict] = []
    for item in parsed.get("facts", [])[:25]:
        if not isinstance(item, dict):
            continue
        fact = _normalize_fact(item)
        if not fact:
            continue
        key = fact["fact"].lower()
        if key in seen_facts:
            continue
        seen_facts.add(key)
        facts.append(fact)

    seen_triples = set()
    triples: List[Dict] = []
    for item in parsed.get("triples", [])[:25]:
        if not isinstance(item, dict):
            continue
        triple = _normalize_triple(item, source=source)
        if not triple:
            continue
        key = (
            triple["subject"].lower(),
            triple["predicate"].lower(),
            triple["object"].lower(),
        )
        if key in seen_triples:
            continue
        seen_triples.add(key)
        triples.append(triple)

    # Some models emit only triples even when facts were requested.
    if not facts and triples:
        for item in _triples_to_facts(triples):
            fact = _normalize_fact(item)
            if not fact:
                continue
            key = fact["fact"].lower()
            if key in seen_facts:
                continue
            seen_facts.add(key)
            facts.append(fact)

    return {"facts": facts, "triples": triples}


def _call_extraction_model(message: str, source: str) -> Dict:
    """
    Run extraction with optional fallback.

    In strict isolation mode this uses ingestion endpoint only.
    """
    providers = _candidate_providers()
    if not providers:
        raise RuntimeError("Extraction targets are temporarily in backoff")

    last_error = None
    for provider in providers:
        host, model = provider.host, provider.model
        try:
            return _call_model_once(message, source, provider)
        except Exception as e:
            last_error = e
            err = str(e).lower()
            model_missing = "not found" in err or ("pull" in err and "model" in err)
            if model_missing:
                _set_target_backoff(host, model, _BACKOFF_SECONDS_MODEL_MISSING, "model unavailable")
                logger.warning("⚠️ Extraction model unavailable (%s @ %s): %s", model, host, e)
                continue
            endpoint_unavailable = "connection refused" in err or "max retries exceeded" in err
            if endpoint_unavailable:
                _set_target_backoff(host, model, _BACKOFF_SECONDS_ENDPOINT, "endpoint unavailable")
                logger.warning("⚠️ Extraction endpoint unavailable (%s @ %s): %s", model, host, e)
                continue
            if "timed out" in err or "timeout" in err:
                _set_target_backoff(host, model, _BACKOFF_SECONDS_TIMEOUT, "timeout")
            # Treat malformed JSON/other model errors as retryable on fallback targets.
            logger.warning("⚠️ Extraction attempt failed (%s @ %s): %s", model, host, e)
            continue
    if last_error:
        raise last_error
    return {"facts": [], "triples": []}


def extract_memory_candidates(message: str, source: str = "user") -> Dict[str, List[Dict]]:
    """Extract profile facts and graph triples from one message."""
    if not message or len(message.strip()) < 5:
        return {"facts": [], "triples": []}

    try:
        return _call_extraction_model(message.strip(), source=source)
    except Exception as e:
        if "temporarily in backoff" in str(e).lower():
            logger.debug("Extraction backoff active (%s): %s", source, e)
        else:
            logger.warning("⚠️ LLM extraction failed (%s): %s", source, e)
        return {"facts": [], "triples": []}


def extract_profile_facts(message: str, source: str = "user") -> List[Dict]:
    """Backwards-compatible fact-only view of extraction output."""
    return extract_memory_candidates(message, source=source).get("facts", [])


def auto_extract_and_save(message: str, principal_id: str, source: str = "user") -> int:
    """
    Extract profile facts from a message and save them to user memory.

    Keeps existing public signature for callers.
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
                logger.info("📝 Auto-extracted (%s): %s", source, candidate["fact"])
            elif success and "Updated" in result:
                saved += 1
                logger.info("📝 Auto-updated (%s): %s", source, result)
    except Exception as e:
        logger.warning(f"⚠️ Auto-extraction error: {e}")

    return saved
