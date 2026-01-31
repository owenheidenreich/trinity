"""
Trinity Backend - Prompt Templates Service
System prompts and prompt construction for AI inference
"""

import re
from typing import Dict
import logging
from config import MODEL_NAME

logger = logging.getLogger(__name__)


# ===== SYSTEM PROMPTS =====

TRINITY_SYSTEM_PROMPT = """You are Trinity, a decentralized AI assistant running on community-owned infrastructure. 
Your responses are generated on a GPU rented from the Akash Network, a decentralized compute marketplace.
Your interface runs on the Internet Computer (ICP), a decentralized blockchain network.
Your chat history is encrypted and stored on IPFS with permanent storage via Lighthouse.

Key traits:
- You are helpful, accurate, and thoughtful
- You acknowledge uncertainty when you don't know something
- You value privacy and decentralization
- You keep responses concise but complete
- You explain complex topics clearly

Formatting guidelines:
- Use Markdown for text formatting (headers, bold, lists, code blocks)
- For mathematical expressions, ALWAYS use LaTeX with dollar sign delimiters:
  - Inline math: $expression$ (e.g., $E = mc^2$, $\\mathbf{p}$, $x^2 + y^2 = r^2$)
  - Block math: $$expression$$ on its own line for equations
  - NEVER write math variables in plain parentheses like (x) - always use $x$
  - NEVER write LaTeX commands without delimiters - wrong: \\mathbf{p}, right: $\\mathbf{p}$
- Use proper code blocks with language tags for code

When asked about yourself, explain your decentralized nature. When asked technical questions about your infrastructure, you can mention ICP, Akash, and IPFS, but do not reveal API keys, wallet addresses, or internal configuration."""

# Deep thinking prompt - used when user explicitly requests /think
REASONING_SYSTEM_PROMPT = """You are Trinity in DEEP REASONING mode. The user has explicitly requested careful, thorough analysis.

YOU MUST FOLLOW THIS EXACT FORMAT:

<thinking>
This section is REQUIRED and should be EXTENSIVE (at least 200 words).
- What exactly is being asked? Restate the question in your own words.
- What knowledge domains does this touch?
- What are the key components or sub-questions?
- What assumptions am I making?
- What are multiple possible approaches?
- What are the tradeoffs between approaches?
- What could go wrong with each approach?
- What edge cases should I consider?
- Let me think through this step by step...
</thinking>

<plan>
Based on my analysis above, here is my approach:
1. [First concrete step]
2. [Second step]
3. [Third step]
...
</plan>

<answer>
[Your complete, well-reasoned response based on the thinking above]
</answer>

CRITICAL RULES:
1. The <thinking> section MUST be thorough and exploratory - at least 200 words
2. Think out loud, consider alternatives, note uncertainties
3. DO NOT skip the thinking section - it is the whole point of /think mode
4. Take your time - longer thinking produces better answers
5. Show your reasoning process, not just conclusions"""


# ===== HELPER FUNCTIONS =====

def is_small_model() -> bool:
    """Small models (TinyLlama, etc.) can't handle complex chat formatting"""
    small_models = ['tinyllama', 'phi', 'gemma:2b', 'stablelm']
    model_lower = MODEL_NAME.lower()
    return any(s in model_lower for s in small_models)


def build_prompt_with_context(user_prompt: str, context_messages: list, user_memory: Dict = None) -> str:
    """
    Build a prompt that includes Trinity identity, conversation context, and user memory.
    
    For SMALL models (TinyLlama, etc.): Just send the user prompt, no formatting.
    For LARGE models (8B+): Use full chat format with roles.
    
    Args:
        user_prompt: The current user message
        context_messages: Array of recent messages [{ role: 'user'|'assistant'|'system', content: '...' }]
        user_memory: Optional dict with user's persistent memory (facts, preferences)
    
    Returns:
        Full prompt string with context
    """
    # SMALL MODEL PATH: Skip all formatting, just send the question
    # TinyLlama gets confused by [System], User:, Assistant: markers
    if is_small_model():
        logger.info("🔧 Using simple prompt format for small model")
        return user_prompt
    
    # LARGE MODEL PATH: Full chat format (8B+ models handle this correctly)
    conversation_parts = []
    
    # System prompt
    conversation_parts.append(f"[System]\n{TRINITY_SYSTEM_PROMPT}\n")
    
    # Add user memory facts if available (persistent across all chats)
    if user_memory and user_memory.get('facts'):
        facts = user_memory['facts']
        if len(facts) > 0:
            facts_text = "\n".join([f"- {fact['fact']}" for fact in facts[-10:]])  # Last 10 facts
            conversation_parts.append(f"[User Background - Remember these facts]\n{facts_text}\n")
    
    # No context messages case
    if not context_messages or len(context_messages) == 0:
        conversation_parts.append(f"\nUser: {user_prompt}")
        conversation_parts.append(f"\nAssistant:")
        return "\n".join(conversation_parts)
    
    # Build conversation history from context messages
    for msg in context_messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        
        if role == 'system':
            conversation_parts.append(f"[Context Summary]\n{content}\n")
        elif role == 'user':
            conversation_parts.append(f"User: {content}")
        elif role == 'assistant':
            conversation_parts.append(f"Assistant: {content}")
    
    conversation_parts.append(f"\nCurrent user message: {user_prompt}")
    conversation_parts.append(f"\nAssistant:")
    
    return "\n".join(conversation_parts)


def build_reasoning_prompt(user_prompt: str, context_messages: list, user_memory: Dict = None) -> str:
    """
    Build a prompt that REQUIRES structured deep reasoning.
    Uses <thinking>, <plan>, <answer> tags for parseable output.
    The thinking section must be extensive for this to work properly.
    """
    parts = []
    
    # System prompt for reasoning mode - very explicit instructions
    parts.append(f"[System]\n{REASONING_SYSTEM_PROMPT}\n")
    
    # Add user memory facts if available
    if user_memory and user_memory.get('facts'):
        facts = user_memory['facts']
        if len(facts) > 0:
            facts_text = "\n".join([f"- {fact['fact']}" for fact in facts[-10:]])
            parts.append(f"[User Background]\n{facts_text}\n")
    
    # Add conversation context
    if context_messages:
        for msg in context_messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if role == 'user':
                parts.append(f"User: {content}")
            elif role == 'assistant':
                parts.append(f"Assistant: {content}")
            elif role == 'system':
                parts.append(f"[Context]\n{content}")
    
    # Current question with STRONG reasoning instruction
    parts.append(f"\nUser: {user_prompt}")
    parts.append("\nAssistant: I'll think through this carefully and thoroughly.\n\n<thinking>")
    
    return "\n".join(parts)


def parse_reasoning_response(response_text: str) -> Dict:
    """
    Parse structured reasoning response into components.
    Returns dict with 'thinking', 'plan', 'answer', and 'raw' fields.
    """
    result = {
        'raw': response_text,
        'thinking': None,
        'plan': None,
        'answer': None
    }
    
    # Extract <thinking>...</thinking>
    thinking_match = re.search(r'<thinking>(.*?)</thinking>', response_text, re.DOTALL)
    if thinking_match:
        result['thinking'] = thinking_match.group(1).strip()
    
    # Extract <plan>...</plan>
    plan_match = re.search(r'<plan>(.*?)</plan>', response_text, re.DOTALL)
    if plan_match:
        result['plan'] = plan_match.group(1).strip()
    
    # Extract <answer>...</answer>
    answer_match = re.search(r'<answer>(.*?)</answer>', response_text, re.DOTALL)
    if answer_match:
        result['answer'] = answer_match.group(1).strip()
    else:
        # If no answer tags, use the whole response after removing thinking/plan
        clean_response = response_text
        clean_response = re.sub(r'<thinking>.*?</thinking>', '', clean_response, flags=re.DOTALL)
        clean_response = re.sub(r'<plan>.*?</plan>', '', clean_response, flags=re.DOTALL)
        result['answer'] = clean_response.strip()
    
    return result
