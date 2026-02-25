"""
Trinity Backend - ReAct Agentic Loop Test Suite
================================================
Tests for the ReAct (Reasoning + Acting) iterative tool-calling loop.

Focus Areas:
1. Loop termination (no tools → immediate answer)
2. Single tool call iteration
3. Max iteration safety limit
4. Tool error handling
5. Streaming event generation
"""

from unittest.mock import MagicMock, patch

from services.react_loop import ReactLoop, ReactResult
from services.tools import ToolResult, parse_tool_calls


class TestParseToolCallsInReactContext:
    """Verify tool call parsing works for ReAct-style outputs."""

    def test_no_tool_calls_in_plain_text(self):
        """Plain text response has no tool calls."""
        text = "The answer is 42. No tools needed here."
        assert parse_tool_calls(text) == []

    def test_single_calculator_call(self):
        """Parses a calculator tool call from model output."""
        text = 'I need to calculate this.\n<tool_call name="calculator"><expression>sqrt(144) + 10**2</expression></tool_call>'
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "calculator"
        assert calls[0].params["expression"] == "sqrt(144) + 10**2"

    def test_multiple_tool_calls_parsed(self):
        """Multiple tool calls in one response are all parsed."""
        text = '<tool_call name="calculator"><expression>2+2</expression></tool_call>\nThen also\n<tool_call name="web_search"><query>test</query></tool_call>'
        calls = parse_tool_calls(text)
        assert len(calls) == 2
        assert calls[0].name == "calculator"
        assert calls[1].name == "web_search"


class TestReactLoopExecute:
    """Test the non-streaming execute() method with mocked Ollama."""

    def _make_mock_client(self, responses):
        """Create a mock OllamaClient that returns predefined responses."""
        client = MagicMock()
        client.model = "phi3"  # Non-native model to force XML mode
        client.chat = MagicMock(side_effect=responses)
        return client

    def test_direct_answer_no_tools(self):
        """Model gives a direct answer without using tools → 1 iteration."""
        client = self._make_mock_client(["The answer is 42."])
        loop = ReactLoop(client, max_iterations=5)

        result = loop.execute(question="What is the meaning of life?")

        assert isinstance(result, ReactResult)
        assert result.answer == "The answer is 42."
        assert result.tools_used == []
        assert result.iterations == 1
        assert client.chat.call_count == 1

    def test_single_tool_then_answer(self):
        """Model calls calculator, gets result, then gives final answer."""
        responses = [
            # First call: model wants to use calculator
            'Let me calculate.\n<tool_call name="calculator"><expression>sqrt(144)</expression></tool_call>',
            # Second call: model gives final answer using tool result
            "The square root of 144 is 12.",
        ]
        client = self._make_mock_client(responses)
        loop = ReactLoop(client, max_iterations=5)

        with patch("services.react_loop.execute_tool", return_value=(True, "12.0")):
            result = loop.execute(question="What is sqrt(144)?")

        assert result.answer == "The square root of 144 is 12."
        assert result.tools_used == ["calculator"]
        assert result.iterations == 2
        assert client.chat.call_count == 2

    def test_multiple_tools_then_answer(self):
        """Model calls multiple tools across iterations."""
        responses = [
            '<tool_call name="calculator"><expression>2+2</expression></tool_call>',
            '<tool_call name="calculator"><expression>4*3</expression></tool_call>',
            "2+2 is 4, and 4*3 is 12.",
        ]
        client = self._make_mock_client(responses)
        loop = ReactLoop(client, max_iterations=5)

        with patch("services.react_loop.execute_tool", return_value=(True, "computed")):
            result = loop.execute(question="Calculate 2+2, then multiply by 3")

        assert result.iterations == 3
        assert result.tools_used == ["calculator", "calculator"]

    def test_max_iterations_forces_answer(self):
        """Loop exits at max_iterations even if model keeps calling tools."""
        # Model always wants to call tools — each with different params to avoid duplicate guard
        tool_responses = [
            '<tool_call name="calculator"><expression>1+1</expression></tool_call>',
            '<tool_call name="calculator"><expression>2+2</expression></tool_call>',
            '<tool_call name="calculator"><expression>3+3</expression></tool_call>',
        ]
        # After max iterations, forced final answer
        final_response = "Based on my calculations: 2."

        responses = tool_responses + [final_response]
        client = self._make_mock_client(responses)
        loop = ReactLoop(client, max_iterations=3)

        with patch("services.react_loop.execute_tool", return_value=(True, "2")):
            result = loop.execute(question="Keep calculating")

        assert result.iterations == 3
        # 3 tool iterations + 1 forced final = 4 chat calls
        assert client.chat.call_count == 4

    def test_duplicate_tool_call_guard(self):
        """Duplicate tool call (same name + params) is blocked, forces final answer."""
        tool_response = '<tool_call name="calculator"><expression>1+1</expression></tool_call>'
        final_response = "The answer is 2."  # Should never be reached

        responses = [tool_response, tool_response, final_response]
        client = self._make_mock_client(responses)
        loop = ReactLoop(client, max_iterations=5)

        with patch("services.react_loop.execute_tool", return_value=(True, "2")):
            result = loop.execute(question="What is 1+1?")

        # Should short-circuit on iteration 2 (duplicate detected)
        assert result.iterations == 2
        assert len(result.tools_used) == 1  # Only executed once
        assert "2" in result.answer  # Should use cached result

    def test_tool_error_continues_loop(self):
        """Tool execution error is reported to model, loop continues."""
        responses = [
            '<tool_call name="calculator"><expression>invalid</expression></tool_call>',
            "I encountered an error, so the expression was invalid.",
        ]
        client = self._make_mock_client(responses)
        loop = ReactLoop(client, max_iterations=5)

        with patch("services.react_loop.execute_tool", return_value=(False, "SyntaxError: invalid expression")):
            result = loop.execute(question="Calculate invalid")

        assert result.iterations == 2
        assert result.tools_used == ["calculator"]
        # Model should still give a coherent answer
        assert "error" in result.answer.lower() or "invalid" in result.answer.lower()

    def test_empty_response_from_ollama(self):
        """Empty Ollama response breaks out of loop gracefully."""
        # First call returns empty, then forced final answer call
        client = self._make_mock_client(["", "I had trouble but here's my answer."])
        loop = ReactLoop(client, max_iterations=5)

        result = loop.execute(question="Something")

        # Empty response triggers forced final answer path
        assert result.answer is not None
        assert len(result.answer) > 0

    def test_only_first_tool_call_executed(self):
        """When model outputs multiple tool calls, only the first is executed."""
        responses = [
            '<tool_call name="calculator"><expression>2+2</expression></tool_call>\n<tool_call name="web_search"><query>test</query></tool_call>',
            "The answer is 4.",
        ]
        client = self._make_mock_client(responses)
        loop = ReactLoop(client, max_iterations=5)

        with patch("services.react_loop.execute_tool", return_value=(True, "4")) as mock_exec:
            result = loop.execute(question="Calculate and search")

        # Only one tool should have been executed per iteration
        assert mock_exec.call_count == 1
        assert result.tools_used == ["calculator"]


class TestReactLoopStreaming:
    """Test the streaming execute_streaming() method."""

    def _make_mock_client(self, chat_responses, stream_tokens=None):
        """Create a mock client for streaming tests."""
        client = MagicMock()
        client.model = "phi3"  # Non-native model to force XML mode
        client.chat = MagicMock(side_effect=chat_responses)
        if stream_tokens:
            client.chat_stream = MagicMock(return_value=iter(stream_tokens))
        return client

    def test_streaming_direct_answer(self):
        """No tools → answer streamed as tokens."""
        client = self._make_mock_client(["Hello world"])
        loop = ReactLoop(client, max_iterations=5)

        events = list(loop.execute_streaming(question="Say hello"))

        # Should have token events and a react_done event
        token_events = [e for e in events if "token" in e]
        done_events = [e for e in events if "react_done" in e]

        assert len(token_events) > 0
        assert len(done_events) == 1
        assert done_events[0]["iterations"] == 1

        # Reconstruct full text
        full_text = "".join(e["token"] for e in token_events)
        assert full_text == "Hello world"

    def test_streaming_with_tool_yields_phase_events(self):
        """Tool calls produce phase events before the final answer."""
        responses = [
            '<tool_call name="calculator"><expression>2+2</expression></tool_call>',
            "The answer is 4.",
        ]
        client = self._make_mock_client(responses)
        loop = ReactLoop(client, max_iterations=5)

        with patch("services.react_loop.execute_tool", return_value=(True, "4")):
            events = list(loop.execute_streaming(question="Calculate 2+2"))

        # Check for tool execution phase events
        phase_events = [e for e in events if "phase" in e]
        assert any(e["phase"] == "tool_execution" for e in phase_events)
        assert any(e["phase"] == "tool_result" for e in phase_events)

        # Check for token events (the final answer)
        token_events = [e for e in events if "token" in e]
        full_text = "".join(e["token"] for e in token_events)
        assert full_text == "The answer is 4."

    def test_streaming_max_iterations_uses_chat_stream(self):
        """When max iterations hit, final answer uses chat_stream for real streaming."""
        # Different params each iteration to avoid duplicate-call guard
        tool_responses = [
            '<tool_call name="calculator"><expression>1+1</expression></tool_call>',
            '<tool_call name="calculator"><expression>2+2</expression></tool_call>',
        ]
        stream_tokens = ["The ", "answer ", "is ", "2."]

        client = self._make_mock_client(tool_responses, stream_tokens=stream_tokens)
        loop = ReactLoop(client, max_iterations=2)

        with patch("services.react_loop.execute_tool", return_value=(True, "2")):
            events = list(loop.execute_streaming(question="Calculate"))

        # Final answer should come from chat_stream
        token_events = [e for e in events if "token" in e]
        full_text = "".join(e["token"] for e in token_events)
        assert full_text == "The answer is 2."


class TestReactLoopMessageBuilding:
    """Test that messages are built correctly for /api/chat."""

    def test_system_message_includes_tools(self):
        """System message contains tool definitions."""
        client = MagicMock()
        client.model = "phi3"
        client.chat = MagicMock(return_value="Direct answer.")
        loop = ReactLoop(client, max_iterations=5)

        loop.execute(question="Hello")

        # Inspect the messages passed to chat()
        call_args = client.chat.call_args
        messages = call_args[0][0] if call_args[0] else call_args[1]["messages"]

        assert messages[0]["role"] == "system"
        assert "calculator" in messages[0]["content"]
        assert "tool_call" in messages[0]["content"]

    def test_context_messages_included(self):
        """Prior conversation is included in messages."""
        client = MagicMock()
        client.model = "phi3"
        client.chat = MagicMock(return_value="Response.")
        loop = ReactLoop(client, max_iterations=5)

        context = [
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"},
        ]
        loop.execute(question="Follow up", context_messages=context)

        call_args = client.chat.call_args
        messages = call_args[0][0] if call_args[0] else call_args[1]["messages"]

        # system + 2 context + current question = 4 messages
        assert len(messages) == 4
        assert messages[1]["content"] == "Previous question"
        assert messages[2]["content"] == "Previous answer"
        assert messages[3]["content"] == "Follow up"

    def test_tool_result_appended_to_conversation(self):
        """After tool execution, result is added to the message history."""
        responses = [
            '<tool_call name="calculator"><expression>5+5</expression></tool_call>',
            "The answer is 10.",
        ]
        client = MagicMock()
        client.model = "phi3"
        client.chat = MagicMock(side_effect=responses)
        loop = ReactLoop(client, max_iterations=5)

        with patch("services.react_loop.execute_tool", return_value=(True, "10")):
            loop.execute(question="What is 5+5?")

        # Second call should have tool result in messages
        second_call_messages = client.chat.call_args_list[1][0][0]
        # Find the tool result message
        tool_result_msg = [m for m in second_call_messages if "Tool Result" in m.get("content", "")]
        assert len(tool_result_msg) == 1
        assert "10" in tool_result_msg[0]["content"]


class TestChunkText:
    """Test the text chunking helper."""

    def test_chunks_text_correctly(self):
        """Text is split into chunks of specified size."""
        chunks = list(ReactLoop._chunk_text("Hello World!", chunk_size=5))
        assert chunks == ["Hello", " Worl", "d!"]

    def test_empty_text(self):
        """Empty text produces no chunks."""
        chunks = list(ReactLoop._chunk_text(""))
        assert chunks == []

    def test_text_shorter_than_chunk(self):
        """Short text is a single chunk."""
        chunks = list(ReactLoop._chunk_text("Hi", chunk_size=10))
        assert chunks == ["Hi"]
