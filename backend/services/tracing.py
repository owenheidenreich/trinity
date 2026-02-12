"""
Trinity Backend - Request Tracing

Professional-grade structured traces for every generate request.
Captures the full execution path: every file activated, every function called,
every model used, every token counted, every millisecond measured.

This is the plumbing inspector — everything outside the LLM black box
is recorded with extreme precision.

Usage:
    trace = RequestTrace.start("/generate/agent", principal="abc123")
    
    with trace.phase("complexity_classify") as p:
        result = classify_complexity(question)
        p.set_result({"complexity": result, "word_count": 42})
    
    with trace.phase("understand", model="qwen2.5:7b") as p:
        response = pass_understand(question)
        p.set_tokens(input=1200, output=350)
        p.set_result({"type": "technical", "domains": ["math"]})
    
    trace.finish(response_text, critique_score=8)
    
    # trace.to_dict() → full structured trace for storage/API
"""

import hashlib
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# How many completed traces to keep in memory for the /admin/traces API
MAX_TRACE_HISTORY = 500

# How many per-principal traces to keep
MAX_TRACES_PER_PRINCIPAL = 50


# =============================================================================
# PHASE TRACE
# =============================================================================

@dataclass
class PhaseTrace:
    """A single phase within a request trace (e.g., 'understand', 'execute')."""

    name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    
    # What file/function was activated
    source_file: Optional[str] = None
    source_function: Optional[str] = None
    
    # Model used (if LLM call)
    model: Optional[str] = None
    
    # Token counts
    input_tokens: int = 0
    output_tokens: int = 0
    
    # Result data (complexity level, critique score, etc.)
    result: Optional[Dict[str, Any]] = None
    
    # Error if phase failed
    error: Optional[str] = None
    status: str = "running"  # running, success, error, skipped

    def finish(self, status: str = "success"):
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.status = status

    def set_tokens(self, input_tokens: int = 0, output_tokens: int = 0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def set_result(self, result: Dict[str, Any]):
        self.result = result

    def set_source(self, file: str, function: str):
        self.source_file = file
        self.source_function = function

    def to_dict(self) -> Dict:
        d = {
            "name": self.name,
            "status": self.status,
            "duration_ms": self.duration_ms,
        }
        if self.model:
            d["model"] = self.model
        if self.input_tokens or self.output_tokens:
            d["tokens"] = {
                "input": self.input_tokens,
                "output": self.output_tokens,
                "total": self.input_tokens + self.output_tokens,
            }
        if self.source_file:
            d["source"] = {
                "file": self.source_file,
                "function": self.source_function,
            }
        if self.result:
            d["result"] = self.result
        if self.error:
            d["error"] = self.error
        return d


# =============================================================================
# PHASE CONTEXT MANAGER
# =============================================================================

class PhaseContext:
    """Context manager for tracing a single phase."""

    def __init__(self, trace: "RequestTrace", phase: PhaseTrace):
        self._trace = trace
        self._phase = phase

    def __enter__(self):
        return self._phase

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._phase.error = f"{exc_type.__name__}: {exc_val}"
            self._phase.finish("error")
        else:
            self._phase.finish("success")
        return False  # Don't suppress exceptions


# =============================================================================
# REQUEST TRACE
# =============================================================================

@dataclass
class RequestTrace:
    """Full structured trace of a single generate request."""

    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    endpoint: str = ""
    principal: Optional[str] = None  # First 8 chars only (privacy)
    
    # Timing
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    total_duration_ms: Optional[float] = None
    
    # Request metadata
    prompt_hash: str = ""  # SHA-256 first 8 chars (privacy)
    prompt_word_count: int = 0
    context_message_count: int = 0
    has_document_context: bool = False
    reasoning_mode: bool = False
    
    # Classification
    complexity: Optional[str] = None
    passes_planned: int = 0
    search_needed: bool = False
    
    # Execution
    phases: List[PhaseTrace] = field(default_factory=list)
    models_used: List[str] = field(default_factory=list)
    
    # Totals
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_llm_calls: int = 0
    
    # Response quality
    response_word_count: int = 0
    critique_score: Optional[float] = None
    was_refined: bool = False
    eval_scores: Optional[Dict[str, float]] = None
    
    # Outcome
    status: str = "running"  # running, success, error
    error: Optional[str] = None

    @classmethod
    def start(cls, endpoint: str, prompt: str = "", principal: str = None,
              context_count: int = 0, has_doc: bool = False,
              reasoning: bool = False) -> "RequestTrace":
        """Create and start a new request trace."""
        trace = cls(
            endpoint=endpoint,
            principal=principal[:8] if principal else None,
            prompt_hash=hashlib.sha256(prompt.encode()).hexdigest()[:8] if prompt else "",
            prompt_word_count=len(prompt.split()) if prompt else 0,
            context_message_count=context_count,
            has_document_context=has_doc,
            reasoning_mode=reasoning,
        )
        return trace

    def phase(self, name: str, model: str = None,
              source_file: str = None, source_function: str = None) -> PhaseContext:
        """Start tracing a new phase. Use as context manager."""
        p = PhaseTrace(
            name=name,
            model=model,
            source_file=source_file,
            source_function=source_function,
        )
        self.phases.append(p)
        if model and model not in self.models_used:
            self.models_used.append(model)
        return PhaseContext(self, p)

    def record_skip(self, name: str, reason: str = ""):
        """Record a phase that was skipped."""
        p = PhaseTrace(name=name, status="skipped", duration_ms=0)
        p.result = {"skip_reason": reason} if reason else None
        p.finish("skipped")
        self.phases.append(p)

    def set_classification(self, complexity: str, passes: int, search: bool):
        self.complexity = complexity
        self.passes_planned = passes
        self.search_needed = search

    def set_eval_scores(self, scores: Dict[str, float]):
        self.eval_scores = scores

    def finish(self, response_text: str = "", critique_score: float = None,
               was_refined: bool = False, status: str = "success",
               error: str = None):
        """Finalize the trace."""
        self.end_time = time.time()
        self.total_duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.response_word_count = len(response_text.split()) if response_text else 0
        self.critique_score = critique_score
        self.was_refined = was_refined
        self.status = status
        self.error = error

        # Aggregate token counts
        for p in self.phases:
            self.total_input_tokens += p.input_tokens
            self.total_output_tokens += p.output_tokens
            if p.model and p.status != "skipped":
                self.total_llm_calls += 1

    def to_dict(self) -> Dict:
        """Full structured trace for API/storage."""
        return {
            "trace_id": self.trace_id,
            "endpoint": self.endpoint,
            "principal": self.principal,
            "status": self.status,
            "timing": {
                "total_ms": self.total_duration_ms,
                "started_at": self.start_time,
            },
            "request": {
                "prompt_hash": self.prompt_hash,
                "prompt_words": self.prompt_word_count,
                "context_messages": self.context_message_count,
                "has_document": self.has_document_context,
                "reasoning_mode": self.reasoning_mode,
            },
            "classification": {
                "complexity": self.complexity,
                "passes_planned": self.passes_planned,
                "search_needed": self.search_needed,
            },
            "execution": {
                "phases": [p.to_dict() for p in self.phases],
                "models_used": self.models_used,
                "total_llm_calls": self.total_llm_calls,
            },
            "tokens": {
                "total_input": self.total_input_tokens,
                "total_output": self.total_output_tokens,
                "total": self.total_input_tokens + self.total_output_tokens,
            },
            "response": {
                "word_count": self.response_word_count,
                "critique_score": self.critique_score,
                "was_refined": self.was_refined,
            },
            "evaluation": self.eval_scores,
            "error": self.error,
        }

    def to_summary(self) -> Dict:
        """Compact summary for list views."""
        return {
            "trace_id": self.trace_id,
            "endpoint": self.endpoint,
            "complexity": self.complexity,
            "status": self.status,
            "total_ms": self.total_duration_ms,
            "llm_calls": self.total_llm_calls,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "critique_score": self.critique_score,
            "eval_scores": self.eval_scores,
            "models_used": self.models_used,
            "prompt_words": self.prompt_word_count,
            "response_words": self.response_word_count,
            "was_refined": self.was_refined,
        }


# =============================================================================
# TRACE STORE (In-Memory Ring Buffer)
# =============================================================================

class TraceStore:
    """
    Thread-safe in-memory store for completed traces.
    Ring buffer — oldest traces are evicted when capacity is reached.
    """

    def __init__(self, max_size: int = MAX_TRACE_HISTORY):
        self._traces: Deque[RequestTrace] = deque(maxlen=max_size)
        self._lock = threading.Lock()
        # Aggregate counters
        self._total_traced = 0
        self._total_tokens = 0
        self._total_duration_ms = 0.0
        self._complexity_counts = {"simple": 0, "medium": 0, "complex": 0}
        self._critique_scores: List[float] = []
        self._eval_scores_accum: Dict[str, List[float]] = {}
        self._refinement_count = 0

    def add(self, trace: RequestTrace):
        """Store a completed trace."""
        with self._lock:
            self._traces.append(trace)
            self._total_traced += 1
            self._total_tokens += trace.total_input_tokens + trace.total_output_tokens
            self._total_duration_ms += trace.total_duration_ms or 0
            if trace.complexity:
                self._complexity_counts[trace.complexity] = (
                    self._complexity_counts.get(trace.complexity, 0) + 1
                )
            if trace.critique_score is not None:
                self._critique_scores.append(trace.critique_score)
                # Keep only last 1000 scores for running average
                if len(self._critique_scores) > 1000:
                    self._critique_scores = self._critique_scores[-500:]
            if trace.was_refined:
                self._refinement_count += 1
            if trace.eval_scores:
                for key, val in trace.eval_scores.items():
                    if key not in self._eval_scores_accum:
                        self._eval_scores_accum[key] = []
                    self._eval_scores_accum[key].append(val)
                    if len(self._eval_scores_accum[key]) > 1000:
                        self._eval_scores_accum[key] = self._eval_scores_accum[key][-500:]

    def get_recent(self, n: int = 50) -> List[Dict]:
        """Get the N most recent trace summaries."""
        with self._lock:
            traces = list(self._traces)
            return [t.to_summary() for t in reversed(traces[-n:])]

    def get_trace(self, trace_id: str) -> Optional[Dict]:
        """Get a specific trace by ID (full detail)."""
        with self._lock:
            for t in self._traces:
                if t.trace_id == trace_id:
                    return t.to_dict()
            return None

    def get_stats(self) -> Dict:
        """Get aggregate trace statistics."""
        with self._lock:
            avg_critique = (
                round(sum(self._critique_scores) / len(self._critique_scores), 2)
                if self._critique_scores
                else None
            )
            avg_duration = (
                round(self._total_duration_ms / self._total_traced, 1)
                if self._total_traced
                else 0
            )
            
            eval_averages = {}
            for key, vals in self._eval_scores_accum.items():
                if vals:
                    eval_averages[key] = round(sum(vals) / len(vals), 2)

            return {
                "total_traced": self._total_traced,
                "total_tokens_consumed": self._total_tokens,
                "avg_duration_ms": avg_duration,
                "complexity_distribution": dict(self._complexity_counts),
                "avg_critique_score": avg_critique,
                "refinement_rate": (
                    round(self._refinement_count / self._total_traced * 100, 1)
                    if self._total_traced
                    else 0
                ),
                "eval_averages": eval_averages,
                "traces_in_buffer": len(self._traces),
            }

    def get_quality_report(self) -> Dict:
        """
        Generate a quality report: the complaints about the LLM.
        This is the adversarial self-assessment.
        """
        with self._lock:
            recent = list(self._traces)[-100:]  # Last 100 traces
            
            if not recent:
                return {"message": "No traces collected yet"}
            
            # Collect quality signals
            low_critique = [t for t in recent if t.critique_score is not None and t.critique_score < 6]
            high_critique = [t for t in recent if t.critique_score is not None and t.critique_score >= 9]
            refined = [t for t in recent if t.was_refined]
            errors = [t for t in recent if t.status == "error"]
            slow = [t for t in recent if t.total_duration_ms and t.total_duration_ms > 30000]
            
            # Token efficiency
            token_per_word = []
            for t in recent:
                total_tok = t.total_input_tokens + t.total_output_tokens
                if total_tok > 0 and t.response_word_count > 0:
                    token_per_word.append(total_tok / t.response_word_count)
            
            # Eval dimension analysis
            eval_complaints = []
            for key, vals in self._eval_scores_accum.items():
                if vals:
                    avg = sum(vals[-50:]) / len(vals[-50:])
                    if avg < 6.0:
                        eval_complaints.append({
                            "dimension": key,
                            "avg_score": round(avg, 2),
                            "severity": "critical" if avg < 4.0 else "warning",
                            "sample_size": len(vals[-50:]),
                        })

            return {
                "period": f"Last {len(recent)} requests",
                "overall": {
                    "error_rate": f"{len(errors)/len(recent)*100:.1f}%",
                    "refinement_rate": f"{len(refined)/len(recent)*100:.1f}%",
                    "low_quality_rate": f"{len(low_critique)/len(recent)*100:.1f}%",
                    "high_quality_rate": f"{len(high_critique)/len(recent)*100:.1f}%",
                },
                "complaints": [
                    *[{
                        "issue": f"Low critique score ({t.critique_score}/10)",
                        "trace_id": t.trace_id,
                        "complexity": t.complexity,
                        "prompt_hash": t.prompt_hash,
                    } for t in low_critique[:10]],
                    *[{
                        "issue": f"Slow response ({t.total_duration_ms:.0f}ms)",
                        "trace_id": t.trace_id,
                        "complexity": t.complexity,
                    } for t in slow[:5]],
                    *[{
                        "issue": f"Error: {t.error}",
                        "trace_id": t.trace_id,
                    } for t in errors[:5]],
                ],
                "eval_dimension_complaints": eval_complaints,
                "token_efficiency": {
                    "avg_tokens_per_response_word": (
                        round(sum(token_per_word) / len(token_per_word), 1)
                        if token_per_word else None
                    ),
                },
            }


# =============================================================================
# SINGLETON
# =============================================================================

_trace_store: Optional[TraceStore] = None
_store_lock = threading.Lock()


def get_trace_store() -> TraceStore:
    """Get or create the global trace store."""
    global _trace_store
    if _trace_store is None:
        with _store_lock:
            if _trace_store is None:
                _trace_store = TraceStore()
    return _trace_store


def reset_trace_store():
    """Reset the trace store (for testing)."""
    global _trace_store
    _trace_store = None
