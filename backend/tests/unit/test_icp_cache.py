"""
Tests for middleware/icp_cache.py — ICP Idempotency Cache

Tests cache get/set/cleanup, TTL expiry, thread safety, and the
icp_idempotent decorator with a Flask test client.
"""

import threading
import time

import pytest
from unittest.mock import patch, MagicMock


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def cache():
    """Fresh ICPIdempotencyCache with short TTL for fast expiry tests."""
    from middleware.icp_cache import ICPIdempotencyCache

    return ICPIdempotencyCache(ttl_seconds=2)


@pytest.fixture
def flask_app():
    """Minimal Flask app with icp_idempotent-decorated route."""
    from flask import Flask, jsonify
    from middleware.icp_cache import icp_idempotent, icp_cache

    app = Flask(__name__)

    call_count = {"n": 0}

    @app.route("/test-endpoint", methods=["POST"])
    @icp_idempotent
    def test_endpoint():
        call_count["n"] += 1
        return jsonify({"result": "ok", "call": call_count["n"]}), 200

    app.config["TESTING"] = True
    yield app, call_count

    # Reset global cache between tests
    icp_cache._cache.clear()
    icp_cache._request_locks.clear()


# =============================================================================
# ICPIdempotencyCache UNIT TESTS
# =============================================================================


class TestCacheGetSet:
    """Test basic cache operations."""

    def test_set_and_get(self, cache):
        cache.set("req-1", {"msg": "hello"}, 200)
        result = cache.get("req-1")

        assert result is not None
        response, status = result
        assert response["msg"] == "hello"
        assert status == 200

    def test_get_missing_returns_none(self, cache):
        assert cache.get("nonexistent") is None

    def test_overwrite_existing(self, cache):
        cache.set("req-1", {"v": 1}, 200)
        cache.set("req-1", {"v": 2}, 201)

        response, status = cache.get("req-1")
        assert response["v"] == 2
        assert status == 201


class TestCacheTTL:
    """Test TTL-based expiry."""

    def test_expired_entry_returns_none(self, cache):
        cache.set("req-ttl", {"msg": "temp"}, 200)

        # Wait for TTL to expire (cache TTL is 2s)
        time.sleep(2.5)

        assert cache.get("req-ttl") is None

    def test_fresh_entry_not_expired(self, cache):
        cache.set("req-fresh", {"msg": "here"}, 200)
        time.sleep(0.5)  # Well within 2s TTL
        assert cache.get("req-fresh") is not None


class TestCacheCleanup:
    """Test cleanup of expired entries."""

    def test_cleanup_removes_expired(self, cache):
        cache.set("old-1", {"v": 1}, 200)
        cache.set("old-2", {"v": 2}, 200)
        time.sleep(2.5)  # Let them expire

        cache.set("new-1", {"v": 3}, 200)  # This triggers _cleanup

        assert "old-1" not in cache._cache
        assert "old-2" not in cache._cache
        assert "new-1" in cache._cache


class TestCacheRequestLock:
    """Test per-request locking for ICP replica serialization."""

    def test_get_request_lock_returns_lock(self, cache):
        lock = cache.get_request_lock("req-lock-1")
        assert hasattr(lock, 'acquire') and hasattr(lock, 'release')

    def test_get_request_lock_returns_same_lock(self, cache):
        lock1 = cache.get_request_lock("req-lock-2")
        lock2 = cache.get_request_lock("req-lock-2")
        assert lock1 is lock2

    def test_different_requests_get_different_locks(self, cache):
        lock_a = cache.get_request_lock("req-a")
        lock_b = cache.get_request_lock("req-b")
        assert lock_a is not lock_b


class TestCacheThreadSafety:
    """Test concurrent access to the cache."""

    def test_concurrent_writes(self, cache):
        errors = []

        def write(idx):
            try:
                cache.set(f"concurrent-{idx}", {"i": idx}, 200)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        # All 50 entries should be cached
        for i in range(50):
            result = cache.get(f"concurrent-{i}")
            assert result is not None

    def test_concurrent_reads_and_writes(self, cache):
        cache.set("shared", {"v": "original"}, 200)
        results = []

        def reader():
            for _ in range(20):
                r = cache.get("shared")
                if r:
                    results.append(r)

        def writer():
            for i in range(20):
                cache.set("shared", {"v": f"update-{i}"}, 200)

        t_read = threading.Thread(target=reader)
        t_write = threading.Thread(target=writer)
        t_read.start()
        t_write.start()
        t_read.join()
        t_write.join()

        # All reads should have returned valid data (no crashes)
        assert len(results) > 0


# =============================================================================
# icp_idempotent DECORATOR TESTS
# =============================================================================


class TestIcpIdempotentDecorator:
    """Test the icp_idempotent Flask decorator."""

    def test_no_request_id_executes_normally(self, flask_app):
        app, call_count = flask_app
        client = app.test_client()

        resp = client.post("/test-endpoint")
        assert resp.status_code == 200
        assert resp.get_json()["call"] == 1

    def test_with_request_id_caches_response(self, flask_app):
        app, call_count = flask_app
        client = app.test_client()

        headers = {"X-Request-ID": "idempotent-1"}

        # First call — executes function
        resp1 = client.post("/test-endpoint", headers=headers)
        assert resp1.status_code == 200
        data1 = resp1.get_json()

        # Second call same request_id — returns cached
        resp2 = client.post("/test-endpoint", headers=headers)
        assert resp2.status_code == 200
        data2 = resp2.get_json()

        # Function should only be called once
        assert call_count["n"] == 1
        assert data1["call"] == data2["call"]

    def test_different_request_ids_execute_separately(self, flask_app):
        app, call_count = flask_app
        client = app.test_client()

        resp1 = client.post("/test-endpoint", headers={"X-Request-ID": "req-A"})
        resp2 = client.post("/test-endpoint", headers={"X-Request-ID": "req-B"})

        # Both should execute (different request IDs)
        assert call_count["n"] == 2
        assert resp1.get_json()["call"] == 1
        assert resp2.get_json()["call"] == 2

    def test_cache_expires_after_ttl(self, flask_app):
        app, call_count = flask_app
        client = app.test_client()

        headers = {"X-Request-ID": "expire-test"}

        client.post("/test-endpoint", headers=headers)
        assert call_count["n"] == 1

        # Wait for global cache TTL (30s) — for unit test, patch the cache TTL
        from middleware.icp_cache import icp_cache
        icp_cache._ttl = 1  # Temporarily shorten
        time.sleep(1.5)

        client.post("/test-endpoint", headers=headers)
        # Function should be called again after expiry
        assert call_count["n"] == 2

        # Restore
        icp_cache._ttl = 30
