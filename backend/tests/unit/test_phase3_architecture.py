"""
Phase 3 Architecture Tests
=============================
Validates the Phase 3 critical fixes:
  3.1 Blueprint route refactor
  3.2 Two-model task-based routing
  3.3 SQLite persistent state
  3.4 Grafana monitoring config
"""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask


# ===== Fixtures =====

@pytest.fixture
def app():
    """Create the Flask app from the refactored app factory."""
    from inference_server import app
    app.config["TESTING"] = True
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


# =============================================================================
# 3.1 BLUEPRINT REFACTOR TESTS
# =============================================================================

class TestBlueprintRegistration:
    """Verify all blueprints are properly registered."""

    def test_all_blueprints_registered(self, app):
        """Canonical blueprints should be registered on the app."""
        blueprint_names = list(app.blueprints.keys())
        expected = ["health", "generate", "chat", "tools", "passphrase"]
        for name in expected:
            assert name in blueprint_names, f"Blueprint '{name}' not registered"

    def test_health_routes_exist(self, client):
        """Health blueprint exposes /health, /health/icp, /metrics, /stats."""
        for path in ["/health", "/health/icp", "/metrics", "/stats"]:
            response = client.get(path)
            assert response.status_code != 404, f"{path} returned 404"

    def test_chat_routes_exist(self, client):
        """Chat blueprint routes should exist (require auth, not 404)."""
        endpoints = [
            ("GET", "/chat/list"),
            ("GET", "/user/status"),
            ("GET", "/user/memory"),
        ]
        for method, path in endpoints:
            if method == "GET":
                response = client.get(path)
            else:
                response = client.post(path, json={})
            assert response.status_code != 404, f"{method} {path} returned 404"

    def test_v4_routes_removed(self, client):
        """Legacy /v4 endpoints are fully removed in hard-cutover mode."""
        response = client.get("/v4/status")
        assert response.status_code == 404

    def test_app_factory_line_count(self):
        """inference_server.py should be slim (< 500 lines)."""
        server_path = Path(__file__).parent.parent.parent / "inference_server.py"
        lines = server_path.read_text().count("\n")
        assert lines < 500, f"inference_server.py has {lines} lines (should be < 500)"

    def test_route_count(self, app):
        """App should have ~31 registered URL rules."""
        rules = list(app.url_map.iter_rules())
        # Filter out the default 'static' rule
        non_static = [r for r in rules if r.endpoint != "static"]
        assert len(non_static) >= 25, f"Only {len(non_static)} routes registered"

    def test_feature_flags_on_config(self, app):
        """V4 feature flags should be on app.config."""
        assert "V4_FEATURES_AVAILABLE" in app.config
        assert "V4_FEATURES" in app.config
        assert isinstance(app.config["V4_FEATURES"], dict)


class TestBlueprintImports:
    """Verify modules export expected symbols."""

    def test_shared_exports(self):
        """routes.shared exports shared state."""
        from routes.shared import (
            error_response,
            document_store,
            _io_executor,
            _funding_cache,
            _funding_cache_lock,
            MAX_DOCUMENT_SIZE,
            FuturesTimeoutError,
            cleanup_document_store,
        )
        assert callable(error_response)
        assert callable(cleanup_document_store)
        assert isinstance(document_store, dict)
        assert _io_executor._max_workers == 10

    def test_all_blueprints_list(self):
        """routes.__init__ exports canonical ALL_BLUEPRINTS list."""
        from routes import ALL_BLUEPRINTS
        assert len(ALL_BLUEPRINTS) == 7


class TestRequestHooks:
    """Verify before/after request hooks work."""

    def test_rate_limit_headers_present(self, client):
        """Responses should include X-RateLimit-* headers."""
        response = client.get("/health")
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers

    def test_origin_validation_blocks_bad_origin(self, client):
        """POST from unknown origin should be blocked."""
        response = client.post(
            "/generate",
            json={"prompt": "test"},
            headers={"Origin": "https://evil.com"},
        )
        assert response.status_code == 403

    def test_origin_validation_allows_good_origin(self, client):
        """POST from allowed origin should pass through."""
        response = client.post(
            "/generate",
            json={"prompt": "test"},
            headers={"Origin": "http://localhost:3000"},
        )
        # May fail for other reasons (no Ollama) but NOT 403
        assert response.status_code != 403


# =============================================================================
# 3.2 SQLITE DATABASE TESTS
# =============================================================================

class TestSQLiteDatabase:
    """Test SQLite persistent state via SQLAlchemy."""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        """Create a fresh temporary database for each test."""
        from database import init_db, get_db, Base, _engine
        db_path = str(tmp_path / "test_trinity.db")
        init_db(db_path)
        self.db = get_db()
        yield
        # Cleanup handled by tmp_path

    def test_init_creates_tables(self, tmp_path):
        """init_db creates all expected tables."""
        from database import init_db, _engine
        from sqlalchemy import inspect
        db_path = str(tmp_path / "tables_test.db")
        init_db(db_path)
        inspector = inspect(_engine)
        tables = inspector.get_table_names()
        assert "rate_limits" in tables
        assert "sessions" in tables
        assert "usage_stats" in tables
        assert "chat_metadata" in tables

    def test_rate_limit_upsert_and_get(self):
        """Can insert and retrieve rate limit records."""
        self.db.upsert_rate_limit("192.168.1.1", 5, 1000)
        result = self.db.get_rate_limit("192.168.1.1")
        assert result is not None
        assert result["request_count"] == 5
        assert result["window_start"] == 1000

    def test_rate_limit_update(self):
        """Upserting an existing IP updates the record."""
        self.db.upsert_rate_limit("10.0.0.1", 1, 100)
        self.db.upsert_rate_limit("10.0.0.1", 10, 200)
        result = self.db.get_rate_limit("10.0.0.1")
        assert result["request_count"] == 10
        assert result["window_start"] == 200

    def test_rate_limit_missing_ip(self):
        """Querying non-existent IP returns None."""
        assert self.db.get_rate_limit("1.2.3.4") is None

    def test_rate_limit_cleanup(self):
        """cleanup_rate_limits removes old entries."""
        self.db.upsert_rate_limit("old-ip", 5, 100)
        self.db.upsert_rate_limit("new-ip", 3, 99999)
        count = self.db.cleanup_rate_limits(500)
        assert count == 1
        assert self.db.get_rate_limit("old-ip") is None
        assert self.db.get_rate_limit("new-ip") is not None

    def test_session_create_and_get(self):
        """Can create and retrieve session records."""
        self.db.create_session("sess_abc123", "principal_xyz", {"tier": 2})
        result = self.db.get_session_record("sess_abc123")
        assert result is not None
        assert result["principal"] == "principal_xyz"
        assert result["data"]["tier"] == 2

    def test_session_not_found(self):
        """Querying non-existent session returns None."""
        assert self.db.get_session_record("nonexistent") is None

    def test_usage_stats_record_and_get(self):
        """Can record and retrieve usage stats."""
        self.db.record_usage("principal_1", "2025-01-15", tokens=100, requests=5)
        result = self.db.get_usage_stats("principal_1", "2025-01-15")
        assert result["tokens_used"] == 100
        assert result["requests"] == 5

    def test_usage_stats_accumulate(self):
        """Multiple record_usage calls accumulate values."""
        self.db.record_usage("p1", "2025-01-15", tokens=50, requests=1)
        self.db.record_usage("p1", "2025-01-15", tokens=30, requests=2)
        result = self.db.get_usage_stats("p1", "2025-01-15")
        assert result["tokens_used"] == 80
        assert result["requests"] == 3

    def test_usage_stats_different_dates(self):
        """Stats for different dates are tracked separately."""
        self.db.record_usage("p1", "2025-01-15", tokens=100)
        self.db.record_usage("p1", "2025-01-16", tokens=200)
        day1 = self.db.get_usage_stats("p1", "2025-01-15")
        day2 = self.db.get_usage_stats("p1", "2025-01-16")
        assert day1["tokens_used"] == 100
        assert day2["tokens_used"] == 200

    def test_chat_metadata_upsert(self):
        """Can create and update chat metadata."""
        self.db.upsert_chat_metadata(
            chat_id="chat_1", principal="p1",
            title="My Chat", pinned=False, message_count=5,
        )
        chats = self.db.get_chats_for_principal("p1")
        assert len(chats) == 1
        assert chats[0]["chatId"] == "chat_1"
        assert chats[0]["title"] == "My Chat"
        assert chats[0]["messageCount"] == 5

    def test_chat_metadata_update(self):
        """Upserting existing chat updates it."""
        self.db.upsert_chat_metadata("c1", "p1", title="V1")
        self.db.upsert_chat_metadata("c1", "p1", title="V2", pinned=True)
        chats = self.db.get_chats_for_principal("p1")
        assert len(chats) == 1
        assert chats[0]["title"] == "V2"
        assert chats[0]["pinned"] is True

    def test_chat_metadata_delete(self):
        """Can delete chat metadata."""
        self.db.upsert_chat_metadata("c1", "p1")
        assert self.db.delete_chat_metadata("c1") is True
        assert self.db.get_chats_for_principal("p1") == []

    def test_chat_metadata_delete_nonexistent(self):
        """Deleting non-existent chat returns False."""
        assert self.db.delete_chat_metadata("nonexistent") is False

    def test_chat_metadata_principal_isolation(self):
        """Chats for different principals are isolated."""
        self.db.upsert_chat_metadata("c1", "alice")
        self.db.upsert_chat_metadata("c2", "bob")
        assert len(self.db.get_chats_for_principal("alice")) == 1
        assert len(self.db.get_chats_for_principal("bob")) == 1

    def test_get_all_usage_for_date(self):
        """Can retrieve all usage for a given date."""
        self.db.record_usage("p1", "2025-01-15", tokens=100)
        self.db.record_usage("p2", "2025-01-15", tokens=200)
        self.db.record_usage("p1", "2025-01-16", tokens=50)
        day_usage = self.db.get_all_usage_for_date("2025-01-15")
        assert len(day_usage) == 2
        total = sum(u["tokens_used"] for u in day_usage)
        assert total == 300


# =============================================================================
# 3.4 MONITORING CONFIG TESTS
# =============================================================================

class TestMonitoringConfig:
    """Validate Grafana/Prometheus configuration files exist and are valid."""

    def test_prometheus_config_exists(self):
        """prometheus.yml exists."""
        path = Path(__file__).parent.parent.parent.parent / "deploy" / "prometheus" / "prometheus.yml"
        assert path.exists(), f"Missing: {path}"

    def test_prometheus_alerts_exist(self):
        """alerts.yml exists."""
        path = Path(__file__).parent.parent.parent.parent / "deploy" / "prometheus" / "alerts.yml"
        assert path.exists(), f"Missing: {path}"

    def test_grafana_dashboard_exists(self):
        """Main trinity dashboard JSON exists."""
        path = Path(__file__).parent.parent.parent.parent / "deploy" / "grafana" / "trinity-dashboard.json"
        assert path.exists(), f"Missing: {path}"

    def test_grafana_dashboard_valid_json(self):
        """Dashboard JSON is valid."""
        path = Path(__file__).parent.parent.parent.parent / "deploy" / "grafana" / "trinity-dashboard.json"
        with open(path) as f:
            data = json.load(f)
        assert "panels" in data or "rows" in data or "templating" in data

    def test_docker_compose_monitoring_exists(self):
        """docker-compose.monitoring.yml exists."""
        path = Path(__file__).parent.parent.parent.parent / "deploy" / "docker-compose.monitoring.yml"
        assert path.exists(), f"Missing: {path}"

    def test_grafana_provisioning_datasource(self):
        """Grafana datasource provisioning config exists."""
        path = (
            Path(__file__).parent.parent.parent.parent
            / "deploy" / "grafana" / "provisioning" / "datasources" / "prometheus.yml"
        )
        assert path.exists(), f"Missing: {path}"

    def test_grafana_provisioning_dashboards(self):
        """Grafana dashboard provisioning config exists."""
        path = (
            Path(__file__).parent.parent.parent.parent
            / "deploy" / "grafana" / "provisioning" / "dashboards" / "dashboards.yml"
        )
        assert path.exists(), f"Missing: {path}"

    def test_no_pii_in_dashboard(self):
        """Dashboard JSON should not contain PII-related panel queries."""
        path = Path(__file__).parent.parent.parent.parent / "deploy" / "grafana" / "trinity-dashboard.json"
        content = path.read_text().lower()
        # These terms should NOT appear in monitoring queries
        for forbidden in ["principal", "ip_address", "chat_title", "message_content"]:
            assert forbidden not in content, f"Dashboard contains PII term: {forbidden}"


# =============================================================================
# 3.2 DOCKERFILE TESTS
# =============================================================================

class TestDockerfileUpdates:
    """Validate Dockerfile changes for Phase 3."""

    def test_dockerfile_copies_routes(self):
        """Dockerfile should COPY routes/ directory."""
        path = Path(__file__).parent.parent.parent.parent / "deploy" / "docker" / "Dockerfile"
        content = path.read_text()
        assert "routes/" in content, "Dockerfile missing COPY for routes/"
