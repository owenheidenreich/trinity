# Rationale: In-Memory Caching vs Redis

## Status
Accepted

## Date
February 2026

## Context
We need caching infrastructure to reduce redundant LLM calls and embedding computations. The primary options are:

| Option | Pros | Cons |
|--------|------|------|
| **In-Memory (LRU)** | Zero latency, no dependencies | Single-node only, lost on restart |
| **Redis** | Shared across replicas, persistent | Additional infrastructure, network latency |
| **Memcached** | Fast, simple | No persistence, less features than Redis |

## Decision
Use in-memory LRU caches with TTL for the current single-node Akash deployment, designed with clean interfaces to enable future Redis migration.

### Architecture
```
┌─────────────────────────────────────────────────────────┐
│                 Trinity Backend                          │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────────────────┐ │
│  │  EmbeddingCache │    │   SemanticResponseCache     │ │
│  │  (LRU + TTL)    │    │   (Similarity Threshold)    │ │
│  │  max_size=1000  │    │   threshold=0.95            │ │
│  │  ttl=3600s      │    │   max_size=500              │ │
│  └─────────────────┘    └─────────────────────────────┘ │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              TokenTracker                            │ │
│  │  Per-user usage tracking + cost estimation           │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Rationale

1. **Simplicity**: No additional infrastructure to deploy/manage
2. **Performance**: Zero network latency for cache operations
3. **Sufficient for Scale**: Single Akash deployment handles current load
4. **Clean Abstraction**: Cache interface designed for easy Redis swap
5. **Cost**: No additional Akash resources needed

## Consequences

### Positive
- Zero operational overhead
- Sub-microsecond cache access
- No external dependencies
- Easy to test and debug
- Thread-safe implementation with `threading.RLock`

### Negative
- Cache lost on server restart
- Cannot share cache across multiple replicas
- Memory pressure on single node
- No persistence for token tracking

## Implementation

### EmbeddingCache
```python
class EmbeddingCache:
    """LRU cache for text embeddings with TTL."""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self._cache: OrderedDict[str, EmbeddingCacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._max_size = max_size
        self._ttl = ttl_seconds
    
    def get(self, text: str) -> Optional[np.ndarray]:
        """Return cached embedding or None if miss/expired."""
        
    def put(self, text: str, embedding: np.ndarray) -> None:
        """Cache embedding with LRU eviction."""
```

### SemanticResponseCache
```python
class SemanticResponseCache:
    """Cache responses for semantically similar queries."""
    
    def __init__(self, similarity_threshold: float = 0.95):
        # Returns cached response if query is >95% similar to cached query
    
    def get(self, query: str, embedding: np.ndarray) -> Optional[Tuple[str, float]]:
        """Return (response, similarity) if similar query cached."""
```

### Integration Points
```python
# Automatic integration in embeddings.py
def embed_text(text: str, use_cache: bool = True) -> Optional[np.ndarray]:
    if use_cache:
        cached = cache.get(text)
        if cached is not None:
            return cached
    
    embedding = compute_embedding(text)
    cache.put(text, embedding)
    return embedding
```

## Future Migration Path

When scaling to multiple replicas, migrate to Redis:

```python
# Future: services/caching_redis.py
class RedisEmbeddingCache:
    """Drop-in replacement using Redis backend."""
    
    def __init__(self, redis_url: str, max_size: int = 1000, ttl_seconds: int = 3600):
        self._redis = redis.from_url(redis_url)
        self._ttl = ttl_seconds
    
    def get(self, text: str) -> Optional[np.ndarray]:
        key = self._compute_key(text)
        data = self._redis.get(key)
        return np.frombuffer(data) if data else None
    
    def put(self, text: str, embedding: np.ndarray) -> None:
        key = self._compute_key(text)
        self._redis.setex(key, self._ttl, embedding.tobytes())
```

## Alternatives Considered

1. **Redis from Start**
   - Pros: Ready for horizontal scaling
   - Cons: Additional infrastructure, overkill for single node

2. **No Caching**
   - Pros: Simpler code
   - Cons: ~60-80% more embedding compute, higher latency

3. **Filesystem Cache**
   - Pros: Persistent across restarts
   - Cons: I/O latency, disk space management

## Metrics

| Metric | Expected Value |
|--------|----------------|
| Embedding cache hit rate | 60-80% |
| Semantic cache hit rate | 10-20% |
| Memory usage | ~50-100MB |
| Cache lookup latency | <1ms |

## References
- [services/caching.py](../../backend/services/caching.py) - Cache implementations
- [tests/unit/test_caching.py](../../backend/tests/unit/test_caching.py) - Cache tests
