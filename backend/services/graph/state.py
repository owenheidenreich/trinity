"""
Trinity LangGraph State Definition

Defines the AgentState TypedDict that flows through the multi-agent graph.
Uses LangGraph's annotation system for message accumulation.
"""

from typing import TypedDict, Annotated, Sequence, Literal, Optional, List, Dict, Any
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    """
    State that flows through the LangGraph.
    
    This state is passed between all nodes in the graph and accumulates
    information as the query is processed by different agents.
    
    Attributes:
        messages: Conversation history (accumulates via operator.add)
        current_agent: Which specialized agent is currently active
        iteration: Current reasoning iteration (max 5 for safety)
        tool_results: Results from tool executions in current iteration
        research_context: Gathered research/search results
        code_output: Results from code execution
        final_answer: Synthesized response ready for user
        complexity: Classified complexity level of the query
        should_continue: Whether to continue iterating or synthesize
        error: Any error message from processing
    """
    # Message accumulation - new messages are appended
    messages: Annotated[Sequence[BaseMessage], operator.add]
    
    # Agent routing
    current_agent: Literal['supervisor', 'research', 'reasoning', 'coding', 'synthesis']
    
    # Iteration control
    iteration: int
    max_iterations: int
    should_continue: bool
    
    # Agent outputs
    tool_results: List[Dict[str, Any]]
    research_context: str
    code_output: Optional[str]
    reasoning_output: Optional[str]
    
    # Final output
    final_answer: Optional[str]
    
    # Metadata
    complexity: Literal['simple', 'medium', 'complex']
    error: Optional[str]
    

def create_initial_state(
    user_message: str,
    complexity: str = 'complex',
    max_iterations: int = 5
) -> AgentState:
    """
    Create initial state for graph execution.
    
    Args:
        user_message: The user's query
        complexity: Query complexity level
        max_iterations: Maximum reasoning iterations
        
    Returns:
        AgentState ready for graph execution
    """
    from langchain_core.messages import HumanMessage
    
    return AgentState(
        messages=[HumanMessage(content=user_message)],
        current_agent='supervisor',
        iteration=0,
        max_iterations=max_iterations,
        should_continue=True,
        tool_results=[],
        research_context='',
        code_output=None,
        reasoning_output=None,
        final_answer=None,
        complexity=complexity,
        error=None,
    )
