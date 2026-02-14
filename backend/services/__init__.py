"""
Trinity Backend - Services Package
Business logic and utilities
"""

from .agent import AgentPipeline, AgentResponse, get_agent_pipeline
from .akash import (
    AKASH_WALLET_ADDRESS,
    DAILY_COST_AKT,
    DEPLOYMENT_TIER,
    DEPLOYMENT_TIER_NAME,
    HOURLY_COST_AKT,
    SESSION_EXPIRY,
    SESSION_FUNDED_AKT,
    SESSION_ID,
    SESSION_TYPE,
    get_actual_lease_price,
    get_akash_deployment_info,
    get_akt_price_usd,
    get_escrow_balance,
)

# ===== COST OPTIMIZATION & CACHING (Phase 5) =====
from .caching import (
    EmbeddingCache,
    SemanticResponseCache,
    TokenTracker,
    TokenUsage,
    clear_all_caches,
    estimate_tokens,
    estimate_tokens_accurate,
    get_all_cache_stats,
    get_embedding_cache,
    get_semantic_cache,
    get_token_tracker,
    reset_embedding_cache,
    reset_semantic_cache,
    reset_token_tracker,
)
from .code_executor import evaluate_math_expression, execute_python_code, execute_tool

# ===== LLM INTELLIGENCE UPGRADES (v4.0) =====
from .embeddings import chunk_text, cosine_similarity, embed_batch, embed_text
from .loading_messages import format_phase_update, get_loading_message, get_loading_sequence
from .memory import SemanticMemory, build_enhanced_context, get_semantic_memory
from .ollama import call_ollama, check_ollama_connection, warmup_model
from .prompts import (
    REASONING_SYSTEM_PROMPT,
    TRINITY_SYSTEM_PROMPT,
    build_prompt_with_context,
    build_reasoning_prompt,
    is_small_model,
    parse_reasoning_response,
)
from .search import format_search_context, is_search_available, search_web
from .structured import SCHEMAS, generate_structured, generate_with_schema
from .tools import (
    TOOL_DEFINITIONS,
    ToolCall,
    ToolResult,
    detect_tools_needed,
    get_tool_definitions_for_prompt,
    parse_tool_calls,
)
from .vector_store import VectorStore, get_user_vector_store, get_vector_store

__all__ = [
    "TRINITY_SYSTEM_PROMPT",
    "REASONING_SYSTEM_PROMPT",
    "build_prompt_with_context",
    "build_reasoning_prompt",
    "parse_reasoning_response",
    "is_small_model",
    "check_ollama_connection",
    "warmup_model",
    "call_ollama",
    "get_akt_price_usd",
    "get_escrow_balance",
    "get_actual_lease_price",
    "get_akash_deployment_info",
    "AKASH_WALLET_ADDRESS",
    "DEPLOYMENT_TIER",
    "DEPLOYMENT_TIER_NAME",
    "HOURLY_COST_AKT",
    "DAILY_COST_AKT",
    "SESSION_TYPE",
    "SESSION_ID",
    "SESSION_EXPIRY",
    "SESSION_FUNDED_AKT",
    # Agent pipeline
    "AgentPipeline",
    "AgentResponse",
    "get_agent_pipeline",
    # Loading messages
    "get_loading_message",
    "get_loading_sequence",
    "format_phase_update",
    # Search
    "search_web",
    "format_search_context",
    "is_search_available",
    # ===== LLM INTELLIGENCE UPGRADES (v4.0) =====
    # Embeddings
    "embed_text",
    "embed_batch",
    "chunk_text",
    "cosine_similarity",
    # Vector Store
    "VectorStore",
    "get_vector_store",
    "get_user_vector_store",
    # Semantic Memory
    "SemanticMemory",
    "get_semantic_memory",
    "build_enhanced_context",
    # Tools
    "TOOL_DEFINITIONS",
    "get_tool_definitions_for_prompt",
    "parse_tool_calls",
    "detect_tools_needed",
    "ToolCall",
    "ToolResult",
    # Code Executor
    "evaluate_math_expression",
    "execute_python_code",
    "execute_tool",
    # Voting
    # (removed — dead code)
    # Structured Output
    "generate_structured",
    "generate_with_schema",
    "SCHEMAS",
    # ===== COST OPTIMIZATION & CACHING (Phase 5) =====
    "EmbeddingCache",
    "get_embedding_cache",
    "reset_embedding_cache",
    "SemanticResponseCache",
    "get_semantic_cache",
    "reset_semantic_cache",
    "TokenUsage",
    "TokenTracker",
    "get_token_tracker",
    "reset_token_tracker",
    "get_all_cache_stats",
    "clear_all_caches",
    "estimate_tokens",
    "estimate_tokens_accurate",
]
