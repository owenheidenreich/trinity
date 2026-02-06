"""
Trinity LangGraph Node Implementations

Each node is a function that takes AgentState and returns updated state.
Nodes represent the actual work done by each agent in the graph.
"""

import logging
from typing import Dict, Any
from langchain_core.messages import AIMessage

from .state import AgentState
from .agents import (
    SupervisorAgent, ResearchAgent, ReasoningAgent, 
    CodingAgent, SynthesisAgent
)

# Observability integration (Phase 5.5A: Direct import, no fallback)
from middleware.observability import track_agent_pass, record_routing

logger = logging.getLogger(__name__)


def router_node(state: AgentState) -> Dict[str, Any]:
    """
    Router node - determines which specialist handles the query.
    
    Uses SupervisorAgent to classify and route the query.
    """
    with track_agent_pass('understand') as tracker:
        try:
            supervisor = SupervisorAgent()
            next_agent = supervisor.invoke(state)
            
            logger.info(f"🎯 Router: Directing to '{next_agent}' agent")
            record_routing('langgraph')  # Track that we're using LangGraph
            
            return {
                'current_agent': next_agent,
                'iteration': state.get('iteration', 0) + 1,
            }
        except Exception as e:
            logger.error(f"Router error: {e}")
            tracker.set_status('error')
            return {
                'current_agent': 'reasoning',  # Default fallback
                'iteration': state.get('iteration', 0) + 1,
                'error': str(e),
            }


def research_node(state: AgentState) -> Dict[str, Any]:
    """
    Research node - handles web search and document analysis.
    
    Integrates with Trinity's existing search capabilities.
    """
    with track_agent_pass('execute') as tracker:
        try:
            agent = ResearchAgent()
            
            # Check if we should do web search
            messages = state.get('messages', [])
            if messages:
                query = messages[-1].content if hasattr(messages[-1], 'content') else str(messages[-1])
                
                # Attempt web search using existing Trinity search
                search_context = _perform_web_search(query)
                
                # Update state with search results, then invoke agent
                state_with_search = {**state, 'research_context': search_context}
                result = agent.invoke(state_with_search)
            else:
                result = agent.invoke(state)
            
            logger.info(f"📚 Research agent completed, output length: {len(result)}")
            
            return {
                'research_context': result,
                'messages': [AIMessage(content=f"[Research Agent]\n{result}")],
            }
        except Exception as e:
            logger.error(f"Research node error: {e}")
            tracker.set_status('error')
            return {
                'error': str(e),
                'messages': [AIMessage(content=f"[Research Agent Error: {e}]")],
            }


def reasoning_node(state: AgentState) -> Dict[str, Any]:
    """
    Reasoning node - handles complex logic and analysis.
    
    Uses the most capable model for deep thinking tasks.
    """
    with track_agent_pass('execute') as tracker:
        try:
            agent = ReasoningAgent()
            result = agent.invoke(state)
            
            logger.info(f"🧠 Reasoning agent completed, output length: {len(result)}")
            
            return {
                'reasoning_output': result,
                'messages': [AIMessage(content=f"[Reasoning Agent]\n{result}")],
            }
        except Exception as e:
            logger.error(f"Reasoning node error: {e}")
            tracker.set_status('error')
            return {
                'error': str(e),
                'messages': [AIMessage(content=f"[Reasoning Agent Error: {e}]")],
            }


def coding_node(state: AgentState) -> Dict[str, Any]:
    """
    Coding node - handles code generation and execution.
    
    Integrates with Trinity's sandboxed code execution.
    """
    with track_agent_pass('execute') as tracker:
        try:
            agent = CodingAgent()
            result = agent.invoke(state)
            
            # Optionally execute code if requested
            executed_result = _maybe_execute_code(result)
            
            logger.info(f"💻 Coding agent completed, output length: {len(result)}")
            
            return {
                'code_output': executed_result or result,
                'messages': [AIMessage(content=f"[Coding Agent]\n{executed_result or result}")],
            }
        except Exception as e:
            logger.error(f"Coding node error: {e}")
            tracker.set_status('error')
            return {
                'error': str(e),
                'messages': [AIMessage(content=f"[Coding Agent Error: {e}]")],
            }


def synthesis_node(state: AgentState) -> Dict[str, Any]:
    """
    Synthesis node - combines outputs into final response.
    
    This is typically the final node before returning to user.
    """
    with track_agent_pass('refine') as tracker:
        try:
            agent = SynthesisAgent()
            result = agent.invoke(state)
            
            logger.info(f"✨ Synthesis completed, output length: {len(result)}")
            
            return {
                'final_answer': result,
                'should_continue': False,
                'messages': [AIMessage(content=result)],
            }
        except Exception as e:
            logger.error(f"Synthesis node error: {e}")
            tracker.set_status('error')
            
            # Fallback: return best available output
            fallback = (
                state.get('reasoning_output') or 
                state.get('research_context') or 
                state.get('code_output') or
                "I apologize, but I encountered an error while synthesizing the response."
            )
            
            return {
                'final_answer': fallback,
                'should_continue': False,
                'error': str(e),
            }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _perform_web_search(query: str) -> str:
    """
    Perform web search using Trinity's existing search module.
    """
    try:
        from services.search import search_web, format_search_context, is_search_available
        
        if not is_search_available():
            return ""
        
        result = search_web(query, count=5, timeout=30)
        if result.error or not result.results:
            return ""
        
        return format_search_context(result)
    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return ""


def _maybe_execute_code(code_response: str) -> str:
    """
    Optionally execute code blocks from the response.
    
    Only executes if code is wrapped in specific markers.
    """
    try:
        from services.code_executor import execute_tool
        from services.tools import parse_tool_calls
        
        # Check for tool calls in the response
        tool_calls = parse_tool_calls(code_response)
        
        if not tool_calls:
            return code_response
        
        # Execute each tool call
        results = []
        for call in tool_calls:
            if call.name in ['calculator', 'code_display']:
                success, output = execute_tool(call.name, call.params)
                if success:
                    results.append(f"[Tool Result: {call.name}]\n{output}")
                else:
                    results.append(f"[Tool Error: {call.name}]\n{output}")
        
        if results:
            return code_response + "\n\n" + "\n\n".join(results)
        
        return code_response
        
    except Exception as e:
        logger.warning(f"Code execution helper failed: {e}")
        return code_response
