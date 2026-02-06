"""
Trinity Backend - Tool Registry
Defines available tools for agentic LLM interactions
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config import CODE_EXECUTION_ENABLED

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


@dataclass
class ToolCall:
    """Represents a parsed tool call from LLM output."""

    name: str
    params: Dict[str, Any]
    raw_text: str


@dataclass
class ToolResult:
    """Result of executing a tool."""

    success: bool
    output: str
    error: Optional[str] = None


# Tool definitions with schemas
TOOL_DEFINITIONS = {
    "calculator": {
        "description": "Evaluate mathematical expressions. Returns the computed result.",
        "params": {
            "expression": 'A mathematical expression to evaluate (e.g., "2 + 3 * 4", "sqrt(16)", "sin(pi/2)")'
        },
        "examples": [
            '<tool_call name="calculator"><expression>2 + 3 * 4</expression></tool_call>',
            '<tool_call name="calculator"><expression>sqrt(144) + 10**2</expression></tool_call>',
        ],
    },
    "code_display": {
        "description": "Display and optionally execute code. For code explanations or running simple Python.",
        "params": {
            "language": "Programming language (python, javascript, etc.)",
            "code": "The code to display or execute",
            "execute": "Whether to execute the code (true/false, Python only)",
        },
        "examples": [
            '<tool_call name="code_display"><language>python</language><code>def factorial(n): return 1 if n <= 1 else n * factorial(n-1)</code><execute>false</execute></tool_call>'
        ],
    },
    "document_search": {
        "description": "Search through uploaded documents for relevant information.",
        "params": {"query": "What to search for in the documents"},
        "examples": [
            '<tool_call name="document_search"><query>contract termination clause</query></tool_call>'
        ],
    },
    "web_search": {
        "description": "Search the web for current information. Use for recent events, prices, news.",
        "params": {"query": "Search query"},
        "examples": ['<tool_call name="web_search"><query>Bitcoin price today</query></tool_call>'],
    },
    "fact_check": {
        "description": "Verify a claim by searching for evidence. Returns supporting or contradicting information.",
        "params": {"claim": "The claim to verify"},
        "examples": [
            '<tool_call name="fact_check"><claim>The Eiffel Tower is 300 meters tall</claim></tool_call>'
        ],
    },
}


def get_tool_definitions_for_prompt() -> str:
    """
    Generate tool documentation for inclusion in LLM prompts.

    Returns:
        Formatted string describing available tools
    """
    lines = ["Available tools:"]

    for name, tool in TOOL_DEFINITIONS.items():
        # Skip code execution if disabled
        if name == "code_display" and not CODE_EXECUTION_ENABLED:
            continue

        lines.append(f'\n**{name}**: {tool["description"]}')
        lines.append("Parameters:")
        for param, desc in tool["params"].items():
            lines.append(f"  - {param}: {desc}")

        if tool.get("examples"):
            lines.append("Example:")
            lines.append(f'  {tool["examples"][0]}')

    lines.append("\nTo use a tool, output it in this exact format:")
    lines.append('<tool_call name="tool_name"><param>value</param></tool_call>')

    return "\n".join(lines)


def parse_tool_calls(text: str) -> List[ToolCall]:
    """
    Parse tool calls from LLM output.

    Extracts all <tool_call> XML blocks and parses their parameters.

    Args:
        text: LLM output text

    Returns:
        List of ToolCall objects
    """
    tool_calls = []

    # Match tool_call blocks
    pattern = r'<tool_call\s+name=["\']([^"\']+)["\']>(.*?)</tool_call>'
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)

    for name, params_text in matches:
        params = {}

        # Parse parameters from XML-like tags
        param_pattern = r"<(\w+)>(.*?)</\1>"
        param_matches = re.findall(param_pattern, params_text, re.DOTALL)

        for param_name, param_value in param_matches:
            params[param_name] = param_value.strip()

        tool_calls.append(
            ToolCall(
                name=name.lower().strip(),
                params=params,
                raw_text=f'<tool_call name="{name}">{params_text}</tool_call>',
            )
        )

    return tool_calls


def detect_tools_needed(query: str, understanding: Dict = None) -> List[str]:
    """
    Detect which tools might be needed for a query.

    Uses heuristics to pre-identify likely tools, helping the LLM
    know what's available.

    Args:
        query: User's query
        understanding: Optional parsed understanding from agentic pipeline

    Returns:
        List of tool names that might be relevant
    """
    tools = []
    query_lower = query.lower()

    # Calculator detection
    math_patterns = [
        r"\d+\s*[\+\-\*/\^]\s*\d+",  # Basic arithmetic
        r"calculate|compute|solve|evaluate",
        r"what is \d+",
        r"sum|product|average|mean|sqrt|log",
    ]
    for pattern in math_patterns:
        if re.search(pattern, query_lower):
            tools.append("calculator")
            break

    # Web search detection
    search_patterns = [
        r"current|today|now|latest|recent",
        r"20\d\d|price|stock|bitcoin|crypto",
        r"news|update|happening",
        r"who is|where is|when is",
    ]
    for pattern in search_patterns:
        if re.search(pattern, query_lower):
            tools.append("web_search")
            break

    # Document search detection
    doc_patterns = [
        r"document|file|upload|pdf|text",
        r"according to|in the|from the",
        r"search.*for|find.*in",
    ]
    for pattern in doc_patterns:
        if re.search(pattern, query_lower):
            tools.append("document_search")
            break

    # Code detection
    code_patterns = [
        r"code|function|program|script",
        r"python|javascript|java|c\+\+",
        r"implement|write.*function|def\s+\w+",
    ]
    for pattern in code_patterns:
        if re.search(pattern, query_lower):
            tools.append("code_display")
            break

    # Fact check detection
    fact_patterns = [
        r"is it true|verify|fact.?check",
        r"really|actually|correct that",
    ]
    for pattern in fact_patterns:
        if re.search(pattern, query_lower):
            tools.append("fact_check")
            break

    return list(set(tools))  # Remove duplicates


def replace_tool_calls_with_results(text: str, results: Dict[str, ToolResult]) -> str:
    """
    Replace tool call blocks in text with their results.

    Args:
        text: Original text with tool_call blocks
        results: Dict mapping tool call raw_text to ToolResult

    Returns:
        Text with tool calls replaced by results
    """
    for raw_text, result in results.items():
        if result.success:
            replacement = f"\n[Tool Result]\n{result.output}\n"
        else:
            replacement = f"\n[Tool Error: {result.error}]\n"

        text = text.replace(raw_text, replacement)

    return text


# Module availability flag for graceful degradation
V4_TOOLS_AVAILABLE = True
