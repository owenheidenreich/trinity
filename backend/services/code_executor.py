"""
Trinity Backend - Code Executor
Sandboxed Python execution using RestrictedPython
"""

import fnmatch
import logging
import math
import os
import shlex
import subprocess
import threading
from io import StringIO
from pathlib import Path
from typing import Dict, Tuple

from config import (
    CODE_EXECUTION_ENABLED,
    CODE_EXECUTION_TIMEOUT,
    WORKSPACE_ALLOWED_COMMANDS,
    WORKSPACE_COMMAND_TIMEOUT,
    WORKSPACE_MAX_DEPTH,
    WORKSPACE_MAX_FILE_SIZE,
    WORKSPACE_MAX_SEARCH_RESULTS,
    WORKSPACE_ROOT,
)

# Observability (Phase 2B)
try:
    from middleware.observability import track_tool_call

    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    from contextlib import contextmanager

    @contextmanager
    def track_tool_call(tool_name):
        yield type("obj", (object,), {"set_status": lambda s: None})()


logger = logging.getLogger(__name__)


# Safe math functions for calculator
SAFE_MATH_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "pow": pow,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
}


def evaluate_math_expression(expression: str) -> Tuple[bool, str]:
    """
    Safely evaluate a mathematical expression.

    Uses AST parsing to ensure only safe operations are performed.

    Args:
        expression: Mathematical expression string

    Returns:
        Tuple of (success, result_or_error)
    """
    import ast
    import operator

    # Allowed operators
    OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def eval_node(node):
        """Recursively evaluate AST node."""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):  # Python 3.7 compatibility
            return node.n
        elif isinstance(node, ast.Name):
            name = node.id.lower()
            if name in SAFE_MATH_FUNCTIONS:
                return SAFE_MATH_FUNCTIONS[name]
            raise ValueError(f"Unknown variable: {node.id}")
        elif isinstance(node, ast.BinOp):
            left = eval_node(node.left)
            right = eval_node(node.right)
            op = OPERATORS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return op(left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = eval_node(node.operand)
            op = OPERATORS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return op(operand)
        elif isinstance(node, ast.Call):
            func = eval_node(node.func)
            args = [eval_node(arg) for arg in node.args]
            if callable(func):
                return func(*args)
            raise ValueError(f"Not callable: {func}")
        elif isinstance(node, ast.Expression):
            return eval_node(node.body)
        else:
            raise ValueError(f"Unsupported node type: {type(node).__name__}")

    try:
        # Clean the expression
        expression = expression.strip()
        if not expression:
            return False, "Empty expression"

        # Parse and evaluate
        tree = ast.parse(expression, mode="eval")
        result = eval_node(tree)

        # Format result
        if isinstance(result, float):
            if result.is_integer():
                return True, str(int(result))
            return True, f"{result:.10g}"  # Reasonable precision

        return True, str(result)

    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except ValueError as e:
        return False, str(e)
    except ZeroDivisionError:
        return False, "Division by zero"
    except OverflowError:
        return False, "Result too large"
    except Exception as e:
        return False, f"Evaluation error: {e}"


def execute_python_code(code: str, timeout: int = CODE_EXECUTION_TIMEOUT) -> Tuple[bool, str]:
    """
    Execute Python code in a RestrictedPython sandbox.

    RestrictedPython prevents:
    - Imports (no access to external modules)
    - File operations (no open, read, write)
    - Network access (no sockets)
    - System access (no os, subprocess)
    - Attribute access to dangerous methods

    Args:
        code: Python code to execute
        timeout: Maximum execution time in seconds

    Returns:
        Tuple of (success, output_or_error)
    """
    if not CODE_EXECUTION_ENABLED:
        return False, "Code execution is disabled"

    try:
        from RestrictedPython import compile_restricted, safe_builtins, safe_globals
        from RestrictedPython.Guards import safer_getattr
    except ImportError:
        logger.error("RestrictedPython not installed")
        return False, "Code execution not available"

    # Capture stdout
    captured_output = StringIO()

    # Build safe globals
    restricted_globals = safe_globals.copy()
    restricted_globals["__builtins__"] = safe_builtins.copy()

    # Add safe math functions
    restricted_globals["__builtins__"].update(SAFE_MATH_FUNCTIONS)

    # Add print that captures to our buffer
    def safe_print(*args, **kwargs):
        kwargs["file"] = captured_output
        print(*args, **kwargs)

    restricted_globals["__builtins__"]["print"] = safe_print
    restricted_globals["_getattr_"] = safer_getattr

    # Local namespace for execution
    local_ns = {}

    # Result container for thread
    result = {"success": False, "output": "", "error": None}

    def run_code():
        try:
            # Compile with restrictions
            byte_code = compile_restricted(code, "<user_code>", "exec")

            if byte_code.errors:
                result["error"] = "\n".join(byte_code.errors)
                return

            # Execute
            exec(byte_code.code, restricted_globals, local_ns)

            # Get output
            output = captured_output.getvalue()

            # If there's a result variable or expression, include it
            if "_result_" in local_ns:
                if output:
                    output += "\n"
                output += f'Result: {local_ns["_result_"]}'

            result["success"] = True
            result["output"] = output if output else "Code executed successfully (no output)"

        except Exception as e:
            result["error"] = str(e)

    # Run with timeout
    thread = threading.Thread(target=run_code)
    thread.daemon = True
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        return False, f"Execution timed out after {timeout} seconds"

    if result["error"]:
        return False, result["error"]

    return result["success"], result["output"]


def format_code_display(language: str, code: str, execute: bool = False) -> Tuple[bool, str]:
    """
    Format code for display and optionally execute it.

    Args:
        language: Programming language
        code: The code
        execute: Whether to execute (Python only)

    Returns:
        Tuple of (success, formatted_output)
    """
    # Format the code display
    output_parts = [f"```{language}", code.strip(), "```"]

    # Execute if requested and it's Python
    if execute and language.lower() in ["python", "py"]:
        success, exec_result = execute_python_code(code)
        output_parts.append("")
        if success:
            output_parts.append("**Execution Output:**")
            output_parts.append(f"```\n{exec_result}\n```")
        else:
            output_parts.append(f"**Execution Error:** {exec_result}")

    return True, "\n".join(output_parts)


def execute_tool(tool_name: str, params: Dict, context: Dict = None) -> Tuple[bool, str]:
    """
    Execute a tool by name with given parameters.

    This is the main entry point for tool execution.

    Args:
        tool_name: Name of the tool
        params: Tool parameters
        context: Optional dict with principal_id, chat_id for context-aware tools

    Returns:
        Tuple of (success, result_or_error)
    """
    tool_name = tool_name.lower()
    context = context or {}

    with track_tool_call(tool_name) as tracker:
        if tool_name == "calculator":
            expression = params.get("expression", "")
            success, result = evaluate_math_expression(expression)
            if not success:
                tracker.set_status("error")
            return success, result

        elif tool_name == "code_display":
            language = params.get("language", "python")
            code = params.get("code", "")
            execute = params.get("execute", "").lower() == "true"
            success, result = format_code_display(language, code, execute)
            if not success:
                tracker.set_status("error")
            return success, result

        elif tool_name == "current_datetime":
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            return True, f"Current date and time: {now.strftime('%A, %B %d, %Y at %H:%M:%S UTC')}"

        elif tool_name == "web_search":
            return _execute_web_search(params, tracker)

        elif tool_name == "fact_check":
            return _execute_fact_check(params, tracker)

        elif tool_name == "document_search":
            return _execute_document_search(params, context, tracker)

        elif tool_name in ("save_memory", "recall_memory", "search_memory", "update_memory", "forget_memory"):
            return _execute_memory_tool(tool_name, params, context, tracker)

        elif tool_name == "read_file":
            return _execute_read_file(params, tracker)

        elif tool_name == "write_file":
            return _execute_write_file(params, tracker)

        elif tool_name == "list_directory":
            return _execute_list_directory(params, tracker)

        elif tool_name == "search_codebase":
            return _execute_search_codebase(params, tracker)

        elif tool_name == "run_command":
            return _execute_run_command(params, tracker)

        else:
            # Fall through to MCP client for external tools
            return _execute_mcp_tool(tool_name, params, tracker)


def _execute_web_search(params: Dict, tracker) -> Tuple[bool, str]:
    """Execute web search using Brave Search API."""
    try:
        from .search import format_search_context, search_web

        query = params.get("query", "")
        if not query.strip():
            return False, "Empty search query"

        result = search_web(query, count=5)
        if result.error:
            tracker.set_status("error")
            return False, f"Search error: {result.error}"

        formatted = format_search_context(result)
        if not formatted:
            return True, f"No results found for: {query}"
        return True, formatted
    except Exception as e:
        tracker.set_status("error")
        return False, f"Web search failed: {e}"


def _execute_fact_check(params: Dict, tracker) -> Tuple[bool, str]:
    """Execute fact check using dual web searches."""
    try:
        from .fact_check import fact_check

        claim = params.get("claim", "")
        if not claim.strip():
            return False, "No claim provided to verify"

        result = fact_check(claim)
        return True, result
    except Exception as e:
        tracker.set_status("error")
        return False, f"Fact check failed: {e}"


def _execute_document_search(params: Dict, context: Dict, tracker) -> Tuple[bool, str]:
    """Execute document search using vector store."""
    try:
        from .embeddings import embed_text
        from .vector_store import get_vector_store

        query = params.get("query", "")
        if not query.strip():
            return False, "Empty search query"

        principal_id = context.get("principal_id")
        if not principal_id:
            tracker.set_status("error")
            return False, "Document search requires user context (principal_id)"

        # Embed the query
        query_embedding = embed_text(query)

        # Search user's vector store
        vs = get_vector_store(principal_id)

        # Try document chunks first, fall back to message history
        results = vs.search_documents(query_embedding, k=5)
        source = "documents"
        if not results:
            results = vs.search_messages(query_embedding, k=5)
            source = "conversation history"

        if not results:
            return True, f"No relevant {source} found for: {query}"

        # Format results
        lines = [f"Found {len(results)} results from {source}:"]
        for i, r in enumerate(results, 1):
            content = r.get("content", "")[:300]
            score = r.get("score", 0)
            filename = r.get("filename", "")
            role = r.get("role", "")
            label = filename if filename else f"{role} message" if role else "result"
            lines.append(f"\n{i}. [{label}] (relevance: {score:.2f})")
            lines.append(f"   {content}")

        return True, "\n".join(lines)
    except ImportError as e:
        tracker.set_status("error")
        return False, f"Document search unavailable: {e}"
    except Exception as e:
        tracker.set_status("error")
        return False, f"Document search failed: {e}"


def _execute_memory_tool(tool_name: str, params: Dict, context: Dict, tracker) -> Tuple[bool, str]:
    """Execute memory tools (save/recall/search/update/forget). Delegated to memory_tools module."""
    try:
        from .memory_tools import (
            tool_forget_memory,
            tool_recall_memory,
            tool_save_memory,
            tool_search_memory,
            tool_update_memory,
        )

        principal_id = context.get("principal_id")
        if not principal_id:
            tracker.set_status("error")
            return False, "Memory tools require user context (principal_id)"

        if tool_name == "save_memory":
            return tool_save_memory(params, principal_id)
        elif tool_name == "recall_memory":
            return tool_recall_memory(params, principal_id)
        elif tool_name == "search_memory":
            return tool_search_memory(params, principal_id)
        elif tool_name == "update_memory":
            return tool_update_memory(params, principal_id)
        elif tool_name == "forget_memory":
            return tool_forget_memory(params, principal_id)
        else:
            tracker.set_status("error")
            return False, f"Unknown memory tool: {tool_name}"
    except ImportError as e:
        tracker.set_status("error")
        return False, f"Memory tools unavailable: {e}"
    except Exception as e:
        tracker.set_status("error")
        return False, f"Memory tool failed: {e}"


# ── Filesystem sandbox ─────────────────────────────────────────────


def _resolve_sandbox_path(user_path: str) -> Tuple[bool, str]:
    """
    Resolve a user-provided path within the workspace sandbox.

    Prevents path traversal attacks by resolving to absolute path
    and verifying it stays within WORKSPACE_ROOT.

    Returns:
        Tuple of (valid, resolved_path_or_error)
    """
    try:
        workspace = Path(WORKSPACE_ROOT).resolve()
        # Ensure workspace exists
        if not workspace.exists():
            workspace.mkdir(parents=True, exist_ok=True)

        # Resolve the user path relative to workspace
        target = (workspace / user_path).resolve()

        # Security check: must be within workspace
        if not str(target).startswith(str(workspace)):
            return False, f"Access denied: path traversal blocked ('{user_path}' resolves outside workspace)"

        return True, str(target)
    except Exception as e:
        return False, f"Invalid path: {e}"


def _execute_read_file(params: Dict, tracker) -> Tuple[bool, str]:
    """Read a file from the sandboxed workspace."""
    path = params.get("path", "")
    if not path.strip():
        return False, "No file path provided"

    valid, resolved = _resolve_sandbox_path(path)
    if not valid:
        tracker.set_status("error")
        return False, resolved

    try:
        target = Path(resolved)
        if not target.exists():
            return False, f"File not found: {path}"
        if not target.is_file():
            return False, f"Not a file: {path}"
        if target.stat().st_size > WORKSPACE_MAX_FILE_SIZE:
            return False, f"File too large (max {WORKSPACE_MAX_FILE_SIZE // 1024 // 1024}MB): {path}"

        content = target.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        # Handle optional line ranges
        start_line = params.get("start_line")
        end_line = params.get("end_line")

        if start_line or end_line:
            try:
                start = int(start_line) - 1 if start_line else 0  # 1-based to 0-based
                end = int(end_line) if end_line else len(lines)
                start = max(0, start)
                end = min(len(lines), end)
                selected = lines[start:end]
                header = f"File: {path} (lines {start + 1}-{end} of {len(lines)})"
                numbered = [f"{start + i + 1:4d} | {line}" for i, line in enumerate(selected)]
                return True, f"{header}\n" + "\n".join(numbered)
            except ValueError:
                pass  # Fall through to full file

        # Return full file with line numbers
        if len(lines) > 500:
            # Truncate very large files
            numbered = [f"{i + 1:4d} | {line}" for i, line in enumerate(lines[:500])]
            return True, (
                f"File: {path} ({len(lines)} lines, showing first 500)\n"
                + "\n".join(numbered)
                + f"\n\n... truncated ({len(lines) - 500} more lines)"
            )

        numbered = [f"{i + 1:4d} | {line}" for i, line in enumerate(lines)]
        return True, f"File: {path} ({len(lines)} lines)\n" + "\n".join(numbered)

    except UnicodeDecodeError:
        return False, f"Cannot read binary file: {path}"
    except Exception as e:
        tracker.set_status("error")
        return False, f"Failed to read file: {e}"


def _execute_write_file(params: Dict, tracker) -> Tuple[bool, str]:
    """Write content to a file in the sandboxed workspace."""
    path = params.get("path", "")
    content = params.get("content", "")

    if not path.strip():
        return False, "No file path provided"

    valid, resolved = _resolve_sandbox_path(path)
    if not valid:
        tracker.set_status("error")
        return False, resolved

    # Size check
    if len(content.encode("utf-8")) > WORKSPACE_MAX_FILE_SIZE:
        return False, f"Content too large (max {WORKSPACE_MAX_FILE_SIZE // 1024 // 1024}MB)"

    try:
        target = Path(resolved)
        # Create parent directories
        target.parent.mkdir(parents=True, exist_ok=True)

        existed = target.exists()
        target.write_text(content, encoding="utf-8")

        line_count = len(content.splitlines())
        action = "Updated" if existed else "Created"
        return True, f"{action} {path} ({line_count} lines, {len(content)} bytes)"

    except Exception as e:
        tracker.set_status("error")
        return False, f"Failed to write file: {e}"


def _execute_list_directory(params: Dict, tracker) -> Tuple[bool, str]:
    """List files and directories in the sandboxed workspace."""
    path = params.get("path", ".")
    recursive = params.get("recursive", "").lower() == "true"

    valid, resolved = _resolve_sandbox_path(path)
    if not valid:
        tracker.set_status("error")
        return False, resolved

    try:
        target = Path(resolved)
        if not target.exists():
            return False, f"Directory not found: {path}"
        if not target.is_dir():
            return False, f"Not a directory: {path}"

        entries = []
        workspace = Path(WORKSPACE_ROOT).resolve()

        if recursive:
            _list_recursive(target, workspace, entries, depth=0, max_depth=WORKSPACE_MAX_DEPTH)
        else:
            for item in sorted(target.iterdir()):
                rel = item.relative_to(workspace)
                suffix = "/" if item.is_dir() else ""
                entries.append(f"  {rel}{suffix}")

        if not entries:
            return True, f"Directory is empty: {path}"

        return True, f"Contents of {path} ({len(entries)} items):\n" + "\n".join(entries)

    except PermissionError:
        return False, f"Permission denied: {path}"
    except Exception as e:
        tracker.set_status("error")
        return False, f"Failed to list directory: {e}"


def _list_recursive(directory: Path, workspace: Path, entries: list, depth: int, max_depth: int):
    """Recursively list directory contents with indentation."""
    if depth > max_depth:
        return
    try:
        for item in sorted(directory.iterdir()):
            # Skip hidden files and common noise
            if item.name.startswith(".") or item.name in ("__pycache__", "node_modules", ".git"):
                continue
            rel = item.relative_to(workspace)
            indent = "  " * (depth + 1)
            suffix = "/" if item.is_dir() else ""
            entries.append(f"{indent}{rel}{suffix}")
            if item.is_dir() and depth < max_depth:
                _list_recursive(item, workspace, entries, depth + 1, max_depth)
    except PermissionError:
        pass


def _execute_search_codebase(params: Dict, tracker) -> Tuple[bool, str]:
    """Search for text patterns in workspace files."""
    query = params.get("query", "")
    file_pattern = params.get("file_pattern", "")

    if not query.strip():
        return False, "No search query provided"

    try:
        workspace = Path(WORKSPACE_ROOT).resolve()
        if not workspace.exists():
            return False, "Workspace directory not found"

        matches = []
        max_results = WORKSPACE_MAX_SEARCH_RESULTS

        for root, dirs, files in os.walk(str(workspace)):
            # Skip hidden/noisy directories
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".") and d not in ("__pycache__", "node_modules", ".git")
            ]

            for filename in files:
                if file_pattern and not fnmatch.fnmatch(filename, file_pattern):
                    continue

                filepath = Path(root) / filename
                rel_path = filepath.relative_to(workspace)

                # Skip binary/large files
                try:
                    if filepath.stat().st_size > 1024 * 1024:  # 1MB max per file
                        continue
                except OSError:
                    continue

                try:
                    content = filepath.read_text(encoding="utf-8", errors="strict")
                except (UnicodeDecodeError, PermissionError):
                    continue

                for line_num, line in enumerate(content.splitlines(), 1):
                    if query.lower() in line.lower():
                        matches.append(f"  {rel_path}:{line_num}: {line.strip()[:120]}")
                        if len(matches) >= max_results:
                            break
                if len(matches) >= max_results:
                    break
            if len(matches) >= max_results:
                break

        if not matches:
            pattern_info = f" (pattern: {file_pattern})" if file_pattern else ""
            return True, f"No matches found for '{query}'{pattern_info}"

        truncated = f" (showing first {max_results})" if len(matches) >= max_results else ""
        return True, f"Found {len(matches)} matches for '{query}'{truncated}:\n" + "\n".join(matches)

    except Exception as e:
        tracker.set_status("error")
        return False, f"Search failed: {e}"


def _execute_run_command(params: Dict, tracker) -> Tuple[bool, str]:
    """Run an allowed command in the sandboxed workspace."""
    command = params.get("command", "")
    if not command.strip():
        return False, "No command provided"

    # Parse command safely into argv tokens; no shell parsing/execution.
    try:
        parts = shlex.split(command)
    except ValueError as e:
        return False, f"Invalid command syntax: {e}"

    if not parts:
        return False, "No command provided"
    executable = parts[0]

    # Security: only allowed executables
    if executable not in WORKSPACE_ALLOWED_COMMANDS:
        allowed = ", ".join(WORKSPACE_ALLOWED_COMMANDS)
        return False, f"Command '{executable}' not allowed. Allowed commands: {allowed}"

    try:
        workspace = Path(WORKSPACE_ROOT).resolve()
        if not workspace.exists():
            workspace.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            parts,
            shell=False,
            capture_output=True,
            text=True,
            timeout=WORKSPACE_COMMAND_TIMEOUT,
            cwd=str(workspace),
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

        output_parts = []
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(f"STDERR:\n{result.stderr}")

        output = "\n".join(output_parts) if output_parts else "(no output)"

        # Truncate long output
        if len(output) > 10000:
            output = output[:10000] + f"\n\n... output truncated ({len(output)} total chars)"

        if result.returncode == 0:
            return True, f"Command completed (exit code 0):\n{output}"
        else:
            return False, f"Command failed (exit code {result.returncode}):\n{output}"

    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {WORKSPACE_COMMAND_TIMEOUT} seconds"
    except Exception as e:
        tracker.set_status("error")
        return False, f"Command execution failed: {e}"


def _execute_mcp_tool(tool_name: str, params: Dict, tracker) -> Tuple[bool, str]:
    """Execute a tool via MCP client (external MCP servers)."""
    try:
        from .mcp_client import get_mcp_client

        client = get_mcp_client()
        if client.has_tool(tool_name):
            return client.execute_tool(tool_name, params)
    except Exception as e:
        logger.debug(f"MCP tool lookup failed: {e}")

    tracker.set_status("error")
    return False, f"Unknown tool: {tool_name}"


# Module availability flag for graceful degradation
V4_CODE_EXECUTOR_AVAILABLE = True
