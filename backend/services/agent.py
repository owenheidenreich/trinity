"""
Trinity Agentic Pipeline - Orchestrator

Multi-pass reasoning pipeline that makes Trinity feel intelligent.
Automatically routes simple vs complex questions and manages pass execution.
Integrates web search when current/real-time information is needed.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Generator, Any
from dataclasses import dataclass, asdict
import requests

from .complexity import classify_complexity, get_pass_count, analyze_question, ComplexityLevel, QuestionAnalysis
from .agent_prompts import (
    build_understand_prompt, build_plan_prompt, build_execute_prompt,
    build_critique_prompt, build_refine_prompt,
    parse_understanding, parse_plan, parse_critique,
    UnderstandingResult, PlanResult, CritiqueResult
)
from .search import search_web, format_search_context, is_search_available, SearchResponse
from .loading_messages import get_loading_message, format_phase_update

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Timeout per pass (seconds) - GENEROUS for deep thinking
# These are connection timeouts, not "how long can it think"
# Streaming keeps connection alive, so these are really just for non-streaming calls
PASS_TIMEOUTS = {
    'understand': 120,   # 2 min - may need to reason about complex questions
    'plan': 120,         # 2 min - planning complex multi-step solutions
    'execute': 300,      # 5 min - main response generation, can be very long
    'critique': 120,     # 2 min - thorough critique takes time
    'refine': 300,       # 5 min - complete rewrite if needed
    'search': 30         # 30s - web search timeout
}

# Token limits per pass - generous for thorough responses
PASS_TOKEN_LIMITS = {
    'understand': 1000,  # Detailed understanding
    'plan': 1000,        # Comprehensive plans
    'execute': 4000,     # Long, detailed responses
    'critique': 1000,    # Thorough critique
    'refine': 4000       # Complete improved response
}

# Critique threshold - if score >= this, skip refinement
CRITIQUE_THRESHOLD = 7

# Max refinement attempts
MAX_REFINE_ATTEMPTS = 2


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
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        result = {
            'answer': self.answer,
            'complexity': self.complexity,
            'passes_used': self.passes_used,
            'total_time_seconds': self.total_time_seconds,
            'search_performed': self.search_performed
        }
        if self.search_query:
            result['search_query'] = self.search_query
        if self.understanding:
            result['understanding'] = {
                'type': self.understanding.question_type,
                'domains': self.understanding.domains,
                'complexity': self.understanding.complexity,
                'summary': self.understanding.summary
            }
        if self.plan:
            result['plan'] = {
                'steps': self.plan.steps,
                'approach': self.plan.approach
            }
        if self.critique:
            result['critique'] = {
                'score': self.critique.score,
                'verdict': self.critique.verdict
            }
        return result


# ============================================================================
# OLLAMA INTERFACE
# ============================================================================

class OllamaClient:
    """Client for Ollama API calls"""
    
    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.host = host
        self.model = model
    
    def generate(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.7, timeout: int = 30) -> str:
        """Generate a response (non-streaming)"""
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature
                    }
                },
                timeout=timeout
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
    
    def generate_stream(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.7, timeout: int = 60) -> Generator[str, None, None]:
        """Generate a response with streaming"""
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature
                    }
                },
                stream=True,
                timeout=timeout
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
                            break
                    except json.JSONDecodeError:
                        continue
                        
        except requests.exceptions.Timeout:
            logger.warning(f"Ollama stream timeout after {timeout}s")
        except Exception as e:
            logger.error(f"Ollama stream error: {e}")


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
    
    def process(
        self,
        question: str,
        context_messages: List[Dict] = None,
        user_memory: Dict = None,
        force_complexity: ComplexityLevel = None
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
        
        logger.info(f"🧠 Agent: {complexity} question, {passes_needed} passes, search={analysis.needs_search}")
        
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
                answer = self._pass_execute_simple(question, context_messages, user_memory, search_context)
                
            elif complexity == "medium":
                # === MEDIUM: Understand → Execute → Critique ===
                understanding = self._pass_understand(question)
                answer = self._pass_execute(question, understanding, None, context_messages, user_memory, search_context)
                critique = self._pass_critique(question, answer)
                
                # Refine if score is low
                if critique and critique.score < CRITIQUE_THRESHOLD:
                    answer = self._pass_refine(question, answer, critique)
                    
            else:
                # === COMPLEX: Full pipeline ===
                understanding = self._pass_understand(question)
                plan = self._pass_plan(question, understanding)
                answer = self._pass_execute(question, understanding, plan, context_messages, user_memory, search_context)
                critique = self._pass_critique(question, answer)
                
                # Refine if score is low (up to MAX_REFINE_ATTEMPTS times)
                refine_attempts = 0
                while critique and critique.score < CRITIQUE_THRESHOLD and refine_attempts < MAX_REFINE_ATTEMPTS:
                    previous_score = critique.score
                    answer = self._pass_refine(question, answer, critique)
                    critique = self._pass_critique(question, answer)
                    refine_attempts += 1
                    
                    # Stop if not improving
                    if critique.score <= previous_score:
                        logger.info(f"Stopping refinement - score not improving ({previous_score} → {critique.score})")
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
            total_time_seconds=round(total_time, 2)
        )
    
    def process_streaming(
        self,
        question: str,
        context_messages: List[Dict] = None,
        user_memory: Dict = None,
        force_complexity: ComplexityLevel = None
    ) -> Generator[Dict, None, None]:
        """
        Process with streaming - yields progress updates and tokens.
        
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
        
        logger.info(f"🧠 Agent streaming: {complexity} question, {passes_needed} passes, search={analysis.needs_search}")
        
        context_messages = context_messages or []
        user_memory = user_memory or {}
        
        understanding = None
        plan = None
        critique = None
        full_response = ""
        search_context = ""
        search_performed = False
        
        # === WEB SEARCH (if needed) ===
        if analysis.needs_search and is_search_available():
            yield format_phase_update("searching")  # "Scouring the web..."
            search_result = search_web(analysis.search_query, count=5, timeout=PASS_TIMEOUTS['search'])
            if not search_result.error and search_result.results:
                search_context = format_search_context(search_result)
                search_performed = True
                yield {"phase": "searching", "message": f"Found {len(search_result.results)} sources..."}
        
        try:
            if complexity == "simple":
                # === SIMPLE: Direct streaming ===
                yield format_phase_update("executing")  # "Brewing the answer..."
                
                prompt = build_execute_prompt(question, None, None, context_messages, user_memory, search_context)
                for token in self.client.generate_stream(prompt, PASS_TOKEN_LIMITS['execute'], timeout=PASS_TIMEOUTS['execute']):
                    full_response += token
                    yield {"token": token}
                    
            elif complexity == "medium":
                # === MEDIUM ===
                yield format_phase_update("understanding")  # "Pondering the question..."
                understanding = self._pass_understand(question)
                
                yield format_phase_update("executing")  # "Crafting the response..."
                prompt = build_execute_prompt(question, understanding, None, context_messages, user_memory, search_context)
                for token in self.client.generate_stream(prompt, PASS_TOKEN_LIMITS['execute'], timeout=PASS_TIMEOUTS['execute']):
                    full_response += token
                    yield {"token": token}
                
                yield format_phase_update("critiquing")  # "Polishing the prose..."
                critique = self._pass_critique(question, full_response)
                
                if critique and critique.score < CRITIQUE_THRESHOLD:
                    yield {"phase": "refining", "message": f"Enhancing quality (score: {critique.score}/10)..."}
                    full_response = ""
                    prompt = build_refine_prompt(question, full_response, critique)
                    for token in self.client.generate_stream(prompt, PASS_TOKEN_LIMITS['refine'], timeout=PASS_TIMEOUTS['refine']):
                        full_response += token
                        yield {"token": token}
                        
            else:
                # === COMPLEX: Full pipeline ===
                yield format_phase_update("understanding")  # "Meditating on the problem..."
                understanding = self._pass_understand(question)
                
                yield format_phase_update("planning")  # "Charting the course..."
                plan = self._pass_plan(question, understanding)
                
                if plan and plan.steps:
                    yield {"phase": "planning", "message": f"Mapped {len(plan.steps)} steps..."}
                
                yield format_phase_update("executing")  # "Weaving the words..."
                prompt = build_execute_prompt(question, understanding, plan, context_messages, user_memory, search_context)
                for token in self.client.generate_stream(prompt, PASS_TOKEN_LIMITS['execute'], timeout=PASS_TIMEOUTS['execute']):
                    full_response += token
                    yield {"token": token}
                
                yield format_phase_update("critiquing")  # "Inspecting the work..."
                critique = self._pass_critique(question, full_response)
                
                if critique:
                    yield {"phase": "critiquing", "message": f"Quality score: {critique.score}/10..."}
                
                if critique and critique.score < CRITIQUE_THRESHOLD:
                    yield format_phase_update("refining")  # "Perfecting the response..."
                    
                    # Clear and stream refined response
                    yield {"clear": True}  # Signal frontend to clear previous response
                    full_response = ""
                    
                    prompt = build_refine_prompt(question, full_response, critique)
                    for token in self.client.generate_stream(prompt, PASS_TOKEN_LIMITS['refine'], timeout=PASS_TIMEOUTS['refine']):
                        full_response += token
                        yield {"token": token}
                    
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
            total_time_seconds=round(total_time, 2)
        )
        
        yield {"done": True, "response": response.to_dict()}
    
    # ========================================================================
    # INDIVIDUAL PASSES
    # ========================================================================
    
    def _pass_understand(self, question: str) -> Optional[UnderstandingResult]:
        """Pass 1: Understand the question"""
        logger.info("🤔 Pass 1: Understanding...")
        
        prompt = build_understand_prompt(question)
        response = self.client.generate(
            prompt,
            max_tokens=PASS_TOKEN_LIMITS['understand'],
            temperature=0.3,  # Lower temp for analysis
            timeout=PASS_TIMEOUTS['understand']
        )
        
        if not response:
            return None
        
        return parse_understanding(response)
    
    def _pass_plan(self, question: str, understanding: UnderstandingResult) -> Optional[PlanResult]:
        """Pass 2: Create a plan"""
        logger.info("📋 Pass 2: Planning...")
        
        prompt = build_plan_prompt(question, understanding)
        response = self.client.generate(
            prompt,
            max_tokens=PASS_TOKEN_LIMITS['plan'],
            temperature=0.3,
            timeout=PASS_TIMEOUTS['plan']
        )
        
        if not response:
            return None
        
        return parse_plan(response)
    
    def _pass_execute(
        self,
        question: str,
        understanding: Optional[UnderstandingResult],
        plan: Optional[PlanResult],
        context_messages: List[Dict],
        user_memory: Dict,
        search_context: str = ""
    ) -> str:
        """Pass 3: Execute (non-streaming version)"""
        logger.info("✍️ Pass 3: Executing...")
        
        prompt = build_execute_prompt(question, understanding, plan, context_messages, user_memory, search_context)
        response = self.client.generate(
            prompt,
            max_tokens=PASS_TOKEN_LIMITS['execute'],
            temperature=0.7,
            timeout=PASS_TIMEOUTS['execute']
        )
        
        return response or "I was unable to generate a response."
    
    def _pass_execute_simple(self, question: str, context_messages: List[Dict], user_memory: Dict, search_context: str = "") -> str:
        """Simple execute without understanding/plan"""
        logger.info("✍️ Simple execution...")
        
        prompt = build_execute_prompt(question, None, None, context_messages, user_memory, search_context)
        response = self.client.generate(
            prompt,
            max_tokens=PASS_TOKEN_LIMITS['execute'],
            temperature=0.7,
            timeout=PASS_TIMEOUTS['execute']
        )
        
        return response or "I was unable to generate a response."
    
    def _pass_critique(self, question: str, response: str) -> Optional[CritiqueResult]:
        """Pass 4: Critique the response"""
        logger.info("🔍 Pass 4: Critiquing...")
        
        prompt = build_critique_prompt(question, response)
        critique_response = self.client.generate(
            prompt,
            max_tokens=PASS_TOKEN_LIMITS['critique'],
            temperature=0.3,  # Lower temp for objective critique
            timeout=PASS_TIMEOUTS['critique']
        )
        
        if not critique_response:
            return None
        
        critique = parse_critique(critique_response)
        
        # Sanity check: if no weaknesses found, be suspicious
        if critique.weakness1 == "No weakness identified" and critique.weakness2 == "No weakness identified":
            logger.warning("Critique found no weaknesses - response might be suspicious")
        
        logger.info(f"🔍 Critique score: {critique.score}/10")
        return critique
    
    def _pass_refine(self, question: str, response: str, critique: CritiqueResult) -> str:
        """Pass 5: Refine based on critique"""
        logger.info(f"✨ Pass 5: Refining (addressing score {critique.score}/10)...")
        
        prompt = build_refine_prompt(question, response, critique)
        refined = self.client.generate(
            prompt,
            max_tokens=PASS_TOKEN_LIMITS['refine'],
            temperature=0.7,
            timeout=PASS_TIMEOUTS['refine']
        )
        
        return refined or response  # Fall back to original if refine fails


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_pipeline_instance: Optional[AgentPipeline] = None


def get_agent_pipeline(ollama_host: str = None, model: str = None) -> AgentPipeline:
    """Get or create the agent pipeline singleton"""
    global _pipeline_instance
    
    if _pipeline_instance is None:
        # Import config from parent directory
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config import OLLAMA_HOST as DEFAULT_HOST, MODEL_NAME as DEFAULT_MODEL
        
        _pipeline_instance = AgentPipeline(
            ollama_host=ollama_host or DEFAULT_HOST,
            model=model or DEFAULT_MODEL
        )
    
    return _pipeline_instance


def reset_agent_pipeline():
    """Reset the pipeline (for testing or config changes)"""
    global _pipeline_instance
    _pipeline_instance = None
