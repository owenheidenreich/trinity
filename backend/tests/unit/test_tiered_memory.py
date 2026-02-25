"""
Trinity Backend — Tiered Memory & Storage Tests
=================================================
Tests for the tiered memory architecture:
- Auto-archival of stale chats (pinned exempt)
- source_chat_id column on memory_facts
- Tier-aware retrieval scoring (source_weight demotion)
- Pure composable helpers (_extract_summary, _collect_cross_conversation_summaries)
- Cross-conversation summaries in context_loader
- Prompt assembler cross-conversation injection + ctx_budget
"""

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from services.state_store import close_all_state_stores, get_state_store


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def store(tmp_path):
    """Isolated PrincipalStateStore for tiered memory tests."""
    close_all_state_stores()
    with patch("services.state_store.CHATS_DIR", str(tmp_path)):
        s = get_state_store("tiered-memory-test-principal")
        yield s
    close_all_state_stores()


# =============================================================================
# AUTO-ARCHIVAL
# =============================================================================


class TestAutoArchiveStaleChats:
    """auto_archive_stale_chats() archives old chats, exempts pinned."""

    def test_archives_old_chat(self, store):
        """A chat older than threshold is auto-archived."""
        cid = store.create_chat(title="Old chat")
        # Backdate updated_at by 10 days
        ten_days_ms = 10 * 86_400_000
        with store._lock:
            store.conn.execute(
                "UPDATE chats SET updated_at = ? WHERE chat_id = ?",
                (int(time.time() * 1000) - ten_days_ms, cid),
            )
            store.conn.commit()

        # Reset throttle so archive runs
        store._last_archive_check = 0.0
        archived = store.auto_archive_stale_chats(days=7)
        assert archived == 1

        chat = store.get_chat(cid)
        assert chat["archived"] is True

    def test_pinned_chat_exempt(self, store):
        """Pinned chats are never auto-archived."""
        cid = store.create_chat(title="Pinned chat")
        store.update_chat(cid, pinned=True)

        # Backdate
        ten_days_ms = 10 * 86_400_000
        with store._lock:
            store.conn.execute(
                "UPDATE chats SET updated_at = ? WHERE chat_id = ?",
                (int(time.time() * 1000) - ten_days_ms, cid),
            )
            store.conn.commit()

        store._last_archive_check = 0.0
        archived = store.auto_archive_stale_chats(days=7)
        assert archived == 0

        chat = store.get_chat(cid)
        assert chat["archived"] is False

    def test_recent_chat_not_archived(self, store):
        """A chat updated today is not archived."""
        store.create_chat(title="Fresh chat")

        store._last_archive_check = 0.0
        archived = store.auto_archive_stale_chats(days=7)
        assert archived == 0

    def test_throttle_prevents_repeated_runs(self, store):
        """Archive check runs at most once per hour."""
        store.create_chat(title="Some chat")

        # First call — runs
        store._last_archive_check = 0.0
        store.auto_archive_stale_chats(days=7)

        # Second immediate call — throttled
        archived = store.auto_archive_stale_chats(days=7)
        assert archived == 0

    def test_already_archived_not_double_counted(self, store):
        """Already-archived chats are not re-archived."""
        cid = store.create_chat(title="Already archived")
        store.update_chat(cid, archived=True)

        ten_days_ms = 10 * 86_400_000
        with store._lock:
            store.conn.execute(
                "UPDATE chats SET updated_at = ? WHERE chat_id = ?",
                (int(time.time() * 1000) - ten_days_ms, cid),
            )
            store.conn.commit()

        store._last_archive_check = 0.0
        archived = store.auto_archive_stale_chats(days=7)
        assert archived == 0

    def test_list_chats_triggers_archive(self, store):
        """list_chats() lazily triggers auto_archive_stale_chats()."""
        cid = store.create_chat(title="Stale chat")
        ten_days_ms = 10 * 86_400_000
        with store._lock:
            store.conn.execute(
                "UPDATE chats SET updated_at = ? WHERE chat_id = ?",
                (int(time.time() * 1000) - ten_days_ms, cid),
            )
            store.conn.commit()

        store._last_archive_check = 0.0
        chats = store.list_chats(include_archived=True)
        # After list_chats, the stale chat should now be archived
        stale = next(c for c in chats if c["chatId"] == cid)
        assert stale["archived"] is True


# =============================================================================
# SOURCE_CHAT_ID COLUMN
# =============================================================================


class TestSourceChatId:
    """source_chat_id column on memory_facts."""

    def test_create_fact_with_source_chat_id(self, store):
        """create_fact() can store source_chat_id."""
        fid = store.create_fact(
            text="User likes Python",
            category="preference",
            importance=3,
            source_chat_id="chat-abc-123",
        )
        assert fid is not None
        facts = store.list_facts()
        matched = [f for f in facts if f["fact_id"] == fid]
        assert len(matched) == 1
        assert matched[0]["source_chat_id"] == "chat-abc-123"

    def test_create_fact_without_source_chat_id(self, store):
        """source_chat_id defaults to None."""
        fid = store.create_fact(text="Global fact", category="general", importance=3)
        facts = store.list_facts()
        matched = [f for f in facts if f["fact_id"] == fid]
        assert len(matched) == 1
        assert matched[0]["source_chat_id"] is None

    def test_update_fact_source_chat_id(self, store):
        """update_fact() can set source_chat_id."""
        fid = store.create_fact(text="Some fact", category="general", importance=3)
        store.update_fact(fid, {"source_chat_id": "chat-updated"})
        facts = store.list_facts()
        matched = [f for f in facts if f["fact_id"] == fid]
        assert matched[0]["source_chat_id"] == "chat-updated"


# =============================================================================
# TIER-AWARE SCORING
# =============================================================================


class TestTierAwareScoring:
    """KnowledgeStore._score_item applies source_weight demotion."""

    def test_same_chat_weight_is_1(self):
        """Items from current chat get weight 1.0."""
        from services.knowledge_store import KnowledgeStore

        w = KnowledgeStore._get_source_weight("chat-a", "chat-a")
        assert w == 1.0

    def test_different_chat_weight_is_demoted(self):
        """Items from other chats get ARCHIVE_RETRIEVAL_WEIGHT."""
        from services.knowledge_store import KnowledgeStore
        from config import ARCHIVE_RETRIEVAL_WEIGHT

        w = KnowledgeStore._get_source_weight("chat-b", "chat-a")
        assert w == ARCHIVE_RETRIEVAL_WEIGHT

    def test_no_current_chat_weight_is_1(self):
        """If no current_chat_id, weight is 1.0 (no demotion)."""
        from services.knowledge_store import KnowledgeStore

        w = KnowledgeStore._get_source_weight("chat-b", None)
        assert w == 1.0

    def test_no_source_chat_weight_is_1(self):
        """Global facts (no source_chat_id) are unpenalised."""
        from services.knowledge_store import KnowledgeStore

        w = KnowledgeStore._get_source_weight(None, "chat-a")
        assert w == 1.0

    def test_score_item_applies_source_weight(self):
        """_score_item combined_score is reduced by source_weight."""
        from services.knowledge_store import KnowledgeStore, ItemType

        now_ms = int(time.time() * 1000)

        full = KnowledgeStore._score_item(
            item_id=1, text="test", category="general", importance=3,
            item_type=ItemType.FACT, similarity=0.9,
            created_at=now_ms, now_ms=now_ms, source_weight=1.0,
        )
        demoted = KnowledgeStore._score_item(
            item_id=1, text="test", category="general", importance=3,
            item_type=ItemType.FACT, similarity=0.9,
            created_at=now_ms, now_ms=now_ms, source_weight=0.6,
        )
        assert demoted.combined_score < full.combined_score
        assert abs(demoted.combined_score - full.combined_score * 0.6) < 0.01


# =============================================================================
# CROSS-CONVERSATION SUMMARIES (context_loader)
# =============================================================================


class TestCrossConversationSummaries:
    """load_context() populates cross_conversation_summaries."""

    def test_loads_summaries_from_other_chats(self, store):
        """Cross-conversation summaries from other chats are loaded."""
        # Create two chats with summaries
        cid1 = store.create_chat(title="Chat One")
        cid2 = store.create_chat(title="Chat Two")
        store.upsert_conversation_summary(
            chat_id=cid1, summary="Summary of chat one", last_message_id=10
        )
        store.upsert_conversation_summary(
            chat_id=cid2, summary="Summary of chat two", last_message_id=20
        )

        # Mock embeddings + knowledge search + tool detection
        mock_embedding = np.zeros(384, dtype=np.float32)
        mock_ks = MagicMock()
        mock_ks.search.return_value = []

        with patch("services.query_classifier.is_personal_disclosure", return_value=False), \
             patch("services.embeddings.embed_text", return_value=mock_embedding), \
             patch("services.tools.detect_tools_needed", return_value=[]), \
             patch("services.query_classifier.classify_temperature", return_value=0.7), \
             patch("services.tiny_classifier.detect_injection", return_value=(False, 0.0)):
            from services.context_loader import load_context

            ctx = load_context(
                store=store,
                knowledge_store=mock_ks,
                prompt="Hello",
                chat_id=cid1,
                principal_id="tiered-memory-test-principal",
            )

        # Should have summary from cid2 (not cid1 since that's current)
        assert len(ctx.cross_conversation_summaries) >= 1
        other_ids = [s["chat_id"] for s in ctx.cross_conversation_summaries]
        assert cid1 not in other_ids
        assert cid2 in other_ids

    def test_archived_chat_detected(self, store):
        """is_archived_chat is True when the current chat is archived."""
        cid = store.create_chat(title="Archived chat")
        store.update_chat(cid, archived=True)

        mock_ks = MagicMock()
        mock_ks.search.return_value = []

        with patch("services.query_classifier.is_personal_disclosure", return_value=False), \
             patch("services.embeddings.embed_text", return_value=np.zeros(384, dtype=np.float32)), \
             patch("services.tools.detect_tools_needed", return_value=[]), \
             patch("services.query_classifier.classify_temperature", return_value=0.7), \
             patch("services.tiny_classifier.detect_injection", return_value=(False, 0.0)):
            from services.context_loader import load_context

            ctx = load_context(
                store=store,
                knowledge_store=mock_ks,
                prompt="Hello",
                chat_id=cid,
                principal_id="tiered-memory-test-principal",
            )

        assert ctx.is_archived_chat is True
        assert ctx.ctx_budget > 0


# =============================================================================
# PROMPT ASSEMBLER — CROSS-CONVERSATION INJECTION
# =============================================================================


class TestPromptAssemblerCrossConv:
    """assemble() injects cross-conversation summaries between summary and history."""

    def test_cross_summaries_appear_in_messages(self):
        """Cross-conversation summaries are injected as a system message."""
        from services.prompt_assembler import PromptAssembler

        assembler = PromptAssembler()
        summaries = [
            {"chat_id": "chat-old", "title": "Old Chat", "summary": "User discussed Python."},
        ]

        messages = assembler.assemble(
            question="Hello",
            cross_conversation_summaries=summaries,
        )

        # Find the cross-conversation system message
        cross_msgs = [
            m for m in messages
            if m["role"] == "system" and "other conversations" in m["content"]
        ]
        assert len(cross_msgs) == 1
        assert "Old Chat" in cross_msgs[0]["content"]
        assert "User discussed Python" in cross_msgs[0]["content"]

    def test_no_cross_summaries_when_empty(self):
        """No cross-conversation message when list is empty."""
        from services.prompt_assembler import PromptAssembler

        assembler = PromptAssembler()
        messages = assembler.assemble(
            question="Hello",
            cross_conversation_summaries=[],
        )

        cross_msgs = [
            m for m in messages
            if m["role"] == "system" and "other conversations" in m.get("content", "")
        ]
        assert len(cross_msgs) == 0

    def test_cross_summaries_none_is_safe(self):
        """Passing None for cross_conversation_summaries doesn't crash."""
        from services.prompt_assembler import PromptAssembler

        assembler = PromptAssembler()
        messages = assembler.assemble(
            question="Hello",
            cross_conversation_summaries=None,
        )
        assert len(messages) >= 2  # system + user at minimum


# =============================================================================
# PURE HELPERS (microgpt composable-function principle)
# =============================================================================


class TestExtractSummary:
    """_extract_summary is a pure function — no I/O, no side-effects."""

    def test_dict_record(self):
        from services.context_loader import _extract_summary

        summaries = {"chat-1": {"summary": "Hello world", "last_message_id": 5}}
        text, last_id = _extract_summary(summaries, "chat-1")
        assert text == "Hello world"
        assert last_id == 5

    def test_string_record(self):
        from services.context_loader import _extract_summary

        summaries = {"chat-1": "Plain string summary"}
        text, last_id = _extract_summary(summaries, "chat-1")
        assert text == "Plain string summary"
        assert last_id == -1

    def test_missing_chat(self):
        from services.context_loader import _extract_summary

        text, last_id = _extract_summary({}, "chat-missing")
        assert text == ""
        assert last_id == -1

    def test_non_dict_input(self):
        from services.context_loader import _extract_summary

        text, last_id = _extract_summary(None, "chat-1")
        assert text == ""
        assert last_id == -1


class TestCollectCrossConversationSummaries:
    """_collect_cross_conversation_summaries is a pure function."""

    def test_excludes_current_chat(self):
        from services.context_loader import _collect_cross_conversation_summaries

        chats = [
            {"chatId": "chat-1", "title": "Current"},
            {"chatId": "chat-2", "title": "Other"},
        ]
        summaries_map = {
            "chat-1": {"summary": "Summary 1"},
            "chat-2": {"summary": "Summary 2"},
        }
        result = _collect_cross_conversation_summaries(
            chats, summaries_map, "chat-1", max_chats=3, char_budget=10000
        )
        assert len(result) == 1
        assert result[0]["chat_id"] == "chat-2"

    def test_respects_max_chats(self):
        from services.context_loader import _collect_cross_conversation_summaries

        chats = [{"chatId": f"c{i}", "title": f"Chat {i}"} for i in range(10)]
        summaries_map = {f"c{i}": {"summary": f"Summary {i}"} for i in range(10)}
        result = _collect_cross_conversation_summaries(
            chats, summaries_map, "c0", max_chats=2, char_budget=10000
        )
        assert len(result) == 2

    def test_skips_empty_summaries(self):
        from services.context_loader import _collect_cross_conversation_summaries

        chats = [
            {"chatId": "c1", "title": "Chat 1"},
            {"chatId": "c2", "title": "Chat 2"},
        ]
        summaries_map = {"c1": {"summary": ""}, "c2": {"summary": "Has content"}}
        result = _collect_cross_conversation_summaries(
            chats, summaries_map, "none", max_chats=5, char_budget=10000
        )
        assert len(result) == 1
        assert result[0]["chat_id"] == "c2"

    def test_respects_char_budget(self):
        from services.context_loader import _collect_cross_conversation_summaries

        chats = [{"chatId": "c1", "title": "C"}]
        summaries_map = {"c1": {"summary": "A" * 5000}}
        result = _collect_cross_conversation_summaries(
            chats, summaries_map, "other", max_chats=5, char_budget=100
        )
        assert len(result) == 1
        assert len(result[0]["summary"]) <= 100


# =============================================================================
# PROMPT ASSEMBLER — ctx_budget (archived chat hard cap)
# =============================================================================


class TestPromptAssemblerCtxBudget:
    """assemble() respects ctx_budget for archived chats."""

    def test_ctx_budget_zero_uses_default(self):
        """ctx_budget=0 means no capping — uses full total_budget."""
        from services.prompt_assembler import PromptAssembler

        assembler = PromptAssembler()
        m1 = assembler.assemble(question="Hi", ctx_budget=0)
        m2 = assembler.assemble(question="Hi")
        # Both should produce identical output
        assert len(m1) == len(m2)

    def test_ctx_budget_caps_conversation_history(self):
        """A very small ctx_budget limits how many history messages fit."""
        from services.prompt_assembler import PromptAssembler

        assembler = PromptAssembler()
        # Create lots of context messages
        history = [
            {"role": "user", "content": f"Message {i} " + "x" * 200, "message_id": i}
            for i in range(50)
        ]

        # With no cap — lots of messages should fit
        m_uncapped = assembler.assemble(
            question="What happened?",
            context_messages=history,
            ctx_budget=0,
        )
        # With a tight cap — fewer messages should fit
        m_capped = assembler.assemble(
            question="What happened?",
            context_messages=history,
            ctx_budget=2000,
        )
        # The capped version should have fewer messages
        assert len(m_capped) < len(m_uncapped)


# =============================================================================
# SINGLE SCORING FUNCTION INVARIANT
# =============================================================================


class TestSingleScoringFunction:
    """Every retrieval path must go through _score_item — no direct KnowledgeItem."""

    def test_score_item_returns_knowledge_item(self):
        """_score_item always returns a KnowledgeItem with combined_score."""
        from services.knowledge_store import KnowledgeStore, KnowledgeItem, ItemType

        now_ms = int(time.time() * 1000)
        item = KnowledgeStore._score_item(
            item_id=1, text="test", category="general", importance=3,
            item_type=ItemType.FACT, similarity=0.8,
            created_at=now_ms, now_ms=now_ms,
        )
        assert isinstance(item, KnowledgeItem)
        assert item.combined_score > 0

    def test_source_weight_zero_zeroes_score(self):
        """source_weight=0 produces combined_score=0 (extreme case)."""
        from services.knowledge_store import KnowledgeStore, ItemType

        now_ms = int(time.time() * 1000)
        item = KnowledgeStore._score_item(
            item_id=1, text="test", category="general", importance=3,
            item_type=ItemType.FACT, similarity=0.9,
            created_at=now_ms, now_ms=now_ms, source_weight=0.0,
        )
        assert item.combined_score == 0.0

    def test_message_type_scored_identically(self):
        """Messages and facts with same inputs produce same score."""
        from services.knowledge_store import KnowledgeStore, ItemType

        now_ms = int(time.time() * 1000)
        kwargs = dict(
            item_id=1, text="test", category="general", importance=3,
            similarity=0.7, created_at=now_ms, now_ms=now_ms, source_weight=1.0,
        )
        fact = KnowledgeStore._score_item(item_type=ItemType.FACT, **kwargs)
        msg = KnowledgeStore._score_item(item_type=ItemType.MESSAGE, **kwargs)
        assert fact.combined_score == msg.combined_score
