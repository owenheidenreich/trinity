"""
Trinity LangGraph Specialized Agents

Defines specialized agents for different task types:
- SupervisorAgent: Routes tasks to appropriate specialists
- ResearchAgent: Web search, document analysis, and fact-checking
- ReasoningAgent: Complex logic, math, and multi-step analysis
- CodingAgent: Code generation and execution
- SynthesisAgent: Combines outputs into final response

All agents can use tools via XML tool_call format. Tool calls in agent output
are parsed and executed by the node layer (nodes.py) with principal_id context.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from .llm import TrinityLLM

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for a specialized agent."""

    name: str
    model_type: str  # 'fast', 'smart', 'reasoning'
    system_prompt: str
    tools: List[str]
    max_tokens: int = 4096
    temperature: float = 0.7


class BaseAgent:
    """Base class for specialized agents."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.llm = TrinityLLM(
            model_type=config.model_type,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

    def invoke(self, state: Dict[str, Any]) -> str:
        """Execute the agent on the given state."""
        raise NotImplementedError


class SupervisorAgent(BaseAgent):
    """
    Routes tasks to specialized agents based on query analysis.

    Uses fast model for quick classification.
    """

    DEFAULT_CONFIG = AgentConfig(
        name="supervisor",
        model_type="fast",
        system_prompt="""Route to the best specialist. Respond with exactly ONE word.

RESEARCH — web search, current events, prices, fact-checking, document lookup
REASONING — logic, math, analysis, comparisons, explanations, strategy
CODING — code generation, debugging, programming, technical implementation

Default to REASONING if unclear. One word only: RESEARCH, REASONING, or CODING""",
        tools=[],
        max_tokens=50,
        temperature=0.3,
    )

    def __init__(self, config: AgentConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)

    def invoke(self, state: Dict[str, Any]) -> str:
        """Determine which agent should handle this task."""
        # Get the latest user message
        messages = state.get("messages", [])
        if not messages:
            return "reasoning"  # Default

        last_message = messages[-1]
        user_query = last_message.content if hasattr(last_message, "content") else str(last_message)

        # Build prompt
        prompt_messages = [
            SystemMessage(content=self.config.system_prompt),
            HumanMessage(content=user_query),
        ]

        response = self.llm.invoke(prompt_messages)
        content = response.content.upper().strip()

        logger.info(f"🎯 Supervisor routing: '{content}' for query: {user_query[:50]}...")

        # Parse response to agent name
        if "RESEARCH" in content:
            return "research"
        elif "CODING" in content:
            return "coding"
        else:
            return "reasoning"


class ResearchAgent(BaseAgent):
    """
    Specialized for web search and document analysis.

    Uses smart model for synthesis of research findings.
    """

    DEFAULT_CONFIG = AgentConfig(
        name="research",
        model_type="smart",
        system_prompt="""You are a research specialist. Synthesize information into clear, accurate summaries.

You have access to tools. Use them by outputting XML tool calls:
- <tool_call name="web_search"><query>search terms</query></tool_call>
- <tool_call name="fact_check"><claim>claim to verify</claim></tool_call>
- <tool_call name="document_search"><query>what to find</query></tool_call>
- <tool_call name="recall_memory"><query>what to recall about the user</query></tool_call>

If research context is provided, use it to answer thoroughly. Cite sources when available.
Structure your response with clear sections.""",
        tools=["web_search", "document_search", "fact_check", "recall_memory"],
        max_tokens=4096,
        temperature=0.5,
    )

    def __init__(self, config: AgentConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)

    def invoke(self, state: Dict[str, Any]) -> str:
        """Execute research task."""
        messages = state.get("messages", [])
        research_context = state.get("research_context", "")

        if not messages:
            return "I need a question to research."

        last_message = messages[-1]
        user_query = last_message.content if hasattr(last_message, "content") else str(last_message)

        # Build prompt with context
        context_section = ""
        if research_context:
            context_section = f"\n\n## Research Context:\n{research_context}\n"

        full_prompt = f"""{self.config.system_prompt}
{context_section}
## User Question:
{user_query}

## Your Research Response:"""

        response = self.llm.invoke(full_prompt)
        return response.content


class ReasoningAgent(BaseAgent):
    """
    Specialized for complex logic and multi-step analysis.

    Uses reasoning model (largest) for deep thinking tasks.
    """

    DEFAULT_CONFIG = AgentConfig(
        name="reasoning",
        model_type="reasoning",
        system_prompt="""You are a reasoning specialist. Break down complex problems step by step.

You have access to tools:
- <tool_call name="calculator"><expression>math expression</expression></tool_call>
- <tool_call name="recall_memory"><query>what to recall about the user</query></tool_call>
- <tool_call name="save_memory"><fact>important fact</fact><category>general</category><importance>3</importance></tool_call>

Think step by step. Show your reasoning clearly. Verify answers before presenting.
For math, use the calculator tool for non-trivial computations.
Consider multiple perspectives and edge cases.""",
        tools=["calculator", "recall_memory", "save_memory"],
        max_tokens=8192,
        temperature=0.5,
    )

    def __init__(self, config: AgentConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)

    def invoke(self, state: Dict[str, Any]) -> str:
        """Execute reasoning task."""
        messages = state.get("messages", [])
        previous_reasoning = state.get("reasoning_output", "")

        if not messages:
            return "I need a problem to analyze."

        last_message = messages[-1]
        user_query = last_message.content if hasattr(last_message, "content") else str(last_message)

        # Build prompt with previous context
        context_section = ""
        if previous_reasoning:
            context_section = (
                f"\n\n## Previous Analysis:\n{previous_reasoning}\n\nBuild upon this analysis.\n"
            )

        full_prompt = f"""{self.config.system_prompt}
{context_section}
## Problem/Question:
{user_query}

## Your Analysis:"""

        response = self.llm.invoke(full_prompt)
        return response.content


class CodingAgent(BaseAgent):
    """
    Specialized for code generation and execution.

    Uses smart model for balanced code quality and speed.
    """

    DEFAULT_CONFIG = AgentConfig(
        name="coding",
        model_type="smart",
        system_prompt="""You are a coding specialist. Write clean, production-quality code.

You have access to tools:
- <tool_call name="code_display"><language>python</language><code>your code</code><execute>true</execute></tool_call>
- <tool_call name="calculator"><expression>math expression</expression></tool_call>

Guidelines:
- Write COMPLETE code — never use "..." or placeholders
- Include imports, error handling, and clear naming
- Use fenced code blocks with language tags (```python)
- Provide example usage when helpful""",
        tools=["code_display", "calculator"],
        max_tokens=8192,
        temperature=0.3,
    )

    def __init__(self, config: AgentConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)

    def invoke(self, state: Dict[str, Any]) -> str:
        """Execute coding task."""
        messages = state.get("messages", [])
        previous_code = state.get("code_output", "")

        if not messages:
            return "I need a coding task to work on."

        last_message = messages[-1]
        user_query = last_message.content if hasattr(last_message, "content") else str(last_message)

        # Build prompt with previous context
        context_section = ""
        if previous_code:
            context_section = f"\n\n## Previous Code:\n```\n{previous_code}\n```\n\nRefine or build upon this code.\n"

        full_prompt = f"""{self.config.system_prompt}
{context_section}
## Coding Task:
{user_query}

## Your Solution:"""

        response = self.llm.invoke(full_prompt)
        return response.content


class SynthesisAgent(BaseAgent):
    """
    Synthesizes outputs from other agents into a final coherent response.
    """

    DEFAULT_CONFIG = AgentConfig(
        name="synthesis",
        model_type="smart",
        system_prompt="""Combine the specialist outputs below into one coherent response.

Rules:
- Address ALL parts of the user's question
- Remove redundancy while keeping important details
- Use Markdown formatting (headers, lists, code blocks)
- Do NOT add new information — only synthesize what is provided
- Start directly with the answer, no preamble""",
        tools=[],
        max_tokens=4096,
        temperature=0.5,
    )

    def __init__(self, config: AgentConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)

    def invoke(self, state: Dict[str, Any]) -> str:
        """Synthesize final response from agent outputs."""
        messages = state.get("messages", [])
        research_context = state.get("research_context", "")
        reasoning_output = state.get("reasoning_output", "")
        code_output = state.get("code_output", "")

        if not messages:
            return "No context to synthesize."

        # Get original question
        first_message = messages[0]
        user_query = (
            first_message.content if hasattr(first_message, "content") else str(first_message)
        )

        # Build synthesis prompt
        sections = []
        if research_context:
            sections.append(f"## Research Findings:\n{research_context}")
        if reasoning_output:
            sections.append(f"## Analysis:\n{reasoning_output}")
        if code_output:
            sections.append(f"## Code Solution:\n{code_output}")

        if not sections:
            return "I apologize, but I wasn't able to gather enough information to provide a complete response."

        combined = "\n\n".join(sections)

        full_prompt = f"""{self.config.system_prompt}

## Original Question:
{user_query}

## Agent Outputs:
{combined}

## Synthesized Response:"""

        response = self.llm.invoke(full_prompt)
        return response.content


# Factory function to get agent by name
def get_agent(agent_name: str) -> BaseAgent:
    """Get an agent instance by name."""
    agents = {
        "supervisor": SupervisorAgent,
        "research": ResearchAgent,
        "reasoning": ReasoningAgent,
        "coding": CodingAgent,
        "synthesis": SynthesisAgent,
    }

    agent_class = agents.get(agent_name.lower())
    if agent_class is None:
        raise ValueError(f"Unknown agent: {agent_name}")

    return agent_class()
