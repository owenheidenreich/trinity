"""
Parallel Agent Pipeline for Trinity

Runs both legacy and LangGraph pipelines in parallel, then votes on the best result.
This enables A/B comparison with actual user queries.

Phase 4: Experimentation Framework
"""

import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Try to import metrics
try:
    from middleware.observability import (
        PROMETHEUS_AVAILABLE,
        PARALLEL_EXECUTIONS,
        PARALLEL_LATENCY
    )
except ImportError:
    PROMETHEUS_AVAILABLE = False
    PARALLEL_EXECUTIONS = None
    PARALLEL_LATENCY = None


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PipelineResult:
    """Result from a single pipeline execution."""
    pipeline: str  # 'legacy' or 'langgraph'
    response: str
    duration_seconds: float
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ParallelResult:
    """Result from parallel pipeline execution with voting."""
    final_response: str
    winner: str  # 'legacy', 'langgraph', or 'tie'
    confidence: float
    legacy_result: PipelineResult
    langgraph_result: PipelineResult
    total_duration: float
    voting_reason: str


# =============================================================================
# PARALLEL PIPELINE
# =============================================================================

class ParallelAgentPipeline:
    """
    Run both legacy and LangGraph pipelines in parallel.
    
    Uses ThreadPoolExecutor to run both pipelines concurrently,
    then votes on the results using text similarity and length heuristics.
    """
    
    def __init__(
        self,
        ollama_host: str,
        model_name: str,
        timeout_seconds: float = 120.0
    ):
        """
        Initialize parallel pipeline.
        
        Args:
            ollama_host: Ollama API URL
            model_name: Model to use
            timeout_seconds: Maximum time to wait for each pipeline
        """
        self.ollama_host = ollama_host
        self.model_name = model_name
        self.timeout = timeout_seconds
        
        # Lazy load pipelines to avoid circular imports
        self._legacy_pipeline = None
        self._langgraph_graph = None
    
    @property
    def legacy_pipeline(self):
        """Lazy load legacy agent pipeline."""
        if self._legacy_pipeline is None:
            from services.agent import AgentPipeline
            self._legacy_pipeline = AgentPipeline(
                self.ollama_host, 
                self.model_name
            )
        return self._legacy_pipeline
    
    @property
    def langgraph_graph(self):
        """Lazy load LangGraph graph."""
        if self._langgraph_graph is None:
            from services.graph import get_trinity_graph
            self._langgraph_graph = get_trinity_graph()
        return self._langgraph_graph
    
    def process(
        self,
        question: str,
        context_messages: List[Dict] = None,
        user_memory: Dict = None,
        complexity: str = 'complex',
        **kwargs
    ) -> ParallelResult:
        """
        Execute both pipelines in parallel and vote on result.
        
        Args:
            question: User's question
            context_messages: Previous conversation messages
            user_memory: User's memory facts
            complexity: Query complexity level
            **kwargs: Additional arguments passed to pipelines
            
        Returns:
            ParallelResult with voted winner and both pipeline results
        """
        start_time = time.time()
        
        # Execute both pipelines in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            legacy_future = executor.submit(
                self._execute_legacy,
                question,
                context_messages or [],
                user_memory,
                **kwargs
            )
            langgraph_future = executor.submit(
                self._execute_langgraph,
                question,
                complexity,
                **kwargs
            )
            
            # Wait for both with timeout
            try:
                legacy_result = legacy_future.result(timeout=self.timeout)
            except Exception as e:
                logger.error(f"Legacy pipeline failed: {e}")
                legacy_result = PipelineResult(
                    pipeline='legacy',
                    response='',
                    duration_seconds=self.timeout,
                    success=False,
                    error=str(e)
                )
            
            try:
                langgraph_result = langgraph_future.result(timeout=self.timeout)
            except Exception as e:
                logger.error(f"LangGraph pipeline failed: {e}")
                langgraph_result = PipelineResult(
                    pipeline='langgraph',
                    response='',
                    duration_seconds=self.timeout,
                    success=False,
                    error=str(e)
                )
        
        total_duration = time.time() - start_time
        
        # Vote on the results
        winner, confidence, reason = self._vote(legacy_result, langgraph_result)
        
        # Record metrics
        if PARALLEL_EXECUTIONS:
            PARALLEL_EXECUTIONS.labels(winner=winner).inc()
        if PARALLEL_LATENCY:
            PARALLEL_LATENCY.observe(total_duration)
        
        # Select final response
        if winner == 'legacy':
            final_response = legacy_result.response
        elif winner == 'langgraph':
            final_response = langgraph_result.response
        else:  # tie - prefer langgraph for complex queries
            final_response = langgraph_result.response if langgraph_result.success else legacy_result.response
        
        logger.info(
            f"Parallel execution complete: winner={winner}, "
            f"confidence={confidence:.2f}, duration={total_duration:.2f}s"
        )
        
        return ParallelResult(
            final_response=final_response,
            winner=winner,
            confidence=confidence,
            legacy_result=legacy_result,
            langgraph_result=langgraph_result,
            total_duration=total_duration,
            voting_reason=reason
        )
    
    def _execute_legacy(
        self,
        question: str,
        context_messages: List[Dict],
        user_memory: Dict,
        **kwargs
    ) -> PipelineResult:
        """Execute the legacy agent pipeline."""
        start = time.time()
        
        try:
            result = self.legacy_pipeline.process(
                question=question,
                context_messages=context_messages,
                user_memory=user_memory
            )
            
            return PipelineResult(
                pipeline='legacy',
                response=result.final_answer,
                duration_seconds=time.time() - start,
                success=True,
                metadata={
                    'passes_used': result.passes_used,
                    'complexity': result.complexity
                }
            )
        except Exception as e:
            logger.error(f"Legacy execution error: {e}")
            return PipelineResult(
                pipeline='legacy',
                response='',
                duration_seconds=time.time() - start,
                success=False,
                error=str(e)
            )
    
    def _execute_langgraph(
        self,
        question: str,
        complexity: str,
        **kwargs
    ) -> PipelineResult:
        """Execute the LangGraph pipeline."""
        start = time.time()
        
        try:
            from services.graph import execute_graph
            
            final_state = execute_graph(
                user_message=question,
                complexity=complexity,
                max_iterations=5
            )
            
            return PipelineResult(
                pipeline='langgraph',
                response=final_state.get('final_answer', ''),
                duration_seconds=time.time() - start,
                success=True,
                metadata={
                    'iterations': final_state.get('iteration', 0),
                    'complexity': complexity
                }
            )
        except Exception as e:
            logger.error(f"LangGraph execution error: {e}")
            return PipelineResult(
                pipeline='langgraph',
                response='',
                duration_seconds=time.time() - start,
                success=False,
                error=str(e)
            )
    
    def _vote(
        self,
        legacy: PipelineResult,
        langgraph: PipelineResult
    ) -> tuple:
        """
        Vote on which result is better.
        
        Voting criteria:
        1. If one failed and other succeeded, pick the successful one
        2. Compare response quality using heuristics:
           - Length (longer is often better for complex queries)
           - Contains code blocks (for coding questions)
           - Contains structured formatting
        3. If very similar, consider speed
        
        Returns:
            Tuple of (winner, confidence, reason)
        """
        # Handle failures
        if not legacy.success and not langgraph.success:
            return ('tie', 0.0, 'Both pipelines failed')
        
        if not legacy.success:
            return ('langgraph', 1.0, 'Legacy pipeline failed')
        
        if not langgraph.success:
            return ('legacy', 1.0, 'LangGraph pipeline failed')
        
        # Both succeeded - compare quality
        legacy_score = self._score_response(legacy.response)
        langgraph_score = self._score_response(langgraph.response)
        
        # Calculate confidence based on score difference
        score_diff = abs(legacy_score - langgraph_score)
        max_score = max(legacy_score, langgraph_score, 1)
        confidence = min(score_diff / max_score, 1.0)
        
        # Determine winner
        if legacy_score > langgraph_score * 1.1:  # 10% margin
            return ('legacy', confidence, f'Legacy scored {legacy_score:.1f} vs {langgraph_score:.1f}')
        elif langgraph_score > legacy_score * 1.1:
            return ('langgraph', confidence, f'LangGraph scored {langgraph_score:.1f} vs {legacy_score:.1f}')
        else:
            # Very close - factor in speed
            if legacy.duration_seconds < langgraph.duration_seconds * 0.8:
                return ('legacy', 0.3, 'Similar quality but legacy faster')
            elif langgraph.duration_seconds < legacy.duration_seconds * 0.8:
                return ('langgraph', 0.3, 'Similar quality but LangGraph faster')
            else:
                return ('tie', 0.1, 'Results very similar')
    
    def _score_response(self, response: str) -> float:
        """
        Score a response based on quality heuristics.
        
        Scoring factors:
        - Length (more content is often better)
        - Code blocks present
        - Structured formatting (lists, headers)
        - Not just an error message
        """
        if not response:
            return 0.0
        
        score = 0.0
        
        # Length score (log scale, max ~10 points)
        words = len(response.split())
        score += min(words / 50, 10)
        
        # Code block bonus
        if '```' in response:
            score += 3
        
        # List formatting bonus
        if any(marker in response for marker in ['- ', '* ', '1. ', '2. ']):
            score += 2
        
        # Header bonus
        if any(response.count(marker) > 0 for marker in ['# ', '## ', '### ']):
            score += 1
        
        # Penalty for error-like responses
        error_indicators = ['error', 'failed', 'cannot', 'unable', 'sorry']
        if any(indicator in response.lower()[:100] for indicator in error_indicators):
            score -= 3
        
        return max(score, 0)


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

_parallel_pipeline = None


def get_parallel_pipeline(
    ollama_host: str = None,
    model_name: str = None
) -> ParallelAgentPipeline:
    """
    Get or create the parallel pipeline singleton.
    
    Args:
        ollama_host: Ollama API URL (uses config default if not provided)
        model_name: Model name (uses config default if not provided)
        
    Returns:
        ParallelAgentPipeline instance
    """
    global _parallel_pipeline
    
    if _parallel_pipeline is None:
        # Get defaults from config if not provided
        if ollama_host is None or model_name is None:
            from config import OLLAMA_HOST, MODEL_NAME
            ollama_host = ollama_host or OLLAMA_HOST
            model_name = model_name or MODEL_NAME
        
        _parallel_pipeline = ParallelAgentPipeline(
            ollama_host=ollama_host,
            model_name=model_name
        )
    
    return _parallel_pipeline


def reset_parallel_pipeline():
    """Reset the parallel pipeline singleton (for testing)."""
    global _parallel_pipeline
    _parallel_pipeline = None
