"""Tests for services/loading_messages.py — whimsical loading message generator."""

from services.loading_messages import (
    LOADING_PHRASES,
    format_phase_update,
    get_loading_message,
    get_loading_sequence,
)


class TestGetLoadingMessage:
    def test_known_phase_returns_message(self):
        msg = get_loading_message("searching")
        assert msg.endswith("...")
        assert "the" in msg

    def test_unknown_phase_returns_default(self):
        msg = get_loading_message("nonexistent_phase")
        assert msg.endswith("...")
        assert "the" in msg

    def test_index_parameter_deterministic(self):
        msg1 = get_loading_message("searching", index=0)
        msg2 = get_loading_message("searching", index=0)
        assert msg1 == msg2

    def test_index_wraps_around(self):
        phrases = LOADING_PHRASES["searching"]
        msg = get_loading_message("searching", index=len(phrases))
        expected = get_loading_message("searching", index=0)
        assert msg == expected

    def test_all_phases_produce_output(self):
        for phase in LOADING_PHRASES:
            msg = get_loading_message(phase)
            assert isinstance(msg, str)
            assert len(msg) > 0


class TestGetLoadingSequence:
    def test_returns_correct_count(self):
        seq = get_loading_sequence("executing", count=3)
        assert len(seq) == 3

    def test_all_messages_have_correct_format(self):
        seq = get_loading_sequence("searching", count=5)
        for msg in seq:
            assert msg.endswith("...")
            assert "the" in msg

    def test_default_count_is_five(self):
        seq = get_loading_sequence("executing")
        assert len(seq) == 5

    def test_count_exceeding_phrases_wraps(self):
        phrases = LOADING_PHRASES["tool_execution"]
        seq = get_loading_sequence("tool_execution", count=len(phrases) + 3)
        assert len(seq) == len(phrases) + 3

    def test_unknown_phase_uses_defaults(self):
        seq = get_loading_sequence("bogus_phase", count=2)
        assert len(seq) == 2


class TestFormatPhaseUpdate:
    def test_auto_generates_message(self):
        result = format_phase_update("searching")
        assert result["phase"] == "searching"
        assert isinstance(result["message"], str)
        assert result["message"].endswith("...")

    def test_custom_message_override(self):
        result = format_phase_update("searching", message="Custom loading...")
        assert result["phase"] == "searching"
        assert result["message"] == "Custom loading..."

    def test_returns_dict_with_required_keys(self):
        result = format_phase_update("executing")
        assert "phase" in result
        assert "message" in result
