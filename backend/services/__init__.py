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
    'is_search_available'
]
