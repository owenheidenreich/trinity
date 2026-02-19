"""
Trinity Integration Tests — Chat Lifecycle, Memory Pipeline & Cross-Account Isolation

Covers the 5 production bugs fixed in this session:
  1. "Recovered Chat" appearing for new accounts  (cross-account leak / stale metadata)
  2. Slow replies due to loose tool detection       (statements routed to ReAct)
  3. Raw tool XML leaking into responses            (bare tool name parsing)
  4. Tool hallucination for unknown facts            (memory recall on statements)
  5. Cross-account chat leak on logout/login         (metadata isolation)

Created: February 15, 2026
"""

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Callable, Dict
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ============================================================================
# HELPERS
# ============================================================================

PRINCIPAL_A = "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa"
PRINCIPAL_B = "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb"


def _make_embedding(seed: int = 42, dim: int = 384):
    """Deterministic fake embedding for testing."""
    rng = np.random.RandomState(seed)
    vec = rng.randn(dim).astype(np.float32)
    return vec / np.linalg.norm(vec)


def _auth_headers(principal: str):
    """Generate fake auth headers for an already-mocked auth layer."""
    return {
        "ICP-Principal": principal,
        "ICP-Signature": "deadbeef" * 16,
        "ICP-PublicKey": "aabb" * 16,
        "ICP-Timestamp": str(int(time.time() * 1000)),
        "ICP-Nonce": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def app():
    """Flask app with test config and isolated temp storage."""
    from inference_server import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["DEBUG"] = False
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _clean_storage(tmp_path, monkeypatch):
    """Point CHATS_DIR to an isolated tmp dir and clean up after each test."""
    test_chats = str(tmp_path / "chats")
    os.makedirs(test_chats, exist_ok=True)
    monkeypatch.setattr("config.CHATS_DIR", test_chats)
    # Also patch storage module's reference
    monkeypatch.setattr("storage.CHATS_DIR", test_chats)
    from middleware.rate_limit import request_counts, storage_request_counts
    request_counts.clear()
    storage_request_counts.clear()
    yield
    request_counts.clear()
    storage_request_counts.clear()
    shutil.rmtree(test_chats, ignore_errors=True)


@pytest.fixture
def mock_ipfs():
    """Legacy fixture retained only for skipped tests in this module."""
    yield {"upload": None, "list": None, "store": {}}


@pytest.fixture
def mock_auth():
    """Mock ICP signature verification to always succeed (routes are already registered)."""
    with patch("icp_auth.verify_icp_signature") as mock_verify:
        mock_verify.return_value = (True, None)
        yield mock_verify


@pytest.fixture
def mock_embeddings():
    """Mock embeddings so tests don't need Ollama running."""
    call_count = {"n": 0}

    def fake_embed(text):
        call_count["n"] += 1
        return _make_embedding(seed=hash(text) % 2**31)

    def fake_cosine(a, b):
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    with patch("services.memory_tools._get_embeddings", return_value=(fake_embed, fake_cosine)):
        yield {"embed": fake_embed, "cosine": fake_cosine, "call_count": call_count}


@pytest.fixture
def mock_storage_no_encrypt(tmp_path):
    """Bypass encryption for load/save user memory during tests."""
    chats_dir = str(tmp_path / "chats")
    os.makedirs(chats_dir, exist_ok=True)

    def plain_load(principal_id):
        pdir = Path(chats_dir) / principal_id.replace("..", "").replace("/", "")
        path = pdir / "user_memory.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return {
            "principalId": principal_id,
            "version": "2.0",
            "facts": [],
            "profile": {},
            "createdAt": int(time.time() * 1000),
            "lastUpdated": int(time.time() * 1000),
        }

    def plain_save(principal_id, memory):
        memory["lastUpdated"] = int(time.time() * 1000)
        pdir = Path(chats_dir) / principal_id.replace("..", "").replace("/", "")
        pdir.mkdir(parents=True, exist_ok=True)
        with open(pdir / "user_memory.json", "w") as f:
            json.dump(memory, f)

    with patch("services.memory_tools._get_storage", return_value=(plain_load, plain_save)):
        yield


# ============================================================================
# 1. TOOL DETECTION — Bug #2 & #4 (slow replies, tool hallucination)
# ============================================================================


class TestToolDetection:
    """Verify detect_tools_needed only triggers recall on questions, not statements."""

    def test_statement_my_name_no_recall(self):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("my name is owen")
        assert "recall_memory" not in tools

    def test_statement_i_work_at_no_recall(self):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("I work at Google")
        assert "recall_memory" not in tools

    def test_statement_i_prefer_python_no_recall(self):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("I prefer Python over JavaScript")
        assert "recall_memory" not in tools

    def test_question_what_is_my_name_triggers_recall(self):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("what is my name?")
        assert "recall_memory" in tools

    def test_question_whats_my_job_triggers_recall(self):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("what's my job?")
        assert "recall_memory" in tools

    def test_question_do_you_remember_triggers_recall(self):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("do you remember my preferences?")
        assert "recall_memory" in tools

    def test_question_what_do_you_know_triggers_recall(self):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("what do you know about me")
        assert "recall_memory" in tools

    def test_statement_i_live_in_no_recall(self):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("I live in Portland")
        assert "recall_memory" not in tools

    def test_greeting_hello_no_tools(self):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("hello there")
        assert tools == []

    def test_simple_question_no_tools(self):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("how does photosynthesis work?")
        assert tools == []

    def test_math_triggers_calculator(self):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("calculate 25 * 38")
        assert "calculator" in tools

    def test_forget_triggers_forget_memory(self):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("forget that I like pizza")
        assert "forget_memory" in tools

    def test_tell_me_about_me_triggers_recall(self):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("tell me about me")
        assert "recall_memory" in tools

    def test_write_code_file_request_without_path_no_filesystem_tools(self):
        """Code-writing prompts should stay inline unless path/workspace intent is explicit."""
        from services.tools import detect_tools_needed

        tools = detect_tools_needed(
            'can you write a javascript file that outputs the word "yo" 10000 times?'
        )
        assert "read_file" not in tools
        assert "code_display" not in tools
        assert "document_search" not in tools

    def test_write_file_with_explicit_path_triggers_filesystem_tools(self):
        """Explicit file path intent should still enable filesystem routing."""
        from services.tools import detect_tools_needed

        tools = detect_tools_needed("create file scripts/yo.js and write code there")
        assert "read_file" in tools

    def test_debug_code_request_triggers_code_display(self):
        """Debug/fix requests should still use code tool mode when enabled."""
        from services.tools import detect_tools_needed
        from unittest.mock import patch

        with patch("services.tools.CODE_EXECUTION_ENABLED", True):
            tools = detect_tools_needed("debug this javascript code and run it")
            assert "code_display" in tools


# ============================================================================
# 2. TOOL CALL PARSING — Bug #3 (raw tool XML in responses)
# ============================================================================


class TestToolCallParsing:
    """Verify both well-formed and bare tool names are parsed correctly."""

    def test_standard_xml_format(self):
        from services.tools import parse_tool_calls
        text = '<tool_call name="recall_memory"><query>user name</query></tool_call>'
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "recall_memory"
        assert calls[0].params["query"] == "user name"

    def test_bare_tool_name_fallback(self):
        from services.tools import parse_tool_calls
        text = 'recall_memory <query>what is my name</query>'
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "recall_memory"
        assert calls[0].params["query"] == "what is my name"

    def test_bare_save_memory(self):
        from services.tools import parse_tool_calls
        text = 'save_memory <fact>User likes cats</fact><category>preferences</category>'
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "save_memory"
        assert calls[0].params["fact"] == "User likes cats"

    def test_no_tool_call_returns_empty(self):
        from services.tools import parse_tool_calls
        text = "Hello! I'd be happy to help you with that."
        calls = parse_tool_calls(text)
        assert calls == []

    def test_multiple_standard_tool_calls(self):
        from services.tools import parse_tool_calls
        text = (
            '<tool_call name="recall_memory"><query>name</query></tool_call>\n'
            'Based on that, <tool_call name="web_search"><query>Portland weather</query></tool_call>'
        )
        calls = parse_tool_calls(text)
        assert len(calls) == 2

    def test_tool_call_without_closing_tag(self):
        from services.tools import parse_tool_calls
        text = '<tool_call name="calculator"><expression>2+2</expression>'
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].params["expression"] == "2+2"

    def test_bare_tool_with_surrounding_text(self):
        from services.tools import parse_tool_calls
        text = "Let me check your memory.\nrecall_memory <query>name</query>"
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "recall_memory"


# ============================================================================
# 3. PROFILE EXTRACTION — Memory pipeline correctness
# ============================================================================


class TestProfileExtraction:
    """Verify LLM-backed profile extractor integration."""

    def test_extract_name(self):
        from services.profile_extractor import extract_profile_facts
        with patch("services.profile_extractor._call_extraction_model") as mock_call:
            mock_call.return_value = {
                "facts": [{"fact": "User's name is Owen", "category": "identity", "importance": 5}],
                "triples": [],
            }
            facts = extract_profile_facts("my name is Owen")
        assert len(facts) >= 1
        assert any("Owen" in f["fact"] for f in facts)

    def test_extract_location(self):
        from services.profile_extractor import extract_profile_facts
        with patch("services.profile_extractor._call_extraction_model") as mock_call:
            mock_call.return_value = {
                "facts": [{"fact": "User lives in Portland", "category": "identity", "importance": 4}],
                "triples": [],
            }
            facts = extract_profile_facts("I live in Portland")
        assert len(facts) >= 1
        assert any("Portland" in f["fact"] for f in facts)

    def test_extract_work(self):
        from services.profile_extractor import extract_profile_facts
        with patch("services.profile_extractor._call_extraction_model") as mock_call:
            mock_call.return_value = {
                "facts": [{"fact": "User works at Google", "category": "work", "importance": 4}],
                "triples": [],
            }
            facts = extract_profile_facts("I work at Google")
        assert len(facts) >= 1
        assert any("Google" in f["fact"] for f in facts)

    def test_no_extraction_from_question(self):
        from services.profile_extractor import extract_profile_facts
        with patch("services.profile_extractor._call_extraction_model", return_value={"facts": [], "triples": []}):
            facts = extract_profile_facts("what is my name?")
        assert facts == []

    def test_negative_pattern_not_sure(self):
        from services.profile_extractor import extract_profile_facts
        with patch("services.profile_extractor._call_extraction_model", return_value={"facts": [], "triples": []}):
            facts = extract_profile_facts("I'm not sure about that")
        assert facts == []

    def test_negative_pattern_happy_to_help(self):
        from services.profile_extractor import extract_profile_facts
        with patch("services.profile_extractor._call_extraction_model", return_value={"facts": [], "triples": []}):
            facts = extract_profile_facts("I'm happy to help you")
        assert facts == []

    def test_assistant_pattern_your_name(self):
        from services.profile_extractor import extract_profile_facts
        with patch("services.profile_extractor._call_extraction_model") as mock_call:
            mock_call.return_value = {
                "facts": [{"fact": "User's name is Owen", "category": "identity", "importance": 5}],
                "triples": [],
            }
            facts = extract_profile_facts("your name is Owen", source="assistant")
        assert len(facts) >= 1
        assert any("Owen" in f["fact"] for f in facts)

    def test_extract_interest(self):
        from services.profile_extractor import extract_profile_facts
        with patch("services.profile_extractor._call_extraction_model") as mock_call:
            mock_call.return_value = {
                "facts": [
                    {"fact": "User is interested in machine learning", "category": "interests", "importance": 3}
                ],
                "triples": [],
            }
            facts = extract_profile_facts("I'm interested in machine learning")
        assert len(facts) >= 1
        assert any("machine learning" in f["fact"].lower() for f in facts)


# ============================================================================
# 4. MEMORY SAVE & RECALL — End-to-end with mock embeddings
# ============================================================================


class TestMemorySaveRecall:
    """Verify save_memory handles dedup/merge and recall returns ranked results."""

    def test_save_and_recall_basic(self, mock_embeddings, mock_storage_no_encrypt):
        from services.memory_tools import tool_recall_memory, tool_save_memory

        # Save a fact
        ok, msg = tool_save_memory(
            {"fact": "User's name is Owen", "category": "identity", "importance": "5"},
            PRINCIPAL_A,
        )
        assert ok
        assert "Saved:" in msg or "Updated" in msg

        # Recall it — the mock embedding is deterministic by text hash,
        # so "Owen" in query should have SOME similarity
        ok2, msg2 = tool_recall_memory({"query": "what is the user's name"}, PRINCIPAL_A)
        assert ok2
        assert "Owen" in msg2

    def test_duplicate_fact_skipped(self, mock_embeddings, mock_storage_no_encrypt):
        from services.memory_tools import tool_save_memory

        # Save same fact twice
        tool_save_memory(
            {"fact": "User likes cats", "category": "preferences", "importance": "3"},
            PRINCIPAL_A,
        )
        ok, msg = tool_save_memory(
            {"fact": "User likes cats", "category": "preferences", "importance": "3"},
            PRINCIPAL_A,
        )
        # Should be skipped as duplicate
        assert ok
        assert "similar" in msg.lower() or "already" in msg.lower()

    def test_empty_memory_recall(self, mock_embeddings, mock_storage_no_encrypt):
        from services.memory_tools import tool_recall_memory

        ok, msg = tool_recall_memory({"query": "anything"}, PRINCIPAL_A)
        assert ok
        assert "no memories" in msg.lower()

    def test_save_no_fact_fails(self, mock_embeddings, mock_storage_no_encrypt):
        from services.memory_tools import tool_save_memory

        ok, msg = tool_save_memory({"fact": "", "category": "general"}, PRINCIPAL_A)
        assert not ok
        assert "no fact" in msg.lower()


# ============================================================================
# 5. CROSS-ACCOUNT ISOLATION — Bug #5
# ============================================================================


class TestCrossAccountIsolation:
    """Verify that memory operations for one user don't leak to another."""

    def test_memory_isolation(self, mock_embeddings, mock_storage_no_encrypt):
        from services.memory_tools import tool_recall_memory, tool_save_memory

        # Save facts for user A
        tool_save_memory(
            {"fact": "User is from New York", "category": "identity", "importance": "4"},
            PRINCIPAL_A,
        )

        # User B should have no memories
        ok, msg = tool_recall_memory({"query": "where is the user from"}, PRINCIPAL_B)
        assert ok
        assert "no memories" in msg.lower()

    def test_metadata_isolation(self, tmp_path, monkeypatch):
        """Each principal gets its own metadata file."""
        from storage import load_metadata, save_metadata

        # Patch passphrase to avoid encryption
        with patch("storage.get_session_passphrase", return_value=None), \
             patch("storage.EncryptionUtils") as mock_enc:
            mock_enc.encrypt_chat.side_effect = lambda d, p: d
            mock_enc.decrypt_auto.side_effect = lambda d, **kw: d

            meta_a = load_metadata(PRINCIPAL_A)
            meta_a["chats"].append({"chatId": "chat-1", "title": "A's Chat"})
            save_metadata(PRINCIPAL_A, meta_a)

            meta_b = load_metadata(PRINCIPAL_B)
            assert len(meta_b["chats"]) == 0, "User B should not see User A's chats"


# ============================================================================
# 6. CHAT AUTOSAVE LIFECYCLE — Bug #1 (Recovered Chat for new accounts)
# ============================================================================


@pytest.mark.skip(reason="Legacy autosave lifecycle retired in canonical-db mode")
class TestChatAutosaveLifecycle:
    """Test the autosave → list → load round-trip."""

    def test_autosave_stores_title(self, client, mock_ipfs, mock_auth):
        """Autosave should store the title from the request body."""
        headers = _auth_headers(PRINCIPAL_A)
        with patch("routes.chat.save_metadata"), \
             patch("routes.chat.load_metadata", return_value={"chats": [], "principalId": PRINCIPAL_A}):
            resp = client.post("/chat/autosave", json={
                "chatId": "chat-001",
                "title": "My First Chat",
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "hi there"},
                ],
                "metadata": {"title": "My First Chat", "updatedAt": int(time.time() * 1000)},
            }, headers=headers)
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["chatId"] == "chat-001"

    def test_autosave_missing_chatid_returns_400(self, client, mock_auth):
        """Autosave without chatId should fail."""
        headers = _auth_headers(PRINCIPAL_A)
        resp = client.post("/chat/autosave", json={
            "messages": [{"role": "user", "content": "hello"}],
        }, headers=headers)
        assert resp.status_code == 400

    def test_list_empty_for_new_user(self, client, mock_ipfs, mock_auth):
        """A brand-new user should see zero chats."""
        headers = _auth_headers(PRINCIPAL_A)
        resp = client.get("/chat/list", headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 0
        assert data["chats"] == []

    def test_autosave_queues_checkpoint_sync(self, client, mock_auth):
        """Autosave should queue a chat checkpoint instead of uploading in-request."""
        headers = _auth_headers(PRINCIPAL_A)

        with patch("routes.chat._ensure_restored"), \
             patch("routes.chat._get_chat_manifest", return_value={"chats": []}), \
             patch("routes.chat.load_metadata", return_value={"chats": [], "principalId": PRINCIPAL_A}), \
             patch("routes.chat.save_metadata"), \
             patch("routes.chat.update_chat_in_manifest"), \
             patch("routes.chat.queue_chat_sync") as mock_queue:
            resp = client.post("/chat/autosave", json={
                "chatId": "chat-queued",
                "title": "Queued Chat",
                "messages": [{"role": "user", "content": "hello"}],
                "metadata": {"title": "Queued Chat"},
            }, headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["syncQueued"] is True
        mock_queue.assert_called_once()

    def test_get_chat_uses_local_snapshot_before_ipfs(self, client, mock_ipfs, mock_auth):
        """After autosave, GET /chat/<id> should return local snapshot without IPFS download."""
        headers = _auth_headers(PRINCIPAL_A)
        chat_id = "chat-local-cache"

        with patch("routes.chat._ensure_restored"), \
             patch("routes.chat._get_chat_manifest", return_value={"chats": []}), \
             patch("routes.chat.load_metadata", return_value={"chats": [], "principalId": PRINCIPAL_A}), \
             patch("routes.chat.save_metadata"), \
             patch("routes.chat.update_chat_in_manifest"), \
             patch("routes.chat.queue_chat_sync"):
            save_resp = client.post("/chat/autosave", json={
                "chatId": chat_id,
                "title": "Local Cache Chat",
                "messages": [{"role": "user", "content": "hello from local cache"}],
                "metadata": {"title": "Local Cache Chat"},
            }, headers=headers)
            assert save_resp.status_code == 200

        with patch("routes.chat.http_session.get") as mock_gateway:
            load_resp = client.get(f"/chat/{chat_id}", headers=headers)

        assert load_resp.status_code == 200
        loaded = load_resp.get_json()
        assert loaded["chatId"] == chat_id
        assert loaded["messages"][0]["content"] == "hello from local cache"
        mock_gateway.assert_not_called()

    def test_archive_flushes_pending_checkpoint_when_cid_missing(self, client, mock_auth):
        """Archiving should force-flush queued checkpoint if manifest chat has no CID yet."""
        headers = _auth_headers(PRINCIPAL_A)
        chat_id = "chat-archive-queued"

        manifest_without_cid = {
            "chats": [{"chatId": chat_id, "title": "Archive Me", "cid": None, "archived": False}]
        }
        manifest_with_cid = {
            "chats": [{"chatId": chat_id, "title": "Archive Me", "cid": "cid-queued", "archived": False}]
        }

        with patch("routes.chat._ensure_restored"), \
             patch("routes.chat._get_chat_manifest", side_effect=[manifest_without_cid, manifest_with_cid]), \
             patch("routes.chat.flush_chat_sync_now", return_value="cid-queued") as mock_flush, \
             patch("routes.chat.save_manifest"), \
             patch("routes.chat.sync_manifest_to_ipfs"), \
             patch("routes.chat.load_metadata", return_value={"chats": [{"chatId": chat_id}]}), \
             patch("routes.chat.save_metadata"):
            resp = client.post(f"/chat/{chat_id}/archive", headers=headers)

        assert resp.status_code == 200
        mock_flush.assert_called_once_with(PRINCIPAL_A, chat_id)


# ============================================================================
# 7. CHAT LIST ISOLATION — Ensures one user's chats don't appear for another
# ============================================================================


class TestChatListIsolation:
    """Verify IPFS filtering by principal prefix."""

    def test_user_b_cannot_see_user_a_chats(self, client, mock_auth):
        """After user A creates a chat, user B's list should still be empty."""
        headers_a = _auth_headers(PRINCIPAL_A)
        start_resp = client.post(
            "/chat/start",
            json={"chat_id": "chat-a1", "title": "A's Chat"},
            headers=headers_a,
        )
        assert start_resp.status_code == 200

        # User B lists chats — should see 0
        headers_b = _auth_headers(PRINCIPAL_B)
        resp = client.get("/chat/list", headers=headers_b)
        data = resp.get_json()
        assert data["count"] == 0


# ============================================================================
# 8. FULL SEND → MEMORY PIPELINE — profile extraction after generate
# ============================================================================


class TestSendToMemoryPipeline:
    """Verify that profile extraction correctly feeds into memory save."""

    def test_extract_then_save(self, mock_embeddings, mock_storage_no_encrypt):
        """Simulate what auto_extract_and_save does after a user message."""
        from services.profile_extractor import auto_extract_and_save

        with patch("services.profile_extractor._call_extraction_model") as mock_call:
            mock_call.return_value = {
                "facts": [{"fact": "User's name is Owen", "category": "identity", "importance": 5}],
                "triples": [],
            }
            saved_count = auto_extract_and_save("my name is Owen", PRINCIPAL_A, source="user")
        assert saved_count >= 1

        # Verify we can recall it
        from services.memory_tools import tool_recall_memory
        ok, msg = tool_recall_memory({"query": "name"}, PRINCIPAL_A)
        assert ok
        assert "Owen" in msg

    def test_extract_from_assistant_echoes(self, mock_embeddings, mock_storage_no_encrypt):
        """Assistant saying 'your name is Owen' should also be captured."""
        from services.profile_extractor import auto_extract_and_save

        with patch("services.profile_extractor._call_extraction_model") as mock_call:
            mock_call.return_value = {
                "facts": [{"fact": "User's name is Owen", "category": "identity", "importance": 5}],
                "triples": [],
            }
            saved = auto_extract_and_save("your name is Owen", PRINCIPAL_A, source="assistant")
        assert saved >= 1

    def test_no_extraction_from_code_help(self, mock_embeddings, mock_storage_no_encrypt):
        """Questions or code help should NOT trigger extraction."""
        from services.profile_extractor import auto_extract_and_save

        with patch("services.profile_extractor._call_extraction_model", return_value={"facts": [], "triples": []}):
            saved = auto_extract_and_save("Can you help me fix this Python bug?", PRINCIPAL_A)
        assert saved == 0


# ============================================================================
# 9. MANIFEST-FIRST CHAT LISTING
# ============================================================================


@pytest.mark.skip(reason="Manifest listing tests target retired manifest-first flow")
class TestManifestChatListing:
    """Chat list should come from manifest, not upload fallback scans."""

    def test_manifest_chats_sorted_by_last_updated(self, client, mock_auth):
        fake_manifest = {
            "chats": [
                {"chatId": "chat-a", "title": "A", "cid": "cid-a", "lastUpdated": 1000, "archived": False},
                {"chatId": "chat-b", "title": "B", "cid": "cid-b", "lastUpdated": 2000, "archived": True},
            ]
        }

        headers = _auth_headers(PRINCIPAL_A)
        with patch("routes.chat.ensure_user_data_restored", return_value=True), \
             patch("routes.chat.load_manifest", return_value=fake_manifest):
            resp = client.get("/chat/list", headers=headers)
            data = resp.get_json()

        assert data["count"] == 2
        assert data["chats"][0]["chatId"] == "chat-b"
        assert data["chats"][0]["isArchived"] is True
        assert data["chats"][1]["chatId"] == "chat-a"

    def test_empty_manifest_returns_empty_sidebar(self, client, mock_auth):
        headers = _auth_headers(PRINCIPAL_A)
        with patch("routes.chat.ensure_user_data_restored", return_value=True), \
             patch("routes.chat.load_manifest", return_value={"chats": []}):
            resp = client.get("/chat/list", headers=headers)
            data = resp.get_json()

        assert data["count"] == 0
        assert data["chats"] == []


# ============================================================================
# 10. CONTRADICTION DETECTION — Memory update correctness
# ============================================================================


class TestContradictionDetection:
    """Verify the heuristic contradiction detector in memory_tools."""

    def test_location_change_is_contradiction(self):
        from services.memory_tools import _detect_contradiction
        assert _detect_contradiction("User lives in NYC", "User lives in LA") is True

    def test_refinement_is_not_contradiction(self):
        from services.memory_tools import _detect_contradiction
        assert _detect_contradiction("User is a developer", "User is a senior developer") is False

    def test_same_text_is_not_contradiction(self):
        from services.memory_tools import _detect_contradiction
        assert _detect_contradiction("User lives in NYC", "User lives in NYC") is False

    def test_name_change_is_contradiction(self):
        from services.memory_tools import _detect_contradiction
        assert _detect_contradiction("User's name is John", "User's name is James") is True

    def test_employer_change_is_contradiction(self):
        from services.memory_tools import _detect_contradiction
        assert _detect_contradiction("User works at Google", "User works at Meta") is True


# ============================================================================
# 11. GENERATE ENDPOINT — SSE streaming with optional auth
# ============================================================================


class TestGenerateEndpoint:
    """Test the /generate/agent endpoint structure."""

    def test_missing_prompt_returns_error(self, client):
        """Generate without a prompt should fail."""
        resp = client.post("/generate/agent", json={})
        # Could be 400 or 500 depending on implementation
        assert resp.status_code in (400, 500) or b"error" in resp.data.lower()

    def test_health_endpoint(self, client):
        """Sanity check: /health should return 200 (or 503 if Ollama not running)."""
        resp = client.get("/health")
        assert resp.status_code in (200, 503)

    def test_new_chat_turn_still_queries_semantic_memory(self, client, app, mock_auth):
        """First turn of a new chat should still query semantic memory across chats."""
        app.config["V4_FEATURES_AVAILABLE"] = True

        process_events = iter([
            {"token": "ok"},
            {"done": True, "response": {"answer": "ok"}, "done_reason": "stop"},
        ])

        headers = _auth_headers(PRINCIPAL_A)
        with patch("routes.generate.get_provider", return_value=MagicMock()), \
             patch("services.agent.AgentPipeline.process_streaming", return_value=process_events), \
             patch("services.memory.build_enhanced_context", return_value=([], [])) as mock_build_context, \
             patch("storage.load_user_memory", return_value={"facts": []}):
            resp = client.post(
                "/generate/agent",
                json={
                    "prompt": "What were we discussing about my startup?",
                    "chat_id": "chat-new-turn",
                },
                headers=headers,
            )
            assert resp.status_code == 200
            _ = resp.get_data(as_text=True)

        mock_build_context.assert_called_once()

@pytest.mark.skip(reason="Legacy message index resolver removed in canonical message-id flow")
class TestMessageIndexResolution:
    """Ensure semantic index fallback never overwrites index 0 repeatedly."""

    def test_uses_provided_index(self):
        from routes.generate import _resolve_message_index

        assert _resolve_message_index("principal", "chat-1", 12) == 12
        assert _resolve_message_index("principal", "chat-1", "7") == 7

    def test_falls_back_to_vector_store_when_missing(self):
        from routes.generate import _resolve_message_index

        mock_store = MagicMock()
        mock_store.get_next_message_index.return_value = 21

        with patch("services.vector_store.get_vector_store", return_value=mock_store):
            assert _resolve_message_index("principal", "chat-1", None) == 21

    def test_fallback_errors_return_zero(self):
        from routes.generate import _resolve_message_index

        with patch("services.vector_store.get_vector_store", side_effect=Exception("db unavailable")):
            assert _resolve_message_index("principal", "chat-1", None) == 0
