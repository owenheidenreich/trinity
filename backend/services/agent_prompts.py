"""
Trinity — Prompt Templates & XML Parsing

Slimmed-down version: only keeps what production code actually imports.

Active exports:
  REACT_SYSTEM_PROMPT   — used by react_loop.py
  TOOL_PROMPT_SECTION   — used by react_loop.py, auto-generated from tools.py
  CHAT_SYSTEM_MESSAGE   — template (also lives in prompt_assembler.py)
  parse_xml_tag()       — used by react_loop.py
  build_chat_messages() — backwards compat (tests + old agent.py wrapper)

Removed:
  build_system_prompt()  — dead code (was never called in production)
  _format_memory_for_chat() — replaced by prompt_assembler
  Hand-written TOOL_PROMPT_SECTION — replaced by auto-generated version
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Auto-generated tool prompt section from TOOL_DEFINITIONS
# ---------------------------------------------------------------------------

try:
    from .prompt_assembler import get_tool_prompt_section

    TOOL_PROMPT_SECTION = get_tool_prompt_section()
except Exception:
    # Fallback if prompt_assembler isn't available yet
    TOOL_PROMPT_SECTION = ""


# ---------------------------------------------------------------------------
# ReAct system prompt
# ---------------------------------------------------------------------------

REACT_SYSTEM_PROMPT = """You are Trinity, a sharp AI assistant with tool access.

{tool_definitions}

## Protocol
1. If a tool can help, output EXACTLY ONE tool call, then STOP.
2. You will receive the result. Then call another tool or write your FINAL ANSWER.
3. Never guess what you can look up — use web_search for current events, prices, facts.
4. Your final answer must NOT contain any tool_call XML tags.

{extra_context}"""


# ---------------------------------------------------------------------------
# Chat system message template
# ---------------------------------------------------------------------------

_NO_MEMORY_MSG = (
    "You have no stored information about this user. "
    "If asked personal questions, say you don't know yet."
)

CHAT_SYSTEM_MESSAGE = """You are Trinity, a sharp AI assistant.

{user_memory}
{search_context}
{tools_section}
Use profile memory only when it's relevant. Be direct — no filler. Use Markdown.
When asked to create code, include the actual code in fenced code blocks.
Inline code is the default contract. Do not claim a file was created unless you have an explicit file path/workspace target and performed a write action."""


# ---------------------------------------------------------------------------
# XML parsing (used by react_loop.py)
# ---------------------------------------------------------------------------


def parse_xml_tag(text: str, tag: str, default: str = "") -> str:
    """Extract content from XML tag with multiple fallback strategies.

    Tries:
    1. Exact XML match: ``<tag>content</tag>``
    2. Unclosed XML: ``<tag>content``
    3. Labeled section: ``tag: content``
    4. Markdown bold: ``**tag**: content``
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
    match = re.search(
        f"{tag}:\\s*(.+?)(?:\\n\\n|\\n<|$)", text, re.DOTALL | re.IGNORECASE
    )
    if match:
        return match.group(1).strip()

    # Strategy 4: Markdown bold label
    match = re.search(
        f"\\*\\*{tag}\\*\\*:\\s*(.+?)(?:\\n\\n|\\n<|$)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    return default


# ---------------------------------------------------------------------------
# Backwards-compat: build_chat_messages (used by tests)
# ---------------------------------------------------------------------------


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

    Preserves old signature for backwards compat. New code should use
    ``PromptAssembler.assemble()`` instead.
    """
    messages = []

    # --- System message ---
    memory = _format_memory(user_memory)
    formatted_search = (
        f"\nWeb research results:\n{search_context}\n" if search_context else ""
    )
    tools_section = TOOL_PROMPT_SECTION if include_tools else ""

    system_content = CHAT_SYSTEM_MESSAGE.format(
        user_memory=memory if memory else _NO_MEMORY_MSG,
        search_context=formatted_search,
        tools_section=tools_section,
    )
    messages.append({"role": "system", "content": system_content})

    # --- Summary (if available) ---
    summary = (conversation_summary or "").strip()
    if summary:
        messages.append(
            {
                "role": "system",
                "content": f"Conversation summary (older messages):\n{summary}",
            }
        )

    # --- Conversation history ---
    if context_messages:
        history = list(context_messages)

        # When a summary covers messages up to last_summarized_index,
        # only include messages AFTER the summarized range.
        if summary and last_summarized_index >= 0:
            if any("message_index" in m for m in history):
                history = [
                    m for m in history
                    if m.get("message_index", 0) > last_summarized_index
                ]
            elif current_message_index > 0:
                # No message_index on messages — use positional tail
                unsummarized_count = current_message_index - last_summarized_index
                keep = max(5, min(15, unsummarized_count))
                history = history[-keep:]

        history = history[-20:]
        for msg in history:
            role = msg.get("role", "user")
            content = (msg.get("content") or "")[:4000]
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    # --- Current user message ---
    messages.append({"role": "user", "content": question})
    return messages


def _format_memory(user_memory) -> str:
    """Minimal memory formatter for backwards compat."""
    if isinstance(user_memory, str):
        return user_memory or ""
    if isinstance(user_memory, dict) and user_memory.get("facts"):
        active = [f for f in user_memory["facts"] if not f.get("deleted", False)]
        if active:
            return "\n".join(
                f"- {f.get('text', str(f)) if isinstance(f, dict) else f}"
                for f in active[:25]
            )
    return ""
