"""Tests for services/slo_metrics.py — SLO tracking metrics."""

import importlib

import pytest


class TestSloMetrics:
    """Test SLO metric recording and snapshot retrieval."""

    def setup_method(self):
        """Reset SLO metrics state before each test."""
        import services.slo_metrics as mod
        importlib.reload(mod)

    def test_records_first_token_latency_exact_values(self):
        from services.slo_metrics import get_slo_snapshot, record_first_token_latency

        record_first_token_latency(100)
        record_first_token_latency(200)
        record_first_token_latency(300)

        snapshot = get_slo_snapshot()
        assert snapshot["first_token_latency"]["samples"] == 3
        assert snapshot["first_token_latency"]["p50_ms"] == 200

    def test_single_sample_latency(self):
        from services.slo_metrics import get_slo_snapshot, record_first_token_latency

        record_first_token_latency(150)
        snapshot = get_slo_snapshot()
        assert snapshot["first_token_latency"]["samples"] == 1
        assert snapshot["first_token_latency"]["p50_ms"] == 150

    def test_unsolicited_reference_rate_detected(self):
        from services.slo_metrics import get_slo_snapshot, record_unsolicited_personal_reference

        record_unsolicited_personal_reference(
            "what is the quadratic formula",
            "I remember you told me this before.",
        )
        snapshot = get_slo_snapshot()
        assert snapshot["unsolicited_personal_reference_rate"] > 0.0

    def test_ipfs_write_count_exact(self):
        from services.slo_metrics import get_slo_snapshot, record_ipfs_write

        record_ipfs_write("user-a")
        record_ipfs_write("user-a")
        record_ipfs_write("user-b")
        snapshot = get_slo_snapshot()
        assert snapshot["ipfs_writes_last_hour"] == 3

    def test_empty_snapshot_has_zero_values(self):
        from services.slo_metrics import get_slo_snapshot

        snapshot = get_slo_snapshot()
        assert snapshot["first_token_latency"]["samples"] == 0
        assert snapshot["ipfs_writes_last_hour"] == 0
