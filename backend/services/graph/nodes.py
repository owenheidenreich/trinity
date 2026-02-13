"""
Trinity LangGraph Node Implementations

Each node is a function that takes AgentState and returns updated state.
Nodes represent the actual work done by each agent in the graph.

Tool integration: nodes use execute_tool() with principal_id context
so all 8 tools (including memory) are available to LangGraph agents.
"""

import logging
from typing import Any, Dict, List

from langchain_core.messages import AIMessage

# Observability integration (Phase 5.5A: Direct import, no fallback)
from middleware.observability import record_routing, track_agent_pass

from .agents import CodingAgent, ReasoningAgent, ResearchAgent, SupervisorAgent, SynthesisAgent
from .state import AgentState

logger = logging.getLogger(__name__)


def _get_tool_context(state: AgentState) -> Dict:
    """Build tool execution context from graph state."""
    ctx = {}
    principal_id = state.get("principal_id")
    if principal_id:
        ctx["principal_id"] = principal_id
    return ctx


def _execute_tool_calls_from_text(text: str, state: AgentState) -> tuple:
    """Parse and execute any tool calls found in agent output.

    Uses the shared execute_tool() with principal_id context so all 8 tools
    (including memory tools) are available.

    Returns (enriched_text, tool_results_list).
    """
    try:
        from services.code_executor import execute_tool
        from services.tools import parse_tool_calls

        tool_calls = parse_tool_calls(text)
        if not tool_calls:
            return text, []

        context = _get_tool_context(state)
        results = []
        for call in tool_calls:
            success, output = execute_tool(call.name, call.params, context=context)
            status = "Result" if success else "Error"
            results.append({
                "tool": call.name,
                "success": success,
                "output": output[:500],
            })
            text += f"\n\n[Tool {status}: {call.name}]\n{output}"

        return text, results
    except Exception as e:
        logger.warning(f"Tool execution helper failed: {e}")
        return text, []


def router_node(state: AgentState) -> Dict[str, Any]:
    """
    Router node - determines which specialist handles the query.

    Uses SupervisorAgent to classify and route the query.
    """
    with track_agent_pass("understand") as tracker:
        try:
            supervisor = SupervisorAgent()
            next_agent = supervisor.invoke(state)

            logger.info(f"🎯 Router: Directing to '{next_agent}' agent")
            record_routing("langgraph")  # Track that we're using LangGraph

            return {
                "current_agent": next_agent,
                "iteration": state.get("iteration", 0) + 1,
            }
        except Exception as e:
            logger.error(f"Router error: {e}")
            tracker.set_status("error")
            return {
                "current_agent": "reasoning",  # Default fallback
                "iteration": state.get("iteration", 0) + 1,
                "error": str(e),
            }


def research_node(state: AgentState) -> Dict[str, Any]:
    """
    Research node - handles web search and document analysis.

    Performs web search first, then invokes the research agent with context.
    Any tool calls in the agent's output are executed with principal_id context.
    """
    with track_agent_pass("execute") as tracker:
        try:
            agent = ResearchAgent()

            # Check if we should do web search
            messages = state.get("messages", [])
            if messages:
                query = (
                    messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
                )

                # Attempt web search using existing Trinity search
                search_context = _perform_web_search(query)

                # Update state with search results, then invoke agent
                state_with_search = {**state, "research_context": search_context}
                result = agent.invoke(state_with_search)
            else:
                result = agent.invoke(state)

            # Execute any tool calls in the agent's output
            result, tool_results = _execute_tool_calls_from_text(result, state)

            logger.info(f"📚 Research agent completed, output length: {len(result)}")

            update = {
                "research_context": result,
                "messages": [AIMessage(content=f"[Research Agent]\n{result}")],
            }
            if tool_results:
                update["tool_results"] = tool_results
            return update
        except Exception as e:
            logger.error(f"Research node error: {e}")
            tracker.set_status("error")
            return {
                "error": str(e),
                "messages": [AIMessage(content=f"[Research Agent Error: {e}]")],
            }


def reasoning_node(state: AgentState) -> Dict[str, Any]:
    """
    Reasoning node - handles complex logic and analysis.

    Uses the most capable model for deep thinking tasks.
    Any tool calls (calculator, memory) are executed with principal_id context.
    """
    with track_agent_pass("execute") as tracker:
        try:
            agent = ReasoningAgent()
            result = agent.invoke(state)

            # Execute any tool calls in the agent's output
            result, tool_results = _execute_tool_calls_from_text(result, state)

            logger.info(f"🧠 Reasoning agent completed, output length: {len(result)}")

            update = {
                "reasoning_output": result,
                "messages": [AIMessage(content=f"[Reasoning Agent]\n{result}")],
            }
            if tool_results:
                update["tool_results"] = tool_results
            return update
        except Exception as e:
            logger.error(f"Reasoning node error: {e}")
            tracker.set_status("error")
            return {
                "error": str(e),
                "messages": [AIMessage(content=f"[Reasoning Agent Error: {e}]")],
            }


def coding_node(state: AgentState) -> Dict[str, Any]:
    """
    Coding node - handles code generation and execution.

    Tool calls (code_display, calculator) are executed with principal_id context.
    """
    with track_agent_pass("execute") as tracker:
        try:
            agent = CodingAgent()
            result = agent.invoke(state)

            # Execute any tool calls in the agent's output
            result, tool_results = _execute_tool_calls_from_text(result, state)

            logger.info(f"💻 Coding agent completed, output length: {len(result)}")

            update = {
                "code_output": result,
                "messages": [AIMessage(content=f"[Coding Agent]\n{result}")],
            }
            if tool_results:
                update["tool_results"] = tool_results
            return update
        except Exception as e:
            logger.error(f"Coding node error: {e}")
            tracker.set_status("error")
            return {
                "error": str(e),
                "messages": [AIMessage(content=f"[Coding Agent Error: {e}]")],
            }


def synthesis_node(state: AgentState) -> Dict[str, Any]:
    """
    Synthesis node - combines outputs into final response.

    This is typically the final node before returning to user.
    """
    with track_agent_pass("refine") as tracker:
        try:
            agent = SynthesisAgent()
            result = agent.invoke(state)

            logger.info(f"✨ Synthesis completed, output length: {len(result)}")

            return {
                "final_answer": result,
                "should_continue": False,
                "messages": [AIMessage(content=result)],
            }
        except Exception as e:
            logger.error(f"Synthesis node error: {e}")
            tracker.set_status("error")

            # Fallback: return best available output
            fallback = (
                state.get("reasoning_output")
                or state.get("research_context")
                or state.get("code_output")
                or "I apologize, but I encountered an error while synthesizing the response."
            )

            return {
                "final_answer": fallback,
                "should_continue": False,
                "error": str(e),
            }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _perform_web_search(query: str) -> str:
    """
    Perform web search using Trinity's existing search module.
    """
    try:
        from services.search import format_search_context, is_search_available, search_web

        if not is_search_available():
            return ""

        result = search_web(query, count=5, timeout=30)
        if result.error or not result.results:
            return ""

        return format_search_context(result)
    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return ""
