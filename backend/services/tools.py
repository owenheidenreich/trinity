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

    lines.append("\nTo use a tool, output it in XML format with the parameter names shown above:")
    lines.append('<tool_call name="calculator"><expression>2 + 3</expression></tool_call>')

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

    # Fallback 2: <tool_call> WITHOUT name attribute — infer tool from child tags.
    # Qwen3 sometimes emits: <tool_call><expression>2+2</expression></tool_call>
    if not matches:
        nameless_strict = r'<tool_call\s*>(.*?)</tool_call>'
        nameless_lenient = r'<tool_call\s*>(.*?)(?:</tool_call>|\Z)'
        nameless = re.findall(nameless_strict, text, re.DOTALL | re.IGNORECASE)
        if not nameless:
            nameless = re.findall(nameless_lenient, text, re.DOTALL | re.IGNORECASE)
        if nameless:
            # Map parameter tags → tool name
            _TAG_TO_TOOL = {
                "expression": "calculator",
                "claim": "fact_check",
                "fact": "save_memory",
                "new_value": "update_memory",
                "command": "run_command",
                "file_pattern": "search_codebase",
                "search_type": "search_memory",
                "language": "code_display",
                "execute": "code_display",
                "recursive": "list_directory",
                "start_line": "read_file",
                "end_line": "read_file",
                "content": "write_file",
            }
            for body in nameless:
                # Find all child tags
                child_tags = re.findall(r'<(\w+)>', body, re.IGNORECASE)
                inferred = None
                for tag in child_tags:
                    tag_lower = tag.lower()
                    if tag_lower in _TAG_TO_TOOL:
                        inferred = _TAG_TO_TOOL[tag_lower]
                        break
                if not inferred:
                    # <query> alone → web_search (most common); <path> alone → read_file
                    if "query" in [t.lower() for t in child_tags]:
                        inferred = "web_search"
                    elif "path" in [t.lower() for t in child_tags]:
                        inferred = "read_file"
                if inferred:
                    matches.append((inferred, body))

    # Fallback 3: bare tool names without <tool_call> wrapper
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

    # Fallback 4: JSON format tool calls
    # Qwen3 models often output JSON instead of XML despite prompt instructions:
    #   {"tool": "calculator", "input": "2+2"}
    #   {"tool": "web_search", "query": "..."}
    #   **save_memory**\n{"key": "...", "value": "..."}
    #   ```json\n{"tool": "..."}\n```
    if not matches:
        json_matches = _parse_json_tool_calls(text)
        if json_matches:
            matches = json_matches

    for name, params_text in matches:
        params = {}

        # Parse parameters from XML-like tags
        param_pattern = r"<(\w+)>(.*?)</\1>"
        param_matches = re.findall(param_pattern, params_text, re.DOTALL)

        for param_name, param_value in param_matches:
            params[param_name] = param_value.strip()

        # Normalize generic <param> tag → tool-specific parameter name.
        # The model sometimes uses <param>value</param> instead of the
        # tool-specific tag (e.g. <expression>).  Map it to the tool's
        # primary parameter so execute_tool finds the value.
        tool_key = name.lower().strip()
        if "param" in params and tool_key in TOOL_DEFINITIONS:
            primary = next(iter(TOOL_DEFINITIONS[tool_key]["params"]))
            if primary != "param" and primary not in params:
                params[primary] = params.pop("param")

        # If no XML params were extracted but there's bare text in the body,
        # treat it as the tool's primary parameter (model omitted the tag).
        if not params and params_text.strip() and tool_key in TOOL_DEFINITIONS:
            bare = params_text.strip()
            # Only accept if it doesn't look like XML at all
            if not bare.startswith("<"):
                primary = next(iter(TOOL_DEFINITIONS[tool_key]["params"]))
                params[primary] = bare

        tool_calls.append(
            ToolCall(
                name=tool_key,
                params=params,
                raw_text=f'<tool_call name="{name}">{params_text}</tool_call>',
            )
        )

    return tool_calls


# ---------------------------------------------------------------------------
# JSON tool call aliases: map common JSON keys → expected XML param names
# ---------------------------------------------------------------------------

_JSON_PARAM_ALIASES = {
    "calculator": {"input": "expression", "expr": "expression", "math": "expression"},
    "web_search": {"input": "query", "search_query": "query", "search": "query"},
    "save_memory": {"value": "fact", "memory": "fact", "content": "fact", "key": "category"},
    "recall_memory": {"input": "query", "key": "query"},
    "search_memory": {"input": "query", "key": "query"},
    "forget_memory": {"input": "query", "memory": "query"},
    "update_memory": {"input": "query", "value": "new_value"},
    "document_search": {"input": "query", "search": "query"},
    "fact_check": {"input": "claim", "query": "claim", "statement": "claim"},
    "code_display": {"input": "code", "source": "code"},
    "read_file": {"file": "path", "filename": "path"},
    "write_file": {"file": "path", "filename": "path"},
    "list_directory": {"dir": "path", "directory": "path"},
    "search_codebase": {"pattern": "query", "search": "query"},
    "run_command": {"cmd": "command", "input": "command"},
}

_KNOWN_TOOL_NAMES = {
    "calculator", "code_display", "document_search", "web_search", "fact_check",
    "save_memory", "recall_memory", "search_memory", "update_memory", "forget_memory",
    "read_file", "write_file", "list_directory", "search_codebase", "run_command",
    "current_datetime",
}


def _apply_param_aliases(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Map JSON parameter names to expected XML parameter names for a tool."""
    aliases = _JSON_PARAM_ALIASES.get(tool_name, {})
    mapped = {}
    for key, value in params.items():
        canonical = aliases.get(key, key)
        mapped[canonical] = value
    return mapped


def _parse_json_tool_calls(text: str) -> List[tuple]:
    """Parse tool calls from JSON format (Qwen3 native tool calling output).

    Handles multiple formats:
      1. ```json\n{"tool": "...", ...}\n```  (code-fenced)
      2. {"tool": "...", ...}                 (bare JSON)
      3. **tool_name**\n{"key": "...", ...}   (markdown bold + JSON)
      4. {"name": "...", "arguments": {...}}  (OpenAI function call format)

    Returns list of (tool_name, params_xml_body) tuples compatible with
    the main parse_tool_calls() match processing.
    """
    import json as _json

    results = []

    # Strip code fences to normalize
    clean = re.sub(r'```(?:json)?\s*', '', text)
    clean = re.sub(r'```', '', clean)

    # Also try markdown bold prefix: **tool_name**\n{...}
    bold_match = re.search(
        r'\*\*(' + '|'.join(re.escape(t) for t in _KNOWN_TOOL_NAMES) + r')\*\*\s*\n?\s*(\{.*)',
        clean, re.DOTALL | re.IGNORECASE
    )
    if bold_match:
        bold_tool = bold_match.group(1).lower().strip()
        json_str = bold_match.group(2).strip()
        try:
            obj = _json.loads(json_str)
            if isinstance(obj, dict):
                params = _apply_param_aliases(bold_tool, obj)
                # Convert params dict to XML-like body for compatibility
                xml_body = ''.join(f'<{k}>{v}</{k}>' for k, v in params.items())
                results.append((bold_tool, xml_body))
                return results
        except _json.JSONDecodeError:
            pass

    # Find all JSON objects in the text
    json_candidates = re.findall(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', clean, re.DOTALL)

    for candidate in json_candidates:
        try:
            obj = _json.loads(candidate)
        except _json.JSONDecodeError:
            continue

        if not isinstance(obj, dict):
            continue

        # Extract tool name
        tool_name = (obj.get("tool") or obj.get("name") or obj.get("function") or "").lower().strip()
        if not tool_name or tool_name not in _KNOWN_TOOL_NAMES:
            continue

        # Extract params — either from an 'arguments'/'input'/'params' sub-dict
        # or from all remaining keys
        raw_params = {}
        if isinstance(obj.get("arguments"), dict):
            raw_params = obj["arguments"]
        elif isinstance(obj.get("params"), dict):
            raw_params = obj["params"]
        elif isinstance(obj.get("input"), dict):
            raw_params = obj["input"]
        else:
            # All other keys become params
            for k, v in obj.items():
                if k not in ("tool", "name", "function", "type"):
                    if isinstance(v, str):
                        raw_params[k] = v
                    elif isinstance(v, (int, float, bool)):
                        raw_params[k] = str(v)
                    elif isinstance(v, dict):
                        # Flatten nested dict into params
                        for nk, nv in v.items():
                            raw_params[nk] = str(nv) if not isinstance(nv, str) else nv

        # For single-value input like {"tool":"calculator","input":"2+2"}
        # where "input" is a string, not a dict
        if not raw_params and isinstance(obj.get("input"), str):
            # Map the generic "input" to the tool's primary param
            raw_params = {"input": obj["input"]}

        params = _apply_param_aliases(tool_name, raw_params)

        # Build XML-body string for compatibility with existing match processing
        xml_body = ''.join(f'<{k}>{v}</{k}>' for k, v in params.items())
        results.append((tool_name, xml_body))

    return results


def _regex_detect_tools(query: str) -> List[str]:
    """Regex-based tool detection fallback when classifier is unavailable or
    returns no tools.  Mirrors the battle-tested heuristics that shipped
    before the MicroGPT overhaul."""
    tools = []
    q = query.lower()

    # Calculator
    math_patterns = [
        r"\d+\s*[\+\-\*/\^]\s*\d+",
        r"calculate|compute|solve|evaluate",
        r"what is \d+",
        r"sum|product|average|mean|sqrt|log",
        r"how many .*(if|when|after|before|left|remain)",
        r"\d+.*(?:plus|minus|add|subtract|give away|take away|more than|less than|divided|times|multiplied).*\d+",
        r"how much is \d+",
        r"what(?:'?s| is) \d+\s*(?:percent|%|divided|times|plus|minus)",
        r"(?:convert|conversion)\s+\d+",
    ]
    if any(re.search(p, q) for p in math_patterns):
        tools.append("calculator")

    # Date / time
    datetime_patterns = [
        r"what (day|date|time) is it",
        r"what('?s| is) today",
        r"current (date|time|day)",
        r"today'?s date",
        r"what year is it",
    ]
    if any(re.search(p, q) for p in datetime_patterns):
        tools.append("current_datetime")

    # Web search
    search_patterns = [
        r"current (price|news|weather|status|version|events?|situation)",
        r"today'?s?\s+(news|weather|price|date|events?)",
        r"(right now|as of now|happening now)\b",
        r"latest (news|version|update|release|price)",
        r"recent (events?|news|developments?|updates?)",
        r"20\d\d|price of|stock price|bitcoin|crypto",
        r"(breaking|trending)\s+news",
        r"who is \w+\s+\w+|where is \w+\s+\w+",
        r"when (was|did)\s+\w+\s+(born|founded|released|created|happen)",
        r"\bsearch\b.*(internet|web|online|for)",
        r"(look|search)\s+(it\s+)?(up|for)",
        r"(find|get)\s+(me\s+)?(info|information|data|details)\s+(on|about)",
        r"(google|bing|browse)\b",
        r"what (is|are) the .*(score|result|winner|weather|price|rate)",
        r"how much (does|is|are|did)",
    ]
    if any(re.search(p, q) for p in search_patterns):
        tools.append("web_search")

    # Document search
    doc_patterns = [
        r"\b(uploaded|attached)\s+(document|file|pdf|attachment)\b",
        r"\b(this|that|the|my)\s+(document|pdf|attachment)\b",
        r"according to (the|my|this|that)\s+(document|pdf|attachment)",
        r"(search|look|find)\s+(in|through|within)\s+(the|my|this)\s+(document|file|pdf|attachment)\b",
    ]
    if any(re.search(p, q) for p in doc_patterns):
        tools.append("document_search")

    # Code execution (only when enabled)
    if CODE_EXECUTION_ENABLED:
        code_exec_patterns = [
            r"\b(debug|refactor|optimize|fix)\s+(this|the|my)\s+(?:\w+\s+){0,2}(code|function|program|script)",
            r"\b(run|execute|test)\s+(this|the|my)\s+(code|script|program)",
            r"\b(run|execute)\b.*\b(python|javascript|node|script)\b",
        ]
        workspace_patterns = [
            r"\b(workspace|project|repo|repository|directory|folder|codebase)\b",
            r"\b(path|filepath|file path)\b",
            r"(?:^|\s)(?:\.{1,2}/|/)\S+",
            r"\b\w[\w\-./]*\.(?:py|js|ts|tsx|jsx|json|md|txt|html|css|yaml|yml|sh|rs|go|java|c|cpp)\b",
        ]
        code_gen_patterns = [
            r"(write|create|generate|build|make)\s+(me\s+)?(a\s+)?(code|function|program|script|class)",
            r"(show|give)\s+me\s+(the\s+)?(code|function|implementation)",
            r"implement\b|write\s+a?\s*function|def\s+\w+\(|class\s+\w+[\(:]",
        ]
        has_exec = any(re.search(p, q) for p in code_exec_patterns)
        has_workspace = any(re.search(p, q) for p in workspace_patterns)
        has_codegen = any(re.search(p, q) for p in code_gen_patterns)
        if has_exec or (has_codegen and has_workspace):
            tools.append("code_display")

    # Fact check
    fact_patterns = [
        r"is it (true|correct|accurate)\s+that",
        r"(verify|fact.?check|confirm)\s+(that|whether|if|this)",
        r"is that (really|actually|correct|true|accurate)",
    ]
    if any(re.search(p, q) for p in fact_patterns):
        tools.append("fact_check")

    # Memory save (explicit "remember" requests)
    save_patterns = [
        r"\bremember (that|this)\b",
        r"\b(save|store|keep|note)\b.*(fact|memory|info|detail|that)",
        r"\bremember\b.*\b(my |i |is |like|prefer|work|live|name)\b",
        r"\bdon'?t forget\b",
        r"\bkeep in mind\b",
        r"\bmemorize\b",
        r"\brecord (that|this)\b",
    ]
    if any(re.search(p, q) for p in save_patterns):
        tools.append("save_memory")

    # Memory recall (questions about the user, NOT statements)
    memory_patterns = [
        r"do you (remember|recall)\b",
        r"what do you know about me",
        r"what('?s| is| was| are) my (name|job|role|prefer\w*|location|email|age|favorite|colour|color|birthday|hobby|hobbies|interest|interests|company|team|project|stack|language|goal|work)",
        r"tell me .*(?:about|know about) me",
        r"what .* about me\??",
        r"you said\b|i told you\b",
        r"what did i\b",
        r"what do i\b",
        r"who am i\b",
        r"where do i (live|work)\b",
        r"do you know (my|me|who i)\b",
    ]
    if any(re.search(p, q) for p in memory_patterns):
        tools.append("recall_memory")

    # Memory forget
    forget_patterns = [
        r"forget (?:that|about|my|the|what)",
        r"don't remember|stop remembering",
        r"delete.*(?:memory|fact|what you know)",
        r"remove.*(?:memory|fact|what you know)",
    ]
    if any(re.search(p, q) for p in forget_patterns):
        tools.append("forget_memory")

    # Filesystem
    fs_scope_patterns = [
        r"\b(workspace|project|repo|repository|directory|folder|codebase)\b",
        r"\b(path|filepath|file path)\b",
        r"(?:^|\s)(?:\.{1,2}/|/)\S+",
        r"\b\w[\w\-./]*\.(?:py|js|ts|tsx|jsx|json|md|txt|html|css|yaml|yml|sh|rs|go|java|c|cpp)\b",
    ]
    fs_action_patterns = [
        r"(read|show|open|cat|display|view)\s+.*?(file|source\s+code|code\s+in)",
        r"(list|show)\s+(the\s+|me\s+the\s+)?(files?|director|folder|project\s+structure)",
        r"(write|create|save)\s+(?:a\s+)?file\b",
        r"(search|find|grep|look\s+for)\s+.*(in\s+the\s+)?(code|project|repo|files?|codebase)",
    ]
    fs_exec_patterns = [
        r"(run|execute)\s+(the\s+)?(test|pytest|python|node|script|command)",
    ]
    has_scope = any(re.search(p, q) for p in fs_scope_patterns)
    has_action = any(re.search(p, q) for p in fs_action_patterns)
    has_fsexec = any(re.search(p, q) for p in fs_exec_patterns)
    if has_fsexec or (has_action and has_scope):
        tools.append("read_file")

    return list(set(tools))


def detect_tools_needed(query: str, understanding: Dict = None) -> List[str]:
    """
    Detect which tools might be needed for a query.

    Uses a tiny byte-level transformer classifier (~100K params, <1ms)
    as the primary detector, with regex heuristics providing both:
      - Fallback when the classifier is unavailable or returns no tools.
      - Confirmation gate to suppress false positives from the classifier.

    The regex safety net embodies MicroGPT's defense-in-depth principle:
    if the classifier says "tool X" but regex says "no tools" AND the
    classifier confidence is below the high-confidence threshold, we
    trust the regex (false positive suppression). High-confidence
    classifier predictions override regex disagreement.

    Args:
        query: User's query
        understanding: Optional parsed understanding (unused, kept for API compat)

    Returns:
        List of tool names that might be relevant
    """
    # High-confidence threshold: above this we trust classifier unconditionally
    HIGH_CONF = 0.92

    classifier_result = []
    classifier_conf = 0.0

    try:
        from services.tiny_classifier import detect_tools, _get_tool_model, TOOL_CLASSES
        import numpy as np

        classifier_result = detect_tools(query)

        # Get raw confidence for the confirmation gate
        if classifier_result:
            model = _get_tool_model()
            if model is not None:
                logits = model.forward(query)
                probs = np.exp(logits - logits.max()) / np.exp(logits - logits.max()).sum()
                classifier_conf = float(probs.max())
    except Exception:
        pass

    regex_result = _regex_detect_tools(query)

    # Case 1: Classifier found tools
    if classifier_result:
        # High confidence → trust classifier unconditionally
        if classifier_conf >= HIGH_CONF:
            return classifier_result

        # Moderate confidence + regex agrees → trust classifier
        if regex_result:
            return classifier_result

        # Moderate confidence + regex disagrees → false positive suppression
        # (e.g. "Hello, how are you?" → classifier says recall_memory,
        #  regex says [] — trust the regex)
        logger.info(
            "🔧 Tool detection: classifier=%s (%.2f) overridden by regex=[] "
            "(confidence below %.2f and no regex match)",
            classifier_result, classifier_conf, HIGH_CONF,
        )
        return []

    # Case 2: Classifier returned [] — fall back to regex
    return regex_result


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
