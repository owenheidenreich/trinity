"""
Trinity Backend - Services Package
Business logic and utilities
"""

from .metrics import MetricsCollector, metrics, get_system_info
from .prompts import (
    TRINITY_SYSTEM_PROMPT,
    REASONING_SYSTEM_PROMPT,
    build_prompt_with_context,
    build_reasoning_prompt,
    parse_reasoning_response,
    is_small_model
)
from .ollama import check_ollama_connection, warmup_model, call_ollama
from .akash import (
    get_akt_price_usd,
    get_escrow_balance,
    get_actual_lease_price,
    get_akash_deployment_info,
    AKASH_WALLET_ADDRESS,
    DEPLOYMENT_TIER,
    DEPLOYMENT_TIER_NAME,
    HOURLY_COST_AKT,
    DAILY_COST_AKT,
    SESSION_TYPE,
    SESSION_ID,
    SESSION_EXPIRY,
    SESSION_FUNDED_AKT
)
from .complexity import (
    classify_complexity, 
    get_pass_count, 
    needs_web_search, 
    analyze_question,
    QuestionAnalysis
)
from .agent import AgentPipeline, AgentResponse, get_agent_pipeline
from .loading_messages import get_loading_message, get_loading_sequence, format_phase_update
from .search import search_web, format_search_context, is_search_available

# ===== LLM INTELLIGENCE UPGRADES (v4.0) =====
from .embeddings import embed_text, embed_batch, chunk_text, cosine_similarity
from .vector_store import VectorStore, get_vector_store, get_user_vector_store
from .memory import SemanticMemory, get_semantic_memory, build_enhanced_context
from .tools import (
    TOOL_DEFINITIONS, 
    get_tool_definitions_for_prompt, 
    parse_tool_calls, 
    detect_tools_needed,
    ToolCall,
    ToolResult
)
from .code_executor import evaluate_math_expression, execute_python_code, execute_tool
from .voting import run_voting_pipeline, VotingResult, should_use_voting
from .structured import generate_structured, generate_with_schema, SCHEMAS

# ===== EXPERIMENTATION FRAMEWORK (Phase 4) =====
from .experiments import (
    Experiment, Variant,
    assign_variant, list_experiments, get_experiment,
    enable_experiment, disable_experiment, add_experiment,
    get_all_assignments, EXPERIMENTS
)
from .parallel import (
    ParallelAgentPipeline, ParallelResult, PipelineResult,
    get_parallel_pipeline, reset_parallel_pipeline
)

# ===== COST OPTIMIZATION & CACHING (Phase 5) =====
from .caching import (
    EmbeddingCache, get_embedding_cache, reset_embedding_cache,
    SemanticResponseCache, get_semantic_cache, reset_semantic_cache,
    TokenUsage, TokenTracker, get_token_tracker, reset_token_tracker,
    get_all_cache_stats, clear_all_caches,
    estimate_tokens, estimate_tokens_accurate
)

__all__ = [
    'MetricsCollector',
    'metrics',
    'get_system_info',
    'TRINITY_SYSTEM_PROMPT',
    'REASONING_SYSTEM_PROMPT',
    'build_prompt_with_context',
    'build_reasoning_prompt',
    'parse_reasoning_response',
    'is_small_model',
    'check_ollama_connection',
    'warmup_model',
    'call_ollama',
    'get_akt_price_usd',
    'get_escrow_balance',
    'get_actual_lease_price',
    'get_akash_deployment_info',
    'AKASH_WALLET_ADDRESS',
    'DEPLOYMENT_TIER',
    'DEPLOYMENT_TIER_NAME',
    'HOURLY_COST_AKT',
    'DAILY_COST_AKT',
    'SESSION_TYPE',
    'SESSION_ID',
    'SESSION_EXPIRY',
    'SESSION_FUNDED_AKT',
    # Agent pipeline
    'classify_complexity',
    'get_pass_count',
    'needs_web_search',
    'analyze_question',
    'QuestionAnalysis',
    'AgentPipeline',
    'AgentResponse',
    'get_agent_pipeline',
    # Loading messages
    'get_loading_message',
    'get_loading_sequence',
    'format_phase_update',
    # Search
    'search_web',
    'format_search_context',
    'is_search_available',
    # ===== LLM INTELLIGENCE UPGRADES (v4.0) =====
    # Embeddings
    'embed_text',
    'embed_batch',
    'chunk_text',
    'cosine_similarity',
    # Vector Store
    'VectorStore',
    'get_vector_store',
    'get_user_vector_store',
    # Semantic Memory
    'SemanticMemory',
    'get_semantic_memory',
    'build_enhanced_context',
    # Tools
    'TOOL_DEFINITIONS',
    'get_tool_definitions_for_prompt',
    'parse_tool_calls',
    'detect_tools_needed',
    'ToolCall',
    'ToolResult',
    # Code Executor
    'evaluate_math_expression',
    'execute_python_code',
    'execute_tool',
    # Voting
    'run_voting_pipeline',
    'VotingResult',
    'should_use_voting',
    # Structured Output
    'generate_structured',
    'generate_with_schema',
    'SCHEMAS',
    # ===== EXPERIMENTATION FRAMEWORK (Phase 4) =====
    'Experiment',
    'Variant',
    'assign_variant',
    'list_experiments',
    'get_experiment',
    'enable_experiment',
    'disable_experiment',
    'add_experiment',
    'get_all_assignments',
    'EXPERIMENTS',
    'ParallelAgentPipeline',
    'ParallelResult',
    'PipelineResult',
    'get_parallel_pipeline',
    'reset_parallel_pipeline',
    # ===== COST OPTIMIZATION & CACHING (Phase 5) =====
    'EmbeddingCache',
    'get_embedding_cache',
    'reset_embedding_cache',
    'SemanticResponseCache',
    'get_semantic_cache',
    'reset_semantic_cache',
    'TokenUsage',
    'TokenTracker',
    'get_token_tracker',
    'reset_token_tracker',
    'get_all_cache_stats',
    'clear_all_caches',
    'estimate_tokens',
    'estimate_tokens_accurate',
]
