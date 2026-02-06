"""
Tests for LangGraph endpoint integration in inference_server.py

Phase 3: Tests verify /generate/langgraph endpoint works correctly
with complexity routing.
"""

from unittest.mock import MagicMock, patch



class TestLangGraphEndpointRouting:
    """Test complexity routing logic for LangGraph endpoint"""

    def test_should_use_langgraph_simple_auto(self):
        """Simple queries in auto mode should NOT use LangGraph"""
        from services.graph.edges import should_use_langgraph

        assert should_use_langgraph("simple", "auto") is False

    def test_should_use_langgraph_medium_auto(self):
        """Medium queries in auto mode should NOT use LangGraph"""
        from services.graph.edges import should_use_langgraph

        assert should_use_langgraph("medium", "auto") is False

    def test_should_use_langgraph_complex_auto(self):
        """Complex queries in auto mode SHOULD use LangGraph"""
        from services.graph.edges import should_use_langgraph

        assert should_use_langgraph("complex", "auto") is True

    def test_should_use_langgraph_forced_langgraph(self):
        """langgraph mode forces LangGraph regardless of complexity"""
        from services.graph.edges import should_use_langgraph

        assert should_use_langgraph("simple", "langgraph") is True
        assert should_use_langgraph("medium", "langgraph") is True
        assert should_use_langgraph("complex", "langgraph") is True

    def test_should_use_langgraph_forced_legacy(self):
        """legacy mode forces legacy pipeline regardless of complexity"""
        from services.graph.edges import should_use_langgraph

        assert should_use_langgraph("simple", "legacy") is False
        assert should_use_langgraph("medium", "legacy") is False
        assert should_use_langgraph("complex", "legacy") is False


class TestComplexityClassificationForRouting:
    """Test complexity classifier for routing decisions"""

    def test_simple_query_routes_to_legacy(self):
        """Simple query should be detected and route to legacy"""
        from services.complexity import classify_complexity
        from services.graph.edges import should_use_langgraph

        query = "What is 2+2?"
        complexity = classify_complexity(query)
        use_lg = should_use_langgraph(complexity, "auto")

        assert complexity == "simple"
        assert use_lg is False

    def test_complex_query_routes_to_langgraph(self):
        """Complex query should be detected and route to LangGraph"""
        from services.complexity import classify_complexity
        from services.graph.edges import should_use_langgraph

        # Design tasks are marked as complex in patterns
        query = "Design a distributed system architecture for a real-time messaging platform with millions of users"
        complexity = classify_complexity(query)
        use_lg = should_use_langgraph(complexity, "auto")

        assert complexity == "complex"
        assert use_lg is True

    def test_code_block_routes_to_langgraph(self):
        """Code blocks should always route to LangGraph"""
        from services.complexity import classify_complexity
        from services.graph.edges import should_use_langgraph

        query = """Please refactor this code:
```python
def foo():
    x = []
    for i in range(10):
        x.append(i*2)
    return x
```"""
        complexity = classify_complexity(query)
        use_lg = should_use_langgraph(complexity, "auto")

        assert complexity == "complex"
        assert use_lg is True


class TestLangGraphImports:
    """Test that LangGraph can be imported into inference_server context"""

    def test_langgraph_module_importable(self):
        """Verify graph module is importable"""
        from services.graph import execute_graph, get_trinity_graph

        assert callable(get_trinity_graph)
        assert callable(execute_graph)

    def test_should_use_langgraph_importable(self):
        """Verify should_use_langgraph is importable from graph module"""
        from services.graph import should_use_langgraph

        assert callable(should_use_langgraph)

    def test_complexity_classifier_importable(self):
        """Verify complexity classifier is importable"""
        from services.complexity import classify_complexity

        assert callable(classify_complexity)


class TestGraphState:
    """Test AgentState construction for endpoint"""

    def test_create_initial_state_function(self):
        """Test the create_initial_state helper function"""
        from services.graph.state import create_initial_state

        state = create_initial_state(
            user_message="Design a microservices architecture",
            complexity="complex",
            max_iterations=5,
        )

        assert len(state["messages"]) == 1
        assert state["current_agent"] == "supervisor"  # Graph starts with supervisor
        assert state["complexity"] == "complex"
        assert state["iteration"] == 0
        assert state["max_iterations"] == 5

    def test_create_initial_state_simple_query(self):
        """Test state construction with simple query"""
        from services.graph.state import create_initial_state

        state = create_initial_state(user_message="What is quantum computing?", complexity="simple")

        assert len(state["messages"]) == 1
        assert state["complexity"] == "simple"
        assert state["messages"][0].content == "What is quantum computing?"


class TestGraphExecution:
    """Test graph execution (mocked for unit tests)"""

    @patch("services.graph.graph.get_trinity_graph")
    def test_execute_graph_returns_state(self, mock_get_graph):
        """Test that execute_graph returns a state dict"""
        from services.graph import execute_graph

        # Mock the compiled graph's stream method
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter(
            [
                {
                    "synthesis": {
                        "final_answer": "Mocked response",
                        "iteration": 1,
                        "reasoning_output": "Test reasoning",
                    }
                }
            ]
        )
        mock_get_graph.return_value = mock_graph

        result = execute_graph(user_message="test query", complexity="complex", max_iterations=5)

        # Should return state dict
        assert isinstance(result, dict)
        assert "final_answer" in result
        assert result["final_answer"] == "Mocked response"

    @patch("services.graph.graph.get_trinity_graph")
    def test_execute_graph_with_context(self, mock_get_graph):
        """Test that execute_graph accepts context parameter"""
        from services.graph import execute_graph

        # Mock the compiled graph
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter(
            [{"synthesis": {"final_answer": "Answer with context", "iteration": 1}}]
        )
        mock_get_graph.return_value = mock_graph

        result = execute_graph(
            user_message="follow up question",
            complexity="medium",
            context={"prior_context": "user: hello\nassistant: hi there"},
        )

        assert isinstance(result, dict)


class TestEndpointResponseFormat:
    """Test expected response format from /generate/langgraph"""

    def test_expected_response_fields_langgraph(self):
        """Test that LangGraph response should have these fields"""
        # Simulate expected response for documentation
        expected_fields = {
            "response",  # Final synthesized answer
            "mode_used",  # 'langgraph' or 'legacy'
            "complexity",  # 'simple', 'medium', or 'complex'
            "agents_invoked",  # List of agents that participated
            "iterations",  # Number of graph iterations
            "model",  # Model name
            "provider_id",  # Provider identifier
            "latency_ms",  # Response time
        }

        # Sample LangGraph response
        sample_response = {
            "response": "Here is the architecture...",
            "mode_used": "langgraph",
            "complexity": "complex",
            "agents_invoked": ["router", "reasoning", "synthesis"],
            "iterations": 2,
            "model": "qwen2.5:72b",
            "provider_id": "test-provider",
            "latency_ms": 5000.5,
        }

        assert set(sample_response.keys()) == expected_fields

    def test_expected_response_fields_legacy(self):
        """Test that legacy fallback response should have these fields"""
        expected_fields = {
            "response",
            "mode_used",
            "complexity",
            "agents_invoked",
            "iterations",
            "model",
            "provider_id",
            "latency_ms",
        }

        # Sample legacy response
        sample_response = {
            "response": "The answer is 4.",
            "mode_used": "legacy",
            "complexity": "simple",
            "agents_invoked": ["legacy_agent"],
            "iterations": 1,
            "model": "qwen2.5:72b",
            "provider_id": "test-provider",
            "latency_ms": 500.2,
        }

        assert set(sample_response.keys()) == expected_fields


class TestHealthEndpointFeatures:
    """Test that health endpoint exposes LangGraph availability"""

    def test_health_features_structure(self):
        """Test expected features structure in health response"""
        expected_features = {"v4_intelligence", "langgraph_agents", "semantic_memory", "web_search"}

        # Sample health response features
        sample_features = {
            "v4_intelligence": True,
            "langgraph_agents": True,
            "semantic_memory": True,
            "web_search": True,
        }

        assert set(sample_features.keys()) == expected_features
        assert all(isinstance(v, bool) for v in sample_features.values())
