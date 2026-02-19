"""
Trinity Agentic Pipeline - Prompts

Single-pass prompt system. Two prompts:
  1. SYSTEM_PROMPT — direct Q&A (no tools)
  2. SYSTEM_PROMPT + TOOL_PROMPT_SECTION — when tools are needed (ReAct handles turn-taking)

Plus REACT_SYSTEM_PROMPT for the ReAct loop's own system message.
"""

import re
from typing import Dict, List, Optional

_NO_MEMORY_MSG = "You have no stored information about this user. If asked personal questions, say you don't know yet."

# ============================================================================
# TOOL DEFINITIONS (for prompt injection)
# ============================================================================

TOOL_PROMPT_SECTION = """
You have access to these tools. Call them when you need external information or actions.

## Available Tools

**calculator** — Evaluate math expressions.
  <tool_call name="calculator"><expression>sqrt(16) + 2^3</expression></tool_call>

**current_datetime** — Get the current date and time.
  <tool_call name="current_datetime"></tool_call>

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
6. Do NOT call write_file for generic "write code" requests without an explicit path/workspace target.
7. For code-generation requests, default to inline output: return the full implementation in fenced Markdown code blocks.
8. Never claim a file was created/written/saved unless you actually executed a write tool with an explicit path.

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

REACT_SYSTEM_PROMPT = """You are Trinity, a sharp AI assistant with tool access.

{tool_definitions}

## Protocol
1. If a tool can help, output EXACTLY ONE tool call, then STOP.
2. You will receive the result. Then call another tool or write your FINAL ANSWER.
3. Never guess what you can look up — use web_search for current events, prices, facts.
4. Your final answer must NOT contain any tool_call XML tags.

{extra_context}"""


# ============================================================================
# SYSTEM PROMPT (single-pass, used for all queries)
# ============================================================================

SYSTEM_PROMPT = """You are Trinity, a sharp AI assistant.

{user_memory}

Previous conversation:
{context}
{search_context}
{tools_section}
Question: {question}

Use profile memory only when it's relevant. Be direct — no filler. Use Markdown.
For code requests:
- Always include actual runnable code in fenced code blocks.
- Inline code is the default (do not claim filesystem writes).
- Never say a file was created unless a real write action with explicit path occurred."""

# ============================================================================
# CHAT SYSTEM MESSAGE (for /api/chat — structured messages, not flat prompt)
# ============================================================================

CHAT_SYSTEM_MESSAGE = """You are Trinity, a sharp AI assistant.

{user_memory}
{search_context}
{tools_section}
Use profile memory only when it's relevant. Be direct — no filler. Use Markdown.
When asked to create code, include the actual code in fenced code blocks.
Inline code is the default contract. Do not claim a file was created unless you have an explicit file path/workspace target and performed a write action."""


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
    # Format context — cap at 20 messages × 4000 chars to stay within
    # the ~49K token prompt budget (NUM_CTX=65536 − num_predict=16384).
    # 20 × 4000 chars ≈ 20K tokens — well within budget.
    if context_messages:
        context_parts = []
        for msg in context_messages[-20:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:4000]
            context_parts.append(f"{role.title()}: {content}")
        context = "\n".join(context_parts)
    else:
        context = "No previous conversation."

    # Format user memory
    if isinstance(user_memory, str):
        # Pre-formatted memory string (from _format_user_memory)
        memory = user_memory if user_memory else _NO_MEMORY_MSG
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
            memory = _NO_MEMORY_MSG
    else:
        memory = _NO_MEMORY_MSG

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


def _format_memory_for_chat(user_memory) -> str:
    """Format user memory consistently for both build_system_prompt and build_chat_messages."""
    if isinstance(user_memory, str):
        return user_memory if user_memory else ""
    elif user_memory and user_memory.get("facts"):
        active = [f for f in user_memory["facts"] if not f.get("deleted", False)]
        if active:
            memory_parts = [
                f"- {fact.get('text', str(fact)) if isinstance(fact, dict) else fact}"
                for fact in active[:25]
            ]
            return "\n".join(memory_parts)
    return ""


def build_chat_messages(
    question: str,
    context_messages: List[Dict] = None,
    user_memory=None,
    search_context: str = "",
    include_tools: bool = False,
    chat_id: Optional[str] = None,
    conversation_summary: str = "",
    last_summarized_index: int = -1,
    current_message_index: int = -1,
) -> List[Dict]:
    """Build a structured messages array for /api/chat.

    Unlike build_system_prompt() which flattens everything into a single string
    for /api/generate, this returns a proper messages array where each
    conversation turn is a separate message with the correct role. This gives
    the model structural awareness of turn-taking — critical for games,
    role-play, and multi-turn reasoning.

    Args:
        question: The user's current message.
        context_messages: Recent conversation history.
        user_memory: Pre-formatted memory string or dict with 'facts'.
        search_context: Formatted web search results (if any).
        include_tools: Whether to inject tool definitions.
        chat_id: Current chat ID for summary lookup.
        conversation_summary: Optional precomputed summary text.
        last_summarized_index: Optional index boundary for summary.
        current_message_index: Optional absolute message index for fallback slicing.

    Returns:
        List of message dicts: [{"role": "system"|"user"|"assistant", "content": ...}]
    """
    messages = []

    # --- System message: identity + memory + search + tools ---
    memory = _format_memory_for_chat(user_memory)
    formatted_search = f"\nWeb research results:\n{search_context}\n" if search_context else ""
    tools_section = TOOL_PROMPT_SECTION if include_tools else ""

    system_content = CHAT_SYSTEM_MESSAGE.format(
        user_memory=memory if memory else _NO_MEMORY_MSG,
        search_context=formatted_search,
        tools_section=tools_section,
    )
    messages.append({"role": "system", "content": system_content})

    summary = (conversation_summary or "").strip()
    summary_boundary = last_summarized_index
    try:
        current_index = int(current_message_index)
    except (TypeError, ValueError):
        current_index = -1
    if not summary and isinstance(user_memory, dict) and chat_id:
        summaries = user_memory.get("conversation_summaries", {})
        if isinstance(summaries, dict):
            summary_record = summaries.get(chat_id, {})
            if isinstance(summary_record, dict):
                summary = str(summary_record.get("summary", "")).strip()
                try:
                    summary_boundary = int(
                        summary_record.get(
                            "last_message_id",
                            summary_record.get("last_summarized_index", -1),
                        )
                    )
                except (TypeError, ValueError):
                    summary_boundary = -1

    if summary:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Conversation summary (older messages):\n"
                    f"{summary}"
                ),
            }
        )

    # --- Conversation history as structured messages ---
    # With summary present: include only unsummarized tail (max 15).
    # Without summary: keep last 20 (legacy behavior).
    if context_messages:
        history = list(context_messages)
        if summary and summary_boundary >= 0:
            indexed = [
                m for m in history if isinstance(m, dict) and ("message_id" in m or "message_index" in m)
            ]
            if indexed:
                filtered = []
                for m in history:
                    try:
                        message_marker = m.get("message_id", m.get("message_index", -1))
                        if int(message_marker) > summary_boundary:
                            filtered.append(m)
                    except (TypeError, ValueError):
                        continue
                history = filtered
                history = history[-15:]
            else:
                # Frontend context messages often exclude absolute message_index.
                # In that case, estimate unsummarized tail size from current_message_index.
                if current_index >= 0:
                    unsummarized_count = current_index - (summary_boundary + 1)
                    if unsummarized_count > 0:
                        history = history[-max(1, min(15, unsummarized_count)):]
                    else:
                        # Never drop all local recency context just because the summary boundary
                        # is ahead of this 20-message window.
                        history = history[-15:]
                else:
                    history = history[-15:]
        else:
            history = history[-20:]

        for msg in history:
            role = msg.get("role", "user")
            content = (msg.get("content") or "")[:4000]
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    # --- Current user message ---
    messages.append({"role": "user", "content": question})

    return messages
