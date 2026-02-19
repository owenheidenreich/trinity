import json


class TestGraphExtractor:
    def test_extracts_user_triples(self):
        from services.graph_extractor import extract_graph_triples
        from unittest.mock import patch

        with patch("services.profile_extractor.extract_memory_candidates") as mock_extract:
            mock_extract.return_value = {
                "facts": [],
                "triples": [
                    {"subject": "user", "predicate": "works_at", "object": "Acme"},
                    {"subject": "user", "predicate": "lives_in", "object": "Austin"},
                ],
            }
            triples = extract_graph_triples("I work at Acme and I live in Austin", source="user")
        assert any(t["predicate"] == "works_at" and "Acme" in t["object"] for t in triples)
        assert any(t["predicate"] == "lives_in" and "Austin" in t["object"] for t in triples)

    def test_ignores_assistant_source(self):
        from services.graph_extractor import extract_graph_triples
        from unittest.mock import patch

        with patch("services.profile_extractor.extract_memory_candidates", return_value={"facts": [], "triples": []}):
            triples = extract_graph_triples("You work at Acme", source="assistant")
        assert triples == []


class TestGraphMemory:
    def test_ingest_and_retrieve_sidecar(self, tmp_path, monkeypatch):
        import services.graph_memory as gm

        monkeypatch.setattr(gm, "CHATS_DIR", str(tmp_path))
        graph = gm.GraphMemory("principal-123")

        added = graph.ingest_triples(
            [
                {
                    "subject": "user",
                    "predicate": "works_at",
                    "object": "Acme",
                    "object_kind": "company",
                    "confidence": 0.8,
                }
            ],
            source="user",
            chat_id="chat-1",
        )
        assert added == 1

        results = graph.retrieve_relevant("where do I work", limit=5)
        assert len(results) >= 1
        assert any(r.get("predicate") == "works_at" for r in results)

        stats = graph.get_stats()
        assert stats["triple_count"] >= 1
        assert stats["graph_path"].endswith("identity.kuzu")

    def test_sidecar_persists(self, tmp_path, monkeypatch):
        import services.graph_memory as gm

        monkeypatch.setattr(gm, "CHATS_DIR", str(tmp_path))
        graph = gm.GraphMemory("principal-456")
        graph.ingest_triples(
            [
                {
                    "subject": "user",
                    "predicate": "lives_in",
                    "object": "Miami",
                    "object_kind": "location",
                    "confidence": 0.8,
                }
            ]
        )

        sidecar = tmp_path / "principal-456" / "identity_triples.json"
        assert sidecar.exists()
        with open(sidecar, "r") as f:
            rows = json.load(f)
        assert len(rows) >= 1
