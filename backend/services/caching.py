"""
Trinity Backend - Caching Service
Phase 5: Cost Optimization and Caching

Provides:
- LRU embedding cache (avoids recomputing identical embeddings)
- Semantic response cache (returns cached response for similar queries)
- Token usage tracking for cost estimation
"""

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# EMBEDDING CACHE
# =============================================================================


@dataclass
class EmbeddingCacheEntry:
    """Cache entry for an embedding."""

    embedding: np.ndarray
    created_at: float
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)


class EmbeddingCache:
    """
    LRU cache for text embeddings.

    Avoids recomputing embeddings for identical text inputs.
    Thread-safe for concurrent access.

    Args:
        max_size: Maximum number of embeddings to cache (default 1000)
        ttl_seconds: Time-to-live for cache entries (default 1 hour)
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self._cache: OrderedDict[str, EmbeddingCacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._max_size = max_size
        self._ttl = ttl_seconds

        # Stats for monitoring
        self._hits = 0
        self._misses = 0

    def _compute_key(self, text: str) -> str:
        """Compute cache key from text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]

    def get(self, text: str) -> Optional[np.ndarray]:
        """
        Get cached embedding for text.

        Args:
            text: Text to look up

        Returns:
            Cached embedding array or None if not found/expired
        """
        key = self._compute_key(text)

        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]
            now = time.time()

            # Check TTL
            if now - entry.created_at > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None

            # Update access tracking (LRU)
            entry.access_count += 1
            entry.last_accessed = now
            self._cache.move_to_end(key)

            self._hits += 1
            return entry.embedding

    def put(self, text: str, embedding: np.ndarray) -> None:
        """
        Cache an embedding for text.

        Args:
            text: Original text
            embedding: Computed embedding array
        """
        key = self._compute_key(text)

        with self._lock:
            # Evict oldest if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[key] = EmbeddingCacheEntry(embedding=embedding, created_at=time.time())

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 4),
                "ttl_seconds": self._ttl,
            }

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def invalidate(self, text: str) -> bool:
        """Invalidate a specific cache entry."""
        key = self._compute_key(text)
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False


# Global embedding cache instance
_embedding_cache: Optional[EmbeddingCache] = None


def get_embedding_cache(max_size: int = 1000, ttl_seconds: int = 3600) -> EmbeddingCache:
    """Get or create the global embedding cache."""
    global _embedding_cache
    if _embedding_cache is None:
        _embedding_cache = EmbeddingCache(max_size=max_size, ttl_seconds=ttl_seconds)
        logger.info(f"📦 Embedding cache initialized (max_size={max_size}, ttl={ttl_seconds}s)")
    return _embedding_cache


def reset_embedding_cache() -> None:
    """Reset the global embedding cache (for testing)."""
    global _embedding_cache
    _embedding_cache = None


# =============================================================================
# SEMANTIC RESPONSE CACHE
# =============================================================================


@dataclass
class SemanticCacheEntry:
    """Cache entry for a semantic response."""

    query: str
    query_embedding: np.ndarray
    response: str
    model: str
    created_at: float
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class SemanticResponseCache:
    """
    Cache that returns stored responses for semantically similar queries.

    Uses cosine similarity to find similar past queries and return
    cached responses, avoiding redundant LLM calls.

    Args:
        max_size: Maximum cached responses (default 500)
        similarity_threshold: Minimum similarity to return cached response (default 0.95)
        ttl_seconds: Time-to-live for entries (default 1 hour)
    """

    def __init__(
        self, max_size: int = 500, similarity_threshold: float = 0.95, ttl_seconds: int = 3600
    ):
        self._cache: List[SemanticCacheEntry] = []
        self._lock = threading.RLock()
        self._max_size = max_size
        self._threshold = similarity_threshold
        self._ttl = ttl_seconds

        # Stats
        self._hits = 0
        self._misses = 0

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _cleanup_expired(self) -> None:
        """Remove expired entries (call with lock held)."""
        now = time.time()
        self._cache = [entry for entry in self._cache if now - entry.created_at <= self._ttl]

    def get(
        self, query: str, query_embedding: np.ndarray, model: Optional[str] = None
    ) -> Optional[Tuple[str, float]]:
        """
        Find a cached response for a similar query.

        Args:
            query: The query text (for logging)
            query_embedding: Embedding of the query
            model: Optional model filter (only return if same model)

        Returns:
            Tuple of (cached_response, similarity_score) or None
        """
        with self._lock:
            self._cleanup_expired()

            best_match: Optional[SemanticCacheEntry] = None
            best_similarity = 0.0

            for entry in self._cache:
                # Filter by model if specified
                if model and entry.model != model:
                    continue

                similarity = self._cosine_similarity(query_embedding, entry.query_embedding)

                if similarity >= self._threshold and similarity > best_similarity:
                    best_similarity = similarity
                    best_match = entry

            if best_match:
                best_match.access_count += 1
                self._hits += 1
                logger.debug(f"🎯 Semantic cache hit (similarity={best_similarity:.4f})")
                return (best_match.response, best_similarity)

            self._misses += 1
            return None

    def put(
        self,
        query: str,
        query_embedding: np.ndarray,
        response: str,
        model: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Cache a response for a query.

        Args:
            query: Original query text
            query_embedding: Embedding of the query
            response: Generated response to cache
            model: Model that generated the response
            metadata: Optional metadata (tokens, duration, etc.)
        """
        with self._lock:
            self._cleanup_expired()

            # Evict oldest if at capacity
            while len(self._cache) >= self._max_size:
                # Remove least recently accessed
                self._cache.sort(key=lambda e: e.access_count)
                self._cache.pop(0)

            self._cache.append(
                SemanticCacheEntry(
                    query=query,
                    query_embedding=query_embedding,
                    response=response,
                    model=model,
                    created_at=time.time(),
                    metadata=metadata or {},
                )
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 4),
                "threshold": self._threshold,
                "ttl_seconds": self._ttl,
            }

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


# Global semantic cache instance
_semantic_cache: Optional[SemanticResponseCache] = None


def get_semantic_cache(
    max_size: int = 500, similarity_threshold: float = 0.95, ttl_seconds: int = 3600
) -> SemanticResponseCache:
    """Get or create the global semantic response cache."""
    global _semantic_cache
    if _semantic_cache is None:
        _semantic_cache = SemanticResponseCache(
            max_size=max_size, similarity_threshold=similarity_threshold, ttl_seconds=ttl_seconds
        )
        logger.info(
            f"🧠 Semantic cache initialized "
            f"(max_size={max_size}, threshold={similarity_threshold}, ttl={ttl_seconds}s)"
        )
    return _semantic_cache


def reset_semantic_cache() -> None:
    """Reset the global semantic cache (for testing)."""
    global _semantic_cache
    _semantic_cache = None


# =============================================================================
# TOKEN USAGE TRACKING
# =============================================================================


@dataclass
class TokenUsage:
    """Token usage for a single request."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    timestamp: float = field(default_factory=time.time)

    @property
    def estimated_cost_usd(self) -> float:
        """
        Estimate cost in USD based on typical Ollama/local pricing.
        For local inference, this represents compute cost equivalent.

        Rates (per 1M tokens, approximate):
        - Small models (7-8B): ~$0.10 prompt, ~$0.20 completion
        - Large models (70B+): ~$1.00 prompt, ~$2.00 completion
        """
        # Detect model size from name
        model_lower = self.model.lower()
        if any(x in model_lower for x in ["70b", "72b", "65b"]):
            prompt_rate = 1.0 / 1_000_000
            completion_rate = 2.0 / 1_000_000
        else:
            # Default to small model rates
            prompt_rate = 0.10 / 1_000_000
            completion_rate = 0.20 / 1_000_000

        return self.prompt_tokens * prompt_rate + self.completion_tokens * completion_rate


class TokenTracker:
    """
    Track token usage across requests for cost estimation.

    Thread-safe accumulator for token usage with per-user breakdown.
    """

    def __init__(self, max_history: int = 10000):
        self._lock = threading.RLock()
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._request_count = 0
        self._history: List[TokenUsage] = []
        self._max_history = max_history
        self._per_user: Dict[str, Dict[str, int]] = {}  # user_id -> {prompt, completion}
        self._start_time = time.time()

    def record(
        self, prompt_tokens: int, completion_tokens: int, model: str, user_id: Optional[str] = None
    ) -> TokenUsage:
        """
        Record token usage for a request.

        Args:
            prompt_tokens: Tokens in the prompt
            completion_tokens: Tokens generated
            model: Model name
            user_id: Optional user identifier for per-user tracking

        Returns:
            TokenUsage record
        """
        usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            model=model,
        )

        with self._lock:
            self._total_prompt_tokens += prompt_tokens
            self._total_completion_tokens += completion_tokens
            self._request_count += 1

            # Add to history (with size limit)
            self._history.append(usage)
            while len(self._history) > self._max_history:
                self._history.pop(0)

            # Per-user tracking
            if user_id:
                if user_id not in self._per_user:
                    self._per_user[user_id] = {"prompt": 0, "completion": 0}
                self._per_user[user_id]["prompt"] += prompt_tokens
                self._per_user[user_id]["completion"] += completion_tokens

        return usage

    def get_totals(self) -> Dict[str, Any]:
        """Get total token usage statistics."""
        with self._lock:
            uptime = time.time() - self._start_time
            total_tokens = self._total_prompt_tokens + self._total_completion_tokens

            # Calculate estimated cost
            estimated_cost = sum(u.estimated_cost_usd for u in self._history)

            return {
                "prompt_tokens": self._total_prompt_tokens,
                "completion_tokens": self._total_completion_tokens,
                "total_tokens": total_tokens,
                "request_count": self._request_count,
                "avg_tokens_per_request": total_tokens / max(1, self._request_count),
                "estimated_cost_usd": round(estimated_cost, 6),
                "uptime_seconds": round(uptime, 2),
                "tokens_per_hour": round(total_tokens / max(1, uptime / 3600), 2),
            }

    def get_user_usage(self, user_id: str) -> Optional[Dict[str, int]]:
        """Get token usage for a specific user."""
        with self._lock:
            return self._per_user.get(user_id)

    def get_top_users(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get users with highest token usage."""
        with self._lock:
            users = [
                (uid, data["prompt"] + data["completion"]) for uid, data in self._per_user.items()
            ]
            users.sort(key=lambda x: x[1], reverse=True)
            return users[:limit]

    def reset(self) -> None:
        """Reset all tracking (for testing)."""
        with self._lock:
            self._total_prompt_tokens = 0
            self._total_completion_tokens = 0
            self._request_count = 0
            self._history.clear()
            self._per_user.clear()
            self._start_time = time.time()


# Global token tracker
_token_tracker: Optional[TokenTracker] = None


def get_token_tracker() -> TokenTracker:
    """Get or create the global token tracker."""
    global _token_tracker
    if _token_tracker is None:
        _token_tracker = TokenTracker()
        logger.info("📊 Token tracker initialized")
    return _token_tracker


def reset_token_tracker() -> None:
    """Reset the global token tracker (for testing)."""
    global _token_tracker
    _token_tracker = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def get_all_cache_stats() -> Dict[str, Any]:
    """Get statistics for all caches."""
    return {
        "embedding_cache": get_embedding_cache().get_stats(),
        "semantic_cache": get_semantic_cache().get_stats(),
        "token_usage": get_token_tracker().get_totals(),
    }


def clear_all_caches() -> None:
    """Clear all caches (for maintenance)."""
    get_embedding_cache().clear()
    get_semantic_cache().clear()
    logger.info("🗑️ All caches cleared")


# =============================================================================
# ESTIMATE TOKEN COUNT (Approximate)
# =============================================================================


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.

    Uses approximate 4 characters per token heuristic.
    For more accurate counting, use tiktoken library.

    Args:
        text: Text to estimate tokens for

    Returns:
        Estimated token count
    """
    if not text:
        return 0
    # Rough estimate: ~4 characters per token for English text
    return max(1, len(text) // 4)


def estimate_tokens_accurate(text: str, model: str = "llama") -> int:
    """
    More accurate token estimation using word-based heuristics.

    Llama/Ollama models use similar tokenization to GPT models.
    """
    if not text:
        return 0

    # Count words (tokens are roughly 0.75 tokens per word on average)
    words = len(text.split())

    # Add tokens for special characters and punctuation
    special_chars = sum(1 for c in text if c in ".,!?;:()[]{}\"'-/")

    # Rough formula: words * 1.3 + special characters * 0.5
    return max(1, int(words * 1.3 + special_chars * 0.5))
