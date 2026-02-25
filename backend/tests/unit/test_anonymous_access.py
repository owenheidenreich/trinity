"""
Trinity Backend — Anonymous / Guest Access Tests
==================================================
Tests for the open-by-default access model:
- get_anonymous_principal() produces deterministic principals
- require_auth_or_anonymous decorator: auth users pass through,
  missing headers → anonymous, invalid headers → 401
- Anonymous users hit tighter rate limits
"""

import time

import pytest

from icp_auth import (
    get_anonymous_principal,
    require_auth_or_anonymous,
)


# =============================================================================
# get_anonymous_principal
# =============================================================================


class TestGetAnonymousPrincipal:
    """Deterministic principal derivation from IP."""

    def test_returns_anon_prefixed_string(self):
        """Principal starts with 'anon-'."""
        p = get_anonymous_principal("192.168.1.1")
        assert p.startswith("anon-")

    def test_deterministic_for_same_ip(self):
        """Same IP always produces the same principal."""
        p1 = get_anonymous_principal("10.0.0.1")
        p2 = get_anonymous_principal("10.0.0.1")
        assert p1 == p2

    def test_different_ips_produce_different_principals(self):
        """Two different IPs must not collide."""
        p1 = get_anonymous_principal("10.0.0.1")
        p2 = get_anonymous_principal("10.0.0.2")
        assert p1 != p2

    def test_hash_is_16_hex_chars(self):
        """The hash portion should be exactly 16 hex chars."""
        p = get_anonymous_principal("127.0.0.1")
        hash_part = p.removeprefix("anon-")
        assert len(hash_part) == 16
        # Verify it's valid hex
        int(hash_part, 16)


# =============================================================================
# require_auth_or_anonymous DECORATOR
# =============================================================================


class TestRequireAuthOrAnonymous:
    """Decorator behavior for auth vs anonymous vs invalid headers."""

    def _make_app(self):
        """Create a minimal Flask app with a test route."""
        from flask import Flask

        app = Flask(__name__)

        @app.route("/test", methods=["POST"])
        @require_auth_or_anonymous
        def test_route():
            from flask import jsonify, request

            return jsonify({
                "principal": request.principal,
                "is_anonymous": request.is_anonymous,
            })

        return app

    def test_anonymous_no_headers(self):
        """Request with no ICP headers → anonymous access."""
        app = self._make_app()
        with app.test_client() as client:
            resp = client.post("/test", json={})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["is_anonymous"] is True
            assert data["principal"].startswith("anon-")

    def test_invalid_auth_headers_rejected(self):
        """Request with invalid ICP headers → 401."""
        app = self._make_app()
        with app.test_client() as client:
            resp = client.post(
                "/test",
                json={},
                headers={
                    "ICP-Principal": "fake-principal",
                    "ICP-Signature": "deadbeef",
                    "ICP-Timestamp": str(int(time.time() * 1000)),
                    "ICP-PublicKey": "aa" * 32,
                    "ICP-Nonce": "testnonce123",
                },
            )
            assert resp.status_code == 401

    def test_partial_headers_treated_as_attempted_auth(self):
        """If ICP-Principal is present but other headers are missing → 401."""
        app = self._make_app()
        with app.test_client() as client:
            resp = client.post(
                "/test",
                json={},
                headers={"ICP-Principal": "some-principal"},
            )
            assert resp.status_code == 401


# =============================================================================
# ANONYMOUS RATE LIMITING
# =============================================================================


class TestAnonymousRateLimiting:
    """Anonymous users use tighter rate limits."""

    def test_anonymous_rate_limit_constants_exist(self):
        """ANONYMOUS_RATE_LIMIT and ANONYMOUS_RATE_WINDOW are defined."""
        from middleware.rate_limit import ANONYMOUS_RATE_LIMIT, ANONYMOUS_RATE_WINDOW

        assert isinstance(ANONYMOUS_RATE_LIMIT, int)
        assert isinstance(ANONYMOUS_RATE_WINDOW, int)
        assert ANONYMOUS_RATE_LIMIT > 0
        assert ANONYMOUS_RATE_WINDOW > 0

    def test_anonymous_rate_limit_is_tighter(self):
        """Anonymous rate limit is stricter than authenticated limit."""
        from middleware.rate_limit import ANONYMOUS_RATE_LIMIT, RATE_LIMIT

        assert ANONYMOUS_RATE_LIMIT < RATE_LIMIT


# =============================================================================
# GENERATE ROUTE — ANONYMOUS ACCESS
# =============================================================================


class TestAnonymousGenerateAccess:
    """The /generate/agent route allows anonymous access (no prompt counting)."""

    def _make_app(self):
        from flask import Flask

        from routes.generate import generate_bp

        app = Flask(__name__)
        app.register_blueprint(generate_bp)
        return app

    def test_anonymous_request_not_rejected_at_auth(self):
        """Anonymous request passes auth gate (will fail at LLM layer, but not 401)."""
        app = self._make_app()
        with app.test_client() as client:
            resp = client.post(
                "/generate/agent",
                json={"prompt": "Hello"},
                content_type="application/json",
            )
            # Expect 500 (LLM unavailable) or 503, NOT 401
            assert resp.status_code != 401

    def test_anonymous_status_endpoint_removed(self):
        """The /generate/anonymous-status endpoint no longer exists."""
        app = self._make_app()
        with app.test_client() as client:
            resp = client.get("/generate/anonymous-status")
            assert resp.status_code == 404
