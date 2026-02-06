"""
Trinity LangGraph StateGraph Assembly

Assembles the complete multi-agent graph from nodes and edges.
"""

import logging
from typing import Any, Dict, Generator

from langgraph.graph import END, StateGraph

from .edges import route_to_agent, should_continue
from .nodes import coding_node, reasoning_node, research_node, router_node, synthesis_node
from .state import AgentState, create_initial_state

# Observability
try:
    pass

    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False

logger = logging.getLogger(__name__)


def create_trinity_graph() -> StateGraph:
    """
    Create and compile the Trinity multi-agent graph.

    Graph Flow:
    1. Router analyzes query, picks specialist (research/reasoning/coding)
    2. Specialist executes their task
    3. Check if more iterations needed (max 5)
    4. If enough content or max iterations, go to synthesis
    5. Synthesis combines outputs into final answer
    6. Return final answer

    Returns:
        Compiled StateGraph ready for execution
    """
    # Create graph with AgentState schema
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("router", router_node)
    workflow.add_node("research", research_node)
    workflow.add_node("reasoning", reasoning_node)
    workflow.add_node("coding", coding_node)
    workflow.add_node("synthesis", synthesis_node)

    # Set entry point - always start with router
    workflow.set_entry_point("router")

    # Router routes to specialists based on query type
    workflow.add_conditional_edges(
        "router",
        route_to_agent,
        {"research": "research", "reasoning": "reasoning", "coding": "coding"},
    )

    # Each specialist routes to either continue or synthesize
    for agent_node in ["research", "reasoning", "coding"]:
        workflow.add_conditional_edges(
            agent_node,
            should_continue,
            {"continue": "router", "synthesize": "synthesis"},  # Another iteration  # Finalize
        )

    # Synthesis ends the graph
    workflow.add_edge("synthesis", END)

    # Compile and return
    return workflow.compile()


# =============================================================================
# SINGLETON GRAPH INSTANCE
# =============================================================================

_compiled_graph = None


def get_trinity_graph():
    """
    Get or create the compiled Trinity graph singleton.

    The graph is compiled once and reused for all requests.
    This is safe because the graph structure is stateless;
    state is passed in per-execution.
    """
    global _compiled_graph

    if _compiled_graph is None:
        logger.info("🔨 Compiling Trinity LangGraph...")
        _compiled_graph = create_trinity_graph()
        logger.info("✅ Trinity LangGraph compiled successfully")

    return _compiled_graph


def reset_graph():
    """Reset the graph singleton (for testing or config changes)."""
    global _compiled_graph
    _compiled_graph = None


# =============================================================================
# EXECUTION HELPERS
# =============================================================================


def execute_graph(
    user_message: str,
    complexity: str = "complex",
    max_iterations: int = 5,
    context: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Execute the Trinity graph on a user message.

    Args:
        user_message: The user's query
        complexity: Query complexity level
        max_iterations: Maximum reasoning iterations
        context: Additional context to merge into initial state

    Returns:
        Final state dict with 'final_answer' and metadata
    """
    graph = get_trinity_graph()

    # Create initial state
    initial_state = create_initial_state(
        user_message=user_message, complexity=complexity, max_iterations=max_iterations
    )

    # Merge any additional context
    if context:
        initial_state = {**initial_state, **context}

    # Execute graph
    logger.info(f"🚀 Executing LangGraph for: {user_message[:50]}...")

    final_state = None
    for event in graph.stream(initial_state):
        final_state = event
        # event is a dict of node_name -> state updates

    # Extract final state from last event
    if final_state:
        # LangGraph returns {node_name: state_update}
        # We need to merge updates to get final state
        merged = {**initial_state}
        for node_updates in final_state.values():
            if isinstance(node_updates, dict):
                merged.update(node_updates)
        return merged

    return initial_state


def execute_graph_streaming(
    user_message: str,
    complexity: str = "complex",
    max_iterations: int = 5,
    context: Dict[str, Any] = None,
) -> Generator[Dict[str, Any], None, None]:
    """
    Execute the Trinity graph with streaming updates.

    Yields progress updates as each node completes.

    Args:
        user_message: The user's query
        complexity: Query complexity level
        max_iterations: Maximum reasoning iterations
        context: Additional context

    Yields:
        Progress updates with node name and state changes
    """
    graph = get_trinity_graph()

    initial_state = create_initial_state(
        user_message=user_message, complexity=complexity, max_iterations=max_iterations
    )

    if context:
        initial_state = {**initial_state, **context}

    logger.info(f"🚀 Streaming LangGraph for: {user_message[:50]}...")

    merged_state = {**initial_state}

    for event in graph.stream(initial_state):
        # event is {node_name: state_updates}
        for node_name, updates in event.items():
            if isinstance(updates, dict):
                merged_state.update(updates)

                yield {
                    "node": node_name,
                    "updates": updates,
                    "iteration": merged_state.get("iteration", 0),
                    "current_agent": merged_state.get("current_agent"),
                }

    # Final yield with complete state
    yield {
        "done": True,
        "final_answer": merged_state.get("final_answer"),
        "state": merged_state,
    }
