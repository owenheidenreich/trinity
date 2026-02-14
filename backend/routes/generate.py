"""
Generate endpoints — AI inference via Ollama.
Routes: /generate, /generate/agent
"""

import hashlib
import json
import time
from datetime import datetime

import requests as requests_lib
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEPLOYMENT_TIER,
    GPU_TYPE,
    MAX_DOCUMENT_CONTEXT_CHARS,
    MAX_PROMPT_LENGTH,
    MAX_QUEUE_SIZE,
    MODEL_NAME,
    OLLAMA_HOST,
    OLLAMA_TIMEOUT,
    PROVIDER_ID,
    REASONING_MIN_TOKENS,
    http_session,
    logger,
)
from middleware import (
    end_request,
    get_active_requests,
    icp_idempotent,
    rate_limit,
    record_request,
    start_request,
    track_error,
    track_inference,
)
from routes.shared import error_response
from services import (
    build_prompt_with_context,
    build_reasoning_prompt,
    is_small_model,
    parse_reasoning_response,
)
from storage import load_user_memory

generate_bp = Blueprint("generate", __name__)


@generate_bp.route("/generate", methods=["POST"])
@rate_limit
@icp_idempotent
def generate():
    """
    Generate text using the AI model.

    Request JSON:
        - prompt: text to generate from (required)
        - max_length: maximum tokens to generate (default: 4000)
        - temperature: randomness 0.1-2.0 (default: 0.7)
        - contextMemory: array of recent messages for conversation context

    Response JSON:
        - response / generated_text: AI-generated text
        - model, provider_id, gpu_type, tokens_generated, latency_ms
    """
    active_reqs = get_active_requests()
    if active_reqs >= MAX_QUEUE_SIZE:
        logger.warning(f"Server at capacity: {active_reqs}/{MAX_QUEUE_SIZE}")
        track_error("CapacityError", "/generate")
        return jsonify({
            "error": "Server at capacity",
            "queue_size": active_reqs,
            "max_queue_size": MAX_QUEUE_SIZE,
            "provider_id": PROVIDER_ID,
        }), 503

    start_request()
    start_time = time.time()
    tier = str(DEPLOYMENT_TIER) if DEPLOYMENT_TIER else "unknown"

    try:
        data = request.json
        if not data:
            raise ValueError("No JSON data provided")

        user_prompt = data.get("prompt", "")
        max_length = data.get("max_length", DEFAULT_MAX_TOKENS)
        context_memory = data.get("context_messages", data.get("contextMemory", []))
        principal = data.get("principal")
        document_context = data.get("documentContext")
        reasoning_mode = data.get("reasoning_mode", False)

        options = data.get("options", {})
        temperature = options.get("temperature", data.get("temperature", DEFAULT_TEMPERATURE))
        seed = options.get("seed")

        is_icp_request = request.headers.get("X-Request-ID") is not None

        if not user_prompt:
            raise ValueError("Prompt cannot be empty")

        if len(user_prompt) > MAX_PROMPT_LENGTH:
            logger.warning(f"⚠️ Prompt too long: {len(user_prompt)} chars (max: {MAX_PROMPT_LENGTH})")
            return error_response(
                400,
                f"Message too long ({len(user_prompt):,} chars). Maximum is {MAX_PROMPT_LENGTH:,}.",
                details={"max_length": MAX_PROMPT_LENGTH, "your_length": len(user_prompt)},
            )

        user_memory = None
        if principal:
            try:
                user_memory = load_user_memory(principal)
                if user_memory.get("facts"):
                    logger.info(f"📚 Including {len(user_memory['facts'])} user memory facts")
            except Exception as e:
                logger.warning(f"Could not load user memory: {e}")

        if document_context:
            doc_prefix = f"[Attached Document]\n{document_context[:MAX_DOCUMENT_CONTEXT_CHARS]}\n[End Document]\n\nBased on the above document, "
            user_prompt = doc_prefix + user_prompt
            logger.info(f"📄 Document attached: {len(document_context)} chars")

        if reasoning_mode and not is_small_model():
            full_prompt = build_reasoning_prompt(user_prompt, context_memory, user_memory)
            max_length = max(max_length, REASONING_MIN_TOKENS)
            logger.info("🧠 Using DEEP REASONING mode with extended output")
        else:
            full_prompt = build_prompt_with_context(user_prompt, context_memory, user_memory)

        prompt_hash = hashlib.sha256(user_prompt.encode()).hexdigest()[:8]
        word_count = len(user_prompt.split())
        context_count = len(context_memory)
        logger.info(
            f"🤖 Request: {word_count} words (#{prompt_hash}), {context_count} ctx, seed={seed}, reasoning={reasoning_mode}"
        )

        ollama_options = {"num_predict": max_length, "temperature": temperature, "num_ctx": 32768}
        if seed is not None:
            ollama_options["seed"] = int(seed)
            logger.info(f"🎲 Using deterministic seed: {seed}")

        with track_inference(MODEL_NAME, tier=tier) as inference_tracker:
            response = http_session.post(
                f"{OLLAMA_HOST}/api/generate",
                json={"model": MODEL_NAME, "prompt": full_prompt, "stream": False, "options": ollama_options},
                timeout=OLLAMA_TIMEOUT,
            )

            if response.status_code != 200:
                inference_tracker.set_status("error")
                raise Exception(f"Ollama returned status {response.status_code}")

            result = response.json()
            generated_text = result.get("response", "")
            tokens_generated = result.get("eval_count", len(generated_text.split()))
            prompt_tokens = result.get("prompt_eval_count", 0)
            inference_tracker.set_tokens(tokens_generated)

        reasoning_result = None
        final_response = generated_text
        if reasoning_mode and not is_small_model():
            reasoning_result = parse_reasoning_response(generated_text)
            if reasoning_result.get("answer"):
                final_response = reasoning_result["answer"]
            logger.info(
                f"🧠 Reasoning parsed: thinking={bool(reasoning_result.get('thinking'))}, plan={bool(reasoning_result.get('plan'))}"
            )

        latency_ms = (time.time() - start_time) * 1000
        record_request(True, tokens_generated, latency_ms)
        logger.info(f"[{PROVIDER_ID}] Generated {tokens_generated} tokens in {latency_ms:.0f}ms")

        response_data = {
            "response": final_response,
            "model": MODEL_NAME,
            "provider_id": PROVIDER_ID,
            "done": True,
        }

        if reasoning_result:
            response_data["reasoning"] = {
                "thinking": reasoning_result.get("thinking"),
                "plan": reasoning_result.get("plan"),
                "raw": reasoning_result.get("raw"),
            }

        if not is_icp_request:
            response_data["prompt"] = user_prompt
            response_data["generated_text"] = final_response
            response_data["gpu_type"] = GPU_TYPE
            response_data["tokens_generated"] = tokens_generated
            response_data["prompt_tokens"] = prompt_tokens
            response_data["latency_ms"] = latency_ms
            response_data["timestamp"] = datetime.utcnow().isoformat()

        return jsonify(response_data)

    except ValueError as e:
        record_request(False, 0, 0)
        track_error("ValidationError", "/generate")
        logger.warning(f"Validation error: {e}")
        return jsonify({"error": str(e), "provider_id": PROVIDER_ID}), 400

    except requests_lib.Timeout:
        record_request(False, 0, 0)
        track_error("TimeoutError", "/generate")
        logger.error("Ollama request timed out")
        return error_response(504, "Server is busy processing your request. Please try again in a moment.")

    except Exception as e:
        record_request(False, 0, 0)
        track_error("InferenceError", "/generate")
        logger.error(f"Generation error: {e}", exc_info=True)
        return error_response(500, "Generation failed. The AI server may be restarting — please try again in 30 seconds.")

    finally:
        end_request()


@generate_bp.route("/generate/agent", methods=["POST"])
@rate_limit
def generate_agent():
    """
    Single-pass agentic generation with SSE streaming.
    Detects tools needed → ReAct loop or direct generation.
    """
    from services.agent import AgentPipeline

    V4_FEATURES_AVAILABLE = current_app.config.get("V4_FEATURES_AVAILABLE", False)

    if get_active_requests() >= MAX_QUEUE_SIZE:
        return jsonify({"error": "Server at capacity"}), 503

    start_request()

    try:
        data = request.json
        if not data:
            raise ValueError("No JSON data provided")

        user_prompt = data.get("prompt", "")
        context_memory = data.get("context_messages", data.get("contextMemory", []))
        principal = data.get("principal")
        chat_id = data.get("chat_id")
        message_index = data.get("message_index")

        if not user_prompt:
            return jsonify({"error": "No prompt provided"}), 400

        user_memory = None
        if principal:
            try:
                user_memory = load_user_memory(principal)
            except Exception:
                pass

        enhanced_context = context_memory
        semantic_context = None
        if V4_FEATURES_AVAILABLE and principal:
            try:
                from services.memory import build_enhanced_context
                enhanced_context, semantic_context = build_enhanced_context(
                    principal_id=principal, query=user_prompt,
                    context_messages=context_memory, chat_id=chat_id,
                )
                if semantic_context:
                    logger.info(f"🧠 V4.0 semantic context: {len(semantic_context)} relevant items retrieved")
            except Exception as e:
                logger.warning(f"⚠️ Semantic memory fallback: {e}")
                enhanced_context = context_memory

        pipeline = AgentPipeline(OLLAMA_HOST, MODEL_NAME)

        v4_options = (
            {"semantic_context": semantic_context, "principal_id": principal}
            if V4_FEATURES_AVAILABLE
            else {}
        )

        logger.info(f"🧠 Agent request: {len(user_prompt.split())} words, v4={V4_FEATURES_AVAILABLE}")

        def generate_sse():
            try:
                full_response = ""
                for event in pipeline.process_streaming(
                    question=user_prompt, context_messages=enhanced_context,
                    user_memory=user_memory, **v4_options,
                ):
                    if isinstance(event, dict) and "token" in event:
                        full_response += event["token"]
                    yield f"data: {json.dumps(event)}\n\n"

                record_request(True, 0, 0)

                if V4_FEATURES_AVAILABLE and principal and chat_id:
                    try:
                        from services.memory import get_semantic_memory
                        sem_memory = get_semantic_memory(principal)
                        idx = message_index if message_index is not None else 0
                        sem_memory.index_message(chat_id, idx, "user", user_prompt)
                        if full_response:
                            sem_memory.index_message(chat_id, idx + 1, "assistant", full_response)
                    except Exception as idx_error:
                        logger.debug(f"V4.0 indexing skipped: {idx_error}")

            except Exception as e:
                logger.error(f"Agent streaming error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                end_request()

        return Response(
            stream_with_context(generate_sse()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    except Exception as e:
        end_request()
        logger.error(f"Agent setup error: {e}")
        return jsonify({"error": str(e)}), 500
