"""
Trinity ReAct Agentic Loop

Implements the ReAct (Reasoning + Acting) pattern for iterative tool calling.
The model reasons about what to do, calls a tool, observes the result,
and repeats until it has enough information to answer.

This module is called from agent.py's execute pass when tools are needed.

Supports dual-mode tool calling:
- Native: Ollama /api/chat tools parameter (Qwen3, Llama3.1+, Mistral)
- XML: Prompt-based XML parsing (all models, fallback)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Generator, List, Optional

from config import REACT_MAX_ITERATIONS, REACT_TOKEN_BUDGET, REFLEXION_MAX_RETRIES

from .agent_prompts import REACT_SYSTEM_PROMPT, TOOL_PROMPT_SECTION
from .code_executor import execute_tool
from .loading_messages import format_phase_update
from .tools import (
    ToolResult,
    parse_tool_calls,
)

# Observability
try:
    from middleware.observability import track_agent_pass, track_tool_call

    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    from contextlib import contextmanager

    @contextmanager
    def track_agent_pass(pass_name):
        yield

    @contextmanager
    def track_tool_call(tool_name):
        yield type("obj", (object,), {"set_status": lambda s: None})()


logger = logging.getLogger(__name__)


@dataclass
class ReactResult:
    """Result from a completed ReAct loop."""

    answer: str
    tools_used: List[str] = field(default_factory=list)
    iterations: int = 0
    tool_results: List[Dict] = field(default_factory=list)


class ReactLoop:
    """
    ReAct agentic loop for iterative tool calling.

    The model gets multiple turns to reason and call tools before
    producing a final answer. This replaces the one-shot tool execution
    in the legacy agent pipeline.
    """

    def __init__(self, client, max_iterations: int = None, context: Dict = None):
        """
        Args:
            client: OllamaClient instance (provides chat() and chat_stream())
            max_iterations: Max tool-calling rounds (default from config)
            context: Optional dict with principal_id, chat_id for context-aware tools
        """
        self.client = client
        self.max_iterations = max_iterations or REACT_MAX_ITERATIONS
        self.token_budget = REACT_TOKEN_BUDGET
        self.reflexion_max_retries = REFLEXION_MAX_RETRIES
        self.context = context or {}

    # ── Reflexion helpers ──────────────────────────────────────────
    # Tools whose errors should trigger Reflexion (self-correction)
    _REFLEXION_TOOLS = {"code_display", "run_command", "write_file"}

    @staticmethod
    def _is_reflexion_tool(tool_name: str) -> bool:
        """Check if a tool supports Reflexion (error → fix → retry)."""
        return tool_name in ReactLoop._REFLEXION_TOOLS

    @staticmethod
    def _build_reflexion_observation(tool_name: str, error_text: str, retry_count: int, max_retries: int) -> str:
        """Build a Reflexion-aware observation that prompts self-correction."""
        return (
            f"[Tool Result: {tool_name}]\n"
            f"ERROR: {error_text}\n\n"
            f"Reflexion attempt {retry_count}/{max_retries}: "
            f"The code had an error. Analyze the error, fix the issue, and try again. "
            f"If you cannot fix it after examining the error, give your best answer with an explanation of the problem."
        )

    # ── Token budget estimation ────────────────────────────────────
    @staticmethod
    def _estimate_tokens(messages: List[Dict]) -> int:
        """Rough token estimate: ~4 chars per token (conservative)."""
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return total_chars // 4

    # ── Think-block filtering ──────────────────────────────────────
    _THINK_RE = re.compile(r"<think>.*?</think>\s*", flags=re.DOTALL)

    @staticmethod
    def _strip_think_blocks(text: str) -> str:
        """Remove <think>…</think> blocks from a complete string."""
        return ReactLoop._THINK_RE.sub("", text).lstrip()

    def _build_system_message(
        self,
        understanding: str = "",
        plan: str = "",
        user_memory: str = "",
        search_context: str = "",
        complexity: int = 5,
    ) -> str:
        """Build the system message with tool definitions and context."""
        extra_parts = []

        if user_memory:
            extra_parts.append(f"Context about the user:\n{user_memory}")
        if understanding:
            extra_parts.append(f"Your analysis:\n{understanding}")
        if plan:
            extra_parts.append(f"Your plan:\n{plan}")
        if search_context:
            extra_parts.append(f"Web search results:\n{search_context}")

        # Inject repo map when workspace exists (helps with filesystem tools)
        try:
            from .repo_map import generate_repo_map
            repo_map = generate_repo_map()
            if repo_map:
                extra_parts.append(repo_map)
        except Exception as e:
            logger.debug(f"Repo map generation skipped: {e}")

        extra_context = "\n\n".join(extra_parts) if extra_parts else ""

        tool_defs = TOOL_PROMPT_SECTION

        return REACT_SYSTEM_PROMPT.format(
            tool_definitions=tool_defs,
            extra_context=extra_context,
        )

    def _build_messages(
        self,
        question: str,
        context_messages: List[Dict] = None,
        understanding: str = "",
        plan: str = "",
        user_memory: str = "",
        search_context: str = "",
        complexity: int = 5,
    ) -> List[Dict]:
        """Build the initial messages array for /api/chat."""
        messages = []

        # System message with tools and context
        system_content = self._build_system_message(
            understanding=understanding,
            plan=plan,
            user_memory=user_memory,
            search_context=search_context,
            complexity=complexity,
        )
        messages.append({"role": "system", "content": system_content})

        # Prior conversation context — cap at 20 messages × 4000 chars
        # to stay within context window and match direct-chat path.
        if context_messages:
            for msg in context_messages[-20:]:
                role = msg.get("role", "user")
                content = (msg.get("content") or "")[:4000]
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})

        # Current question
        messages.append({"role": "user", "content": question})

        return messages

    def _extract_tool_calls(self, response):
        """Extract tool calls from response using XML parser."""
        if isinstance(response, str):
            return parse_tool_calls(response)
        return []

    def _get_response_content(self, response) -> str:
        """Extract text content from response.

        Strips <think>...</think> blocks and residual <tool_call> XML from
        the visible output.  If stripping produces empty content, falls back
        to the text inside the think blocks (the model put its answer there).
        """
        raw = response if isinstance(response, str) else ""
        # Extract think-block content before stripping (fallback if stripped is empty)
        think_contents = re.findall(r"<think>(.*?)</think>", raw, flags=re.DOTALL)
        # Strip Qwen3 thinking blocks — keep only the visible answer
        content = re.sub(r"<think>.*?</think>\s*", "", raw, flags=re.DOTALL).strip()
        # Strip any residual <tool_call> XML so it never reaches the user
        content = re.sub(
            r"</?tool_call[^>]*>", "", content, flags=re.IGNORECASE
        ).strip()
        if not content and think_contents:
            # Model put entire answer inside think blocks — use it as the answer
            content = "\n".join(tc.strip() for tc in think_contents if tc.strip())
            logger.info("Think-block fallback: extracted %d chars from think blocks", len(content))
        return content

    def _run_tools(self, tool_calls) -> List[ToolResult]:
        """Execute parsed tool calls and return results."""
        results = []
        for tc in tool_calls:
            try:
                with track_tool_call(tc.name) as tracker:
                    success, output = execute_tool(tc.name, tc.params, context=self.context)
                    if not success:
                        tracker.set_status("error")
                    results.append(ToolResult(success=success, output=output))
            except Exception as e:
                logger.error(f"Tool execution error ({tc.name}): {e}")
                results.append(ToolResult(success=False, output="", error=str(e)))
        return results

    def execute(
        self,
        question: str,
        context_messages: List[Dict] = None,
        understanding: str = "",
        plan: str = "",
        user_memory: str = "",
        search_context: str = "",
        max_tokens: int = 24000,
        temperature: float = 0.7,
        timeout: int = 300,
        complexity: int = 5,
    ) -> ReactResult:
        """
        Run the ReAct loop (non-streaming).

        Returns a ReactResult with the final answer and metadata.
        """
        messages = self._build_messages(
            question, context_messages, understanding, plan, user_memory, search_context,
            complexity=complexity,
        )

        tools_used = []
        tool_log = []
        reflexion_counts = {}  # Track retries per tool type

        for iteration in range(self.max_iterations):
            with track_agent_pass("react_iteration"):
                # THINK: Ask the model (think=False to save tokens)
                response = self.client.chat(
                    messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout,
                    pass_name="execute",
                    complexity=complexity,
                    think=False,
                )

                if not response:
                    logger.warning("Empty response from Ollama chat")
                    break

                # CHECK: Does response contain tool calls?
                tool_calls = self._extract_tool_calls(response)
                content = self._get_response_content(response)

                if not tool_calls:
                    # No tools — model is done, this is the final answer
                    return ReactResult(
                        answer=content,
                        tools_used=tools_used,
                        iterations=iteration + 1,
                        tool_results=tool_log,
                    )

                # ACT: Execute the first tool call only (one per turn)
                tc = tool_calls[0]
                logger.info(f"ReAct iteration {iteration + 1}: calling {tc.name}")
                tools_used.append(tc.name)

                results = self._run_tools([tc])
                result = results[0]

                tool_log.append({
                    "tool": tc.name,
                    "params": tc.params,
                    "success": result.success,
                    "output": result.output[:500],  # Truncate for logging
                })

                # OBSERVE: Add assistant response + tool result to messages
                messages.append({"role": "assistant", "content": content})

                if not result.success and self._is_reflexion_tool(tc.name):
                    # Reflexion: code execution error → prompt self-correction
                    reflexion_counts[tc.name] = reflexion_counts.get(tc.name, 0) + 1
                    retry_count = reflexion_counts[tc.name]
                    error_text = result.error or result.output

                    if retry_count <= self.reflexion_max_retries:
                        logger.info(
                            f"Reflexion retry {retry_count}/{self.reflexion_max_retries} "
                            f"for {tc.name}"
                        )
                        observation = self._build_reflexion_observation(
                            tc.name, error_text, retry_count, self.reflexion_max_retries
                        )
                    else:
                        logger.info(
                            f"Reflexion max retries exceeded for {tc.name}, "
                            f"proceeding normally"
                        )
                        observation = (
                            f"[Tool Result: {tc.name}]\n"
                            f"Error: {error_text}\n\n"
                            f"Max retry attempts reached. Give your final answer "
                            f"with an explanation of what went wrong."
                        )
                else:
                    result_text = (
                        result.output if result.success
                        else f"Error: {result.error or result.output}"
                    )
                    observation = (
                        f"[Tool Result: {tc.name}]\n{result_text}\n\n"
                        f"Continue based on this result. Use another tool if needed, "
                        f"or give your final answer."
                    )

                messages.append({"role": "user", "content": observation})

                # TOKEN BUDGET: Force final answer if approaching context limit
                estimated_tokens = self._estimate_tokens(messages)
                if estimated_tokens > self.token_budget:
                    logger.info(
                        f"ReAct token budget exceeded (~{estimated_tokens} tokens > {self.token_budget}), "
                        f"forcing final answer at iteration {iteration + 1}"
                    )
                    break

        # Hit max iterations or token budget — force a final answer
        logger.info(f"ReAct hit max iterations ({self.max_iterations}), forcing final answer")
        messages.append({
            "role": "user",
            "content": "You've used all your tool calls. Now give your final answer based on everything you've gathered.",
        })
        response = self.client.chat(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            pass_name="execute",
            complexity=complexity,
            think=False,
        )

        return ReactResult(
            answer=response or "I was unable to generate a response.",
            tools_used=tools_used,
            iterations=self.max_iterations,
            tool_results=tool_log,
        )

    def execute_streaming(
        self,
        question: str,
        context_messages: List[Dict] = None,
        understanding: str = "",
        plan: str = "",
        user_memory: str = "",
        search_context: str = "",
        max_tokens: int = 24000,
        temperature: float = 0.7,
        timeout: int = 300,
        complexity: int = 5,
        messages: List[Dict] = None,
    ) -> Generator[Dict, None, None]:
        """
        Run the ReAct loop with streaming.

        Yields SSE-compatible dicts:
            {"phase": "tool_execution", "message": "Running the tool..."}
            {"phase": "tool_result", "message": "Calculator: 112"}
            {"token": "..."} — during final answer streaming
            {"react_done": True, "tools_used": [...], "iterations": N}

        If *messages* is provided (pre-assembled by PromptAssembler), it is
        used directly, skipping the internal _build_messages() call.
        """
        if messages is not None:
            # Caller supplied pre-assembled messages (knowledge-enriched, budget-aware)
            pass
        else:
            messages = self._build_messages(
                question, context_messages, understanding, plan, user_memory, search_context,
                complexity=complexity,
            )

        tools_used = []
        reflexion_counts = {}  # Track retries per tool type

        for iteration in range(self.max_iterations):
            with track_agent_pass("react_iteration"):
                # Non-final iterations: use non-streaming to detect tool calls.
                # think=False avoids burning output tokens on hidden reasoning
                # and prevents proxy timeouts during idle SSE gaps.
                response = self.client.chat(
                    messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout,
                    pass_name="execute",
                    complexity=complexity,
                    think=False,
                )

                if not response:
                    logger.warning("Empty response from Ollama chat in streaming mode")
                    break

                # CHECK: Does response contain tool calls?
                tool_calls = self._extract_tool_calls(response)
                content = self._get_response_content(response)

                if not tool_calls:
                    # Final answer — stream it token by token
                    content = self._strip_think_blocks(content)
                    for char_chunk in self._chunk_text(content):
                        yield {"token": char_chunk}

                    yield {
                        "react_done": True,
                        "tools_used": tools_used,
                        "iterations": iteration + 1,
                    }
                    return

                # ACT: Execute the first tool call
                tc = tool_calls[0]
                logger.info(f"ReAct streaming iteration {iteration + 1}: calling {tc.name}")
                tools_used.append(tc.name)

                yield format_phase_update(
                    "tool_execution",
                    f"Using {tc.name}...",
                )

                results = self._run_tools([tc])
                result = results[0]

                status = "done" if result.success else "error"
                yield format_phase_update(
                    "tool_result",
                    f"{tc.name}: {status}",
                )

                # OBSERVE: Add to conversation with Reflexion support
                messages.append({"role": "assistant", "content": content})

                if not result.success and self._is_reflexion_tool(tc.name):
                    # Reflexion: code execution error → prompt self-correction
                    reflexion_counts[tc.name] = reflexion_counts.get(tc.name, 0) + 1
                    retry_count = reflexion_counts[tc.name]
                    error_text = result.error or result.output

                    if retry_count <= self.reflexion_max_retries:
                        logger.info(
                            f"Reflexion retry {retry_count}/{self.reflexion_max_retries} "
                            f"for {tc.name}"
                        )
                        observation = self._build_reflexion_observation(
                            tc.name, error_text, retry_count, self.reflexion_max_retries
                        )
                        yield format_phase_update(
                            "tool_execution",
                            f"Reflexion: fixing error ({retry_count}/{self.reflexion_max_retries})...",
                        )
                    else:
                        observation = (
                            f"[Tool Result: {tc.name}]\n"
                            f"Error: {error_text}\n\n"
                            f"Max retry attempts reached. Give your final answer "
                            f"with an explanation of what went wrong."
                        )
                else:
                    result_text = (
                        result.output if result.success
                        else f"Error: {result.error or result.output}"
                    )
                    observation = (
                        f"[Tool Result: {tc.name}]\n{result_text}\n\n"
                        f"Continue based on this result. Use another tool if needed, "
                        f"or give your final answer."
                    )

                messages.append({"role": "user", "content": observation})

                # TOKEN BUDGET: Force final answer if approaching context limit
                estimated_tokens = self._estimate_tokens(messages)
                if estimated_tokens > self.token_budget:
                    logger.info(
                        f"ReAct streaming token budget exceeded (~{estimated_tokens} tokens > "
                        f"{self.token_budget}), forcing final answer at iteration {iteration + 1}"
                    )
                    break

        # Max iterations or token budget — force final answer with streaming
        logger.info(f"ReAct streaming hit max iterations ({self.max_iterations})")
        messages.append({
            "role": "user",
            "content": "You've used all your tool calls. Now give your final answer based on everything you've gathered.",
        })

        # Collect streaming response with think disabled — save all tokens
        # for the actual answer instead of burning budget on reasoning.
        raw_tokens = []
        for token in self.client.chat_stream(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            pass_name="execute",
            complexity=complexity,
            think=False,
        ):
            if isinstance(token, dict) and "__done_reason" in token:
                continue
            raw_tokens.append(token)
        final_text = self._strip_think_blocks("".join(raw_tokens))
        for chunk in self._chunk_text(final_text):
            yield {"token": chunk}

        yield {
            "react_done": True,
            "tools_used": tools_used,
            "iterations": self.max_iterations,
        }

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 4) -> Generator[str, None, None]:
        """Split text into small chunks for simulated streaming."""
        for i in range(0, len(text), chunk_size):
            yield text[i : i + chunk_size]
