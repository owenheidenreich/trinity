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
You have access to these tools. Use them when needed:

**calculator**: Evaluate mathematical expressions
  Example: <tool_call name="calculator"><expression>sqrt(16) + 2^3</expression></tool_call>

**web_search**: Search the web for current information
  Example: <tool_call name="web_search"><query>Bitcoin price today</query></tool_call>

**document_search**: Search through uploaded documents
  Example: <tool_call name="document_search"><query>contract termination clause</query></tool_call>

**code_display**: Display and optionally execute Python code
  Example: <tool_call name="code_display"><language>python</language><code>def factorial(n): return 1 if n <= 1 else n * factorial(n-1)</code><execute>true</execute></tool_call>

To use a tool, output it in this exact XML format. Tool results will be provided before your final answer.
"""


# ============================================================================
# PASS 1: UNDERSTAND
# ============================================================================

UNDERSTAND_PROMPT = """Analyze this question briefly but thoroughly.

Question: {question}

Respond in EXACTLY this format:
<type>factual|analytical|creative|code|design|debug|explanation</type>
<domains>comma-separated knowledge domains needed</domains>
<complexity>1-10 rating</complexity>
<tools_needed>calculator|web_search|document_search|code_display (comma-separated, or "none")</tools_needed>
<summary>One sentence: what is actually being asked?</summary>
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

EXECUTE_PROMPT_WITH_PLAN = """You are Trinity, a highly capable AI assistant built on decentralized infrastructure.

Context about the user:
{user_memory}

Previous conversation:
{context}
{search_context}
Your analysis of this question:
{understanding}

Your plan:
{plan}
{tools_section}
Now execute your plan to answer this question thoroughly:
{question}

IMPORTANT GUIDELINES:
- Be COMPLETE. If writing code, write the ENTIRE file, not snippets with "..." or "# rest of code".
- If explaining a concept, cover ALL aspects thoroughly.
- Never truncate or abbreviate. You have space for 16,000 tokens - USE IT when the question warrants it.
- Show your reasoning step by step for complex problems.
- For code: include imports, error handling, comments, and complete implementations.
- For explanations: use examples, analogies, and cover edge cases.

Formatting: Use Markdown for text. For ALL math, use LaTeX with dollar signs: $x^2$ for inline, $$\\sum_{{i=1}}^n i$$ for blocks. NEVER write math without $ delimiters.
Take your time. Be thorough. Quality over speed."""


EXECUTE_PROMPT_SIMPLE = """You are Trinity, a highly capable AI assistant built on decentralized infrastructure.

Context about the user:
{user_memory}

Previous conversation:
{context}
{search_context}
{tools_section}
Question: {question}

GUIDELINES:
- Be complete and thorough in your response.
- If writing code, provide the FULL implementation, not snippets.
- Never use "..." or "# rest of code" - write everything out.
- You have plenty of space - use it when the question warrants depth.

Formatting: Use Markdown for text. For ALL math, use LaTeX with dollar signs: $x^2$ for inline, $$\\sum_{{i=1}}^n i$$ for blocks. NEVER write math without $ delimiters.
Provide a clear, helpful, COMPLETE response."""


# ============================================================================
# PASS 4: CRITIQUE
# ============================================================================

CRITIQUE_PROMPT = """You are a critical reviewer. Your job is to find weaknesses.

Original Question: {question}

Response to Review:
{response}

You MUST find exactly 3 weaknesses or gaps, even if the response is good.
Be specific and actionable. Don't be nice - be helpful.

Respond in EXACTLY this format:
<weakness1>First specific weakness or gap</weakness1>
<weakness2>Second specific weakness or gap</weakness2>
<weakness3>Third specific weakness or gap</weakness3>
<score>1-10 quality score (7+ means good enough)</score>
<verdict>Brief overall assessment</verdict>"""


# ============================================================================
# PASS 5: REFINE
# ============================================================================

REFINE_PROMPT = """Improve this response based on the critique.

Original Question: {question}

Original Response:
{response}

Critique:
- Weakness 1: {weakness1}
- Weakness 2: {weakness2}
- Weakness 3: {weakness3}
- Score: {score}/10
- Verdict: {verdict}

Write an IMPROVED response that addresses these weaknesses.
Keep what was good, fix what was weak. Be thorough.

CRITICAL: Start your response immediately with the actual content.
Do NOT include phrases like "Here is my improved response" or "Based on the critique".
Do NOT reference this refinement process. Just write the answer directly."""


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


def build_understand_prompt(question: str) -> str:
    """Build the understanding pass prompt"""
    return UNDERSTAND_PROMPT.format(question=question)


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
    include_tools: bool = True,
) -> str:
    """Build the execute pass prompt"""

    # Format context
    if context_messages:
        context_parts = []
        for msg in context_messages[-6:]:  # Last 6 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:500]  # Truncate long messages
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
