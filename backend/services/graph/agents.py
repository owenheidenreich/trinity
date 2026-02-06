"""
Trinity LangGraph Specialized Agents

Defines specialized agents for different task types:
- SupervisorAgent: Routes tasks to appropriate specialists
- ResearchAgent: Web search and document analysis
- ReasoningAgent: Complex logic and multi-step analysis  
- CodingAgent: Code generation and execution
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from .llm import TrinityLLM, get_fast_llm, get_smart_llm, get_reasoning_llm

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
            max_tokens=config.max_tokens
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
        system_prompt="""You are a task router for a multi-agent AI system. Analyze the user's query and decide which specialist should handle it.

Available specialists:
- RESEARCH: For queries requiring web search, fact-finding, current information, news, prices, or document analysis
- REASONING: For complex logic, math, multi-step analysis, strategic thinking, comparisons, or explanations
- CODING: For code generation, debugging, technical implementation, or programming questions

Rules:
1. Choose exactly ONE specialist
2. If unclear, default to REASONING
3. If the query mentions code, programming, or technical implementation, choose CODING
4. If the query asks about current events, prices, or needs external data, choose RESEARCH

Respond with exactly one word: RESEARCH, REASONING, or CODING""",
        tools=[],
        max_tokens=50,
        temperature=0.3
    )
    
    def __init__(self, config: AgentConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)
    
    def invoke(self, state: Dict[str, Any]) -> str:
        """Determine which agent should handle this task."""
        # Get the latest user message
        messages = state.get('messages', [])
        if not messages:
            return 'reasoning'  # Default
        
        last_message = messages[-1]
        user_query = last_message.content if hasattr(last_message, 'content') else str(last_message)
        
        # Build prompt
        prompt_messages = [
            SystemMessage(content=self.config.system_prompt),
            HumanMessage(content=user_query)
        ]
        
        response = self.llm.invoke(prompt_messages)
        content = response.content.upper().strip()
        
        logger.info(f"🎯 Supervisor routing: '{content}' for query: {user_query[:50]}...")
        
        # Parse response to agent name
        if 'RESEARCH' in content:
            return 'research'
        elif 'CODING' in content:
            return 'coding'
        else:
            return 'reasoning'


class ResearchAgent(BaseAgent):
    """
    Specialized for web search and document analysis.
    
    Uses smart model for synthesis of research findings.
    """
    
    DEFAULT_CONFIG = AgentConfig(
        name="research",
        model_type="smart",
        system_prompt="""You are a research specialist AI. Your job is to:
1. Analyze the user's question to identify information needs
2. Formulate effective search queries
3. Synthesize findings into clear, accurate summaries
4. Always cite your sources when presenting external information

When you need to search for information, indicate what you would search for.
Structure your response with clear sections and supporting evidence.

If you have research context provided, use it to answer the question thoroughly.""",
        tools=['web_search', 'document_search', 'fact_check'],
        max_tokens=4096,
        temperature=0.5
    )
    
    def __init__(self, config: AgentConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)
    
    def invoke(self, state: Dict[str, Any]) -> str:
        """Execute research task."""
        messages = state.get('messages', [])
        research_context = state.get('research_context', '')
        
        if not messages:
            return "I need a question to research."
        
        last_message = messages[-1]
        user_query = last_message.content if hasattr(last_message, 'content') else str(last_message)
        
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
        system_prompt="""You are a reasoning specialist AI. Your job is to:
1. Break down complex problems into clear steps
2. Apply logical analysis and critical thinking
3. Consider multiple perspectives and edge cases
4. Provide well-structured, thorough explanations
5. Use calculations when needed (show your work)

Think step by step. Show your reasoning process clearly.
Structure your response with numbered steps or clear sections.

When solving math or logic problems, verify your answer before presenting it.""",
        tools=['calculator'],
        max_tokens=8192,
        temperature=0.5
    )
    
    def __init__(self, config: AgentConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)
    
    def invoke(self, state: Dict[str, Any]) -> str:
        """Execute reasoning task."""
        messages = state.get('messages', [])
        previous_reasoning = state.get('reasoning_output', '')
        
        if not messages:
            return "I need a problem to analyze."
        
        last_message = messages[-1]
        user_query = last_message.content if hasattr(last_message, 'content') else str(last_message)
        
        # Build prompt with previous context
        context_section = ""
        if previous_reasoning:
            context_section = f"\n\n## Previous Analysis:\n{previous_reasoning}\n\nBuild upon this analysis.\n"
        
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
        system_prompt="""You are a coding specialist AI. Your job is to:
1. Write clean, well-documented, production-quality code
2. Debug and fix issues with clear explanations
3. Explain technical concepts at the appropriate level
4. Follow best practices and coding standards
5. Include error handling and edge cases

When writing code:
- Use clear variable and function names
- Add helpful comments
- Handle potential errors gracefully
- Provide example usage when helpful

Languages you excel at: Python, JavaScript, TypeScript, SQL, Bash, and more.""",
        tools=['code_execute', 'code_display'],
        max_tokens=8192,
        temperature=0.3  # Lower temp for more precise code
    )
    
    def __init__(self, config: AgentConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)
    
    def invoke(self, state: Dict[str, Any]) -> str:
        """Execute coding task."""
        messages = state.get('messages', [])
        previous_code = state.get('code_output', '')
        
        if not messages:
            return "I need a coding task to work on."
        
        last_message = messages[-1]
        user_query = last_message.content if hasattr(last_message, 'content') else str(last_message)
        
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
        system_prompt="""You are a synthesis specialist. Your job is to:
1. Combine outputs from multiple specialist agents
2. Create a coherent, well-structured final response
3. Ensure all parts of the user's question are addressed
4. Remove redundancy while preserving important information
5. Present the response in a clear, user-friendly format

Do NOT add new information. Only synthesize what has been provided.""",
        tools=[],
        max_tokens=4096,
        temperature=0.5
    )
    
    def __init__(self, config: AgentConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)
    
    def invoke(self, state: Dict[str, Any]) -> str:
        """Synthesize final response from agent outputs."""
        messages = state.get('messages', [])
        research_context = state.get('research_context', '')
        reasoning_output = state.get('reasoning_output', '')
        code_output = state.get('code_output', '')
        
        if not messages:
            return "No context to synthesize."
        
        # Get original question
        first_message = messages[0]
        user_query = first_message.content if hasattr(first_message, 'content') else str(first_message)
        
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
        'supervisor': SupervisorAgent,
        'research': ResearchAgent,
        'reasoning': ReasoningAgent,
        'coding': CodingAgent,
        'synthesis': SynthesisAgent,
    }
    
    agent_class = agents.get(agent_name.lower())
    if agent_class is None:
        raise ValueError(f"Unknown agent: {agent_name}")
    
    return agent_class()
