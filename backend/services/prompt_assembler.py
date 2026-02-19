"""
Trinity Backend — Prompt Assembler

Single module that replaces the three formatting pipelines:
  - agent.py _format_user_memory() (scored, token-budgeted)
  - agent_prompts.py _format_memory_for_chat() (dead fallback)
  - agent_prompts.py build_system_prompt() (dead flat path)

Provides one assembler with a global token budget that allocates across
all memory sources: identity prompt, conversation context, knowledge items.

Also auto-generates the tool prompt section from TOOL_DEFINITIONS (single
source of truth — replaces the hand-written TOOL_PROMPT_SECTION string).
"""

import logging
from typing import Dict, List, Optional

from config import DEFAULT_MAX_TOKENS, NUM_CTX

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Safety margin to prevent context overflow
SAFETY_MARGIN_TOKENS = 2000

# Allocation ratios
CONVERSATION_RATIO = 0.55  # Up to 55% of budget for conversation history
# Remaining goes to knowledge items

# Approximate token estimation (chars / 4)
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Rough token count — chars / 4."""
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


# ---------------------------------------------------------------------------
# Tool prompt auto-generation
# ---------------------------------------------------------------------------

_TOOL_PROMPT_HEADER = """You have access to these tools. Call them when you need external information or actions.

## Available Tools
"""

_TOOL_PROMPT_RULES = """
## Rules
1. Output EXACTLY ONE tool call per turn, then STOP — do not write anything after it.
2. Tool results will appear in the next message. Then decide: call another tool or give your final answer.
3. Do NOT guess answers you can look up. Use web_search for current events, prices, news.
4. Do NOT include tool_call tags in your final answer.
5. For file operations: paths are relative to /workspace. Path traversal (../) is blocked.
6. Do NOT call write_file for generic "write code" requests without an explicit path/workspace target.
7. For code-generation requests, default to inline output: return the full implementation in fenced Markdown code blocks.
8. Never claim a file was created/written/saved unless you actually executed a write tool with an explicit path.
"""

_MEMORY_TOOL_GUIDELINES = """
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

**When to search memories:**
- Before answering personal questions ("what do you know about me?") → search_memory
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


def generate_tool_prompt_section() -> str:
    """
    Auto-generate the tool prompt section from TOOL_DEFINITIONS.

    Single source of truth — replaces the hand-written TOOL_PROMPT_SECTION
    string that had to be manually kept in sync with TOOL_DEFINITIONS.
    """
    try:
        from services.tools import TOOL_DEFINITIONS
    except ImportError:
        logger.warning("tools.py not available — using empty tool section")
        return ""

    parts = [_TOOL_PROMPT_HEADER]

    for tool_name, tool_def in TOOL_DEFINITIONS.items():
        desc = tool_def.get("description", "")
        params = tool_def.get("parameters", {})
        example = tool_def.get("example", "")

        parts.append(f"**{tool_name}** — {desc}")

        if example:
            parts.append(f"  {example}")
        elif params:
            # Auto-generate example from params
            param_xml = ""
            for pname, pdef in params.items():
                default = pdef.get("example", pdef.get("default", f"..."))
                param_xml += f"<{pname}>{default}</{pname}>"
            parts.append(f'  <tool_call name="{tool_name}">{param_xml}</tool_call>')

        parts.append("")

    parts.append(_TOOL_PROMPT_RULES)
    parts.append(_MEMORY_TOOL_GUIDELINES)

    return "\n".join(parts)


# Cache — generated once at import time
_cached_tool_section: Optional[str] = None


def get_tool_prompt_section() -> str:
    """Get the cached tool prompt section."""
    global _cached_tool_section
    if _cached_tool_section is None:
        _cached_tool_section = generate_tool_prompt_section()
    return _cached_tool_section


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_NO_MEMORY_MSG = (
    "You have no stored information about this user. "
    "If asked personal questions, say you don't know yet."
)

CHAT_SYSTEM_TEMPLATE = """You are Trinity, a sharp AI assistant.

{knowledge_section}
{search_context}
{tools_section}{extra_context}
Use profile memory only when it's relevant. Be direct — no filler. Use Markdown.
When asked to create code, include the actual code in fenced code blocks.
Inline code is the default contract. Do not claim a file was created unless you have an explicit file path/workspace target and performed a write action."""

REACT_SYSTEM_TEMPLATE = """You are Trinity, a sharp AI assistant with tool access.

{tool_definitions}

## Protocol
1. If a tool can help, output EXACTLY ONE tool call, then STOP.
2. You will receive the result. Then call another tool or write your FINAL ANSWER.
3. Never guess what you can look up — use web_search for current events, prices, facts.
4. Your final answer must NOT contain any tool_call XML tags.

{extra_context}"""


# ---------------------------------------------------------------------------
# Knowledge formatting
# ---------------------------------------------------------------------------

# Category display order
_CATEGORY_ORDER = [
    "identity",
    "work",
    "interests",
    "preferences",
    "relationships",
    "general",
    "relationship",
    "conversation",
]


def _format_knowledge_items(items: list, token_budget: int) -> str:
    """
    Format knowledge items into a prompt section, respecting token budget.

    Groups by category with headers. Items are assumed pre-sorted by score.
    """
    if not items:
        return _NO_MEMORY_MSG

    # Group by category
    groups: Dict[str, List[str]] = {}
    for item in items:
        cat = getattr(item, "category", "general") if hasattr(item, "category") else item.get("category", "general")
        text = getattr(item, "text", "") if hasattr(item, "text") else item.get("text", "")
        item_type = getattr(item, "item_type", None)

        if not text:
            continue

        # Format based on type
        if item_type and str(item_type) == "message":
            role = item.metadata.get("role", "user") if hasattr(item, "metadata") else "user"
            formatted = f'[Past {role}]: "{text[:300]}"'
        else:
            formatted = f"- {text}"

        if cat not in groups:
            groups[cat] = []
        groups[cat].append(formatted)

    if not groups:
        return _NO_MEMORY_MSG

    # Build output respecting token budget
    parts = ["## What you know about this user"]
    used_tokens = _estimate_tokens(parts[0])

    for category in _CATEGORY_ORDER:
        if category not in groups:
            continue
        header = f"### {category.title()}"
        header_tokens = _estimate_tokens(header)
        if used_tokens + header_tokens > token_budget:
            break
        parts.append(header)
        used_tokens += header_tokens

        for line in groups[category]:
            line_tokens = _estimate_tokens(line)
            if used_tokens + line_tokens > token_budget:
                break
            parts.append(line)
            used_tokens += line_tokens

    # Add any remaining categories not in the order list
    for category, lines in groups.items():
        if category in _CATEGORY_ORDER:
            continue
        header = f"### {category.title()}"
        header_tokens = _estimate_tokens(header)
        if used_tokens + header_tokens > token_budget:
            break
        parts.append(header)
        used_tokens += header_tokens

        for line in lines:
            line_tokens = _estimate_tokens(line)
            if used_tokens + line_tokens > token_budget:
                break
            parts.append(line)
            used_tokens += line_tokens

    parts.append("*(This is everything you know. If it's not listed here, say so.)*")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# PromptAssembler
# ---------------------------------------------------------------------------


class PromptAssembler:
    """
    Assembles the final message array for LLM calls.

    Single point of prompt construction — replaces build_chat_messages(),
    build_system_prompt(), _format_user_memory(), _format_memory_for_chat(),
    and ReactLoop._build_messages().

    Global token budget ensures the total prompt never exceeds the context window.
    """

    def __init__(
        self,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        num_ctx: int = NUM_CTX,
        safety_margin: int = SAFETY_MARGIN_TOKENS,
    ):
        self.max_tokens = max_tokens
        self.num_ctx = num_ctx
        self.total_budget = num_ctx - max_tokens - safety_margin

    def assemble(
        self,
        question: str,
        context_messages: Optional[List[Dict]] = None,
        conversation_summary: str = "",
        last_summarized_id: int = -1,
        knowledge_items: Optional[list] = None,
        search_context: str = "",
        tools_active: bool = False,
        react_mode: bool = False,
        extra_context: str = "",
    ) -> List[Dict]:
        """
        Assemble the complete message array.

        Args:
            question: Current user prompt.
            context_messages: Recent conversation messages from state store.
            conversation_summary: Rolling summary of older messages.
            last_summarized_id: Message ID boundary for summary.
            knowledge_items: Scored KnowledgeItems from KnowledgeStore.search().
            search_context: Web search results (if any).
            tools_active: Whether tool definitions should be included.
            react_mode: Whether to use the ReAct system prompt template.
            extra_context: Additional context (web search, repo map, etc).

        Returns:
            List of message dicts ready for Ollama /api/chat.
        """
        messages: List[Dict] = []

        # --- Budget accounting ---
        question_tokens = _estimate_tokens(question)
        remaining = self.total_budget - question_tokens

        # --- Tool section ---
        tools_section = ""
        if tools_active:
            tools_section = get_tool_prompt_section()
            remaining -= _estimate_tokens(tools_section)

        # --- Knowledge section ---
        knowledge_budget = max(500, int(remaining * (1 - CONVERSATION_RATIO)))
        knowledge_section = _format_knowledge_items(
            knowledge_items or [], knowledge_budget
        )
        knowledge_tokens = _estimate_tokens(knowledge_section)
        remaining -= knowledge_tokens

        # --- Search context ---
        search_section = ""
        if search_context:
            search_section = f"\nWeb research results:\n{search_context}\n"
            remaining -= _estimate_tokens(search_section)

        # --- System message ---
        if react_mode:
            extra_parts = []
            if knowledge_section and knowledge_section != _NO_MEMORY_MSG:
                extra_parts.append(f"Context about the user:\n{knowledge_section}")
            if extra_context:
                extra_parts.append(extra_context)
            if search_section:
                extra_parts.append(search_section)

            system_content = REACT_SYSTEM_TEMPLATE.format(
                tool_definitions=tools_section,
                extra_context="\n\n".join(extra_parts),
            )
        else:
            extra_block = ""
            if extra_context:
                extra_block = f"\n{extra_context}\n"
            system_content = CHAT_SYSTEM_TEMPLATE.format(
                knowledge_section=knowledge_section,
                search_context=search_section,
                tools_section=tools_section,
                extra_context=extra_block,
            )

        messages.append({"role": "system", "content": system_content})
        remaining -= _estimate_tokens(system_content)

        # --- Conversation summary ---
        if conversation_summary:
            summary_msg = f"Conversation summary (older messages):\n{conversation_summary}"
            summary_tokens = _estimate_tokens(summary_msg)
            if summary_tokens < remaining * 0.2:  # Don't let summary eat too much
                messages.append({"role": "system", "content": summary_msg})
                remaining -= summary_tokens

        # --- Conversation history ---
        conversation_budget = remaining  # Whatever's left goes to conversation
        if context_messages:
            history = list(context_messages)

            # If we have a summary, only include unsummarized messages
            if conversation_summary and last_summarized_id >= 0:
                history = [
                    m for m in history
                    if int(m.get("message_id", m.get("message_index", 0))) > last_summarized_id
                ]

            # Pack messages from oldest to newest, respecting budget
            packed = []
            used = 0
            # Work backwards from most recent to oldest, then reverse
            for msg in reversed(history):
                content = (msg.get("content") or "")[:4000]
                role = msg.get("role", "user")
                if role not in ("user", "assistant"):
                    continue
                msg_tokens = _estimate_tokens(content)
                if used + msg_tokens > conversation_budget:
                    break
                packed.append({"role": role, "content": content})
                used += msg_tokens

            packed.reverse()
            messages.extend(packed)

        # --- Current question ---
        messages.append({"role": "user", "content": question})

        return messages

    def assemble_for_react(
        self,
        question: str,
        context_messages: Optional[List[Dict]] = None,
        conversation_summary: str = "",
        last_summarized_id: int = -1,
        knowledge_items: Optional[list] = None,
        search_context: str = "",
        extra_context: str = "",
    ) -> List[Dict]:
        """Convenience wrapper for ReAct loop assembly."""
        return self.assemble(
            question=question,
            context_messages=context_messages,
            conversation_summary=conversation_summary,
            last_summarized_id=last_summarized_id,
            knowledge_items=knowledge_items,
            search_context=search_context,
            tools_active=True,
            react_mode=True,
            extra_context=extra_context,
        )


# ---------------------------------------------------------------------------
# Module-level instance
# ---------------------------------------------------------------------------


_assembler: Optional[PromptAssembler] = None


def get_assembler() -> PromptAssembler:
    """Get the global PromptAssembler instance."""
    global _assembler
    if _assembler is None:
        _assembler = PromptAssembler()
    return _assembler
