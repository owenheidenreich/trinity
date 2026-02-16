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
    "save_memory": {
        "description": "Remember an important fact about the user (name, job, preferences, goals). Only save meaningful, lasting information — not trivial session details.",
        "params": {
            "fact": "The fact to remember (e.g., 'User works in AI research')",
            "category": "Category: personal, work, preferences, or general (default: general)",
            "importance": "1-5 importance rating (default: 3). Use 4-5 for key identity facts.",
        },
        "examples": [
            '<tool_call name="save_memory"><fact>User prefers Python over JavaScript</fact><category>preferences</category><importance>4</importance></tool_call>'
        ],
    },
    "recall_memory": {
        "description": "Retrieve saved facts about the user by relevance. Use BEFORE answering personal questions like 'what do you know about me?' or 'do you remember...?'",
        "params": {
            "query": "What to recall (e.g., 'user preferences', 'their job')",
            "category": "Optional: filter by category (personal, work, preferences, general)",
            "limit": "Max number of facts to return (default: 5)",
        },
        "examples": [
            '<tool_call name="recall_memory"><query>what does the user do for work</query></tool_call>'
        ],
    },
    "search_memory": {
        "description": "Search through all saved memories by keyword or meaning. Use when looking for a specific saved fact.",
        "params": {
            "query": "Search query",
            "search_type": "Search mode: semantic (default), exact, or hybrid",
            "limit": "Max results (default: 5)",
        },
        "examples": [
            '<tool_call name="search_memory"><query>Python</query><search_type>hybrid</search_type></tool_call>'
        ],
    },
    "update_memory": {
        "description": "Update a previously saved fact with new information. Use when the user's situation changes (moved, new job, etc).",
        "params": {
            "query": "What fact to find (describes the existing memory)",
            "new_value": "The updated fact text",
            "category": "Optional: new category for the fact",
            "importance": "Optional: new importance rating (1-5)",
        },
        "examples": [
            '<tool_call name="update_memory"><query>where user lives</query><new_value>User moved to San Francisco</new_value></tool_call>'
        ],
    },
    "forget_memory": {
        "description": "Forget a fact the user wants removed. Soft-deletes it (preserved in data exports for the user's review).",
        "params": {
            "query": "What fact to forget (describes the memory to remove)",
        },
        "examples": [
            '<tool_call name="forget_memory"><query>old job at Google</query></tool_call>'
        ],
    },
    # ── Filesystem Tools ──────────────────────────────────────────
    "read_file": {
        "description": "Read a file from the workspace. Supports optional line ranges. Sandboxed to /workspace.",
        "params": {
            "path": "File path relative to workspace root (e.g., 'src/main.py')",
            "start_line": "Optional: first line to read (1-based)",
            "end_line": "Optional: last line to read (1-based)",
        },
        "examples": [
            '<tool_call name="read_file"><path>src/main.py</path></tool_call>',
            '<tool_call name="read_file"><path>src/main.py</path><start_line>10</start_line><end_line>50</end_line></tool_call>',
        ],
    },
    "write_file": {
        "description": "Write content to a file in the workspace. Creates parent directories if needed. Sandboxed to /workspace. Max 5MB.",
        "params": {
            "path": "File path relative to workspace root (e.g., 'src/output.py')",
            "content": "The content to write to the file",
        },
        "examples": [
            '<tool_call name="write_file"><path>hello.py</path><content>print("Hello, world!")</content></tool_call>',
        ],
    },
    "list_directory": {
        "description": "List files and directories in the workspace. Sandboxed to /workspace. Max depth 3.",
        "params": {
            "path": "Directory path relative to workspace root (default: '.')",
            "recursive": "Whether to list recursively (true/false, default: false)",
        },
        "examples": [
            '<tool_call name="list_directory"><path>.</path></tool_call>',
            '<tool_call name="list_directory"><path>src</path><recursive>true</recursive></tool_call>',
        ],
    },
    "search_codebase": {
        "description": "Search for text patterns in workspace files. Returns matching lines with file paths and line numbers. Max 50 matches.",
        "params": {
            "query": "Text or regex pattern to search for",
            "file_pattern": "Optional: glob pattern to filter files (e.g., '*.py', 'src/**/*.js')",
        },
        "examples": [
            '<tool_call name="search_codebase"><query>def main</query><file_pattern>*.py</file_pattern></tool_call>',
        ],
    },
    "run_command": {
        "description": "Run an allowed command in the workspace. Only python, pytest, and node are allowed. Sandboxed to /workspace.",
        "params": {
            "command": "The command to run (e.g., 'python main.py', 'pytest tests/', 'node index.js')",
        },
        "examples": [
            '<tool_call name="run_command"><command>pytest tests/ -x</command></tool_call>',
            '<tool_call name="run_command"><command>python main.py</command></tool_call>',
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

    # Match tool_call blocks — closing </tool_call> tag is optional because
    # some models (e.g. qwen2.5) omit it.  We try the strict pattern first,
    # then fall back to a greedy-to-end-of-string match.
    pattern_strict = r'<tool_call\s+name=["\']([^"\']+)["\']>(.*?)</tool_call>'
    pattern_lenient = r'<tool_call\s+name=["\']([^"\']+)["\']>(.*?)(?:</tool_call>|\Z)'
    matches = re.findall(pattern_strict, text, re.DOTALL | re.IGNORECASE)
    if not matches:
        matches = re.findall(pattern_lenient, text, re.DOTALL | re.IGNORECASE)

    # Fallback: bare tool names without <tool_call> wrapper
    # e.g. "recall_memory  <query>name</query>" or "save_memory <fact>...</fact>"
    if not matches:
        _KNOWN_TOOLS = (
            "calculator|code_display|document_search|web_search|fact_check|"
            "save_memory|recall_memory|search_memory|update_memory|forget_memory|"
            "read_file|write_file|list_directory|search_codebase|run_command"
        )
        bare_pattern = rf'\b({_KNOWN_TOOLS})\b\s*(<[a-z_]+>.*?)$'
        bare_match = re.search(bare_pattern, text, re.DOTALL | re.IGNORECASE)
        if bare_match:
            matches = [(bare_match.group(1), bare_match.group(2))]

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

    # Web search detection - anchored to avoid matching casual uses of "now", "current", etc.
    search_patterns = [
        r"current (price|news|weather|status|version|events?|situation)",
        r"today'?s?\s+(news|weather|price|date|events?)",
        r"(right now|as of now|happening now)\b",
        r"latest (news|version|update|release|price)",
        r"recent (events?|news|developments?|updates?)",
        r"20\d\d|price of|stock price|bitcoin|crypto",
        r"(breaking|trending)\s+news",
        r"who is \w+\s+\w+|where is \w+\s+\w+",  # "who is Elon Musk" but not "who is this"
        r"when (was|did)\s+\w+\s+(born|founded|released|created|happen)",
    ]
    for pattern in search_patterns:
        if re.search(pattern, query_lower):
            tools.append("web_search")
            break

    # Document search detection - require explicit document/file references
    doc_patterns = [
        r"(this |the |my |uploaded )?(document|file|upload|pdf|attachment)",
        r"according to (the|my|this|that)",
        r"(search|look|find)\s+(in|through|within)\s+(the|my|this)",
    ]
    for pattern in doc_patterns:
        if re.search(pattern, query_lower):
            tools.append("document_search")
            break

    # Code detection - only detect if code execution is actually enabled.
    # When disabled, code_display is just a formatting tool and the model
    # should write code inline using markdown fenced blocks.
    if CODE_EXECUTION_ENABLED:
        code_patterns = [
            r"(write|create|generate|build|make)\s+(me\s+)?(a\s+)?(code|function|program|script|class)",
            r"(show|give)\s+me\s+(the\s+)?(code|function|implementation)",
            r"\b(debug|refactor|optimize|fix)\s+(this|the|my)\s+(code|function|program|script)",
            r"(python|javascript|typescript|java|c\+\+|rust|go)\s+(code|function|program|script|implementation)",
            r"implement\b|write\s+a?\s*function|def\s+\w+\(|class\s+\w+[\(:]",
        ]
        for pattern in code_patterns:
            if re.search(pattern, query_lower):
                tools.append("code_display")
                break

    # Fact check detection - require full phrases, not bare words
    fact_patterns = [
        r"is it (true|correct|accurate)\s+that",
        r"(verify|fact.?check|confirm)\s+(that|whether|if|this)",
        r"is that (really|actually|correct|true|accurate)",
    ]
    for pattern in fact_patterns:
        if re.search(pattern, query_lower):
            tools.append("fact_check")
            break

    # Memory recall detection — only QUESTIONS about the user, not statements
    # "what is my name" → recall.  "my name is owen" → NOT recall (that's save).
    memory_patterns = [
        r"(do you )?(remember|recall)",
        r"what do you know about me",
        r"what('?s| is| was) my (name|job|role|prefer|location|email|age)",
        r"tell me (about|what you know about) me",
        r"about me\??",
        r"last time|previously|you said|i told you",
        r"what did i|do you remember",
    ]
    for pattern in memory_patterns:
        if re.search(pattern, query_lower):
            tools.append("recall_memory")
            break

    # Memory forget detection
    forget_patterns = [
        r"forget (?:that|about|my|the|what)",
        r"don't remember|stop remembering",
        r"delete.*(?:memory|fact|what you know)",
        r"remove.*(?:memory|fact|what you know)",
    ]
    for pattern in forget_patterns:
        if re.search(pattern, query_lower):
            tools.append("forget_memory")
            break

    # Filesystem tool detection
    fs_patterns = [
        r"(read|show|open|cat|display|view)\s+.*?(file|source\s+code|code\s+in)",
        r"(list|show)\s+(the\s+|me\s+the\s+)?(files?|director|folder|project\s+structure)",
        r"(write|create|save)\s+(a\s+)?(file|to\s+file)",
        r"(search|find|grep|look\s+for)\s+.*(in\s+the\s+)?(code|project|repo|files?|codebase)",
        r"(run|execute)\s+(the\s+)?(test|pytest|python|node|script|command)",
        r"what('?s|\s+is)\s+in\s+(this|the|my)\s+(project|directory|folder|repo)",
    ]
    for pattern in fs_patterns:
        if re.search(pattern, query_lower):
            tools.append("read_file")  # General filesystem signal
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
