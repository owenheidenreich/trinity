"""
Trinity LangGraph Multi-Agent System

Phase 3 implementation: Complexity-routed multi-agent orchestration.
Only complex queries use this pipeline (~10-20% of traffic).

Components:
- state.py: AgentState TypedDict defining graph state
- llm.py: LangChain-compatible Ollama wrapper
- agents.py: Specialized agents (Supervisor, Research, Reasoning, Coding)
- nodes.py: Graph node implementations
- edges.py: Conditional routing logic
- graph.py: StateGraph assembly and compilation
"""

from .graph import (
    get_trinity_graph, 
    create_trinity_graph,
    execute_graph,
    execute_graph_streaming,
    reset_graph
)
from .state import AgentState
from .edges import should_use_langgraph

__all__ = [
    'get_trinity_graph',
    'create_trinity_graph',
    'execute_graph',
    'execute_graph_streaming',
    'reset_graph',
    'should_use_langgraph',
    'AgentState',
]
