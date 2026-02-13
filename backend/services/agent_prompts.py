"""
Trinity Agentic Pipeline - Pass Prompts

Prompts for each pass of the multi-pass reasoning pipeline.
Uses XML tags for reliable parsing.

v4.0 Enhancements:
- Tool calling support with XML format
- Enhanced context from semantic memory
"""

import re
from dataclasses import dataclass
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

## Rules
1. Output EXACTLY ONE tool call per turn, then STOP — do not write anything after it.
2. Tool results will appear in the next message. Then decide: call another tool or give your final answer.
3. Do NOT guess answers you can look up. Use web_search for current events, prices, news.
4. Do NOT include tool_call tags in your final answer.

## Memory Guidelines
- Save important user facts (name, job, preferences, goals) with save_memory when shared
- Before answering personal questions ("what do you know about me?", "do you remember...?"), call recall_memory first
- Do NOT save trivial or session-specific details (e.g., "user asked about weather")
- Use search_memory when looking for a specific saved fact by keyword
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
# PASS 1: UNDERSTAND
# ============================================================================

UNDERSTAND_PROMPT = """Analyze this question. Be precise and brief.
{context}
Question: {question}

Respond in EXACTLY this XML format (no other text):
<type>factual|analytical|creative|code|design|debug|explanation</type>
<domains>comma-separated knowledge domains</domains>
<complexity>1-10 integer</complexity>
<tools_needed>calculator|web_search|fact_check|document_search|code_display|save_memory|recall_memory|search_memory (comma-separated, or "none")</tools_needed>
<summary>One sentence: what is the user really asking?</summary>
<key_challenges>What makes this hard to answer well?</key_challenges>"""


# ============================================================================
# PASS 2: PLAN
# ============================================================================

PLAN_PROMPT = """Based on this analysis:
{understanding}

Create a plan to thoroughly answer this question:
{question}

Respond in EXACTLY this format:
<plan>
1. [First concrete step]
2. [Second step]
3. [Third step]
4. [Fourth step if needed]
5. [Fifth step if needed]
</plan>
<approach>Brief description of your overall strategy</approach>
<pitfalls>What could go wrong? What should you avoid?</pitfalls>"""


# ============================================================================
# PASS 3: EXECUTE
# ============================================================================

EXECUTE_PROMPT_WITH_PLAN = """You are Trinity, a sharp and knowledgeable AI assistant.

Context about the user:
{user_memory}

Previous conversation:
{context}
{search_context}
Your analysis:
{understanding}

Your plan:
{plan}
{tools_section}
Now answer this question by executing your plan:
{question}

## Guidelines
- Write COMPLETE code — never use "..." or "# rest of code". Include imports and error handling.
- When showing code: briefly explain your approach first, then show the full code, then highlight key design decisions.
- For explanations: cover all key aspects, use concrete examples.
- For complex problems: show your reasoning step by step.
- Be direct and substantive — skip filler phrases like "Great question!" or "Sure, I'd be happy to help!"

## Formatting
- Use Markdown for structure (headers, lists, bold).
- Math: always use LaTeX — $x^2$ inline, $$\\sum_{{i=1}}^n i$$ for blocks.
- Code: use fenced blocks with language tags (```python).
- NEVER use <tool_call> or <code_display> XML tags. Always write code in ```language markdown blocks."""


EXECUTE_PROMPT_SIMPLE = """You are Trinity, a sharp and knowledgeable AI assistant.

Context about the user:
{user_memory}

Previous conversation:
{context}
{search_context}
{tools_section}
Question: {question}

## How to respond
- Answer directly and substantively — no filler phrases.
- For factual questions: give the answer, then a brief explanation if helpful.
- For code requests: briefly explain the approach, show complete code in ```language fenced blocks, then note any important details.
- For explanations: be clear and concrete, use examples when they help.
- For math: use LaTeX — $x^2$ inline, $$\\sum_{{i=1}}^n i$$ for blocks.
- Use Markdown for structure when the answer benefits from it.
- NEVER use <tool_call> or <code_display> XML tags. Always write code in ```language markdown blocks."""


# ============================================================================
# PASS 4: CRITIQUE
# ============================================================================

CRITIQUE_PROMPT = """You are a fair quality reviewer. Evaluate this response honestly.

Question: {question}

Response:
{response}

Scoring guidelines:
- 9-10: Correct, clear, well-organized answer
- 7-8: Good answer with minor gaps or formatting issues
- 5-6: Has notable errors, missing key info, or poor organization
- 3-4: Mostly wrong, incoherent, or severely incomplete
- 1-2: Completely wrong or off-topic

IMPORTANT: For simple factual questions, a short correct answer IS a high-quality answer.
Do NOT penalize brevity when the question is simple. Only find real weaknesses that exist.

Respond in EXACTLY this XML format (no other text):
<weakness1>First weakness (or 'None' if answer is good)</weakness1>
<weakness2>Second weakness (or 'None')</weakness2>
<weakness3>Third weakness (or 'None')</weakness3>
<score>1-10 integer (7+ means acceptable quality)</score>
<verdict>One sentence overall assessment</verdict>"""


# ============================================================================
# PASS 5: REFINE
# ============================================================================

REFINE_PROMPT = """Improve this response by fixing the weaknesses identified below.

Question: {question}

Original Response:
{response}

Weaknesses to fix:
1. {weakness1}
2. {weakness2}
3. {weakness3}
Score: {score}/10 — Verdict: {verdict}

Write the improved response. Keep what was good, fix what was weak.
Start directly with the answer — do NOT mention the refinement process."""


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class UnderstandingResult:
    question_type: str
    domains: List[str]
    complexity: int
    summary: str
    key_challenges: str
    raw: str
    tools_needed: List[str] = None  # v4.0: tools detected as needed


@dataclass
class PlanResult:
    steps: List[str]
    approach: str
    pitfalls: str
    raw: str


@dataclass
class CritiqueResult:
    weakness1: str
    weakness2: str
    weakness3: str
    score: int
    verdict: str
    raw: str


# ============================================================================
# XML PARSING (with fallbacks)
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


def parse_numbered_list(text: str) -> List[str]:
    """Extract numbered list items from text"""
    # Match lines starting with number, period/paren, then content
    matches = re.findall(r"^\s*\d+[\.\)]\s*(.+)$", text, re.MULTILINE)
    return [m.strip() for m in matches if m.strip()]


# ============================================================================
# PARSING FUNCTIONS
# ============================================================================


def parse_understanding(response: str) -> UnderstandingResult:
    """Parse Pass 1 (Understand) response"""
    # Extract complexity - model may return "8/10" or "8 (hard)" so extract just the number
    complexity_str = parse_xml_tag(response, "complexity", "5")
    complexity_match = re.search(r"\d+", complexity_str)
    complexity = int(complexity_match.group()) if complexity_match else 5
    complexity = min(10, max(1, complexity))  # Clamp to 1-10

    # Extract tools_needed (v4.0)
    tools_str = parse_xml_tag(response, "tools_needed", "none")
    if tools_str.lower() == "none":
        tools_needed = []
    else:
        tools_needed = [t.strip().lower() for t in tools_str.split(",") if t.strip()]

    return UnderstandingResult(
        question_type=parse_xml_tag(response, "type", "unknown"),
        domains=[d.strip() for d in parse_xml_tag(response, "domains", "").split(",") if d.strip()],
        complexity=complexity,
        summary=parse_xml_tag(response, "summary", "Question analysis unavailable"),
        key_challenges=parse_xml_tag(response, "key_challenges", ""),
        raw=response,
        tools_needed=tools_needed,
    )


def parse_plan(response: str) -> PlanResult:
    """Parse Pass 2 (Plan) response"""
    plan_text = parse_xml_tag(response, "plan", "")
    steps = parse_numbered_list(plan_text) if plan_text else []

    return PlanResult(
        steps=steps,
        approach=parse_xml_tag(response, "approach", ""),
        pitfalls=parse_xml_tag(response, "pitfalls", ""),
        raw=response,
    )


def parse_critique(response: str) -> CritiqueResult:
    """Parse Pass 4 (Critique) response"""
    score_str = parse_xml_tag(response, "score", "5")
    # Extract just the number
    score_match = re.search(r"\d+", score_str)
    score = int(score_match.group()) if score_match else 5

    return CritiqueResult(
        weakness1=parse_xml_tag(response, "weakness1", "No weakness identified"),
        weakness2=parse_xml_tag(response, "weakness2", "No weakness identified"),
        weakness3=parse_xml_tag(response, "weakness3", "No weakness identified"),
        score=min(10, max(1, score)),  # Clamp to 1-10
        verdict=parse_xml_tag(response, "verdict", ""),
        raw=response,
    )


# ============================================================================
# PROMPT BUILDERS
# ============================================================================


def build_understand_prompt(question: str, context_messages: List[Dict] = None) -> str:
    """Build the understanding pass prompt with optional conversation context."""
    if context_messages:
        context_parts = []
        for msg in context_messages[-4:]:  # Last 4 messages for context
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:500]
            context_parts.append(f"{role.title()}: {content}")
        context = "\nRecent conversation:\n" + "\n".join(context_parts)
    else:
        context = ""
    return UNDERSTAND_PROMPT.format(question=question, context=context)


def build_plan_prompt(question: str, understanding: UnderstandingResult) -> str:
    """Build the planning pass prompt"""
    understanding_summary = f"""Type: {understanding.question_type}
Domains: {', '.join(understanding.domains)}
Complexity: {understanding.complexity}/10
Summary: {understanding.summary}
Challenges: {understanding.key_challenges}"""

    return PLAN_PROMPT.format(understanding=understanding_summary, question=question)


def build_execute_prompt(
    question: str,
    understanding: Optional[UnderstandingResult],
    plan: Optional[PlanResult],
    context_messages: List[Dict],
    user_memory: Optional[Dict],
    search_context: str = "",
    include_tools: bool = False,
) -> str:
    """Build the execute pass prompt.

    NOTE: include_tools defaults to False. Tool instructions are harmful in
    one-shot /api/generate prompts because the model is told to "STOP after
    one tool call" but there's no turn-taking mechanism. Tools are handled
    by the ReAct loop which has its own prompt pipeline.
    """

    # Format context
    if context_messages:
        context_parts = []
        for msg in context_messages[-6:]:  # Last 6 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:2000]  # Preserve enough context for follow-ups
            context_parts.append(f"{role.title()}: {content}")
        context = "\n".join(context_parts)
    else:
        context = "No previous conversation."

    # Format user memory
    if user_memory and user_memory.get("facts"):
        memory_parts = [f"- {fact}" for fact in user_memory["facts"][:10]]
        memory = "\n".join(memory_parts)
    else:
        memory = "No stored information about this user."

    # Format search context (if we did a web search)
    if search_context:
        formatted_search = f"\nWeb research results:\n{search_context}\n"
    else:
        formatted_search = ""

    # Tools section (v4.0)
    tools_section = ""
    if include_tools:
        # Only include tools if they might be needed
        needs_tools = False
        if understanding and understanding.tools_needed:
            needs_tools = True
        # Also check for math/code keywords
        if any(
            kw in question.lower() for kw in ["calculate", "compute", "code", "python", "function"]
        ):
            needs_tools = True

        if needs_tools:
            tools_section = TOOL_PROMPT_SECTION

    # Use simple prompt for simple questions
    if not understanding and not plan:
        return EXECUTE_PROMPT_SIMPLE.format(
            user_memory=memory,
            context=context,
            search_context=formatted_search,
            tools_section=tools_section,
            question=question,
        )

    # Full prompt with understanding and plan
    understanding_text = ""
    if understanding:
        understanding_text = f"""Type: {understanding.question_type}
Complexity: {understanding.complexity}/10
Summary: {understanding.summary}"""

    plan_text = ""
    if plan:
        plan_text = "\n".join(f"{i+1}. {step}" for i, step in enumerate(plan.steps))

    return EXECUTE_PROMPT_WITH_PLAN.format(
        user_memory=memory,
        context=context,
        search_context=formatted_search,
        understanding=understanding_text or "Quick question - no deep analysis needed.",
        plan=plan_text or "Direct response - no complex plan needed.",
        tools_section=tools_section,
        question=question,
    )


def build_critique_prompt(question: str, response: str) -> str:
    """Build the critique pass prompt"""
    return CRITIQUE_PROMPT.format(
        question=question, response=response[:4000]  # Truncate if too long
    )


def build_refine_prompt(question: str, response: str, critique: CritiqueResult) -> str:
    """Build the refine pass prompt"""
    return REFINE_PROMPT.format(
        question=question,
        response=response[:4000],
        weakness1=critique.weakness1,
        weakness2=critique.weakness2,
        weakness3=critique.weakness3,
        score=critique.score,
        verdict=critique.verdict,
    )
