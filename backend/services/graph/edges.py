"""
Trinity LangGraph Conditional Edge Functions

Defines routing logic between nodes in the graph.
"""

import logging
from typing import Literal

from .state import AgentState

logger = logging.getLogger(__name__)

# Maximum iterations to prevent infinite loops
MAX_ITERATIONS = 5


def route_to_agent(state: AgentState) -> Literal['research', 'reasoning', 'coding']:
    """
    Route from router node to appropriate specialist.
    
    Args:
        state: Current graph state with current_agent set by router
        
    Returns:
        Name of the specialist node to route to
    """
    current_agent = state.get('current_agent', 'reasoning')
    
    if current_agent == 'research':
        return 'research'
    elif current_agent == 'coding':
        return 'coding'
    else:
        return 'reasoning'


def should_continue(state: AgentState) -> Literal['continue', 'synthesize']:
    """
    Determine whether to continue iterating or synthesize final response.
    
    Conditions for continuing:
    1. Haven't reached max iterations
    2. should_continue flag is True
    3. No error has occurred
    
    Args:
        state: Current graph state
        
    Returns:
        'continue' to route back to router, 'synthesize' to finalize
    """
    iteration = state.get('iteration', 0)
    max_iterations = state.get('max_iterations', MAX_ITERATIONS)
    should_cont = state.get('should_continue', True)
    error = state.get('error')
    
    # Check for termination conditions
    if error:
        logger.info(f"🛑 Stopping due to error: {error}")
        return 'synthesize'
    
    if iteration >= max_iterations:
        logger.info(f"🛑 Reached max iterations ({max_iterations})")
        return 'synthesize'
    
    if not should_cont:
        logger.info("🛑 should_continue is False")
        return 'synthesize'
    
    # Check if we have enough content to synthesize
    # (After first specialist pass, we typically have enough)
    has_research = bool(state.get('research_context'))
    has_reasoning = bool(state.get('reasoning_output'))
    has_code = bool(state.get('code_output'))
    
    # If we have any substantive output after first pass, synthesize
    if iteration >= 1 and (has_research or has_reasoning or has_code):
        logger.info(f"✅ Have content after {iteration} iteration(s), synthesizing")
        return 'synthesize'
    
    # Continue iterating
    logger.info(f"🔄 Continuing iteration {iteration + 1}")
    return 'continue'


def should_use_langgraph(complexity: str, mode: str = 'auto') -> bool:
    """
    Determine if LangGraph should be used for this query.
    
    This is the key complexity routing decision:
    - Only complex queries use LangGraph (~10-20% of traffic)
    - Simple/medium queries use legacy pipeline
    
    Args:
        complexity: Query complexity ('simple', 'medium', 'complex')
        mode: Override mode ('auto', 'langgraph', 'legacy')
        
    Returns:
        True if LangGraph should be used
    """
    if mode == 'langgraph':
        return True
    elif mode == 'legacy':
        return False
    else:  # 'auto' mode
        return complexity == 'complex'
