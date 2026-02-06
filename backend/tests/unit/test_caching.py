"""
Phase 5 Tests: Cost Optimization and Caching

Tests for:
- Embedding cache (LRU with TTL)
- Semantic response cache (cosine similarity)
- Token usage tracking
- Per-user token quotas
"""

import pytest
import time
import numpy as np
from unittest.mock import patch, MagicMock


# =============================================================================
# EMBEDDING CACHE TESTS
# =============================================================================

class TestEmbeddingCache:
    """Test the embedding cache."""
    
    def test_cache_initialization(self):
        """Cache should initialize with correct parameters."""
        from services.caching import EmbeddingCache
        
        cache = EmbeddingCache(max_size=100, ttl_seconds=60)
        
        stats = cache.get_stats()
        assert stats['max_size'] == 100
        assert stats['ttl_seconds'] == 60
        assert stats['size'] == 0
    
    def test_cache_put_and_get(self):
        """Should store and retrieve embeddings."""
        from services.caching import EmbeddingCache
        
        cache = EmbeddingCache()
        embedding = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        
        cache.put('test text', embedding)
        result = cache.get('test text')
        
        assert result is not None
        np.testing.assert_array_equal(result, embedding)
    
    def test_cache_miss(self):
        """Should return None for cache misses."""
        from services.caching import EmbeddingCache
        
        cache = EmbeddingCache()
        result = cache.get('nonexistent text')
        
        assert result is None
    
    def test_cache_stats_tracking(self):
        """Should track hits and misses."""
        from services.caching import EmbeddingCache
        
        cache = EmbeddingCache()
        embedding = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        
        # Miss
        cache.get('test')
        
        # Put and hit
        cache.put('test', embedding)
        cache.get('test')
        cache.get('test')
        
        stats = cache.get_stats()
        assert stats['hits'] == 2
        assert stats['misses'] == 1
        assert stats['hit_rate'] == pytest.approx(0.6667, rel=0.01)
    
    def test_cache_ttl_expiration(self):
        """Entries should expire after TTL."""
        from services.caching import EmbeddingCache
        
        cache = EmbeddingCache(ttl_seconds=0)  # Immediate expiration
        embedding = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        
        cache.put('test', embedding)
        time.sleep(0.01)  # Small delay to ensure expiration
        
        result = cache.get('test')
        assert result is None
    
    def test_cache_lru_eviction(self):
        """Should evict oldest entries when full."""
        from services.caching import EmbeddingCache
        
        cache = EmbeddingCache(max_size=2, ttl_seconds=3600)
        
        cache.put('first', np.array([1.0]))
        cache.put('second', np.array([2.0]))
        cache.put('third', np.array([3.0]))  # Should evict 'first'
        
        assert cache.get('first') is None
        assert cache.get('second') is not None
        assert cache.get('third') is not None
    
    def test_cache_clear(self):
        """Clear should reset cache state."""
        from services.caching import EmbeddingCache
        
        cache = EmbeddingCache()
        cache.put('test', np.array([1.0]))
        cache.get('test')
        
        cache.clear()
        
        stats = cache.get_stats()
        assert stats['size'] == 0
        assert stats['hits'] == 0
        assert stats['misses'] == 0
    
    def test_cache_invalidate(self):
        """Should invalidate specific entries."""
        from services.caching import EmbeddingCache
        
        cache = EmbeddingCache()
        cache.put('keep', np.array([1.0]))
        cache.put('remove', np.array([2.0]))
        
        result = cache.invalidate('remove')
        
        assert result is True
        assert cache.get('keep') is not None
        assert cache.get('remove') is None


class TestEmbeddingCacheGlobal:
    """Test global embedding cache singleton."""
    
    def test_get_embedding_cache_singleton(self):
        """Should return same instance."""
        from services.caching import get_embedding_cache, reset_embedding_cache
        
        reset_embedding_cache()
        
        cache1 = get_embedding_cache()
        cache2 = get_embedding_cache()
        
        assert cache1 is cache2
    
    def test_reset_embedding_cache(self):
        """Reset should clear singleton."""
        from services.caching import get_embedding_cache, reset_embedding_cache
        
        cache1 = get_embedding_cache()
        reset_embedding_cache()
        cache2 = get_embedding_cache()
        
        assert cache1 is not cache2


# =============================================================================
# SEMANTIC RESPONSE CACHE TESTS
# =============================================================================

class TestSemanticResponseCache:
    """Test the semantic response cache."""
    
    def test_cache_initialization(self):
        """Cache should initialize with correct parameters."""
        from services.caching import SemanticResponseCache
        
        cache = SemanticResponseCache(
            max_size=100,
            similarity_threshold=0.9,
            ttl_seconds=60
        )
        
        stats = cache.get_stats()
        assert stats['max_size'] == 100
        assert stats['threshold'] == 0.9
        assert stats['ttl_seconds'] == 60
    
    def test_exact_match_retrieval(self):
        """Should retrieve response for identical query."""
        from services.caching import SemanticResponseCache
        
        cache = SemanticResponseCache(similarity_threshold=0.95)
        
        query_embedding = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        
        cache.put(
            query='test query',
            query_embedding=query_embedding,
            response='test response',
            model='test-model'
        )
        
        result = cache.get(
            query='same query',
            query_embedding=query_embedding,  # Same embedding
            model='test-model'
        )
        
        assert result is not None
        response, similarity = result
        assert response == 'test response'
        assert similarity == 1.0
    
    def test_similar_query_retrieval(self):
        """Should retrieve response for similar query."""
        from services.caching import SemanticResponseCache
        
        cache = SemanticResponseCache(similarity_threshold=0.9)
        
        original = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        similar = np.array([0.98, 0.1, 0.1], dtype=np.float32)
        similar = similar / np.linalg.norm(similar)  # Normalize
        
        cache.put(
            query='original',
            query_embedding=original,
            response='cached response',
            model='test'
        )
        
        result = cache.get('similar', similar, model='test')
        
        assert result is not None
        response, similarity = result
        assert response == 'cached response'
        assert similarity >= 0.9
    
    def test_dissimilar_query_miss(self):
        """Should not return response for dissimilar query."""
        from services.caching import SemanticResponseCache
        
        cache = SemanticResponseCache(similarity_threshold=0.95)
        
        original = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        different = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        
        cache.put('original', original, 'response', 'test')
        
        result = cache.get('different', different, model='test')
        
        assert result is None
    
    def test_model_filtering(self):
        """Should filter by model when specified."""
        from services.caching import SemanticResponseCache
        
        cache = SemanticResponseCache(similarity_threshold=0.95)
        
        embedding = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        
        cache.put('query', embedding, 'llama response', 'llama')
        
        # Same embedding, different model
        result = cache.get('query', embedding, model='gpt')
        
        assert result is None
    
    def test_stats_tracking(self):
        """Should track hits and misses."""
        from services.caching import SemanticResponseCache
        
        cache = SemanticResponseCache(similarity_threshold=0.95)
        
        embedding = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        
        # Miss
        cache.get('query1', embedding)
        
        # Put and hit
        cache.put('query2', embedding, 'response', 'test')
        cache.get('query2', embedding)
        
        stats = cache.get_stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1


# =============================================================================
# TOKEN USAGE TRACKING TESTS
# =============================================================================

class TestTokenUsage:
    """Test TokenUsage dataclass."""
    
    def test_token_usage_creation(self):
        """Should create token usage record."""
        from services.caching import TokenUsage
        
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model='llama3.1:8b'
        )
        
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150
    
    def test_cost_estimation_small_model(self):
        """Should estimate cost for small models."""
        from services.caching import TokenUsage
        
        usage = TokenUsage(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            model='llama3.1:8b'
        )
        
        cost = usage.estimated_cost_usd
        # Small model: $0.10/1M prompt + $0.20/1M completion
        expected = (1000 * 0.10 + 500 * 0.20) / 1_000_000
        assert cost == pytest.approx(expected, rel=0.01)
    
    def test_cost_estimation_large_model(self):
        """Should estimate higher cost for large models."""
        from services.caching import TokenUsage
        
        usage = TokenUsage(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            model='qwen2.5:72b'
        )
        
        cost = usage.estimated_cost_usd
        # Large model: $1.00/1M prompt + $2.00/1M completion
        expected = (1000 * 1.0 + 500 * 2.0) / 1_000_000
        assert cost == pytest.approx(expected, rel=0.01)


class TestTokenTracker:
    """Test TokenTracker class."""
    
    def test_tracker_initialization(self):
        """Tracker should initialize with zero counts."""
        from services.caching import TokenTracker
        
        tracker = TokenTracker()
        totals = tracker.get_totals()
        
        assert totals['prompt_tokens'] == 0
        assert totals['completion_tokens'] == 0
        assert totals['request_count'] == 0
    
    def test_record_tokens(self):
        """Should accumulate token usage."""
        from services.caching import TokenTracker
        
        tracker = TokenTracker()
        
        tracker.record(100, 50, 'test-model')
        tracker.record(200, 100, 'test-model')
        
        totals = tracker.get_totals()
        assert totals['prompt_tokens'] == 300
        assert totals['completion_tokens'] == 150
        assert totals['total_tokens'] == 450
        assert totals['request_count'] == 2
    
    def test_per_user_tracking(self):
        """Should track per-user usage."""
        from services.caching import TokenTracker
        
        tracker = TokenTracker()
        
        tracker.record(100, 50, 'model', user_id='user1')
        tracker.record(200, 100, 'model', user_id='user2')
        tracker.record(50, 25, 'model', user_id='user1')
        
        user1_usage = tracker.get_user_usage('user1')
        user2_usage = tracker.get_user_usage('user2')
        
        assert user1_usage['prompt'] == 150
        assert user1_usage['completion'] == 75
        assert user2_usage['prompt'] == 200
        assert user2_usage['completion'] == 100
    
    def test_top_users(self):
        """Should return top users by usage."""
        from services.caching import TokenTracker
        
        tracker = TokenTracker()
        
        tracker.record(1000, 500, 'model', user_id='heavy_user')
        tracker.record(100, 50, 'model', user_id='light_user')
        
        top = tracker.get_top_users(limit=2)
        
        assert top[0][0] == 'heavy_user'
        assert top[0][1] == 1500
        assert top[1][0] == 'light_user'
    
    def test_reset_tracker(self):
        """Reset should clear all data."""
        from services.caching import TokenTracker
        
        tracker = TokenTracker()
        tracker.record(100, 50, 'model', user_id='user1')
        
        tracker.reset()
        
        totals = tracker.get_totals()
        assert totals['total_tokens'] == 0
        assert tracker.get_user_usage('user1') is None


# =============================================================================
# TOKEN ESTIMATION TESTS
# =============================================================================

class TestTokenEstimation:
    """Test token estimation functions."""
    
    def test_estimate_tokens_empty(self):
        """Empty string should return 0."""
        from services.caching import estimate_tokens
        
        assert estimate_tokens('') == 0
    
    def test_estimate_tokens_short(self):
        """Short text estimation."""
        from services.caching import estimate_tokens
        
        # ~4 chars per token
        result = estimate_tokens('Hello')  # 5 chars
        assert result >= 1
    
    def test_estimate_tokens_long(self):
        """Longer text estimation."""
        from services.caching import estimate_tokens
        
        text = 'This is a longer text that should have more tokens than a short one.'
        result = estimate_tokens(text)
        
        # Should be roughly len(text) / 4
        assert 10 < result < 30
    
    def test_estimate_tokens_accurate(self):
        """Word-based estimation."""
        from services.caching import estimate_tokens_accurate
        
        text = 'This is a test sentence with seven words.'
        result = estimate_tokens_accurate(text)
        
        # ~1.3 tokens per word
        assert 8 < result < 15


# =============================================================================
# RATE LIMIT TOKEN QUOTA TESTS
# =============================================================================

class TestTokenQuota:
    """Test per-user token quota functionality."""
    
    def test_check_quota_allowed(self):
        """Should allow requests under quota."""
        from middleware.rate_limit import check_token_quota, token_usage_tracking
        
        # Clear any existing tracking
        test_user = 'test_quota_user_1'
        if test_user in token_usage_tracking:
            del token_usage_tracking[test_user]
        
        is_allowed, info = check_token_quota(test_user, estimated_tokens=1000)
        
        assert is_allowed is True
        assert info['tokens_remaining'] > 0
    
    def test_record_usage(self):
        """Should record and accumulate usage."""
        from middleware.rate_limit import record_token_usage, check_token_quota, token_usage_tracking
        
        test_user = 'test_quota_user_2'
        if test_user in token_usage_tracking:
            del token_usage_tracking[test_user]
        
        record_token_usage(test_user, 5000)
        record_token_usage(test_user, 3000)
        
        _, info = check_token_quota(test_user, 0)
        
        assert info['tokens_used'] == 8000
    
    def test_quota_enforcement(self):
        """Should deny when quota exceeded."""
        from middleware.rate_limit import (
            check_token_quota, record_token_usage,
            token_usage_tracking, TOKEN_QUOTA_DAILY
        )
        
        test_user = 'test_quota_user_3'
        
        # Set up a user near quota
        token_usage_tracking[test_user] = {
            'tokens': TOKEN_QUOTA_DAILY - 100,
            'requests': 50,
            'window_start': time.time()
        }
        
        # Should deny large request
        is_allowed, info = check_token_quota(test_user, estimated_tokens=500)
        
        assert is_allowed is False
        assert info['tokens_remaining'] == 100


# =============================================================================
# COST METRICS TESTS
# =============================================================================

class TestCostMetrics:
    """Test cost-related Prometheus metrics."""
    
    def test_embedding_cache_metrics_exist(self):
        """Embedding cache metrics should be defined."""
        from middleware.observability import (
            EMBEDDING_CACHE_HITS, EMBEDDING_CACHE_MISSES,
            EMBEDDING_CACHE_SIZE, PROMETHEUS_AVAILABLE
        )
        
        if PROMETHEUS_AVAILABLE:
            assert EMBEDDING_CACHE_HITS is not None
            assert EMBEDDING_CACHE_MISSES is not None
            assert EMBEDDING_CACHE_SIZE is not None
    
    def test_semantic_cache_metrics_exist(self):
        """Semantic cache metrics should be defined."""
        from middleware.observability import (
            SEMANTIC_CACHE_HITS, SEMANTIC_CACHE_MISSES,
            SEMANTIC_CACHE_SIZE, SEMANTIC_CACHE_SIMILARITY,
            PROMETHEUS_AVAILABLE
        )
        
        if PROMETHEUS_AVAILABLE:
            assert SEMANTIC_CACHE_HITS is not None
            assert SEMANTIC_CACHE_MISSES is not None
            assert SEMANTIC_CACHE_SIZE is not None
            assert SEMANTIC_CACHE_SIMILARITY is not None
    
    def test_token_metrics_exist(self):
        """Token metrics should be defined."""
        from middleware.observability import (
            TOKENS_PROMPT, TOKENS_COMPLETION,
            ESTIMATED_COST_USD, TOKEN_RATE, USER_TOKENS,
            PROMETHEUS_AVAILABLE
        )
        
        if PROMETHEUS_AVAILABLE:
            assert TOKENS_PROMPT is not None
            assert TOKENS_COMPLETION is not None
            assert ESTIMATED_COST_USD is not None
            assert TOKEN_RATE is not None
            assert USER_TOKENS is not None


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestCachingIntegration:
    """Integration tests for the caching system."""
    
    def test_get_all_cache_stats(self):
        """Should return stats for all caches."""
        from services.caching import (
            get_all_cache_stats,
            reset_embedding_cache,
            reset_semantic_cache,
            reset_token_tracker
        )
        
        # Reset to known state
        reset_embedding_cache()
        reset_semantic_cache()
        reset_token_tracker()
        
        stats = get_all_cache_stats()
        
        assert 'embedding_cache' in stats
        assert 'semantic_cache' in stats
        assert 'token_usage' in stats
    
    def test_clear_all_caches(self):
        """Should clear all caches."""
        from services.caching import (
            clear_all_caches, get_embedding_cache,
            get_semantic_cache, reset_embedding_cache,
            reset_semantic_cache
        )
        
        # Reset and populate
        reset_embedding_cache()
        reset_semantic_cache()
        
        embedding_cache = get_embedding_cache()
        embedding_cache.put('test', np.array([1.0]))
        
        clear_all_caches()
        
        stats = embedding_cache.get_stats()
        assert stats['size'] == 0


class TestEmbeddingsWithCache:
    """Test embeddings module integration with cache."""
    
    @patch('services.embeddings.get_embedding_model')
    def test_embed_text_uses_cache(self, mock_model):
        """embed_text should use cache."""
        from services.embeddings import embed_text
        from services.caching import reset_embedding_cache, get_embedding_cache
        
        reset_embedding_cache()
        
        # Mock the model to return a known embedding
        mock_instance = MagicMock()
        mock_instance.embed.return_value = iter([np.array([1.0, 2.0, 3.0])])
        mock_model.return_value = mock_instance
        
        # First call - should compute
        result1 = embed_text('test text')
        assert result1 is not None
        assert mock_instance.embed.call_count == 1
        
        # Second call - should use cache
        result2 = embed_text('test text')
        assert result2 is not None
        # Model should not be called again
        assert mock_instance.embed.call_count == 1
        
        # Verify cache stats
        cache = get_embedding_cache()
        stats = cache.get_stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1
