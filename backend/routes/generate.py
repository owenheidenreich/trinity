"""
Generate endpoints — AI inference via Ollama.
Routes: /generate, /generate/simple, /generate/simple/stream,
        /generate/stream, /generate/agent, /generate/langgraph
"""

import hashlib
import json
import time
from datetime import datetime

import requests as requests_lib
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context, g

from config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MAX_TOKENS_STREAM,
    DEFAULT_TEMPERATURE,
    DEPLOYMENT_TIER,
    GPU_TYPE,
    MAX_DOCUMENT_CONTEXT_CHARS,
    MAX_PROMPT_LENGTH,
    MAX_QUEUE_SIZE,
    MODEL_NAME,
    OLLAMA_HOST,
    OLLAMA_TIMEOUT,
    OLLAMA_TIMEOUT_SIMPLE,
    OLLAMA_TIMEOUT_STREAM,
    PROVIDER_ID,
    REASONING_MIN_TOKENS,
    REASONING_MIN_TOKENS_STREAM,
    SIMPLE_MAX_TOKENS,
    SIMPLE_MAX_TOKENS_CAP,
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
        context_memory = data.get("contextMemory", [])
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


@generate_bp.route("/generate/simple", methods=["POST"])
@rate_limit
def generate_simple():
    """Ultra-minimal generate endpoint for testing. No auth, no context, no metrics."""
    try:
        data = request.json or {}
        prompt = data.get("prompt", "").strip()

        if not prompt:
            return jsonify({"ok": False, "error": "No prompt provided"}), 400

        max_length = min(data.get("max_length", 150), 300)
        temperature = data.get("temperature", 0.7)
        framed_prompt = f"User: {prompt}\n\nAssistant:"

        response = http_session.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": framed_prompt,
                "stream": False,
                "options": {"num_predict": max_length, "temperature": temperature, "stop": ["User:", "\n\nUser"]},
            },
            timeout=OLLAMA_TIMEOUT_SIMPLE,
        )

        if response.status_code != 200:
            return jsonify({"ok": False, "error": f"Ollama error: {response.status_code}"}), 500

        result = response.json()
        return jsonify({"ok": True, "response": result.get("response", ""), "model": MODEL_NAME})

    except Exception as e:
        logger.error(f"Simple generate error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@generate_bp.route("/generate/simple/stream", methods=["POST"])
@rate_limit
def generate_simple_stream():
    """Ultra-minimal streaming generate endpoint. No auth, no context."""
    try:
        data = request.json or {}
        prompt = data.get("prompt", "").strip()

        if not prompt:
            return jsonify({"ok": False, "error": "No prompt provided"}), 400

        max_length = min(data.get("max_length", SIMPLE_MAX_TOKENS), SIMPLE_MAX_TOKENS_CAP)
        temperature = data.get("temperature", DEFAULT_TEMPERATURE)
        framed_prompt = f"User: {prompt}\n\nAssistant:"

        def stream_response():
            try:
                response = http_session.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json={
                        "model": MODEL_NAME,
                        "prompt": framed_prompt,
                        "stream": True,
                        "options": {"num_predict": max_length, "temperature": temperature, "stop": ["User:", "\n\nUser"]},
                    },
                    stream=True,
                    timeout=OLLAMA_TIMEOUT_SIMPLE,
                )

                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("response", "")
                            if token:
                                yield f"data: {json.dumps({'token': token})}\n\n"
                            if chunk.get("done"):
                                yield f"data: {json.dumps({'done': True})}\n\n"
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return Response(
            stream_response(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no", "Access-Control-Allow-Origin": "*"},
        )

    except Exception as e:
        logger.error(f"Simple stream error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@generate_bp.route("/generate/stream", methods=["POST"])
@rate_limit
def generate_stream():
    """Generate text with Server-Sent Events (SSE) streaming."""
    if get_active_requests() >= MAX_QUEUE_SIZE:
        return jsonify({"error": "Server at capacity"}), 503

    start_request()

    try:
        data = request.json
        if not data:
            raise ValueError("No JSON data provided")

        user_prompt = data.get("prompt", "")
        max_length = data.get("max_length", DEFAULT_MAX_TOKENS_STREAM)
        context_memory = data.get("contextMemory", [])
        principal = data.get("principal")
        document_context = data.get("documentContext")
        temperature = data.get("temperature", DEFAULT_TEMPERATURE)
        reasoning_mode = data.get("reasoning_mode", False)

        user_memory = None
        if principal:
            try:
                user_memory = load_user_memory(principal)
            except Exception:
                pass

        if document_context:
            doc_prefix = f"[Attached Document]\n{document_context[:MAX_DOCUMENT_CONTEXT_CHARS]}\n[End Document]\n\nBased on the above document, "
            user_prompt = doc_prefix + user_prompt

        if reasoning_mode and not is_small_model():
            full_prompt = build_reasoning_prompt(user_prompt, context_memory, user_memory)
            max_length = max(max_length, REASONING_MIN_TOKENS_STREAM)
            logger.info("🧠 STREAM: Using DEEP REASONING mode with extended output")
        else:
            full_prompt = build_prompt_with_context(user_prompt, context_memory, user_memory)

        logger.info(f"🌊 Streaming request: {len(user_prompt.split())} words, {len(context_memory)} ctx, reasoning={reasoning_mode}")

        def generate_sse():
            try:
                response = http_session.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json={"model": MODEL_NAME, "prompt": full_prompt, "stream": True, "options": {"num_predict": max_length, "temperature": temperature, "num_ctx": 32768}},
                    stream=True,
                    timeout=OLLAMA_TIMEOUT_STREAM,
                )

                if response.status_code != 200:
                    yield f"data: {json.dumps({'error': 'Ollama error'})}\n\n"
                    return

                full_response = ""
                total_eval_count = 0
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("response", "")
                            full_response += token
                            yield f"data: {json.dumps({'token': token})}\n\n"
                            if chunk.get("done", False):
                                total_eval_count = chunk.get("eval_count", len(full_response.split()))
                                done_reason = chunk.get("done_reason", "stop")
                                yield f"data: {json.dumps({'done': True, 'model': MODEL_NAME, 'done_reason': done_reason})}\n\n"
                                break
                        except json.JSONDecodeError:
                            continue

                record_request(True, total_eval_count or len(full_response.split()), 0)

            except Exception as e:
                logger.error(f"Streaming error: {e}")
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
        logger.error(f"Stream setup error: {e}")
        return jsonify({"error": str(e)}), 500


@generate_bp.route("/generate/agent", methods=["POST"])
@rate_limit
def generate_agent():
    """
    Agentic multi-pass generation with streaming.
    Routes by complexity: Simple (1 pass), Medium (3), Complex (5).
    V4.0: Semantic memory, tool detection, multi-model routing.
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
        context_memory = data.get("contextMemory", [])
        principal = data.get("principal")
        force_mode = data.get("force_mode")
        enable_voting = data.get("enable_voting")

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
                    principal_id=principal, query=user_prompt, recent_messages=context_memory
                )
                if semantic_context:
                    logger.info(f"🧠 V4.0 semantic context: {len(semantic_context)} relevant items retrieved")
            except Exception as e:
                logger.warning(f"⚠️ Semantic memory fallback: {e}")
                enhanced_context = context_memory

        pipeline = AgentPipeline(OLLAMA_HOST, MODEL_NAME)

        v4_options = (
            {"semantic_context": semantic_context, "enable_voting": enable_voting, "principal_id": principal}
            if V4_FEATURES_AVAILABLE
            else {}
        )

        logger.info(f"🧠 Agent request: {len(user_prompt.split())} words, force_mode={force_mode}, v4={V4_FEATURES_AVAILABLE}")

        def generate_sse():
            try:
                for event in pipeline.process_streaming(
                    question=user_prompt, context_messages=enhanced_context,
                    user_memory=user_memory, force_complexity=force_mode, **v4_options,
                ):
                    yield f"data: {json.dumps(event)}\n\n"

                record_request(True, 0, 0)

                if V4_FEATURES_AVAILABLE and principal:
                    try:
                        from services.vector_store import get_user_vector_store
                        vector_store = get_user_vector_store(principal)
                        vector_store.add_message_embedding(content=user_prompt, role="user", timestamp=time.time())
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


@generate_bp.route("/generate/langgraph", methods=["POST"])
@rate_limit
def generate_langgraph():
    """
    LangGraph multi-agent generation with complexity routing.
    V5.0: StateGraph agents, supervisor routing, A/B experiments.
    """
    from services.complexity import classify_complexity

    LANGGRAPH_AVAILABLE = current_app.config.get("LANGGRAPH_AVAILABLE", False)

    # Apply experiment assignments
    try:
        from middleware.ab_test import get_experiment_config, get_session_id
        from services.experiments import assign_variant

        session_id = get_session_id()
        if not hasattr(g, "experiments"):
            g.experiments = {}
        for exp_name in ["agent_mode", "complexity_threshold", "reasoning_depth"]:
            variant = assign_variant(exp_name, session_id)
            if variant:
                g.experiments[exp_name] = {"variant": variant.name, "config": variant.config}
        EXPERIMENTS_ENABLED = True
    except ImportError:
        EXPERIMENTS_ENABLED = False

    if not LANGGRAPH_AVAILABLE:
        return jsonify({"error": "LangGraph not available", "fallback": "/generate/agent is available"}), 503

    if get_active_requests() >= MAX_QUEUE_SIZE:
        return jsonify({"error": "Server at capacity"}), 503

    start_request()
    start_time = time.time()
    tier = str(DEPLOYMENT_TIER) if DEPLOYMENT_TIER else "unknown"

    try:
        data = request.json
        if not data:
            raise ValueError("No JSON data provided")

        user_prompt = data.get("prompt", "")
        context_memory = data.get("contextMemory", [])
        principal = data.get("principal")
        mode = data.get("mode", "auto")

        if not user_prompt:
            return jsonify({"error": "No prompt provided"}), 400

        complexity = classify_complexity(user_prompt)

        if EXPERIMENTS_ENABLED and mode == "auto":
            exp_mode = get_experiment_config("agent_mode", "mode")
            if exp_mode:
                mode = exp_mode
                logger.info(f"🧪 Experiment override: mode={mode}")

        # Handle parallel mode
        if mode == "parallel":
            try:
                from services.parallel import get_parallel_pipeline

                parallel_pipeline = get_parallel_pipeline(OLLAMA_HOST, MODEL_NAME)
                user_memory = None
                if principal:
                    try:
                        user_memory = load_user_memory(principal)
                    except Exception:
                        pass

                result = parallel_pipeline.process(
                    question=user_prompt, context_messages=context_memory,
                    user_memory=user_memory, complexity=complexity,
                )

                latency_ms = (time.time() - start_time) * 1000
                record_request(True, 0, latency_ms)

                response_data = {
                    "response": result.final_response,
                    "mode_used": "parallel",
                    "winner": result.winner,
                    "confidence": result.confidence,
                    "voting_reason": result.voting_reason,
                    "complexity": complexity,
                    "agents_invoked": ["parallel_legacy", "parallel_langgraph"],
                    "iterations": 1,
                    "model": MODEL_NAME,
                    "provider_id": PROVIDER_ID,
                    "latency_ms": latency_ms,
                    "parallel_details": {
                        "legacy_duration_ms": result.legacy_result.duration_seconds * 1000,
                        "langgraph_duration_ms": result.langgraph_result.duration_seconds * 1000,
                        "legacy_success": result.legacy_result.success,
                        "langgraph_success": result.langgraph_result.success,
                    },
                }

                if EXPERIMENTS_ENABLED and hasattr(g, "experiments") and g.experiments:
                    response_data["_experiments"] = {
                        name: {"variant": d["variant"]} for name, d in g.experiments.items()
                    }

                return jsonify(response_data)

            except Exception as e:
                logger.error(f"Parallel execution failed: {e}, falling back to auto")
                mode = "auto"

        # Determine pipeline
        from services.graph.edges import should_use_langgraph
        use_langgraph = should_use_langgraph(complexity, mode)
        logger.info(f"🔀 LangGraph routing: complexity={complexity}, mode={mode}, use_langgraph={use_langgraph}")

        if not use_langgraph:
            from services.agent import AgentPipeline

            user_memory = None
            if principal:
                try:
                    user_memory = load_user_memory(principal)
                except Exception:
                    pass

            pipeline = AgentPipeline(OLLAMA_HOST, MODEL_NAME)
            result = pipeline.process(
                question=user_prompt, context_messages=context_memory, user_memory=user_memory
            )

            latency_ms = (time.time() - start_time) * 1000
            record_request(True, 0, latency_ms)

            response_data = {
                "response": result.final_answer,
                "mode_used": "legacy",
                "complexity": complexity,
                "agents_invoked": ["legacy_agent"],
                "iterations": result.passes_used,
                "model": MODEL_NAME,
                "provider_id": PROVIDER_ID,
                "latency_ms": latency_ms,
            }

            if EXPERIMENTS_ENABLED and hasattr(g, "experiments") and g.experiments:
                response_data["_experiments"] = {
                    name: {"variant": d["variant"]} for name, d in g.experiments.items()
                }

            return jsonify(response_data)

        # Use LangGraph multi-agent pipeline
        from services.graph import execute_graph

        with track_inference(MODEL_NAME, tier=tier) as inference_tracker:
            context_str = ""
            if context_memory:
                recent_exchanges = context_memory[-6:]
                for ctx_msg in recent_exchanges:
                    role = ctx_msg.get("role", "user")
                    content = ctx_msg.get("content", "")
                    context_str += f"{role}: {content}\n"

            final_state = execute_graph(
                user_message=user_prompt,
                complexity=complexity,
                max_iterations=5,
                context={"prior_context": context_str} if context_str else None,
            )

            final_answer = final_state.get("final_answer", "")
            iterations = final_state.get("iteration", 0)
            tokens_generated = final_state.get("eval_count", len(final_answer.split()))
            inference_tracker.set_tokens(tokens_generated)

        latency_ms = (time.time() - start_time) * 1000
        record_request(True, tokens_generated, latency_ms)

        agents_invoked = ["router"]
        if final_state.get("research_context"):
            agents_invoked.append("research")
        if final_state.get("reasoning_output"):
            agents_invoked.append("reasoning")
        if final_state.get("code_output"):
            agents_invoked.append("coding")
        agents_invoked.append("synthesis")

        logger.info(f"✅ LangGraph complete: {tokens_generated} tokens, {iterations} iterations, {latency_ms:.0f}ms")

        response_data = {
            "response": final_answer,
            "mode_used": "langgraph",
            "complexity": complexity,
            "agents_invoked": agents_invoked,
            "iterations": iterations,
            "model": MODEL_NAME,
            "provider_id": PROVIDER_ID,
            "latency_ms": latency_ms,
        }

        if EXPERIMENTS_ENABLED and hasattr(g, "experiments") and g.experiments:
            response_data["_experiments"] = {
                name: {"variant": d["variant"]} for name, d in g.experiments.items()
            }

        return jsonify(response_data)

    except ValueError as e:
        record_request(False, 0, 0)
        track_error("ValidationError", "/generate/langgraph")
        logger.warning(f"Validation error: {e}")
        return jsonify({"error": str(e), "provider_id": PROVIDER_ID}), 400

    except Exception as e:
        record_request(False, 0, 0)
        track_error("LangGraphError", "/generate/langgraph")
        logger.error(f"LangGraph generation error: {e}", exc_info=True)
        return jsonify({
            "error": f"LangGraph generation failed: {str(e)}",
            "provider_id": PROVIDER_ID,
            "fallback": "/generate/agent available",
        }), 500

    finally:
        end_request()
