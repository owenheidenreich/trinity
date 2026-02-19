"""
Generate endpoints — AI inference via LLM provider.
Route: /generate/agent
"""

import json
import threading
import time

from flask import Blueprint, Response, jsonify, request, stream_with_context

from icp_auth import require_auth
from config import (
    AUTO_EXTRACT_ASSISTANT_MEMORY,
    GRAPH_MEMORY_ENABLED,
    GRAPH_MEMORY_TOP_K,
    MAX_QUEUE_SIZE,
    logger,
)
from services.provider_factory import get_provider
from middleware import (
    end_request,
    get_active_requests,
    rate_limit,
    record_request,
    start_request,
)
from middleware.rate_limit import get_user_id, record_token_usage, token_quota

generate_bp = Blueprint("generate", __name__)


def _enqueue_async_ingestion(principal: str, user_text: str, assistant_text: str = "", chat_id: str = None):
    """Queue strict async ingestion for facts + triples."""
    if not principal:
        return
    try:
        from services.memory_ingestion import enqueue_ingestion

        enqueue_ingestion(principal, user_text, source="user", chat_id=chat_id)
        if assistant_text and AUTO_EXTRACT_ASSISTANT_MEMORY:
            enqueue_ingestion(principal, assistant_text, source="assistant", chat_id=chat_id)
    except Exception as e:
        logger.debug(f"Memory ingestion enqueue skipped: {e}")


def _index_semantic_async(
    principal: str,
    chat_id: str,
    message_id: int,
    role: str,
    content: str,
):
    """Best-effort semantic indexing without blocking user-visible streaming."""
    if not principal or not chat_id or not content:
        return

    def _worker():
        try:
            from services.memory import get_semantic_memory

            get_semantic_memory(principal).index_message(
                chat_id=chat_id,
                message_id=message_id,
                role=role,
                content=content,
            )
        except Exception as idx_error:
            logger.debug(f"V4.0 async {role} indexing skipped: {idx_error}")

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"semantic-index-{role}",
    ).start()


def _is_lightweight_non_memory_prompt(prompt: str) -> bool:
    """
    Fast guard for short prompts that do not need heavy memory retrieval layers.
    Keeps chat responsive for lightweight turns while preserving intelligence on
    memory-sensitive, search-like, and technical requests.
    """
    text = str(prompt or "").strip().lower()
    if not text:
        return False

    words = text.split()
    if len(words) > 6:
        return False

    memory_signals = (
        "remember",
        "recall",
        "about me",
        "my name",
        "i'm ",
        "i am ",
        "my project",
        "my startup",
        "my company",
        "i moved",
        "i live",
        "i work",
        "actually",
    )
    retrieval_signals = (
        "latest",
        "today",
        "news",
        "price",
        "weather",
        "search",
        "look up",
        "find out",
        "code",
        "function",
        "script",
        "file",
        "debug",
        "fix",
    )
    if any(signal in text for signal in memory_signals):
        return False
    if any(signal in text for signal in retrieval_signals):
        return False
    if "?" in text:
        return False
    return True


def _load_prompt_memory_from_store(store):
    return {
        "facts": store.list_facts(include_deleted=True, include_invalid=True, with_embeddings=True),
        "conversation_summaries": store.list_conversation_summaries(),
    }


@generate_bp.route("/generate/agent", methods=["POST"])
@require_auth
@rate_limit
@token_quota(estimated_tokens=1500)
def generate_agent():
    """Canonical streaming route: server persists user+assistant turns transactionally."""
    from services.agent import AgentPipeline, is_personal_disclosure, is_trivial_smalltalk
    from services.memory_ingestion import enqueue_ingestion
    from services.state_store import get_state_store

    if get_active_requests() >= MAX_QUEUE_SIZE:
        return jsonify({"error": "Server at capacity"}), 503

    start_request()
    start_time = time.time()

    try:
        data = request.json or {}
        user_prompt = str(data.get("prompt", "")).strip()
        if not user_prompt:
            return jsonify({"error": "No prompt provided"}), 400

        principal = request.principal
        chat_id = data.get("chat_id")
        store = get_state_store(principal)
        chat_id = store.ensure_chat(chat_id) if chat_id else store.create_chat()

        # Detect trivial greetings before any expensive retrieval/index work.
        fast_path = is_trivial_smalltalk(user_prompt, None)
        lightweight_prompt = (not fast_path) and _is_lightweight_non_memory_prompt(user_prompt)

        # Canonical context is loaded from state_store, not request body.
        # Skip this for smalltalk and lightweight paths to minimize first-token latency.
        context_messages = []
        if not fast_path and not lightweight_prompt:
            persisted_context = store.get_messages(chat_id=chat_id, limit=25)
            context_messages = [
                {
                    "role": m["role"],
                    "content": m["content"],
                    "message_id": m["message_id"],
                }
                for m in persisted_context
            ]

        # Re-evaluate with context if needed (function is currently context-agnostic,
        # but this keeps behavior future-proof).
        if not fast_path:
            fast_path = is_trivial_smalltalk(user_prompt, context_messages)

        disclosure_path = is_personal_disclosure(user_prompt)

        user_memory = None
        graph_context = None
        if principal and not fast_path and not lightweight_prompt:
            try:
                user_memory = _load_prompt_memory_from_store(store)
            except Exception:
                user_memory = None
            if GRAPH_MEMORY_ENABLED:
                try:
                    graph_context = store.search_graph_triples(user_prompt, limit=GRAPH_MEMORY_TOP_K)
                except Exception as graph_error:
                    logger.debug(f"Graph retrieval skipped: {graph_error}")

        semantic_context = None
        enhanced_context = context_messages
        if principal and not fast_path and not lightweight_prompt:
            try:
                from services.memory import build_enhanced_context

                enhanced_context, semantic_context = build_enhanced_context(
                    principal_id=principal,
                    query=user_prompt,
                    context_messages=context_messages,
                    chat_id=chat_id,
                )
            except Exception as e:
                logger.warning(f"⚠️ Semantic memory fallback: {e}")
                enhanced_context = context_messages

        # Persist user turn before generation.
        user_message_id = store.append_message(
            chat_id=chat_id,
            role="user",
            content=user_prompt,
            token_count=len(user_prompt.split()),
        )
        if not fast_path:
            enqueue_ingestion(
                principal_id=principal,
                source="user",
                chat_id=chat_id,
                message_id=user_message_id,
            )

        if not fast_path:
            _index_semantic_async(
                principal=principal,
                chat_id=chat_id,
                message_id=user_message_id,
                role="user",
                content=user_prompt,
            )

        pipeline = AgentPipeline(provider=get_provider(prompt=user_prompt))

        v4_options = {
            "graph_context": graph_context,
            "principal_id": principal,
            "semantic_context": semantic_context,
            "chat_id": chat_id,
            "message_index": user_message_id,
        }

        logger.info(
            "🧠 Agent request: %s words, fast_path=%s, lightweight=%s, disclosure=%s",
            len(user_prompt.split()),
            fast_path,
            lightweight_prompt,
            disclosure_path,
        )

        def generate_sse():
            assistant_message_id = None
            full_response = ""
            done_reason = "stop"
            response_mode = "normal"
            first_token_recorded = False

            try:
                # Canonical IDs first so frontend can bind stream to persisted rows.
                yield f"data: {json.dumps({'type': 'session', 'chat_id': chat_id, 'user_message_id': user_message_id})}\n\n"

                for event in pipeline.process_streaming(
                    question=user_prompt,
                    context_messages=enhanced_context,
                    user_memory=user_memory,
                    fast_path=fast_path,
                    disclosure_path=disclosure_path,
                    **v4_options,
                ):
                    if isinstance(event, dict) and event.get("done"):
                        done_reason = event.get("done_reason", "stop")
                        response_mode = event.get("response_mode", "normal")
                        continue

                    if isinstance(event, dict) and "token" in event:
                        full_response += event["token"]
                        if not first_token_recorded:
                            try:
                                from services.slo_metrics import record_first_token_latency

                                record_first_token_latency((time.time() - start_time) * 1000)
                            except Exception:
                                pass
                            first_token_recorded = True

                    yield f"data: {json.dumps(event)}\n\n"

                if full_response:
                    assistant_message_id = store.append_message(
                        chat_id=chat_id,
                        role="assistant",
                        content=full_response,
                        token_count=len(full_response.split()),
                    )
                    if not fast_path:
                        _index_semantic_async(
                            principal=principal,
                            chat_id=chat_id,
                            message_id=assistant_message_id,
                            role="assistant",
                            content=full_response,
                        )

                    if AUTO_EXTRACT_ASSISTANT_MEMORY and not fast_path:
                        enqueue_ingestion(
                            principal_id=principal,
                            source="assistant",
                            chat_id=chat_id,
                            message_id=assistant_message_id,
                        )

                    record_token_usage(get_user_id(), len(full_response.split()))

                record_request(True, 0, 0)
                yield (
                    "data: "
                    f"{json.dumps({'done': True, 'assistant_message_id': assistant_message_id, 'done_reason': done_reason, 'response_mode': response_mode})}\n\n"
                )

            except Exception as e:
                logger.error(f"Agent streaming error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                end_request()

        return Response(
            stream_with_context(generate_sse()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except Exception as e:
        end_request()
        logger.error(f"Agent setup error: {e}")
        return jsonify({"error": str(e)}), 500
