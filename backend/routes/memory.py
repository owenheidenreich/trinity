"""
Memory fact routes — CRUD for user memory facts.
"""

import time
from typing import Dict

from flask import Blueprint, jsonify, request

from icp_auth import require_auth
from middleware import storage_rate_limit
from services.state_store import get_state_store

memory_bp = Blueprint("memory", __name__)


def _memory_response(principal: str, include_embeddings: bool = False, raw: bool = False) -> Dict:
    store = get_state_store(principal)
    facts = store.list_facts(
        include_deleted=True,
        include_invalid=True,
        with_embeddings=include_embeddings,
    )
    summaries = store.list_conversation_summaries()
    payload = {
        "principalId": principal,
        "version": "3.0",
        "facts": facts,
        "conversation_summaries": summaries,
        "ingestion_jobs_recent": store.list_recent_ingestion_jobs(limit=30),
        "createdAt": None,
        "lastUpdated": int(time.time() * 1000),
    }
    if raw:
        payload["graph_triples"] = store.list_graph_triples(limit=200, include_invalid=True)
        payload["sync_checkpoint"] = store.get_sync_checkpoint()
    return payload


@memory_bp.route("/user/memory", methods=["GET"])
@require_auth
@storage_rate_limit
def get_user_memory():
    principal = request.principal
    include_embeddings = str(request.args.get("include_embeddings", "")).lower() in {
        "1",
        "true",
        "yes",
    }
    raw = str(request.args.get("raw", "")).lower() in {"1", "true", "yes"}
    return jsonify(_memory_response(principal, include_embeddings=include_embeddings, raw=raw))


@memory_bp.route("/user/memory", methods=["POST"])
@require_auth
@storage_rate_limit
def update_user_memory():
    return (
        jsonify(
            {
                "error": "Route retired",
                "message": "Use /user/memory/fact and /user/memory/fact/{fact_id} for memory writes.",
            }
        ),
        410,
    )


@memory_bp.route("/user/memory/fact", methods=["POST"])
@require_auth
@storage_rate_limit
def add_memory_fact():
    principal = request.principal
    data = request.json or {}
    text = (data.get("fact") or data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Fact text is required"}), 400

    category = str(data.get("category", "general")).strip().lower() or "general"
    try:
        importance = int(data.get("importance", 3))
    except (TypeError, ValueError):
        importance = 3
    importance = max(1, min(5, importance))

    embedding = None
    try:
        from services.embeddings import embed_text

        vec = embed_text(text)
        if vec is not None:
            embedding = vec.tolist()
    except Exception:
        embedding = None

    store = get_state_store(principal)
    fact_id = store.create_fact(
        text=text,
        category=category,
        importance=importance,
        source_message_id=data.get("source_message_id"),
        embedding=embedding,
    )

    fact = store.get_fact(fact_id, with_embedding=False)
    return jsonify({"success": True, "fact": fact, "fact_id": fact_id})


@memory_bp.route("/user/memory/fact/<int:fact_id>", methods=["PATCH", "PUT"])
@require_auth
@storage_rate_limit
def edit_memory_fact(fact_id):
    principal = request.principal
    data = request.json or {}

    updates: Dict = {}
    if "text" in data:
        text = str(data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "text cannot be empty"}), 400
        updates["text"] = text
        try:
            from services.embeddings import embed_text

            vec = embed_text(text)
            if vec is not None:
                updates["embedding"] = vec.tolist()
        except Exception:
            pass

    if "category" in data:
        updates["category"] = str(data.get("category") or "general").strip().lower() or "general"

    if "importance" in data:
        try:
            updates["importance"] = max(1, min(5, int(data.get("importance", 3))))
        except (TypeError, ValueError):
            updates["importance"] = 3

    if not updates:
        return jsonify({"error": "No updates provided"}), 400

    store = get_state_store(principal)
    if not store.update_fact(fact_id, updates):
        return jsonify({"error": "Fact not found"}), 404

    return jsonify({"success": True, "fact": store.get_fact(fact_id, with_embedding=False)})


@memory_bp.route("/user/memory/fact/<int:fact_id>", methods=["DELETE"])
@require_auth
@storage_rate_limit
def delete_memory_fact(fact_id):
    principal = request.principal
    store = get_state_store(principal)

    if not store.soft_delete_fact(fact_id):
        return jsonify({"error": "Fact not found"}), 404

    return jsonify({"success": True, "fact_id": fact_id, "deletedAt": int(time.time() * 1000)})
