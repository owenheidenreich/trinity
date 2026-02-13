"""
Trinity Backend - Code Executor
Sandboxed Python execution using RestrictedPython
"""

import logging
import math
import threading
from io import StringIO
from typing import Dict, Tuple

from config import CODE_EXECUTION_ENABLED, CODE_EXECUTION_TIMEOUT

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

        elif tool_name == "web_search":
            return _execute_web_search(params, tracker)

        elif tool_name == "fact_check":
            return _execute_fact_check(params, tracker)

        elif tool_name == "document_search":
            return _execute_document_search(params, context, tracker)

        elif tool_name in ("save_memory", "recall_memory", "search_memory"):
            return _execute_memory_tool(tool_name, params, context, tracker)

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
    """Execute memory tools (save/recall/search). Delegated to memory_tools module."""
    try:
        from .memory_tools import tool_recall_memory, tool_save_memory, tool_search_memory

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
        else:
            tracker.set_status("error")
            return False, f"Unknown memory tool: {tool_name}"
    except ImportError as e:
        tracker.set_status("error")
        return False, f"Memory tools unavailable: {e}"
    except Exception as e:
        tracker.set_status("error")
        return False, f"Memory tool failed: {e}"


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
