"""
Trinity Agentic Pipeline - Orchestrator

Multi-pass reasoning pipeline that makes Trinity feel intelligent.
Automatically routes simple vs complex questions and manages pass execution.
Integrates web search when current/real-time information is needed.

v4.0 Enhancements:
- Multi-model support (Tier 2+): Fast model for classification, smart for execution
- Tool integration: Calculator, code display, document search
- Self-consistency voting for complex questions
- Semantic memory retrieval
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Dict, Generator, List, Optional

import requests

# Observability (Phase 2B) - Direct import (Phase 5.5A cleanup)
from middleware.observability import record_complexity, record_routing, track_agent_pass

from .agent_prompts import (
    CritiqueResult,
    PlanResult,
    UnderstandingResult,
    build_critique_prompt,
    build_execute_prompt,
    build_plan_prompt,
    build_refine_prompt,
    build_understand_prompt,
    parse_critique,
    parse_plan,
    parse_understanding,
)
from .complexity import (
    ComplexityLevel,
    analyze_question,
    get_pass_count,
)
from .loading_messages import format_phase_update
from .search import format_search_context, is_search_available, search_web
from .tools import detect_tools_needed

# Import new v4.0 modules (with graceful fallback)
try:
    from config import REACT_ENABLED
    from .react_loop import ReactLoop

    REACT_AVAILABLE = True
except ImportError as e:
    logging.warning(f"ReAct loop not available: {e}")
    REACT_AVAILABLE = False
    REACT_ENABLED = False

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Timeout per pass (seconds) - GENEROUS for deep thinking
# These are connection timeouts, not "how long can it think"
# Streaming keeps connection alive, so these are really just for non-streaming calls
PASS_TIMEOUTS = {
    "understand": 120,  # 2 min - may need to reason about complex questions
    "plan": 120,  # 2 min - planning complex multi-step solutions
    "execute": 300,  # 5 min - main response generation, can be very long
    "critique": 180,  # 3 min - thorough critique takes time
    "refine": 600,  # 10 min - complete rewrite if needed
    "search": 30,  # 30s - web search timeout
}

# Token limits per pass - very generous for thorough responses
PASS_TOKEN_LIMITS = {
    "understand": 2000,  # Detailed understanding
    "plan": 2000,  # Comprehensive plans
    "execute": 24000,  # Long, detailed responses (code, essays, complete files)
    "critique": 2000,  # Thorough critique
    "refine": 24000,  # Complete improved response
}

# Critique threshold - if score >= this, skip refinement
CRITIQUE_THRESHOLD = 7

# Max refinement attempts
MAX_REFINE_ATTEMPTS = 2

# Regex to strip <think>...</think> blocks from streaming tokens
_THINK_OPEN = re.compile(r"<think>", re.IGNORECASE)
_THINK_CLOSE = re.compile(r"</think>", re.IGNORECASE)

# Multi-model configuration (Tier 2+ only)
# These are set from config.py at runtime
MULTI_MODEL_ENABLED = False
FAST_MODEL = None
SMART_MODEL = None
REASONING_MODEL = None


def _format_user_memory(user_memory: Dict) -> str:
    """Format user memory dict into clean text for LLM consumption.

    Avoids passing raw Python dict repr (e.g. {'facts': [...]}) which
    confuses the model. Produces a clean bullet list instead.
    """
    if not user_memory:
        return ""
    facts = user_memory.get("facts", [])
    if not facts:
        return ""
    return "\n".join(f"- {fact}" for fact in facts[:10])


def _format_understanding(understanding) -> str:
    """Format UnderstandingResult into clean text for LLM consumption.

    Avoids passing raw dataclass repr which looks like Python source code.
    """
    if not understanding:
        return ""
    parts = []
    if hasattr(understanding, "question_type"):
        parts.append(f"Type: {understanding.question_type}")
    if hasattr(understanding, "domains") and understanding.domains:
        parts.append(f"Domains: {', '.join(understanding.domains)}")
    if hasattr(understanding, "complexity"):
        parts.append(f"Complexity: {understanding.complexity}/10")
    if hasattr(understanding, "summary"):
        parts.append(f"Summary: {understanding.summary}")
    if hasattr(understanding, "key_challenges") and understanding.key_challenges:
        parts.append(f"Challenges: {understanding.key_challenges}")
    return "\n".join(parts)


def init_multi_model_config():
    """Initialize multi-model configuration from config.py"""
    global MULTI_MODEL_ENABLED, FAST_MODEL, SMART_MODEL, REASONING_MODEL
    try:
        import os
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config import FAST_MODEL as FM
        from config import MULTI_MODEL_ENABLED as MME
        from config import REASONING_MODEL as RM
        from config import SMART_MODEL as SM

        MULTI_MODEL_ENABLED = MME
        FAST_MODEL = FM
        SMART_MODEL = SM
        REASONING_MODEL = RM
        if MULTI_MODEL_ENABLED:
            logger.info(f"🎯 Multi-model enabled: fast={FM}, smart={SM}, reasoning={RM}")
    except ImportError:
        logger.warning("Multi-model config not available")


# Initialize on module load
init_multi_model_config()


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class AgentResponse:
    """Final response from the agent pipeline"""

    answer: str
    complexity: ComplexityLevel
    passes_used: int
    understanding: Optional[UnderstandingResult] = None
    plan: Optional[PlanResult] = None
    critique: Optional[CritiqueResult] = None
    search_performed: bool = False
    search_query: Optional[str] = None
    total_time_seconds: float = 0.0
    # v4.0 fields
    tools_used: List[str] = None
    voting_confidence: Optional[float] = None
    model_used: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        result = {
            "answer": self.answer,
            "complexity": self.complexity,
            "passes_used": self.passes_used,
            "total_time_seconds": self.total_time_seconds,
            "search_performed": self.search_performed,
        }
        if self.search_query:
            result["search_query"] = self.search_query
        if self.understanding:
            result["understanding"] = {
                "type": self.understanding.question_type,
                "domains": self.understanding.domains,
                "complexity": self.understanding.complexity,
                "summary": self.understanding.summary,
            }
        if self.plan:
            result["plan"] = {"steps": self.plan.steps, "approach": self.plan.approach}
        if self.critique:
            result["critique"] = {"score": self.critique.score, "verdict": self.critique.verdict}
        # v4.0 fields
        if self.tools_used:
            result["tools_used"] = self.tools_used
        if self.voting_confidence is not None:
            result["voting_confidence"] = self.voting_confidence
        if self.model_used:
            result["model_used"] = self.model_used
        return result


# ============================================================================
# OLLAMA INTERFACE
# ============================================================================


class OllamaClient:
    """Client for Ollama API calls with multi-model support"""

    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.host = host
        self.model = model  # Default model

    def _get_model_for_pass(self, pass_name: str, complexity: int = 5) -> str:
        """
        Select the appropriate model based on pass type and complexity.

        For Tier 2+, uses specialized models:
        - Fast model (phi3:mini): understand, plan, critique
        - Smart model (llama3.1:8b): simple/medium execute
        - Reasoning model (qwen2.5:32b): complex execute, refine

        For Tier 1, always uses the default model.
        """
        if not MULTI_MODEL_ENABLED:
            return self.model

        # Fast model for classification passes
        if pass_name in ["understand", "plan", "critique"]:
            return FAST_MODEL or self.model

        # Reasoning model for complex tasks
        if pass_name in ["refine"] or (pass_name == "execute" and complexity >= 7):
            return REASONING_MODEL or SMART_MODEL or self.model

        # Smart model for general execution
        return SMART_MODEL or self.model

    def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 30,
        pass_name: str = None,
        complexity: int = 5,
    ) -> str:
        """Generate a response (non-streaming)"""
        model = self._get_model_for_pass(pass_name, complexity) if pass_name else self.model

        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens, "temperature": temperature, "num_ctx": 32768},
                },
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"Ollama error: {response.status_code}")
                return ""

            result = response.json()
            return result.get("response", "")

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama timeout after {timeout}s")
            return ""
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return ""

    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 60,
        pass_name: str = None,
        complexity: int = 5,
    ) -> Generator[str, None, None]:
        """Generate a response with streaming"""
        model = self._get_model_for_pass(pass_name, complexity) if pass_name else self.model

        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {"num_predict": max_tokens, "temperature": temperature, "num_ctx": 32768},
                },
                stream=True,
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"Ollama error: {response.status_code}")
                return

            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            yield {"__done_reason": chunk.get("done_reason", "stop")}
                            break
                    except json.JSONDecodeError:
                        continue

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama stream timeout after {timeout}s")
        except Exception as e:
            logger.error(f"Ollama stream error: {e}")

    def chat(
        self,
        messages: List[Dict],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 60,
        pass_name: str = None,
        complexity: int = 5,
        tools: List[Dict] = None,
        raw_message: bool = False,
    ) -> str:
        """Call Ollama /api/chat with messages array (non-streaming).

        Args:
            tools: Optional native tool definitions for Ollama function calling
            raw_message: If True, return the full message dict (for native tool call extraction)
        """
        model = self._get_model_for_pass(pass_name, complexity) if pass_name else self.model

        try:
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": temperature, "num_ctx": 32768},
            }
            if tools:
                payload["tools"] = tools

            response = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"Ollama chat error: {response.status_code}")
                return {} if raw_message else ""

            result = response.json()
            message = result.get("message", {})

            if raw_message:
                return message
            return message.get("content", "")

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama chat timeout after {timeout}s")
            return {} if raw_message else ""
        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
            return {} if raw_message else ""

    def chat_stream(
        self,
        messages: List[Dict],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 60,
        pass_name: str = None,
        complexity: int = 5,
    ) -> Generator[str, None, None]:
        """Call Ollama /api/chat with messages array (streaming)."""
        model = self._get_model_for_pass(pass_name, complexity) if pass_name else self.model

        try:
            response = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "options": {"num_predict": max_tokens, "temperature": temperature, "num_ctx": 32768},
                },
                stream=True,
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"Ollama chat stream error: {response.status_code}")
                return

            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            yield {"__done_reason": chunk.get("done_reason", "stop")}
                            break
                    except json.JSONDecodeError:
                        continue

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama chat stream timeout after {timeout}s")
        except Exception as e:
            logger.error(f"Ollama chat stream error: {e}")


# ============================================================================
# AGENT PIPELINE
# ============================================================================


class AgentPipeline:
    """
    Multi-pass reasoning pipeline.

    Routes questions by complexity:
    - Simple: Direct answer (1 pass)
    - Medium: Understand → Execute → Critique (3 passes)
    - Complex: Understand → Plan → Execute → Critique → Refine (5 passes)
    """

    def __init__(self, ollama_host: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.client = OllamaClient(ollama_host, model)

    def _get_react_loop(self, principal_id: str = None) -> "ReactLoop":
        """Create a ReactLoop with user context for this request."""
        if not REACT_AVAILABLE:
            return None
        context = {}
        if principal_id:
            context["principal_id"] = principal_id
        return ReactLoop(self.client, context=context)

    def _should_use_react(self, question: str, understanding=None, analysis=None) -> bool:
        """Check if this query should use the ReAct loop."""
        if not REACT_AVAILABLE or not REACT_ENABLED:
            return False
        # Use pre-computed analysis from analyze_question() if available
        if analysis and hasattr(analysis, "tools_needed") and analysis.tools_needed:
            return True
        # Check if understanding pass detected tools
        if understanding and hasattr(understanding, "tools_needed") and understanding.tools_needed:
            return True
        # Fallback to heuristic detection
        tools = detect_tools_needed(question)
        return len(tools) > 0

    def _filter_think_blocks(
        self, token_stream: Generator, accumulator: list
    ) -> Generator[str, None, None]:
        """Filter <think>...</think> blocks from a streaming token generator.

        Qwen3 (and some other models) emit <think>reasoning</think> before
        the actual answer. These must be stripped so the frontend never sees
        raw XML tags. Tokens inside think blocks are silently discarded.
        Works for Qwen2.5 too (no-op if no think blocks present).

        Args:
            token_stream: Generator yielding str tokens or dict metadata
            accumulator: Mutable list — we append the clean full_response text
                         so the caller can read it after iteration.
        Yields:
            str tokens with think blocks removed.
            dict metadata tokens (e.g. __done_reason) are yielded unchanged.
        """
        inside_think = False
        buf = ""  # Buffer to handle partial tags across token boundaries

        for token in token_stream:
            # Pass through metadata dicts unchanged
            if isinstance(token, dict):
                yield token
                continue

            buf += token

            # Process buffer looking for think tags
            while buf:
                if inside_think:
                    # Look for closing </think>
                    close_match = _THINK_CLOSE.search(buf)
                    if close_match:
                        # Discard everything up to and including </think>
                        buf = buf[close_match.end():]
                        inside_think = False
                        continue
                    else:
                        # Still inside think block — discard entire buffer
                        # but keep last 8 chars in case </think> spans tokens
                        if len(buf) > 8:
                            buf = buf[-8:]
                        break
                else:
                    # Look for opening <think>
                    open_match = _THINK_OPEN.search(buf)
                    if open_match:
                        # Yield text before <think>
                        before = buf[:open_match.start()]
                        if before:
                            accumulator.append(before)
                            yield before
                        buf = buf[open_match.end():]
                        inside_think = True
                        continue
                    else:
                        # No think tag — yield text (keep last 7 chars for partial <think>)
                        if len(buf) > 7:
                            safe = buf[:-7]
                            buf = buf[-7:]
                            accumulator.append(safe)
                            yield safe
                        break

        # Flush remaining buffer
        if buf and not inside_think:
            accumulator.append(buf)
            yield buf

    def process(
        self,
        question: str,
        context_messages: List[Dict] = None,
        user_memory: Dict = None,
        force_complexity: ComplexityLevel = None,
    ) -> AgentResponse:
        """
        Process a question through the appropriate pipeline.

        Args:
            question: The user's question
            context_messages: Previous conversation context
            user_memory: Stored facts about the user
            force_complexity: Override automatic classification

        Returns:
            AgentResponse with the final answer and metadata
        """
        start_time = time.time()

        # Analyze question (complexity + search needs)
        analysis = analyze_question(question)
        complexity = force_complexity or analysis.complexity
        passes_needed = get_pass_count(complexity)

        # Record observability metrics
        record_complexity(complexity)
        record_routing("langgraph" if complexity == "complex" else "legacy")

        logger.info(
            f"🧠 Agent: {complexity} question, {passes_needed} passes, "
            f"search={analysis.needs_search}, tools={analysis.tools_needed}"
        )

        context_messages = context_messages or []
        user_memory = user_memory or {}

        understanding = None
        plan = None
        critique = None
        answer = ""
        search_context = ""
        search_performed = False

        # === WEB SEARCH (if needed) ===
        if analysis.needs_search and is_search_available():
            logger.info(f"🔍 Performing web search: {analysis.search_query}")
            search_result = search_web(analysis.search_query, count=5)
            if not search_result.error and search_result.results:
                search_context = format_search_context(search_result)
                search_performed = True
                logger.info(f"🔍 Search found {len(search_result.results)} results")

        try:
            if complexity == "simple":
                # === SIMPLE: Direct answer ===
                answer = self._pass_execute_simple(
                    question, context_messages, user_memory, search_context
                )

            elif complexity == "medium":
                # === MEDIUM: Understand → Execute → Critique ===
                understanding = self._pass_understand(question, context_messages)
                answer = self._pass_execute(
                    question, understanding, None, context_messages, user_memory, search_context
                )
                critique = self._pass_critique(question, answer)

                # Refine if score is low
                if critique and critique.score < CRITIQUE_THRESHOLD:
                    answer = self._pass_refine(question, answer, critique)

            else:
                # === COMPLEX: Full pipeline ===
                understanding = self._pass_understand(question, context_messages)
                plan = self._pass_plan(question, understanding)
                answer = self._pass_execute(
                    question, understanding, plan, context_messages, user_memory, search_context
                )
                critique = self._pass_critique(question, answer)

                # Refine if score is low (up to MAX_REFINE_ATTEMPTS times)
                refine_attempts = 0
                while (
                    critique
                    and critique.score < CRITIQUE_THRESHOLD
                    and refine_attempts < MAX_REFINE_ATTEMPTS
                ):
                    previous_score = critique.score
                    answer = self._pass_refine(question, answer, critique)
                    critique = self._pass_critique(question, answer)
                    refine_attempts += 1

                    # Stop if not improving
                    if critique.score <= previous_score:
                        logger.info(
                            f"Stopping refinement - score not improving ({previous_score} → {critique.score})"
                        )
                        break

        except Exception as e:
            logger.error(f"Agent pipeline error: {e}")
            if not answer:
                answer = f"I encountered an issue while processing your question. Let me give you a direct response:\n\n{self._pass_execute_simple(question, context_messages, user_memory, search_context)}"

        total_time = time.time() - start_time

        return AgentResponse(
            answer=answer,
            complexity=complexity,
            passes_used=passes_needed,
            understanding=understanding,
            plan=plan,
            critique=critique,
            search_performed=search_performed,
            search_query=analysis.search_query if search_performed else None,
            total_time_seconds=round(total_time, 2),
        )

    def process_streaming(
        self,
        question: str,
        context_messages: List[Dict] = None,
        user_memory: Dict = None,
        force_complexity: ComplexityLevel = None,
        semantic_context: List[Dict] = None,
        enable_voting: bool = None,
        principal_id: str = None,
        **kwargs,  # Accept additional v4.0 options
    ) -> Generator[Dict, None, None]:
        """
        Process with streaming - yields progress updates and tokens.

        V4.0 Enhancements:
        - semantic_context: Pre-retrieved relevant context from vector DB
        - enable_voting: Override for self-consistency voting
        - principal_id: User ID for tool execution context

        Yields whimsical loading messages during thinking phases,
        then streams tokens during generation.

        Yields:
            {"phase": "understanding", "message": "Pondering the question..."}
            {"token": "Hello"}
            {"done": True, "response": AgentResponse}
        """
        start_time = time.time()

        # Analyze question (complexity + search needs)
        yield format_phase_update("classifying")  # "Examining the question..."

        analysis = analyze_question(question)
        complexity = force_complexity or analysis.complexity
        passes_needed = get_pass_count(complexity)

        # Record observability metrics
        record_complexity(complexity)
        record_routing("langgraph" if complexity == "complex" else "legacy")

        logger.info(
            f"🧠 Agent streaming: {complexity} question, {passes_needed} passes, "
            f"search={analysis.needs_search}, tools={analysis.tools_needed}"
        )

        context_messages = context_messages or []
        user_memory = user_memory or {}

        understanding = None
        plan = None
        critique = None
        full_response = ""
        search_context = ""
        search_performed = False
        last_done_reason = "stop"  # Track truncation from final streaming pass

        # === WEB SEARCH (if needed) ===
        if analysis.needs_search and is_search_available():
            yield format_phase_update("searching")  # "Scouring the web..."
            search_result = search_web(
                analysis.search_query, count=5, timeout=PASS_TIMEOUTS["search"]
            )
            if not search_result.error and search_result.results:
                search_context = format_search_context(search_result)
                search_performed = True
                yield {
                    "phase": "searching",
                    "message": f"Found {len(search_result.results)} sources...",
                }

        try:
            if complexity == "simple":
                # === SIMPLE: Direct streaming ===
                yield format_phase_update("executing")  # "Brewing the answer..."

                if self._should_use_react(question, analysis=analysis):
                    # ReAct loop for tool-using queries
                    for event in self._get_react_loop(principal_id).execute_streaming(
                        question=question,
                        context_messages=context_messages,
                        user_memory=_format_user_memory(user_memory),
                        search_context=search_context,
                        max_tokens=PASS_TOKEN_LIMITS["execute"],
                        timeout=PASS_TIMEOUTS["execute"],
                    ):
                        if "token" in event:
                            full_response += event["token"]
                        yield event
                else:
                    prompt = build_execute_prompt(
                        question, None, None, context_messages, user_memory, search_context
                    )
                    filtered_parts = []
                    for token in self._filter_think_blocks(
                        self.client.generate_stream(
                            prompt, PASS_TOKEN_LIMITS["execute"], timeout=PASS_TIMEOUTS["execute"]
                        ),
                        filtered_parts,
                    ):
                        if isinstance(token, dict) and "__done_reason" in token:
                            last_done_reason = token["__done_reason"]
                            continue
                        yield {"token": token}
                    full_response = "".join(filtered_parts)

            elif complexity == "medium":
                # === MEDIUM: Understand + Execute + Critique ===
                yield format_phase_update("understanding")  # "Pondering the question..."
                understanding = self._pass_understand(question, context_messages)

                yield format_phase_update("executing")  # "Crafting the response..."

                if self._should_use_react(question, understanding, analysis=analysis):
                    for event in self._get_react_loop(principal_id).execute_streaming(
                        question=question,
                        context_messages=context_messages,
                        understanding=_format_understanding(understanding),
                        user_memory=_format_user_memory(user_memory),
                        search_context=search_context,
                        max_tokens=PASS_TOKEN_LIMITS["execute"],
                        timeout=PASS_TIMEOUTS["execute"],
                        complexity=5,
                    ):
                        if "token" in event:
                            full_response += event["token"]
                        yield event
                else:
                    prompt = build_execute_prompt(
                        question, understanding, None, context_messages, user_memory, search_context
                    )
                    filtered_parts = []
                    for token in self._filter_think_blocks(
                        self.client.generate_stream(
                            prompt, PASS_TOKEN_LIMITS["execute"], timeout=PASS_TIMEOUTS["execute"]
                        ),
                        filtered_parts,
                    ):
                        if isinstance(token, dict) and "__done_reason" in token:
                            last_done_reason = token["__done_reason"]
                            continue
                        yield {"token": token}
                    full_response = "".join(filtered_parts)

                yield format_phase_update("critiquing")  # "Polishing the prose..."
                critique = self._pass_critique(question, full_response)

                if critique and critique.score < CRITIQUE_THRESHOLD:
                    yield {
                        "phase": "refining",
                        "message": f"Enhancing quality (score: {critique.score}/10)...",
                    }
                    original_response = full_response
                    full_response = ""
                    prompt = build_refine_prompt(question, original_response, critique)
                    filtered_parts = []
                    for token in self._filter_think_blocks(
                        self.client.generate_stream(
                            prompt, PASS_TOKEN_LIMITS["refine"], timeout=PASS_TIMEOUTS["refine"]
                        ),
                        filtered_parts,
                    ):
                        if isinstance(token, dict) and "__done_reason" in token:
                            last_done_reason = token["__done_reason"]
                            continue
                        yield {"token": token}
                    full_response = "".join(filtered_parts)

            else:
                # === COMPLEX: Full pipeline ===
                yield format_phase_update("understanding")  # "Meditating on the problem..."
                understanding = self._pass_understand(question, context_messages)

                yield format_phase_update("planning")  # "Charting the course..."
                plan = self._pass_plan(question, understanding)

                if plan and plan.steps:
                    yield {"phase": "planning", "message": f"Mapped {len(plan.steps)} steps..."}

                yield format_phase_update("executing")  # "Weaving the words..."

                if self._should_use_react(question, understanding, analysis=analysis):
                    plan_str = "\n".join(f"{i+1}. {s}" for i, s in enumerate(plan.steps)) if plan and plan.steps else ""
                    for event in self._get_react_loop(principal_id).execute_streaming(
                        question=question,
                        context_messages=context_messages,
                        understanding=_format_understanding(understanding),
                        plan=plan_str,
                        user_memory=_format_user_memory(user_memory),
                        search_context=search_context,
                        max_tokens=PASS_TOKEN_LIMITS["execute"],
                        timeout=PASS_TIMEOUTS["execute"],
                        complexity=8,
                    ):
                        if "token" in event:
                            full_response += event["token"]
                        yield event
                else:
                    prompt = build_execute_prompt(
                        question, understanding, plan, context_messages, user_memory, search_context
                    )
                    filtered_parts = []
                    for token in self._filter_think_blocks(
                        self.client.generate_stream(
                            prompt, PASS_TOKEN_LIMITS["execute"], timeout=PASS_TIMEOUTS["execute"]
                        ),
                        filtered_parts,
                    ):
                        if isinstance(token, dict) and "__done_reason" in token:
                            last_done_reason = token["__done_reason"]
                            continue
                        yield {"token": token}
                    full_response = "".join(filtered_parts)

                yield format_phase_update("critiquing")  # "Inspecting the work..."
                critique = self._pass_critique(question, full_response)

                if critique:
                    yield {
                        "phase": "critiquing",
                        "message": f"Quality score: {critique.score}/10...",
                    }

                if critique and critique.score < CRITIQUE_THRESHOLD:
                    yield format_phase_update("refining")  # "Perfecting the response..."

                    # Clear and stream refined response
                    yield {"clear": True}  # Signal frontend to clear previous response
                    original_response = full_response  # Save before clearing
                    full_response = ""

                    prompt = build_refine_prompt(question, original_response, critique)
                    filtered_parts = []
                    for token in self._filter_think_blocks(
                        self.client.generate_stream(
                            prompt, PASS_TOKEN_LIMITS["refine"], timeout=PASS_TIMEOUTS["refine"]
                        ),
                        filtered_parts,
                    ):
                        if isinstance(token, dict) and "__done_reason" in token:
                            last_done_reason = token["__done_reason"]
                            continue
                        yield {"token": token}
                    full_response = "".join(filtered_parts)

                    # Re-critique if needed
                    new_critique = self._pass_critique(question, full_response)
                    if new_critique:
                        critique = new_critique

        except Exception as e:
            logger.error(f"Agent streaming error: {e}")
            yield {"error": str(e)}

        total_time = time.time() - start_time

        # Final response
        response = AgentResponse(
            answer=full_response,
            complexity=complexity,
            passes_used=passes_needed,
            understanding=understanding,
            plan=plan,
            critique=critique,
            search_performed=search_performed,
            search_query=analysis.search_query if search_performed else None,
            total_time_seconds=round(total_time, 2),
        )

        yield {"done": True, "response": response.to_dict(), "done_reason": last_done_reason}

    # ========================================================================
    # INDIVIDUAL PASSES
    # ========================================================================

    def _pass_understand(self, question: str, context_messages: List[Dict] = None) -> Optional[UnderstandingResult]:
        """Pass 1: Understand the question"""
        logger.info("🤔 Pass 1: Understanding...")

        with track_agent_pass("understand") as tracker:
            prompt = build_understand_prompt(question, context_messages)
            response = self.client.generate(
                prompt,
                max_tokens=PASS_TOKEN_LIMITS["understand"],
                temperature=0.3,  # Lower temp for analysis
                timeout=PASS_TIMEOUTS["understand"],
            )

            if not response:
                tracker.set_status("error")
                return None

            return parse_understanding(response)

    def _pass_plan(self, question: str, understanding: UnderstandingResult) -> Optional[PlanResult]:
        """Pass 2: Create a plan"""
        logger.info("📋 Pass 2: Planning...")

        with track_agent_pass("plan") as tracker:
            prompt = build_plan_prompt(question, understanding)
            response = self.client.generate(
                prompt,
                max_tokens=PASS_TOKEN_LIMITS["plan"],
                temperature=0.3,
                timeout=PASS_TIMEOUTS["plan"],
            )

            if not response:
                tracker.set_status("error")
                return None

            return parse_plan(response)

    def _pass_execute(
        self,
        question: str,
        understanding: Optional[UnderstandingResult],
        plan: Optional[PlanResult],
        context_messages: List[Dict],
        user_memory: Dict,
        search_context: str = "",
    ) -> str:
        """Pass 3: Execute (non-streaming version)"""
        logger.info("✍️ Pass 3: Executing...")

        # Use ReAct loop if tools are needed
        if self._should_use_react(question, understanding):
            logger.info("🔄 Using ReAct loop for tool-assisted execution")
            plan_str = "\n".join(f"{i+1}. {s}" for i, s in enumerate(plan.steps)) if plan and plan.steps else ""
            result = self._get_react_loop().execute(
                question=question,
                context_messages=context_messages,
                understanding=_format_understanding(understanding),
                plan=plan_str,
                user_memory=_format_user_memory(user_memory),
                search_context=search_context,
                max_tokens=PASS_TOKEN_LIMITS["execute"],
                timeout=PASS_TIMEOUTS["execute"],
            )
            return result.answer

        with track_agent_pass("execute") as tracker:
            prompt = build_execute_prompt(
                question, understanding, plan, context_messages, user_memory, search_context
            )
            response = self.client.generate(
                prompt,
                max_tokens=PASS_TOKEN_LIMITS["execute"],
                temperature=0.7,
                timeout=PASS_TIMEOUTS["execute"],
            )

            if not response:
                tracker.set_status("error")
                return "I was unable to generate a response."

            return response

    def _pass_execute_simple(
        self,
        question: str,
        context_messages: List[Dict],
        user_memory: Dict,
        search_context: str = "",
    ) -> str:
        """Simple execute without understanding/plan"""
        logger.info("✍️ Simple execution...")

        # Use ReAct loop if tools are needed
        if self._should_use_react(question):
            logger.info("🔄 Using ReAct loop for simple tool-assisted execution")
            result = self._get_react_loop().execute(
                question=question,
                context_messages=context_messages,
                user_memory=_format_user_memory(user_memory),
                search_context=search_context,
                max_tokens=PASS_TOKEN_LIMITS["execute"],
                timeout=PASS_TIMEOUTS["execute"],
            )
            return result.answer

        prompt = build_execute_prompt(
            question, None, None, context_messages, user_memory, search_context
        )
        response = self.client.generate(
            prompt,
            max_tokens=PASS_TOKEN_LIMITS["execute"],
            temperature=0.7,
            timeout=PASS_TIMEOUTS["execute"],
        )

        return response or "I was unable to generate a response."

    def _pass_critique(self, question: str, response: str) -> Optional[CritiqueResult]:
        """Pass 4: Critique the response"""
        logger.info("🔍 Pass 4: Critiquing...")

        with track_agent_pass("critique") as tracker:
            prompt = build_critique_prompt(question, response)
            critique_response = self.client.generate(
                prompt,
                max_tokens=PASS_TOKEN_LIMITS["critique"],
                temperature=0.3,  # Lower temp for objective critique
                timeout=PASS_TIMEOUTS["critique"],
            )

            if not critique_response:
                tracker.set_status("error")
                return None

            critique = parse_critique(critique_response)

            # Sanity check: if no weaknesses found, be suspicious
            if (
                critique.weakness1 == "No weakness identified"
                and critique.weakness2 == "No weakness identified"
            ):
                logger.warning("Critique found no weaknesses - response might be suspicious")

            logger.info(f"🔍 Critique score: {critique.score}/10")
            return critique

    def _pass_refine(self, question: str, response: str, critique: CritiqueResult) -> str:
        """Pass 5: Refine based on critique"""
        logger.info(f"✨ Pass 5: Refining (addressing score {critique.score}/10)...")

        with track_agent_pass("refine") as tracker:
            prompt = build_refine_prompt(question, response, critique)
            refined = self.client.generate(
                prompt,
                max_tokens=PASS_TOKEN_LIMITS["refine"],
                temperature=0.7,
                timeout=PASS_TIMEOUTS["refine"],
            )

            if not refined:
                tracker.set_status("error")
                return response  # Fall back to original if refine fails

            return refined


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_pipeline_instance: Optional[AgentPipeline] = None


def get_agent_pipeline(ollama_host: str = None, model: str = None) -> AgentPipeline:
    """Get or create the agent pipeline singleton"""
    global _pipeline_instance

    if _pipeline_instance is None:
        # Import config from parent directory
        import os
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config import MODEL_NAME as DEFAULT_MODEL
        from config import OLLAMA_HOST as DEFAULT_HOST

        _pipeline_instance = AgentPipeline(
            ollama_host=ollama_host or DEFAULT_HOST, model=model or DEFAULT_MODEL
        )

    return _pipeline_instance


def reset_agent_pipeline():
    """Reset the pipeline (for testing or config changes)"""
    global _pipeline_instance
    _pipeline_instance = None
