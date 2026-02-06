"""
Trinity LangGraph Tests - Phase 3

Tests for the LangGraph multi-agent system components.
"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

# =============================================================================
# TEST: STATE MODULE
# =============================================================================


class TestAgentState:
    """Tests for AgentState TypedDict and helpers"""

    def test_import_agent_state(self):
        """AgentState can be imported"""
        from services.graph.state import AgentState

        assert AgentState is not None

    def test_create_initial_state(self):
        """create_initial_state returns valid state"""
        from services.graph.state import create_initial_state

        state = create_initial_state("What is 2+2?")

        assert state["messages"] is not None
        assert len(state["messages"]) == 1
        assert state["messages"][0].content == "What is 2+2?"
        assert state["current_agent"] == "supervisor"
        assert state["iteration"] == 0
        assert state["should_continue"] is True
        assert state["complexity"] == "complex"

    def test_create_initial_state_custom_params(self):
        """create_initial_state accepts custom parameters"""
        from services.graph.state import create_initial_state

        state = create_initial_state(
            user_message="Test query", complexity="medium", max_iterations=3
        )

        assert state["complexity"] == "medium"
        assert state["max_iterations"] == 3


# =============================================================================
# TEST: LLM WRAPPER
# =============================================================================


class TestTrinityLLM:
    """Tests for TrinityLLM LangChain wrapper"""

    def test_import_trinity_llm(self):
        """TrinityLLM can be imported"""
        from services.graph.llm import TrinityLLM

        assert TrinityLLM is not None

    def test_llm_type(self):
        """LLM reports correct type"""
        from services.graph.llm import TrinityLLM

        llm = TrinityLLM()
        assert llm._llm_type == "trinity_ollama"

    def test_llm_model_types(self):
        """Different model types can be instantiated"""
        from services.graph.llm import TrinityLLM

        fast = TrinityLLM(model_type="fast")
        smart = TrinityLLM(model_type="smart")
        reasoning = TrinityLLM(model_type="reasoning")

        assert fast.model_type == "fast"
        assert smart.model_type == "smart"
        assert reasoning.model_type == "reasoning"

    def test_messages_to_prompt(self):
        """Messages are converted to prompt string correctly"""
        from services.graph.llm import TrinityLLM

        llm = TrinityLLM()
        messages = [
            SystemMessage(content="You are helpful."),
            HumanMessage(content="Hello!"),
        ]

        prompt = llm._messages_to_prompt(messages)

        assert "System: You are helpful." in prompt
        assert "User: Hello!" in prompt
        assert "Assistant:" in prompt

    def test_get_model_helpers(self):
        """Helper functions return correct LLM types"""
        from services.graph.llm import get_fast_llm, get_reasoning_llm, get_smart_llm

        fast = get_fast_llm()
        assert fast.model_type == "fast"
        assert fast.temperature == 0.3

        smart = get_smart_llm()
        assert smart.model_type == "smart"

        reasoning = get_reasoning_llm()
        assert reasoning.model_type == "reasoning"
        assert reasoning.timeout == 300


# =============================================================================
# TEST: AGENTS
# =============================================================================


class TestAgents:
    """Tests for specialized agent classes"""

    def test_import_agents(self):
        """All agents can be imported"""
        from services.graph.agents import (
            CodingAgent,
            ReasoningAgent,
            ResearchAgent,
            SupervisorAgent,
            SynthesisAgent,
        )

        assert SupervisorAgent is not None
        assert ResearchAgent is not None
        assert ReasoningAgent is not None
        assert CodingAgent is not None
        assert SynthesisAgent is not None

    def test_supervisor_default_config(self):
        """SupervisorAgent has correct default config"""
        from services.graph.agents import SupervisorAgent

        agent = SupervisorAgent()
        assert agent.config.name == "supervisor"
        assert agent.config.model_type == "fast"
        assert "RESEARCH" in agent.config.system_prompt
        assert "REASONING" in agent.config.system_prompt
        assert "CODING" in agent.config.system_prompt

    def test_research_default_config(self):
        """ResearchAgent has correct default config"""
        from services.graph.agents import ResearchAgent

        agent = ResearchAgent()
        assert agent.config.name == "research"
        assert agent.config.model_type == "smart"
        assert "web_search" in agent.config.tools

    def test_reasoning_default_config(self):
        """ReasoningAgent has correct default config"""
        from services.graph.agents import ReasoningAgent

        agent = ReasoningAgent()
        assert agent.config.name == "reasoning"
        assert agent.config.model_type == "reasoning"
        assert "calculator" in agent.config.tools

    def test_coding_default_config(self):
        """CodingAgent has correct default config"""
        from services.graph.agents import CodingAgent

        agent = CodingAgent()
        assert agent.config.name == "coding"
        assert agent.config.model_type == "smart"
        assert agent.config.temperature == 0.3  # Lower for precise code

    def test_get_agent_factory(self):
        """get_agent factory returns correct agent types"""
        from services.graph.agents import ReasoningAgent, SupervisorAgent, get_agent

        supervisor = get_agent("supervisor")
        assert isinstance(supervisor, SupervisorAgent)

        reasoning = get_agent("reasoning")
        assert isinstance(reasoning, ReasoningAgent)

    def test_get_agent_invalid(self):
        """get_agent raises for invalid agent name"""
        from services.graph.agents import get_agent

        with pytest.raises(ValueError, match="Unknown agent"):
            get_agent("invalid_agent")


# =============================================================================
# TEST: EDGES
# =============================================================================


class TestEdges:
    """Tests for conditional edge functions"""

    def test_route_to_agent_research(self):
        """route_to_agent returns 'research' when current_agent is research"""
        from services.graph.edges import route_to_agent

        state = {"current_agent": "research"}
        assert route_to_agent(state) == "research"

    def test_route_to_agent_coding(self):
        """route_to_agent returns 'coding' when current_agent is coding"""
        from services.graph.edges import route_to_agent

        state = {"current_agent": "coding"}
        assert route_to_agent(state) == "coding"

    def test_route_to_agent_reasoning(self):
        """route_to_agent returns 'reasoning' for reasoning or default"""
        from services.graph.edges import route_to_agent

        state = {"current_agent": "reasoning"}
        assert route_to_agent(state) == "reasoning"

        # Default when not set
        state = {}
        assert route_to_agent(state) == "reasoning"

    def test_should_continue_max_iterations(self):
        """should_continue returns 'synthesize' at max iterations"""
        from services.graph.edges import should_continue

        state = {"iteration": 5, "max_iterations": 5}
        assert should_continue(state) == "synthesize"

    def test_should_continue_on_error(self):
        """should_continue returns 'synthesize' on error"""
        from services.graph.edges import should_continue

        state = {"iteration": 1, "error": "Something went wrong"}
        assert should_continue(state) == "synthesize"

    def test_should_continue_with_content(self):
        """should_continue returns 'synthesize' when content is available"""
        from services.graph.edges import should_continue

        state = {
            "iteration": 1,
            "reasoning_output": "Some analysis...",
            "should_continue": True,
        }
        assert should_continue(state) == "synthesize"

    def test_should_continue_first_iteration(self):
        """should_continue returns 'continue' on first iteration without content"""
        from services.graph.edges import should_continue

        state = {
            "iteration": 0,
            "should_continue": True,
        }
        assert should_continue(state) == "continue"

    def test_should_use_langgraph(self):
        """should_use_langgraph respects complexity routing"""
        from services.graph.edges import should_use_langgraph

        # Only complex uses LangGraph in auto mode
        assert should_use_langgraph("complex", "auto") is True
        assert should_use_langgraph("medium", "auto") is False
        assert should_use_langgraph("simple", "auto") is False

        # Force modes
        assert should_use_langgraph("simple", "langgraph") is True
        assert should_use_langgraph("complex", "legacy") is False


# =============================================================================
# TEST: NODES
# =============================================================================


class TestNodes:
    """Tests for graph node functions"""

    def test_import_nodes(self):
        """All nodes can be imported"""
        from services.graph.nodes import (
            coding_node,
            reasoning_node,
            research_node,
            router_node,
            synthesis_node,
        )

        assert router_node is not None
        assert research_node is not None
        assert reasoning_node is not None
        assert coding_node is not None
        assert synthesis_node is not None

    @patch("services.graph.nodes.SupervisorAgent")
    def test_router_node_routes_correctly(self, mock_supervisor_class):
        """router_node sets current_agent based on supervisor decision"""
        from services.graph.nodes import router_node

        # Mock supervisor to return 'research'
        mock_supervisor = MagicMock()
        mock_supervisor.invoke.return_value = "research"
        mock_supervisor_class.return_value = mock_supervisor

        state = {
            "messages": [HumanMessage(content="What's the weather?")],
            "iteration": 0,
        }

        result = router_node(state)

        assert result["current_agent"] == "research"
        assert result["iteration"] == 1

    @patch("services.graph.nodes.ReasoningAgent")
    def test_reasoning_node_produces_output(self, mock_agent_class):
        """reasoning_node produces reasoning_output"""
        from services.graph.nodes import reasoning_node

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = "Step 1: Analyze..."
        mock_agent_class.return_value = mock_agent

        state = {
            "messages": [HumanMessage(content="Explain quantum computing")],
        }

        result = reasoning_node(state)

        assert "reasoning_output" in result
        assert result["reasoning_output"] == "Step 1: Analyze..."
        assert "messages" in result

    @patch("services.graph.nodes.SynthesisAgent")
    def test_synthesis_node_produces_final(self, mock_agent_class):
        """synthesis_node produces final_answer"""
        from services.graph.nodes import synthesis_node

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = "Final synthesized response"
        mock_agent_class.return_value = mock_agent

        state = {
            "messages": [HumanMessage(content="Test")],
            "reasoning_output": "Analysis...",
        }

        result = synthesis_node(state)

        assert "final_answer" in result
        assert result["final_answer"] == "Final synthesized response"
        assert result["should_continue"] is False


# =============================================================================
# TEST: GRAPH ASSEMBLY
# =============================================================================


class TestGraphAssembly:
    """Tests for graph creation and compilation"""

    def test_create_trinity_graph(self):
        """create_trinity_graph returns a compiled graph"""
        from services.graph.graph import create_trinity_graph

        graph = create_trinity_graph()

        # Should be a compiled graph
        assert graph is not None
        assert hasattr(graph, "stream")
        assert hasattr(graph, "invoke")

    def test_get_trinity_graph_singleton(self):
        """get_trinity_graph returns same instance"""
        from services.graph.graph import get_trinity_graph, reset_graph

        reset_graph()  # Clear any existing

        graph1 = get_trinity_graph()
        graph2 = get_trinity_graph()

        assert graph1 is graph2

    def test_reset_graph(self):
        """reset_graph clears the singleton"""
        from services.graph.graph import get_trinity_graph, reset_graph

        graph1 = get_trinity_graph()
        reset_graph()
        graph2 = get_trinity_graph()

        # Should be different instances after reset
        assert graph1 is not graph2

    def test_graph_has_expected_nodes(self):
        """Graph contains all expected nodes"""
        from services.graph.graph import get_trinity_graph, reset_graph

        reset_graph()
        graph = get_trinity_graph()

        # Check node names
        node_names = list(graph.nodes.keys())

        assert "router" in node_names
        assert "research" in node_names
        assert "reasoning" in node_names
        assert "coding" in node_names
        assert "synthesis" in node_names


# =============================================================================
# TEST: EXECUTION HELPERS
# =============================================================================


class TestExecutionHelpers:
    """Tests for graph execution helper functions"""

    def test_execute_graph_import(self):
        """execute_graph can be imported"""
        from services.graph.graph import execute_graph, execute_graph_streaming

        assert execute_graph is not None
        assert execute_graph_streaming is not None

    @patch("services.graph.graph.get_trinity_graph")
    def test_execute_graph_returns_state(self, mock_get_graph):
        """execute_graph returns final state with answer"""
        from services.graph.graph import execute_graph

        # Mock graph that yields one event
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter(
            [{"synthesis": {"final_answer": "Test answer", "should_continue": False}}]
        )
        mock_get_graph.return_value = mock_graph

        result = execute_graph("Test question")

        assert result is not None
        assert "final_answer" in result


# =============================================================================
# TEST: INTEGRATION (Mocked)
# =============================================================================


class TestIntegration:
    """Integration tests with mocked LLM calls"""

    @patch("services.graph.llm.TrinityLLM._call")
    def test_full_pipeline_mocked(self, mock_llm_call):
        """Full pipeline executes with mocked LLM"""
        from services.graph.graph import execute_graph, reset_graph

        # Mock LLM responses
        mock_llm_call.side_effect = [
            "REASONING",  # Supervisor routes to reasoning
            "Step 1: Think\nStep 2: Analyze\nConclusion: 42",  # Reasoning output
            "The answer is 42 based on careful analysis.",  # Synthesis
        ]

        reset_graph()
        result = execute_graph("What is the meaning of life?", max_iterations=1)

        # Should have completed
        assert result is not None

    def test_complexity_routing_integration(self):
        """Complexity routing correctly selects pipeline"""
        from services.complexity import classify_complexity
        from services.graph.edges import should_use_langgraph

        # Simple query should use legacy
        simple_complexity = classify_complexity("Hi")
        use_langgraph = should_use_langgraph(simple_complexity, "auto")
        # Note: classify_complexity may return 'simple' or 'medium' for "Hi"
        # Either way, it shouldn't trigger langgraph
        if simple_complexity in ["simple", "medium"]:
            assert use_langgraph is False

        # Force langgraph mode
        assert should_use_langgraph("simple", "langgraph") is True
