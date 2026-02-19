"""
Generate endpoints — AI inference via LLM provider.

Route: POST /generate/agent

Rewritten to use the new module architecture:
  - context_loader.load_context()  → single context loading path
  - prompt_assembler.assemble()    → single prompt builder
  - pipeline.StreamingPipeline     → streaming generation
  - ingestion_worker.enqueue()     → background indexing + extraction
"""

import json
import time

from flask import Blueprint, Response, jsonify, request, stream_with_context

from config import (
    AUTO_EXTRACT_ASSISTANT_MEMORY,
    MAX_QUEUE_SIZE,
    logger,
)
from icp_auth import require_auth
from middleware import (
    end_request,
    get_active_requests,
    rate_limit,
    record_request,
    start_request,
)
from middleware.rate_limit import get_user_id, record_token_usage, token_quota
from services.provider_factory import get_provider

generate_bp = Blueprint("generate", __name__)


@generate_bp.route("/generate/agent", methods=["POST"])
@require_auth
@rate_limit
@token_quota(estimated_tokens=1500)
def generate_agent():
    """Canonical streaming route: server persists user+assistant turns transactionally."""
    from services.context_loader import load_context
    from services.ingestion_worker import enqueue_ingestion
    from services.pipeline import StreamingPipeline, get_pipeline
    from services.prompt_assembler import PromptAssembler
    from services.provider_factory import get_provider
    from services.query_classifier import ContextLevel, is_trivial_smalltalk, smalltalk_fast_response
    from services.state_store import get_state_store
    from services.knowledge_store import KnowledgeStore

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
        knowledge_store = KnowledgeStore(store)

        # --- Load context (single path replaces 5 divergent ones) ---
        ctx = load_context(
            store=store,
            knowledge_store=knowledge_store,
            prompt=user_prompt,
            chat_id=chat_id,
            principal_id=principal,
        )

        # --- Persist user turn before generation ---
        user_message_id = store.append_message(
            chat_id=chat_id,
            role="user",
            content=user_prompt,
            token_count=len(user_prompt.split()),
        )

        # --- Enqueue ingestion (replaces fire-and-forget threads) ---
        if ctx.level not in (ContextLevel.NONE, ContextLevel.MINIMAL):
            enqueue_ingestion(
                principal_id=principal,
                source="user",
                chat_id=chat_id,
                message_id=user_message_id,
            )

        logger.info(
            "🧠 Agent request: %d words, level=%s, tools=%s",
            len(user_prompt.split()),
            ctx.level.value,
            bool(ctx.tools_needed),
        )

        # --- Build messages array ---
        assembler = PromptAssembler()
        messages = assembler.assemble(
            question=user_prompt,
            context_messages=ctx.messages,
            knowledge_items=ctx.knowledge_items,
            conversation_summary=ctx.conversation_summary,
            search_context="",  # web search handled inside pipeline
            tools_active=bool(ctx.tools_needed),
        )

        # --- Stream response ---
        pipeline = get_pipeline(provider=get_provider(prompt=user_prompt))

        def generate_sse():
            assistant_message_id = None
            full_response = ""
            done_reason = "stop"
            response_mode = "normal"
            first_token_recorded = False

            try:
                # Session metadata so frontend can bind stream to persisted rows
                yield f"data: {json.dumps({'type': 'session', 'chat_id': chat_id, 'user_message_id': user_message_id})}\n\n"

                for event in pipeline.process_streaming(
                    question=user_prompt,
                    messages=messages,
                    principal_id=principal,
                    fast_path=(ctx.level == ContextLevel.NONE),
                    disclosure_path=ctx.is_disclosure,
                    tools_needed=ctx.tools_needed,
                    chat_id=chat_id,
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

                # Persist assistant turn
                if full_response:
                    assistant_message_id = store.append_message(
                        chat_id=chat_id,
                        role="assistant",
                        content=full_response,
                        token_count=len(full_response.split()),
                    )

                    # Enqueue assistant message for ingestion
                    if AUTO_EXTRACT_ASSISTANT_MEMORY and ctx.level not in (ContextLevel.NONE, ContextLevel.MINIMAL):
                        enqueue_ingestion(
                            principal_id=principal,
                            source="assistant",
                            chat_id=chat_id,
                            message_id=assistant_message_id,
                        )

                    record_token_usage(get_user_id(), len(full_response.split()))

                record_request(True, 0, 0)
                yield (
                    f"data: {json.dumps({'done': True, 'assistant_message_id': assistant_message_id, 'done_reason': done_reason, 'response_mode': response_mode})}\n\n"
                )

            except Exception as e:
                logger.error("Agent streaming error: %s", e)
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
        logger.error("Agent setup error: %s", e)
        return jsonify({"error": str(e)}), 500
