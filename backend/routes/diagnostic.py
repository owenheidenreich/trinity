"""
Diagnostic endpoints — full-pipeline LLM behavior analysis.

Route: POST /diagnostic/probe
Route: GET  /diagnostic/status

Runs the REAL Trinity pipeline (context_loader → prompt_assembler → LLM → think_filter)
but in non-streaming "capture everything" mode. Returns structured JSON with raw LLM
output, pipeline decisions, think block analysis, and timing.

Gated by DIAGNOSTIC_ENABLED env var (default false). No auth required.
"""

import re
import time

from flask import Blueprint, jsonify, request

from config import DIAGNOSTIC_ENABLED, MODEL_NAME, MODEL_BACKEND, logger

diagnostic_bp = Blueprint("diagnostic", __name__)


def _analyze_think_blocks(raw: str) -> dict:
    """Extract think block metadata from raw LLM output."""
    opens = [m.start() for m in re.finditer(r"<think>", raw, re.IGNORECASE)]
    closes = [m.start() for m in re.finditer(r"</think>", raw, re.IGNORECASE)]
    contents = re.findall(r"<think>(.*?)</think>", raw, re.DOTALL | re.IGNORECASE)
    total_chars = sum(len(c) for c in contents)
    return {
        "count": len(opens),
        "all_closed": len(opens) == len(closes),
        "total_chars": total_chars,
        "content": [c.strip()[:500] for c in contents],  # truncate for readability
    }


def _strip_think_blocks(raw: str) -> str:
    """Remove <think>...</think> blocks from text."""
    result = re.sub(r"<think>.*?</think>\s*", "", raw, flags=re.DOTALL | re.IGNORECASE)
    return result.strip()


def _analyze_tool_calls(raw: str) -> dict:
    """Analyze tool call XML in raw output."""
    # Match <tool_call name="...">...</tool_call> or unclosed
    calls = re.findall(
        r'<tool_call\s+name="([^"]+)"[^>]*>(.*?)(?:</tool_call>|$)',
        raw,
        re.DOTALL | re.IGNORECASE,
    )
    unclosed = len(re.findall(r"<tool_call", raw, re.IGNORECASE)) - len(
        re.findall(r"</tool_call>", raw, re.IGNORECASE)
    )
    parsed = []
    for name, body in calls:
        # Extract params from XML tags inside the tool call body
        params = dict(re.findall(r"<(\w+)>(.*?)</\1>", body, re.DOTALL))
        parsed.append({"name": name, "params": params})
    return {
        "count": len(calls),
        "unclosed_tags": unclosed,
        "calls": parsed,
        "raw_xml": re.findall(r"<tool_call.*?(?:</tool_call>|$)", raw, re.DOTALL | re.IGNORECASE),
    }


@diagnostic_bp.route("/diagnostic/status")
def diagnostic_status():
    """Check if diagnostics are enabled and return backend info."""
    if not DIAGNOSTIC_ENABLED:
        return jsonify({"enabled": False}), 403

    from services.provider_factory import get_provider
    provider = get_provider()
    connected = provider.check_connection()

    return jsonify({
        "enabled": True,
        "model": MODEL_NAME,
        "backend": MODEL_BACKEND,
        "llm_connected": connected,
    })


@diagnostic_bp.route("/diagnostic/probe", methods=["POST"])
def diagnostic_probe():
    """
    Full pipeline execution with diagnostic capture.

    Runs the exact same pipeline as /generate/agent but non-streaming,
    capturing raw LLM output before think-block filtering.

    Request body:
        {
            "prompt": "What is 2+2?",
            "temperature": 0.7,        // optional override
            "max_tokens": 2048,         // optional
            "skip_context": false,      // optional: skip context loading (use raw prompt only)
            "system_prompt": null,      // optional: override system prompt entirely
            "messages": null            // optional: provide exact messages array (bypasses assembler)
        }
    """
    if not DIAGNOSTIC_ENABLED:
        return jsonify({"error": "Diagnostics not enabled"}), 403

    data = request.json or {}
    prompt = str(data.get("prompt", "")).strip()
    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    temp_override = data.get("temperature")
    max_tokens = data.get("max_tokens", 2048)
    skip_context = data.get("skip_context", False)
    system_prompt_override = data.get("system_prompt")
    messages_override = data.get("messages")

    timing = {}
    result = {
        "pipeline": {},
        "prompt": {},
        "llm": {},
        "think_blocks": {},
        "tool_calls": {},
        "react": None,
        "timing": {},
    }

    try:
        from services.provider_factory import get_provider
        from services.prompt_assembler import PromptAssembler
        provider = get_provider()

        # ── Step 1: Context loading ──────────────────────────────────
        t0 = time.time()

        if messages_override:
            # Caller provided exact messages — use them directly
            messages = messages_override
            result["pipeline"] = {
                "context_level": "OVERRIDE",
                "temperature": temp_override or 0.7,
                "tools_detected": [],
                "is_disclosure": False,
            }
        elif skip_context:
            # Minimal: system prompt + user message, no context loading
            sys_content = system_prompt_override or "You are Trinity, a sharp AI assistant."
            messages = [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": prompt},
            ]
            result["pipeline"] = {
                "context_level": "SKIP",
                "temperature": temp_override or 0.7,
                "tools_detected": [],
                "is_disclosure": False,
            }
        else:
            # Full pipeline context loading
            from services.context_loader import load_context
            from services.state_store import get_state_store
            from services.knowledge_store import KnowledgeStore

            # Use a diagnostic principal to avoid polluting real user data
            diag_principal = "diagnostic-probe-000000"
            store = get_state_store(diag_principal)
            chat_id = store.create_chat()
            knowledge_store = KnowledgeStore(store)

            ctx = load_context(
                store=store,
                knowledge_store=knowledge_store,
                prompt=prompt,
                chat_id=chat_id,
                principal_id=diag_principal,
            )

            temperature = temp_override if temp_override is not None else ctx.temperature

            result["pipeline"] = {
                "context_level": "FULL",  # All queries get full context now
                "temperature": temperature,
                "tools_detected": ctx.tools_needed,
                "is_disclosure": ctx.is_disclosure,
                "knowledge_items_count": len(ctx.knowledge_items),
                "context_messages_count": len(ctx.messages),
            }

            # ── Step 2: Prompt assembly ──────────────────────────────
            assembler = PromptAssembler()
            messages = assembler.assemble(
                question=prompt,
                context_messages=ctx.messages,
                knowledge_items=ctx.knowledge_items,
                conversation_summary=ctx.conversation_summary,
                search_context="",
                tools_active=bool(ctx.tools_needed),
            )

        timing["context_load_ms"] = round((time.time() - t0) * 1000, 1)

        # Apply system prompt override if provided (and not using messages_override)
        if system_prompt_override and not messages_override:
            if messages and messages[0]["role"] == "system":
                messages[0]["content"] = system_prompt_override
            else:
                messages.insert(0, {"role": "system", "content": system_prompt_override})

        # Capture assembled prompt
        result["prompt"] = {
            "message_count": len(messages),
            "messages": [
                {"role": m["role"], "content": m["content"][:2000]}
                for m in messages
            ],
            "estimated_tokens": sum(len(m.get("content", "")) for m in messages) // 4,
        }

        # ── Step 3: LLM call ────────────────────────────────────────
        temperature = temp_override if temp_override is not None else result["pipeline"].get("temperature", 0.7)
        tools_detected = result["pipeline"].get("tools_detected", [])
        use_react = bool(tools_detected) and not skip_context and not messages_override

        t1 = time.time()

        if use_react:
            # ReAct loop (non-streaming) — capture each iteration
            from services.react_loop import ReactLoop
            react = ReactLoop(provider, context={"principal_id": "diagnostic-probe"})

            # Build messages via ReactLoop's own builder for consistency
            react_messages = react._build_messages(
                question=prompt,
                context_messages=[],
            )
            # Use the assembled messages instead for full pipeline fidelity
            react_messages = messages

            react_steps = []
            react_tools_used = []

            for iteration in range(react.max_iterations):
                iter_start = time.time()
                raw_response = provider.chat(
                    react_messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=300,
                )

                if not raw_response:
                    react_steps.append({
                        "iteration": iteration + 1,
                        "raw_response": "",
                        "tool_called": None,
                        "error": "Empty response",
                        "latency_ms": round((time.time() - iter_start) * 1000, 1),
                    })
                    break

                # Analyze tool calls
                from services.tools import parse_tool_calls
                tool_calls = parse_tool_calls(raw_response)

                step = {
                    "iteration": iteration + 1,
                    "raw_response": raw_response,
                    "think_blocks": _analyze_think_blocks(raw_response),
                    "tool_analysis": _analyze_tool_calls(raw_response),
                    "latency_ms": round((time.time() - iter_start) * 1000, 1),
                }

                if not tool_calls:
                    step["tool_called"] = None
                    step["final_answer"] = True
                    react_steps.append(step)
                    break

                tc = tool_calls[0]
                step["tool_called"] = tc.name
                step["tool_params"] = tc.params
                react_tools_used.append(tc.name)

                # Execute tool
                from services.code_executor import execute_tool
                success, output = execute_tool(tc.name, tc.params, context={"principal_id": "diagnostic-probe"})
                step["tool_success"] = success
                step["tool_output"] = str(output)[:1000]
                react_steps.append(step)

                # Build observation and continue
                content = _strip_think_blocks(raw_response)
                react_messages.append({"role": "assistant", "content": content})
                result_text = output if success else f"Error: {output}"
                observation = (
                    f"[Tool Result: {tc.name}]\n{result_text}\n\n"
                    f"Continue based on this result. Use another tool if needed, "
                    f"or give your final answer."
                )
                react_messages.append({"role": "user", "content": observation})

            # Final raw response is the last step
            final_raw = react_steps[-1]["raw_response"] if react_steps else ""
            final_filtered = _strip_think_blocks(final_raw)

            result["react"] = {
                "iterations": len(react_steps),
                "tools_used": react_tools_used,
                "steps": react_steps,
                "final_raw": final_raw,
                "final_filtered": final_filtered,
            }
            result["llm"] = {
                "raw_response": final_raw,
                "filtered_response": final_filtered,
                "finish_reason": "stop",
                "latency_seconds": round(time.time() - t1, 2),
                "estimated_tokens_response": len(final_raw) // 4,
            }

        else:
            # Direct LLM call (non-streaming)
            raw_response = provider.chat(
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=300,
            )

            filtered_response = _strip_think_blocks(raw_response)

            result["llm"] = {
                "raw_response": raw_response,
                "filtered_response": filtered_response,
                "finish_reason": "stop",
                "latency_seconds": round(time.time() - t1, 2),
                "estimated_tokens_response": len(raw_response) // 4,
            }

        timing["llm_call_ms"] = round((time.time() - t1) * 1000, 1)

        # ── Step 4: Analysis ─────────────────────────────────────────
        raw = result["llm"]["raw_response"]
        result["think_blocks"] = _analyze_think_blocks(raw)
        result["tool_calls"] = _analyze_tool_calls(raw)

        timing["total_ms"] = round(timing["context_load_ms"] + timing["llm_call_ms"], 1)
        result["timing"] = timing

        return jsonify(result)

    except Exception as e:
        logger.error("Diagnostic probe error: %s", e, exc_info=True)
        return jsonify({"error": str(e), "timing": timing}), 500
