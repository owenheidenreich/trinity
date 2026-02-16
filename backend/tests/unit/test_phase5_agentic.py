"""
Trinity Backend - Phase 5 Agentic Scaffolding Test Suite
========================================================
Tests for Phase 5: filesystem tools, sandbox security, Reflexion pattern,
token budget guard, repo map, and ReAct iteration limits.

Verification Matrix (from INTELLIGENCE-OVERHAUL.md §5.5):
1. File tools: list_directory, read_file, write_file, search_codebase
2. Code execution: run_command with allowed commands
3. Security: path traversal blocked, disallowed commands blocked
4. Reflexion: error → retry observation format
5. Token budget: force final answer when approaching limit
6. Repo map: generates structural overview from workspace files
7. Iteration limit: REACT_MAX_ITERATIONS = 15
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# Filesystem Tool Tests
# ============================================================================


class TestSandboxPathResolution:
    """Test path traversal prevention in _resolve_sandbox_path."""

    def test_normal_path_resolves(self, tmp_path):
        """Normal relative path resolves within workspace."""
        from services.code_executor import _resolve_sandbox_path

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            valid, resolved = _resolve_sandbox_path("src/main.py")
            assert valid is True
            assert resolved.startswith(str(tmp_path))
            assert resolved.endswith("src/main.py")

    def test_path_traversal_blocked(self, tmp_path):
        """Path traversal with ../ is blocked."""
        from services.code_executor import _resolve_sandbox_path

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            valid, resolved = _resolve_sandbox_path("../../etc/passwd")
            assert valid is False
            assert "path traversal blocked" in resolved.lower()

    def test_absolute_path_outside_workspace_blocked(self, tmp_path):
        """Absolute path outside workspace is blocked."""
        from services.code_executor import _resolve_sandbox_path

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            valid, resolved = _resolve_sandbox_path("/etc/passwd")
            assert valid is False
            assert "path traversal blocked" in resolved.lower()

    def test_dot_path_resolves_to_workspace(self, tmp_path):
        """Dot path resolves to workspace root."""
        from services.code_executor import _resolve_sandbox_path

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            valid, resolved = _resolve_sandbox_path(".")
            assert valid is True
            assert resolved == str(tmp_path)


class TestReadFile:
    """Test _execute_read_file tool."""

    def test_read_existing_file(self, tmp_path):
        """Reads an existing file with line numbers."""
        from services.code_executor import _execute_read_file

        # Create test file
        test_file = tmp_path / "hello.py"
        test_file.write_text("print('hello')\nprint('world')\n")

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_read_file({"path": "hello.py"}, tracker)

        assert success is True
        assert "hello.py" in output
        assert "print('hello')" in output
        assert "2 lines" in output

    def test_read_file_with_line_range(self, tmp_path):
        """Reads specific line range from a file."""
        from services.code_executor import _execute_read_file

        # Create test file with 10 lines
        lines = [f"line {i}" for i in range(1, 11)]
        test_file = tmp_path / "data.txt"
        test_file.write_text("\n".join(lines))

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_read_file(
                {"path": "data.txt", "start_line": "3", "end_line": "5"}, tracker
            )

        assert success is True
        assert "line 3" in output
        assert "line 5" in output
        assert "lines 3-5" in output

    def test_read_nonexistent_file(self, tmp_path):
        """Returns error for nonexistent file."""
        from services.code_executor import _execute_read_file

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_read_file({"path": "missing.py"}, tracker)

        assert success is False
        assert "not found" in output.lower()

    def test_read_file_path_traversal_blocked(self, tmp_path):
        """Path traversal in read_file is blocked."""
        from services.code_executor import _execute_read_file

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_read_file({"path": "../../etc/passwd"}, tracker)

        assert success is False
        assert "path traversal" in output.lower()


class TestWriteFile:
    """Test _execute_write_file tool."""

    def test_write_new_file(self, tmp_path):
        """Creates a new file with content."""
        from services.code_executor import _execute_write_file

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_write_file(
                {"path": "output.py", "content": "print('hello')\n"}, tracker
            )

        assert success is True
        assert "Created" in output
        assert (tmp_path / "output.py").read_text() == "print('hello')\n"

    def test_write_creates_parent_dirs(self, tmp_path):
        """Creates parent directories when writing nested file."""
        from services.code_executor import _execute_write_file

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_write_file(
                {"path": "src/deep/file.py", "content": "x = 1\n"}, tracker
            )

        assert success is True
        assert (tmp_path / "src" / "deep" / "file.py").exists()

    def test_write_updates_existing_file(self, tmp_path):
        """Updates an existing file."""
        from services.code_executor import _execute_write_file

        (tmp_path / "existing.py").write_text("old content")

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_write_file(
                {"path": "existing.py", "content": "new content\n"}, tracker
            )

        assert success is True
        assert "Updated" in output
        assert (tmp_path / "existing.py").read_text() == "new content\n"

    def test_write_file_path_traversal_blocked(self, tmp_path):
        """Path traversal in write_file is blocked."""
        from services.code_executor import _execute_write_file

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_write_file(
                {"path": "../../../tmp/evil.sh", "content": "rm -rf /"}, tracker
            )

        assert success is False
        assert "path traversal" in output.lower()

    def test_write_file_size_limit(self, tmp_path):
        """Rejects files exceeding size limit."""
        from services.code_executor import _execute_write_file

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        # 6MB content (exceeds 5MB limit)
        huge_content = "x" * (6 * 1024 * 1024)

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_write_file(
                {"path": "huge.txt", "content": huge_content}, tracker
            )

        assert success is False
        assert "too large" in output.lower()


class TestListDirectory:
    """Test _execute_list_directory tool."""

    def test_list_workspace_root(self, tmp_path):
        """Lists files in workspace root."""
        from services.code_executor import _execute_list_directory

        (tmp_path / "file1.py").write_text("x = 1")
        (tmp_path / "file2.js").write_text("const x = 1")
        (tmp_path / "subdir").mkdir()

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_list_directory({"path": "."}, tracker)

        assert success is True
        assert "file1.py" in output
        assert "file2.js" in output
        assert "subdir/" in output

    def test_list_nonexistent_dir(self, tmp_path):
        """Returns error for nonexistent directory."""
        from services.code_executor import _execute_list_directory

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_list_directory({"path": "nonexistent"}, tracker)

        assert success is False
        assert "not found" in output.lower()


class TestSearchCodebase:
    """Test _execute_search_codebase tool."""

    def test_search_matches_content(self, tmp_path):
        """Finds matches in workspace files."""
        from services.code_executor import _execute_search_codebase

        (tmp_path / "app.py").write_text("def main():\n    print('hello')\n")
        (tmp_path / "utils.py").write_text("def helper():\n    pass\n")

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_search_codebase({"query": "def main"}, tracker)

        assert success is True
        assert "app.py" in output
        assert "def main" in output

    def test_search_with_file_pattern(self, tmp_path):
        """File pattern filter works."""
        from services.code_executor import _execute_search_codebase

        (tmp_path / "app.py").write_text("hello world\n")
        (tmp_path / "readme.md").write_text("hello world\n")

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_search_codebase(
                {"query": "hello", "file_pattern": "*.py"}, tracker
            )

        assert success is True
        assert "app.py" in output
        assert "readme.md" not in output

    def test_search_no_matches(self, tmp_path):
        """Returns clean message when no matches found."""
        from services.code_executor import _execute_search_codebase

        (tmp_path / "app.py").write_text("x = 1\n")

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_search_codebase({"query": "nonexistent_string"}, tracker)

        assert success is True
        assert "no matches" in output.lower()


class TestRunCommand:
    """Test _execute_run_command tool."""

    def test_allowed_python_command(self, tmp_path):
        """python command is allowed."""
        from services.code_executor import _execute_run_command

        (tmp_path / "test.py").write_text("print('hello from python')\n")

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_run_command(
                {"command": "python3 test.py"}, tracker
            )

        assert success is True
        assert "hello from python" in output

    def test_disallowed_command_blocked(self, tmp_path):
        """Commands not in allowlist are blocked."""
        from services.code_executor import _execute_run_command

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_run_command(
                {"command": "rm -rf /"}, tracker
            )

        assert success is False
        assert "not allowed" in output.lower()

    def test_disallowed_curl_blocked(self, tmp_path):
        """curl is not in allowed commands."""
        from services.code_executor import _execute_run_command

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_run_command(
                {"command": "curl https://evil.com"}, tracker
            )

        assert success is False
        assert "not allowed" in output.lower()

    def test_disallowed_bash_blocked(self, tmp_path):
        """bash is not in allowed commands."""
        from services.code_executor import _execute_run_command

        tracker = MagicMock()
        tracker.set_status = MagicMock()

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = _execute_run_command(
                {"command": "bash -c 'echo owned'"}, tracker
            )

        assert success is False
        assert "not allowed" in output.lower()


# ============================================================================
# Tool Routing Tests
# ============================================================================


class TestExecuteToolRouting:
    """Test that execute_tool correctly routes to filesystem tools."""

    def test_routes_read_file(self, tmp_path):
        """execute_tool routes 'read_file' correctly."""
        from services.code_executor import execute_tool

        (tmp_path / "test.txt").write_text("hello\n")

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = execute_tool("read_file", {"path": "test.txt"})

        assert success is True
        assert "hello" in output

    def test_routes_list_directory(self, tmp_path):
        """execute_tool routes 'list_directory' correctly."""
        from services.code_executor import execute_tool

        (tmp_path / "a.py").write_text("x = 1")

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = execute_tool("list_directory", {"path": "."})

        assert success is True
        assert "a.py" in output

    def test_routes_write_file(self, tmp_path):
        """execute_tool routes 'write_file' correctly."""
        from services.code_executor import execute_tool

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = execute_tool("write_file", {"path": "new.txt", "content": "hi"})

        assert success is True
        assert (tmp_path / "new.txt").read_text() == "hi"

    def test_routes_search_codebase(self, tmp_path):
        """execute_tool routes 'search_codebase' correctly."""
        from services.code_executor import execute_tool

        (tmp_path / "app.py").write_text("def main(): pass\n")

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = execute_tool("search_codebase", {"query": "def main"})

        assert success is True
        assert "main" in output

    def test_routes_run_command(self, tmp_path):
        """execute_tool routes 'run_command' correctly."""
        from services.code_executor import execute_tool

        with patch("services.code_executor.WORKSPACE_ROOT", str(tmp_path)):
            success, output = execute_tool("run_command", {"command": "python3 -c 'print(42)'"})

        assert success is True
        assert "42" in output


# ============================================================================
# Reflexion Pattern Tests
# ============================================================================


class TestReflexionPattern:
    """Test Reflexion self-correction in the ReAct loop."""

    def test_reflexion_tools_identified(self):
        """Correct tools are identified as Reflexion-capable."""
        from services.react_loop import ReactLoop

        assert ReactLoop._is_reflexion_tool("code_display") is True
        assert ReactLoop._is_reflexion_tool("run_command") is True
        assert ReactLoop._is_reflexion_tool("write_file") is True
        assert ReactLoop._is_reflexion_tool("calculator") is False
        assert ReactLoop._is_reflexion_tool("web_search") is False
        assert ReactLoop._is_reflexion_tool("read_file") is False

    def test_reflexion_observation_format(self):
        """Reflexion observation includes error and retry guidance."""
        from services.react_loop import ReactLoop

        obs = ReactLoop._build_reflexion_observation(
            "run_command", "SyntaxError: invalid syntax", 1, 3
        )
        assert "ERROR:" in obs
        assert "SyntaxError" in obs
        assert "1/3" in obs
        assert "fix the issue" in obs.lower()

    def test_reflexion_retry_tracking_in_execute(self):
        """ReAct execute() tracks Reflexion retries correctly."""
        from services.react_loop import ReactLoop

        # Simulate: tool call → error → retry → success
        responses = [
            # Iteration 1: model calls run_command
            '<tool_call name="run_command"><command>python3 test.py</command></tool_call>',
            # Iteration 2: model fixes and calls again
            '<tool_call name="run_command"><command>python3 test_fixed.py</command></tool_call>',
            # Iteration 3: final answer
            "The test passed successfully after fixing the syntax error.",
        ]

        client = MagicMock()
        client.chat = MagicMock(side_effect=responses)

        loop = ReactLoop(client, max_iterations=5)

        with patch("services.react_loop.execute_tool") as mock_exec:
            # First call fails, second succeeds
            mock_exec.side_effect = [
                (False, "SyntaxError: invalid syntax"),
                (True, "Test passed!"),
            ]

            result = loop.execute(question="Run the tests")

        assert result.iterations == 3
        assert "run_command" in result.tools_used
        assert len(result.tools_used) == 2  # Two tool calls


# ============================================================================
# Token Budget Guard Tests
# ============================================================================


class TestTokenBudgetGuard:
    """Test token budget estimation and enforcement."""

    def test_token_estimation(self):
        """Token estimation is roughly 4 chars per token."""
        from services.react_loop import ReactLoop

        messages = [
            {"role": "system", "content": "x" * 400},  # ~100 tokens
            {"role": "user", "content": "y" * 800},  # ~200 tokens
        ]
        estimate = ReactLoop._estimate_tokens(messages)
        assert estimate == 300  # (400 + 800) / 4

    def test_budget_forces_final_answer(self):
        """ReAct loop forces final answer when budget exceeded."""
        from services.react_loop import ReactLoop

        # Create responses: tool call with huge result, then final answer
        responses = [
            '<tool_call name="calculator"><expression>1+1</expression></tool_call>',
            "Final answer: 2",
        ]

        client = MagicMock()
        client.chat = MagicMock(side_effect=responses)

        # Set very low budget to force early termination
        loop = ReactLoop(client, max_iterations=15)
        loop.token_budget = 10  # Very low budget

        with patch("services.react_loop.execute_tool") as mock_exec:
            mock_exec.return_value = (True, "x" * 1000)  # Large result
            result = loop.execute(question="What is 1+1?")

        # Should force final answer after budget exceeded
        assert result.answer == "Final answer: 2"


# ============================================================================
# Tool Definitions Tests
# ============================================================================


class TestPhase5ToolDefinitions:
    """Test that Phase 5 tool definitions are registered."""

    def test_filesystem_tools_in_definitions(self):
        """All 5 filesystem tools are defined."""
        from services.tools import TOOL_DEFINITIONS

        fs_tools = ["read_file", "write_file", "list_directory", "search_codebase", "run_command"]
        for tool in fs_tools:
            assert tool in TOOL_DEFINITIONS, f"Missing tool definition: {tool}"

    def test_filesystem_tools_have_params(self):
        """Filesystem tools have required parameters defined."""
        from services.tools import TOOL_DEFINITIONS

        assert "path" in TOOL_DEFINITIONS["read_file"]["params"]
        assert "path" in TOOL_DEFINITIONS["write_file"]["params"]
        assert "content" in TOOL_DEFINITIONS["write_file"]["params"]
        assert "path" in TOOL_DEFINITIONS["list_directory"]["params"]
        assert "query" in TOOL_DEFINITIONS["search_codebase"]["params"]
        assert "command" in TOOL_DEFINITIONS["run_command"]["params"]

    def test_detect_tools_recognizes_filesystem_queries(self):
        """detect_tools_needed identifies filesystem-related queries."""
        from services.tools import detect_tools_needed

        # These should trigger filesystem tool detection
        assert detect_tools_needed("list the files in this project")
        assert detect_tools_needed("show me the source code in main.py")
        assert detect_tools_needed("run the tests")
        assert detect_tools_needed("search for def main in the codebase")

    def test_15_tools_total(self):
        """Total tool count is 15 (8 original + 5 filesystem + 2 memory management)."""
        from services.tools import TOOL_DEFINITIONS

        assert len(TOOL_DEFINITIONS) == 15


# ============================================================================
# Repo Map Tests
# ============================================================================


class TestRepoMap:
    """Test repo map V1 generation."""

    def test_generates_python_symbols(self, tmp_path):
        """Extracts class and def signatures from Python files."""
        from services.repo_map import generate_repo_map

        (tmp_path / "app.py").write_text(
            "class MyApp:\n"
            "    def run(self):\n"
            "        pass\n\n"
            "def main():\n"
            "    pass\n"
        )

        result = generate_repo_map(workspace_path=str(tmp_path))

        assert "app.py" in result
        assert "class MyApp:" in result
        assert "def run(self):" in result
        assert "def main():" in result

    def test_generates_js_symbols(self, tmp_path):
        """Extracts function and const from JavaScript files."""
        from services.repo_map import generate_repo_map

        (tmp_path / "index.js").write_text(
            "function handleClick() {\n"
            "  return true;\n"
            "}\n\n"
            "const API_URL = 'https://api.example.com';\n"
        )

        result = generate_repo_map(workspace_path=str(tmp_path))

        assert "index.js" in result
        assert "handleClick" in result
        assert "API_URL" in result

    def test_empty_workspace(self, tmp_path):
        """Returns empty string for empty workspace."""
        from services.repo_map import generate_repo_map

        result = generate_repo_map(workspace_path=str(tmp_path))
        assert result == ""

    def test_skips_hidden_directories(self, tmp_path):
        """Skips .git and __pycache__ directories."""
        from services.repo_map import generate_repo_map

        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config.py").write_text("def secret(): pass\n")

        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "cache.py").write_text("def cached(): pass\n")

        (tmp_path / "real.py").write_text("def real_func(): pass\n")

        result = generate_repo_map(workspace_path=str(tmp_path))

        assert "real_func" in result
        assert "secret" not in result
        assert "cached" not in result

    def test_nonexistent_workspace(self):
        """Returns empty string for nonexistent workspace."""
        from services.repo_map import generate_repo_map

        result = generate_repo_map(workspace_path="/nonexistent/path/abc123")
        assert result == ""


# ============================================================================
# Config Tests
# ============================================================================


class TestPhase5Config:
    """Test Phase 5 configuration values."""

    def test_react_max_iterations_is_15(self):
        """REACT_MAX_ITERATIONS defaults to 15."""
        from config import REACT_MAX_ITERATIONS

        assert REACT_MAX_ITERATIONS == 15

    def test_token_budget_exists(self):
        """REACT_TOKEN_BUDGET config exists."""
        from config import REACT_TOKEN_BUDGET

        assert REACT_TOKEN_BUDGET == 24000

    def test_reflexion_retries_config(self):
        """REFLEXION_MAX_RETRIES defaults to 3."""
        from config import REFLEXION_MAX_RETRIES

        assert REFLEXION_MAX_RETRIES == 3

    def test_workspace_config_exists(self):
        """Workspace configuration values exist."""
        from config import (
            WORKSPACE_ALLOWED_COMMANDS,
            WORKSPACE_COMMAND_TIMEOUT,
            WORKSPACE_MAX_DEPTH,
            WORKSPACE_MAX_FILE_SIZE,
            WORKSPACE_MAX_SEARCH_RESULTS,
            WORKSPACE_ROOT,
        )

        assert WORKSPACE_ROOT == "/workspace"
        assert WORKSPACE_MAX_FILE_SIZE == 5 * 1024 * 1024
        assert WORKSPACE_MAX_DEPTH == 3
        assert WORKSPACE_MAX_SEARCH_RESULTS == 50
        assert "python3" in WORKSPACE_ALLOWED_COMMANDS
        assert "pytest" in WORKSPACE_ALLOWED_COMMANDS
        assert WORKSPACE_COMMAND_TIMEOUT == 30


# ============================================================================
# Prompt Tests
# ============================================================================


class TestPhase5Prompts:
    """Test that Phase 5 tools appear in prompts."""

    def test_tool_prompt_includes_filesystem_tools(self):
        """TOOL_PROMPT_SECTION mentions all filesystem tools."""
        from services.agent_prompts import TOOL_PROMPT_SECTION

        assert "read_file" in TOOL_PROMPT_SECTION
        assert "write_file" in TOOL_PROMPT_SECTION
        assert "list_directory" in TOOL_PROMPT_SECTION
        assert "search_codebase" in TOOL_PROMPT_SECTION
        assert "run_command" in TOOL_PROMPT_SECTION

    def test_tool_prompt_includes_reflexion_guidance(self):
        """TOOL_PROMPT_SECTION includes code execution guidelines."""
        from services.agent_prompts import TOOL_PROMPT_SECTION

        assert "Code Execution Guidelines" in TOOL_PROMPT_SECTION
        assert "fix the code" in TOOL_PROMPT_SECTION.lower()

    def test_tool_prompt_mentions_sandbox(self):
        """TOOL_PROMPT_SECTION mentions sandboxing."""
        from services.agent_prompts import TOOL_PROMPT_SECTION

        assert "/workspace" in TOOL_PROMPT_SECTION
        assert "path traversal" in TOOL_PROMPT_SECTION.lower()
