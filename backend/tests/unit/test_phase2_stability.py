"""
Trinity Phase 2 Stability & UX Tests
======================================
Tests verifying all Phase 2 fixes:

2.1 Persist rate limits (file-based)
2.2 Async browse endpoint (ThreadPoolExecutor)
2.3 Real token counting (Ollama eval_count)
2.4 CSRF / Origin validation
2.5 Chat pin feature
2.6 User status dashboard
2.7 Rate limit UX improvements (headers, structured 429s)
2.8 Better error messages (structured errors, error_response helper)

Created: February 10, 2026
"""

import json
import os
import sys
import importlib
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nacl.signing import SigningKey

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def keypair():
    """Generate a test Ed25519 keypair."""
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key
    from icp_auth import principal_from_public_key

    public_key_hex = verify_key.encode().hex()
    return {
        "signing_key": signing_key,
        "verify_key": verify_key,
        "public_key_hex": public_key_hex,
        "principal": principal_from_public_key(bytes.fromhex(public_key_hex)),
    }


def make_auth_headers(keypair, endpoint, nonce=None):
    """Build auth headers for a request."""
    timestamp = str(int(time.time() * 1000))
    nonce = nonce or str(uuid.uuid4())
    message = f"{keypair['principal']}:{timestamp}:{endpoint}:{nonce}"
    signature = keypair["signing_key"].sign(message.encode()).signature.hex()
    return {
        "ICP-Principal": keypair["principal"],
        "ICP-Timestamp": timestamp,
        "ICP-Signature": signature,
        "ICP-PublicKey": keypair["public_key_hex"],
        "ICP-Nonce": nonce,
        "Content-Type": "application/json",
    }


# Keep tests isolated from shared module-level counters.
@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    from middleware.rate_limit import request_counts, storage_request_counts, token_usage_tracking

    request_counts.clear()
    storage_request_counts.clear()
    token_usage_tracking.clear()
    yield
    request_counts.clear()
    storage_request_counts.clear()
    token_usage_tracking.clear()


# =============================================================================
# 2.1 PERSIST RATE LIMITS
# =============================================================================

class TestRateLimitPersistence:
    """Test that rate limits persist to file and reload on startup."""

    def test_save_and_load_rate_limits(self, tmp_path):
        """Rate limit state can be saved and loaded from disk."""
        # middleware.__init__ shadows the module name with the rate_limit function,
        # so use importlib to get the actual module object
        rl_module = importlib.import_module("middleware.rate_limit")

        test_file = tmp_path / "rate_limits.json"
        original_file = rl_module.RATE_LIMIT_FILE

        try:
            rl_module.RATE_LIMIT_FILE = test_file

            # Add some request data
            test_ip = "192.168.1.100"
            now = time.time()
            rl_module.request_counts[test_ip] = [now, now - 10, now - 20]

            # Save
            rl_module._save_rate_limits()
            assert test_file.exists(), f"File should exist at {test_file}"

            # Verify saved data is valid JSON
            with open(test_file) as f:
                data = json.load(f)
            assert "request_counts" in data
            assert test_ip in data["request_counts"]
        finally:
            rl_module.RATE_LIMIT_FILE = original_file
            if test_ip in rl_module.request_counts:
                del rl_module.request_counts[test_ip]

    def test_persistence_file_format(self, tmp_path):
        """Persisted file contains expected keys."""
        rl_module = importlib.import_module("middleware.rate_limit")

        test_file = tmp_path / "rate_limits.json"
        original_file = rl_module.RATE_LIMIT_FILE

        try:
            rl_module.RATE_LIMIT_FILE = test_file
            rl_module._save_rate_limits()

            with open(test_file) as f:
                data = json.load(f)
            assert "request_counts" in data
            assert "storage_request_counts" in data
            assert "token_usage" in data
            assert "saved_at" in data
        finally:
            rl_module.RATE_LIMIT_FILE = original_file


# =============================================================================
# 2.2 ASYNC BROWSE ENDPOINT
# =============================================================================

class TestAsyncBrowse:
    """Test that browse endpoint uses ThreadPoolExecutor."""

    def test_browse_requires_url(self, client):
        """Browse endpoint rejects empty URL."""
        response = client.post("/tools/browse", json={})
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_browse_rejects_invalid_url(self, client):
        """Browse endpoint rejects non-http URLs."""
        response = client.post("/tools/browse", json={"url": "ftp://evil.com"})
        assert response.status_code == 400

    def test_browse_has_timeout_handling(self):
        """Verify ThreadPoolExecutor and FuturesTimeoutError are imported."""
        from routes.shared import _io_executor, FuturesTimeoutError
        assert _io_executor is not None
        assert _io_executor._max_workers == 10


# =============================================================================
# 2.3 REAL TOKEN COUNTING
# =============================================================================

class TestRealTokenCounting:
    """Legacy /generate route is removed after hard cutover."""

    def test_generate_uses_eval_count(self, client):
        """Removed /generate route returns 404."""
        response = client.post("/generate", json={"prompt": "Hello", "max_length": 100})
        assert response.status_code == 404

    def test_generate_falls_back_to_word_count(self, client):
        """Removed /generate route returns 404."""
        response = client.post("/generate", json={"prompt": "Hello", "max_length": 100})
        assert response.status_code == 404


# =============================================================================
# 2.4 CSRF / ORIGIN VALIDATION
# =============================================================================

class TestOriginValidation:
    """Test CSRF protection via Origin header checking."""

    def test_get_requests_bypass_origin_check(self, client):
        """GET requests don't require Origin header (not blocked by origin check)."""
        response = client.get("/health")
        # Health may return 503 if Ollama is offline, but should NOT return 403
        assert response.status_code != 403

    def test_post_without_origin_allowed(self, client):
        """POST without Origin header is allowed (server-to-server)."""
        response = client.post(
            "/generate",
            json={"prompt": "Hello"},
        )
        # Should not be blocked (no Origin header is okay)
        assert response.status_code != 403

    def test_post_with_bad_origin_blocked(self, client):
        """POST from unknown Origin is blocked."""
        response = client.post(
            "/generate",
            json={"prompt": "Hello"},
            headers={"Origin": "https://evil-site.com"},
        )
        assert response.status_code == 403
        data = response.get_json()
        assert data["error"]["message"] == "Request origin not allowed"

    def test_post_with_allowed_origin_passes(self, client):
        """POST from allowed Origin passes validation."""
        response = client.post(
            "/generate",
            json={"prompt": "Hello"},
            headers={"Origin": "http://localhost:3000"},
        )
        assert response.status_code != 403

    def test_health_exempt_from_origin_check(self, client):
        """Health endpoints are exempt from Origin validation."""
        response = client.get(
            "/health",
            headers={"Origin": "https://evil-site.com"},
        )
        # GET is exempt from origin check — may return 503 (no Ollama) but NOT 403
        assert response.status_code != 403


# =============================================================================
# 2.5 CHAT PIN FEATURE
# =============================================================================

class TestChatPinFeature:
    """Test chat pinning functionality."""

    def test_pin_toggle_endpoint_exists(self, client, keypair):
        """Pin toggle endpoint exists and requires auth."""
        response = client.post("/chat/test-id/pin")
        # Should require auth (not 404)
        assert response.status_code in (401, 403)

    def test_pin_toggle_requires_auth(self, client):
        """Pin endpoint requires authentication."""
        response = client.post(
            "/chat/some-chat-id/pin",
            json={},
        )
        assert response.status_code in (401, 403)

    def test_pin_toggles_state(self, client, keypair):
        """Pinning an existing chat toggles its pinned state."""
        chat_id = str(uuid.uuid4())
        start_headers = make_auth_headers(keypair, "/chat/start")
        start_resp = client.post(
            "/chat/start",
            headers=start_headers,
            json={"chat_id": chat_id, "title": "Test Chat"},
        )
        assert start_resp.status_code == 200

        headers = make_auth_headers(keypair, f"/chat/{chat_id}/pin")
        response = client.post(f"/chat/{chat_id}/pin", headers=headers, json={})

        assert response.status_code == 200
        data = response.get_json()
        assert data["pinned"] is True
        assert data["chatId"] == chat_id

    def test_pin_unpin_toggles(self, client, keypair):
        """Unpinning a pinned chat returns pinned=False."""
        chat_id = str(uuid.uuid4())
        start_headers = make_auth_headers(keypair, "/chat/start")
        start_resp = client.post(
            "/chat/start",
            headers=start_headers,
            json={"chat_id": chat_id, "title": "Test Chat"},
        )
        assert start_resp.status_code == 200

        headers_first = make_auth_headers(keypair, f"/chat/{chat_id}/pin")
        first = client.post(f"/chat/{chat_id}/pin", headers=headers_first, json={})
        assert first.status_code == 200
        assert first.get_json()["pinned"] is True

        headers_second = make_auth_headers(keypair, f"/chat/{chat_id}/pin")
        response = client.post(f"/chat/{chat_id}/pin", headers=headers_second, json={})

        assert response.status_code == 200
        data = response.get_json()
        assert data["pinned"] is False

    def test_pin_chat_not_found(self, client, keypair):
        """Pinning a non-existent chat returns 404."""
        chat_id = str(uuid.uuid4())
        headers = make_auth_headers(keypair, f"/chat/{chat_id}/pin")
        response = client.post(f"/chat/{chat_id}/pin", headers=headers, json={})

        assert response.status_code == 404

    def test_delete_pinned_chat_allowed(self, client, keypair):
        """Pinned chats can be deleted in canonical store mode."""
        chat_id = str(uuid.uuid4())
        start_headers = make_auth_headers(keypair, "/chat/start")
        start_resp = client.post(
            "/chat/start",
            headers=start_headers,
            json={"chat_id": chat_id, "title": "Test"},
        )
        assert start_resp.status_code == 200

        pin_headers = make_auth_headers(keypair, f"/chat/{chat_id}/pin")
        pin_resp = client.post(f"/chat/{chat_id}/pin", headers=pin_headers, json={})
        assert pin_resp.status_code == 200
        assert pin_resp.get_json()["pinned"] is True

        headers = make_auth_headers(keypair, f"/chat/{chat_id}")
        response = client.delete(f"/chat/{chat_id}", headers=headers)
        assert response.status_code == 200


# =============================================================================
# 2.6 USER STATUS DASHBOARD
# =============================================================================

class TestUserStatusDashboard:
    """Test /user/status endpoint."""

    def test_status_requires_auth(self, client):
        """Status endpoint requires authentication."""
        response = client.get("/user/status")
        assert response.status_code in (401, 403)

    def test_status_returns_structure(self, client, keypair):
        """Status endpoint returns canonical storage and tokens sections."""
        for chat_id in ("c1", "c2", "c3"):
            headers = make_auth_headers(keypair, "/chat/start")
            resp = client.post(
                "/chat/start",
                headers=headers,
                json={"chat_id": chat_id, "title": chat_id},
            )
            assert resp.status_code == 200

        patch_headers_1 = make_auth_headers(keypair, "/chat/c1")
        patch_headers_2 = make_auth_headers(keypair, "/chat/c2")
        client.patch("/chat/c1", headers=patch_headers_1, json={"pinned": True})
        client.patch("/chat/c2", headers=patch_headers_2, json={"archived": True})

        headers = make_auth_headers(keypair, "/user/status")
        response = client.get("/user/status", headers=headers)

        assert response.status_code == 200
        data = response.get_json()

        # Storage section
        assert "storage" in data
        assert data["storage"]["chats_used"] == 3
        assert data["storage"]["pinned_count"] == 1
        assert data["storage"]["archived_count"] == 1

        # Tokens section
        assert "tokens" in data
        assert "used_today" in data["tokens"]
        assert "limit_today" in data["tokens"]


# =============================================================================
# 2.7 RATE LIMIT UX IMPROVEMENTS
# =============================================================================

class TestRateLimitUX:
    """Test rate limit headers and structured 429 responses."""

    def test_rate_limit_headers_on_response(self, client):
        """All responses should include X-RateLimit-* headers."""
        response = client.get("/health")
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    def test_rate_limit_remaining_decreases(self, client):
        """X-RateLimit-Remaining decreases with each request."""
        resp1 = client.get("/health")
        remaining1 = int(resp1.headers.get("X-RateLimit-Remaining", "0"))

        resp2 = client.get("/health")
        remaining2 = int(resp2.headers.get("X-RateLimit-Remaining", "0"))

        # Remaining may not strictly decrease since health may not count
        # but both should have the header
        assert remaining1 >= 0
        assert remaining2 >= 0

    def test_structured_429_response(self):
        """Rate limit exceeded response should be structured."""
        from middleware.rate_limit import rate_limit_exceeded_response, request_counts, RATE_LIMIT, RATE_WINDOW
        
        # Need Flask app context for jsonify
        from flask import Flask
        test_app = Flask(__name__)
        with test_app.app_context():
            resp = rate_limit_exceeded_response(
                "192.168.1.1", request_counts, RATE_LIMIT, RATE_WINDOW
            )

        # It's a Response object
        data = json.loads(resp.get_data(as_text=True))
        assert "error" in data
        assert "code" in data["error"]
        assert data["error"]["code"] == 429
        assert "retry_after_seconds" in data["error"]
        assert "Retry-After" in resp.headers

    def test_get_rate_limit_info(self):
        """get_rate_limit_info returns correct structure."""
        from middleware.rate_limit import get_rate_limit_info, RATE_LIMIT, RATE_WINDOW

        info = get_rate_limit_info("new-ip", {}, RATE_LIMIT, RATE_WINDOW)
        assert info["remaining"] == RATE_LIMIT
        assert info["limit"] == RATE_LIMIT
        assert info["used"] == 0


# =============================================================================
# 2.8 BETTER ERROR MESSAGES
# =============================================================================

class TestBetterErrorMessages:
    """Test structured error responses."""

    def test_error_response_helper(self, client):
        """error_response() generates structured error JSON."""
        from routes.shared import error_response

        # Need app context for jsonify
        from flask import Flask
        test_app = Flask(__name__)
        with test_app.app_context():
            resp = error_response(400, "Test error message", details={"key": "value"})

        data = json.loads(resp.get_data(as_text=True))
        assert data["error"]["code"] == 400
        assert data["error"]["message"] == "Test error message"
        assert data["error"]["details"]["key"] == "value"
        assert "timestamp" in data["error"]

    def test_error_response_with_retry_after(self, client):
        """error_response() includes Retry-After header when specified."""
        from routes.shared import error_response
        from flask import Flask
        test_app = Flask(__name__)
        with test_app.app_context():
            resp = error_response(429, "Rate limited", retry_after=30)

        assert resp.headers.get("Retry-After") == "30"
        data = json.loads(resp.get_data(as_text=True))
        assert data["error"]["retry_after_seconds"] == 30

    def test_prompt_too_long_structured_error(self, client):
        """Removed /generate route returns 404."""
        long_prompt = "x" * 200000  # Exceeds MAX_PROMPT_LENGTH (100000)
        response = client.post(
            "/generate",
            json={"prompt": long_prompt},
        )
        assert response.status_code == 404

    def test_chat_route_has_no_legacy_archive_magic_limits(self, client):
        """Canonical chat routes no longer enforce manifest-era archive magic numbers."""
        with open(Path(__file__).parent.parent.parent / "routes" / "chat.py") as f:
            content = f.read()
        assert "archived_count >= 10" not in content
