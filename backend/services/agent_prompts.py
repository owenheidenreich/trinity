"""
Trinity Agentic Pipeline - Prompts

Single-pass prompt system. Two prompts:
  1. SYSTEM_PROMPT — direct Q&A (no tools)
  2. SYSTEM_PROMPT + TOOL_PROMPT_SECTION — when tools are needed (ReAct handles turn-taking)

Plus REACT_SYSTEM_PROMPT for the ReAct loop's own system message.
"""

import re
from typing import Dict, List, Optional

# ============================================================================
# TOOL DEFINITIONS (for prompt injection)
# ============================================================================

TOOL_PROMPT_SECTION = """
You have access to these tools. Call them when you need external information or actions.

## Available Tools

**calculator** — Evaluate math expressions.
  <tool_call name="calculator"><expression>sqrt(16) + 2^3</expression></tool_call>

**web_search** — Search the web for current/real-time information.
  <tool_call name="web_search"><query>Bitcoin price today</query></tool_call>

**fact_check** — Verify a claim with evidence from multiple sources.
  <tool_call name="fact_check"><claim>The Eiffel Tower is 300 meters tall</claim></tool_call>

**document_search** — Search through the user's uploaded documents.
  <tool_call name="document_search"><query>contract termination clause</query></tool_call>

**code_display** — Display and optionally execute Python code.
  <tool_call name="code_display"><language>python</language><code>print("hello")</code><execute>true</execute></tool_call>

**save_memory** — Remember a fact about the user for future conversations.
  <tool_call name="save_memory"><fact>User works in AI research</fact><category>work</category><importance>4</importance></tool_call>

**recall_memory** — Retrieve saved facts about the user.
  <tool_call name="recall_memory"><query>what does the user do for work</query></tool_call>

**search_memory** — Search through all saved memories (exact, semantic, or hybrid).
  <tool_call name="search_memory"><query>Python</query><search_type>hybrid</search_type></tool_call>

**update_memory** — Update a previously saved fact with new information.
  <tool_call name="update_memory"><query>where user lives</query><new_value>User moved to San Francisco</new_value></tool_call>

**forget_memory** — Remove a fact the user wants forgotten (soft-delete, preserved in exports).
  <tool_call name="forget_memory"><query>old job at Google</query></tool_call>

**read_file** — Read a file from the workspace (sandboxed to /workspace).
  <tool_call name="read_file"><path>src/main.py</path></tool_call>
  <tool_call name="read_file"><path>src/main.py</path><start_line>10</start_line><end_line>50</end_line></tool_call>

**write_file** — Write content to a file in the workspace (sandboxed, max 5MB).
  <tool_call name="write_file"><path>output.py</path><content>print("hello")</content></tool_call>

**list_directory** — List files and directories in the workspace (max depth 3).
  <tool_call name="list_directory"><path>.</path></tool_call>
  <tool_call name="list_directory"><path>src</path><recursive>true</recursive></tool_call>

**search_codebase** — Search for text patterns in workspace files (max 50 matches).
  <tool_call name="search_codebase"><query>def main</query><file_pattern>*.py</file_pattern></tool_call>

**run_command** — Run an allowed command (python, pytest, node only).
  <tool_call name="run_command"><command>pytest tests/ -x</command></tool_call>

## Rules
1. Output EXACTLY ONE tool call per turn, then STOP — do not write anything after it.
2. Tool results will appear in the next message. Then decide: call another tool or give your final answer.
3. Do NOT guess answers you can look up. Use web_search for current events, prices, news.
4. Do NOT include tool_call tags in your final answer.
5. For file operations: paths are relative to /workspace. Path traversal (../) is blocked.

## Memory — Your Most Important Responsibility
You build and maintain a persistent profile of each user. This profile survives across
conversations and even server restarts — it's encrypted and stored on IPFS.

**When to save memories:**
- User shares their name, role, company, tech stack, project → save_memory (importance: 4-5)
- User states preferences (language, style, tools) → save_memory (category: preferences)
- User mentions goals, interests, hobbies → save_memory (category: interests)
- User mentions people (colleagues, partners, friends) → save_memory (category: relationships)

**When to update memories:**
- User says something that contradicts a saved fact → update_memory
- User's situation changed ("I switched jobs", "I moved to...") → update_memory

**When to forget memories:**
- User explicitly asks you to forget something → forget_memory
- User corrects a wrong fact → update_memory (not forget)

**When to recall memories:**
- Before answering personal questions ("what do you know about me?") → recall_memory
- When memory directly helps with the current request
- When context from previous conversations would help

**Do NOT save:**
- Trivial session details ("user asked about weather")
- Temporary debugging context
- Anything the user explicitly asks you not to remember

## Code Execution Guidelines
- When code has errors, examine the error message and fix the code, then try again
- Use run_command for running tests or scripts
- Use code_display with execute=true for quick Python snippets
"""

# ============================================================================
# REACT SYSTEM PROMPT (for iterative tool calling)
# ============================================================================

REACT_SYSTEM_PROMPT = """You are Trinity, a sharp and knowledgeable AI assistant.

You solve problems by reasoning step-by-step and using tools when needed.

{tool_definitions}

## Protocol
1. REASON about what information you need.
2. If a tool can help, output EXACTLY ONE tool call, then STOP your response.
3. You will receive the tool result. Then either call another tool or write your FINAL ANSWER.
4. Your final answer must NOT contain any tool_call tags — just the answer itself.

## Key Principles
- Never guess when a tool can give you the answer (prices, dates, facts → web_search)
- Use calculator for any non-trivial math
- Be concise during tool-calling turns; be thorough and direct in your final answer
- Skip filler phrases — get to the substance
- If a tool returns an error, try rephrasing or use an alternative approach
- Your FINAL ANSWER must use standard Markdown — fenced code blocks (```python), headers, lists. NEVER use <tool_call> or <code_display> XML in your final answer.

{extra_context}"""


# ============================================================================
# SYSTEM PROMPT (single-pass, used for all queries)
# ============================================================================

SYSTEM_PROMPT = """You are Trinity, a sharp and knowledgeable AI assistant.

Use profile memory only when it materially improves the current answer.
Do not force personalized greetings or random profile callbacks.
If the user asks a neutral factual or coding question, answer directly without making it about prior memory.
When the user explicitly asks about themselves, you can use profile facts naturally and concisely.

{user_memory}

Previous conversation:
{context}
{search_context}
{tools_section}
Question: {question}

## How to respond
- Answer directly and substantively — no filler phrases.
- If the user shares a personal preference or fact (not a question), acknowledge it naturally and continue that topic.
- Do not pivot to unrelated old projects, profile details, or callbacks unless the user asked for that.
- For factual questions: give the answer, then a brief explanation if helpful.
- For code requests: briefly explain the approach, show complete code in ```language fenced blocks, then note any important details.
- For explanations: be clear and concrete, use examples when they help.
- For math: use LaTeX — $x^2$ inline, $$\\sum_{{i=1}}^n i$$ for blocks.
- Use Markdown for structure when the answer benefits from it.
- NEVER use <tool_call> or <code_display> XML tags. Always write code in ```language markdown blocks."""


# ============================================================================
# XML PARSING
# ============================================================================


def parse_xml_tag(text: str, tag: str, default: str = "") -> str:
    """
    Extract content from XML tag with multiple fallback strategies.

    Tries:
    1. Exact XML match: <tag>content</tag>
    2. Unclosed XML: <tag>content
    3. Labeled section: tag: content
    4. Markdown bold: **tag**: content
    """
    # Strategy 1: Exact XML
    match = re.search(f"<{tag}>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Strategy 2: Unclosed XML (model forgets closing tag)
    match = re.search(f"<{tag}>([^<]+)", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Strategy 3: Labeled section
    match = re.search(f"{tag}:\\s*(.+?)(?:\\n\\n|\\n<|$)", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Strategy 4: Markdown bold label
    match = re.search(
        f"\\*\\*{tag}\\*\\*:\\s*(.+?)(?:\\n\\n|\\n<|$)", text, re.DOTALL | re.IGNORECASE
    )
    if match:
        return match.group(1).strip()

    return default


# ============================================================================
# PROMPT BUILDER
# ============================================================================


def build_system_prompt(
    question: str,
    context_messages: List[Dict] = None,
    user_memory: Optional[Dict] = None,
    search_context: str = "",
    include_tools: bool = False,
) -> str:
    """Build the single-pass system prompt.

    Args:
        question: The user's question.
        context_messages: Recent conversation history.
        user_memory: Dict with 'facts' list.
        search_context: Formatted web search results (if any).
        include_tools: Whether to inject tool definitions.

    Returns:
        Fully formatted prompt string.
    """
    # Format context
    if context_messages:
        context_parts = []
        for msg in context_messages[-40:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:4000]
            context_parts.append(f"{role.title()}: {content}")
        context = "\n".join(context_parts)
    else:
        context = "No previous conversation."

    # Format user memory
    if isinstance(user_memory, str):
        # Pre-formatted memory string (from _format_user_memory)
        memory = user_memory if user_memory else "No stored information about this user."
    elif user_memory and user_memory.get("facts"):
        # Fallback: if raw dict passed, format non-deleted facts
        active = [f for f in user_memory["facts"] if not f.get("deleted", False)]
        if active:
            memory_parts = [
                f"- {fact.get('text', str(fact)) if isinstance(fact, dict) else fact}"
                for fact in active[:25]
            ]
            memory = "\n".join(memory_parts)
        else:
            memory = "No stored information about this user."
    else:
        memory = "No stored information about this user."

    # Format search context
    formatted_search = f"\nWeb research results:\n{search_context}\n" if search_context else ""

    # Tools section
    tools_section = TOOL_PROMPT_SECTION if include_tools else ""

    return SYSTEM_PROMPT.format(
        user_memory=memory,
        context=context,
        search_context=formatted_search,
        tools_section=tools_section,
        question=question,
    )
