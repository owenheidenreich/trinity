class TestSloMetrics:
    def test_records_first_token_latency(self):
        from services.slo_metrics import get_slo_snapshot, record_first_token_latency

        record_first_token_latency(120)
        record_first_token_latency(240)
        snapshot = get_slo_snapshot()
        assert snapshot["first_token_latency"]["samples"] >= 2
        assert snapshot["first_token_latency"]["p50_ms"] >= 120

    def test_unsolicited_reference_rate(self):
        from services.slo_metrics import get_slo_snapshot, record_unsolicited_personal_reference

        record_unsolicited_personal_reference(
            "what is the quadratic formula",
            "I remember you told me this before.",
        )
        snapshot = get_slo_snapshot()
        assert snapshot["unsolicited_personal_reference_rate"] >= 0.0

    def test_ipfs_write_rate(self):
        from services.slo_metrics import get_slo_snapshot, record_ipfs_write

        record_ipfs_write("user-a")
        record_ipfs_write("user-a")
        snapshot = get_slo_snapshot()
        assert snapshot["ipfs_writes_last_hour"] >= 2
