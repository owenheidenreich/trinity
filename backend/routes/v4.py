"""
V4 Blueprint — /v4/*
====================
V4.0 Intelligence endpoints: vector indexing, semantic search, tool execution.
All endpoints gated by V4_FEATURES_AVAILABLE flag on current_app.config.
"""

import time

from flask import Blueprint, current_app, jsonify, request

from config import PRINCIPAL_DISPLAY_LENGTH, logger
from icp_auth import require_auth
from middleware import storage_rate_limit

from routes.shared import MAX_DOCUMENT_SIZE

v4_bp = Blueprint("v4", __name__)


@v4_bp.route("/v4/vector/index", methods=["POST"])
@require_auth
@storage_rate_limit
def index_chat_history():
    """Bulk index chat history into the user's vector database for semantic retrieval."""
    if not current_app.config.get("V4_FEATURES_AVAILABLE"):
        return jsonify({"error": "V4.0 features not available", "v4_available": False}), 503

    try:
        principal = request.principal
        data = request.json or {}
        messages = data.get("messages", [])
        chat_id = data.get("chatId", "default")

        if not messages:
            return jsonify({"error": "No messages provided"}), 400

        from services.vector_store import get_user_vector_store
        vector_store = get_user_vector_store(principal)

        indexed_count = 0
        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "user")
            timestamp = msg.get("timestamp", time.time())

            if content and len(content) > 10:
                vector_store.add_message_embedding(
                    content=content, role=role, timestamp=timestamp, chat_id=chat_id
                )
                indexed_count += 1

        total_embeddings = vector_store.get_total_embeddings()

        logger.info(
            f"📊 Indexed {indexed_count} messages for {principal[:PRINCIPAL_DISPLAY_LENGTH]}... (total: {total_embeddings})"
        )

        return jsonify(
            {"success": True, "indexed": indexed_count, "vectorDbSize": total_embeddings}
        )

    except Exception as e:
        logger.error(f"❌ Vector indexing error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@v4_bp.route("/v4/vector/document", methods=["POST"])
@require_auth
@storage_rate_limit
def embed_document():
    """Embed and store document chunks for RAG retrieval."""
    if not current_app.config.get("V4_FEATURES_AVAILABLE"):
        return jsonify({"error": "V4.0 features not available", "v4_available": False}), 503

    try:
        principal = request.principal
        data = request.json or {}
        content = data.get("content", "")
        filename = data.get("filename", "document.txt")

        if not content:
            return jsonify({"error": "No content provided"}), 400

        if len(content) > MAX_DOCUMENT_SIZE:
            return jsonify({"error": f"Document too large (max {MAX_DOCUMENT_SIZE} bytes)"}), 400

        from config import RAG_CHUNK_OVERLAP, RAG_CHUNK_SIZE
        from services.embeddings import chunk_text
        from services.vector_store import get_user_vector_store

        chunks = chunk_text(content, RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP)
        vector_store = get_user_vector_store(principal)

        document_id = f"{filename}_{int(time.time())}"

        vector_store.add_document_chunks(chunks=chunks, document_id=document_id, filename=filename)

        logger.info(
            f'📄 Embedded document "{filename}" ({len(chunks)} chunks) for {principal[:PRINCIPAL_DISPLAY_LENGTH]}...'
        )

        return jsonify(
            {
                "success": True,
                "chunks": len(chunks),
                "documentId": document_id,
                "filename": filename,
            }
        )

    except Exception as e:
        logger.error(f"❌ Document embedding error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@v4_bp.route("/v4/vector/search", methods=["POST"])
@require_auth
def v4_semantic_search():
    """Search the user's vector database for semantically similar content."""
    if not current_app.config.get("V4_FEATURES_AVAILABLE"):
        return jsonify({"error": "V4.0 features not available", "v4_available": False}), 503

    try:
        principal = request.principal
        data = request.json or {}
        query = data.get("query", "").strip()
        top_k = min(int(data.get("top_k", 5)), 20)
        search_type = data.get("search_type", "all")

        if not query:
            return jsonify({"error": "No query provided"}), 400

        from services.vector_store import get_user_vector_store
        vector_store = get_user_vector_store(principal)
        results = []

        if search_type in ["all", "messages"]:
            msg_results = vector_store.search_messages(query, top_k=top_k)
            for r in msg_results:
                results.append(
                    {
                        "content": r["content"],
                        "score": r["score"],
                        "type": "message",
                        "metadata": {"role": r.get("role"), "timestamp": r.get("timestamp")},
                    }
                )

        if search_type in ["all", "documents"]:
            doc_results = vector_store.search_documents(query, top_k=top_k)
            for r in doc_results:
                results.append(
                    {
                        "content": r["content"],
                        "score": r["score"],
                        "type": "document",
                        "metadata": {
                            "filename": r.get("filename"),
                            "document_id": r.get("document_id"),
                        },
                    }
                )

        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:top_k]

        logger.info(
            f'🔍 Semantic search for {principal[:PRINCIPAL_DISPLAY_LENGTH]}...: "{query[:50]}" → {len(results)} results'
        )

        return jsonify({"results": results, "query": query})

    except Exception as e:
        logger.error(f"❌ Semantic search error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@v4_bp.route("/v4/vector/sync", methods=["POST"])
@require_auth
@storage_rate_limit
def sync_vector_db():
    """Sync user's vector database to/from IPFS."""
    if not current_app.config.get("V4_FEATURES_AVAILABLE"):
        return jsonify({"error": "V4.0 features not available", "v4_available": False}), 503

    try:
        principal = request.principal
        data = request.json or {}
        action = data.get("action", "upload")

        if action == "upload":
            from lighthouse import upload_vector_db
            cid = upload_vector_db(principal)
            if cid:
                logger.info(f"☁️ Uploaded vector DB for {principal[:PRINCIPAL_DISPLAY_LENGTH]}... → {cid[:16]}")
                return jsonify({"success": True, "cid": cid})
            else:
                return jsonify({"success": False, "error": "Upload failed"}), 500

        elif action == "download":
            from lighthouse import sync_vector_db_on_login
            success, count = sync_vector_db_on_login(principal)
            if success:
                logger.info(f"☁️ Downloaded vector DB for {principal[:PRINCIPAL_DISPLAY_LENGTH]}... ({count} embeddings)")
                return jsonify({"success": True, "embeddings": count})
            else:
                return jsonify({"success": False, "error": "Download failed or no data"}), 404

        else:
            return jsonify({"error": 'Invalid action. Use "upload" or "download"'}), 400

    except Exception as e:
        logger.error(f"❌ Vector DB sync error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@v4_bp.route("/v4/tools/execute", methods=["POST"])
@require_auth
def execute_tool_endpoint():
    """Execute a tool and return the result."""
    if not current_app.config.get("V4_FEATURES_AVAILABLE"):
        return jsonify({"error": "V4.0 features not available", "v4_available": False}), 503

    try:
        principal = request.principal
        data = request.json or {}
        tool_name = data.get("tool", "")
        tool_args = data.get("args", {})

        if not tool_name:
            return jsonify({"error": "No tool specified"}), 400

        from services.code_executor import execute_tool
        success, result = execute_tool(tool_name, tool_args)

        logger.info(f'🔧 Executed tool "{tool_name}" for {principal[:PRINCIPAL_DISPLAY_LENGTH]}...')

        if success:
            return jsonify({"success": True, "tool": tool_name, "result": result})
        else:
            return jsonify({"success": False, "tool": tool_name, "error": result}), 400

    except Exception as e:
        logger.error(f"❌ Tool execution error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@v4_bp.route("/v4/status", methods=["GET"])
def v4_status():
    """Get V4.0 feature availability status."""
    features = current_app.config.get("V4_FEATURES", {})
    v4_available = current_app.config.get("V4_FEATURES_AVAILABLE", False)
    import_error = current_app.config.get("V4_IMPORT_ERROR")

    response = {"available": v4_available, "features": features, "version": "4.0.0"}

    if import_error:
        response["import_error"] = import_error

    return jsonify(response)
