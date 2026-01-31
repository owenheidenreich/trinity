"""
Trinity Agentic Pipeline - Complexity Classifier & Tool Detection

Determines:
1. How many passes a question needs (simple/medium/complex)
2. What tools are needed (web search, etc.)
"""

import re
from typing import Literal, List, NamedTuple
from dataclasses import dataclass

ComplexityLevel = Literal["simple", "medium", "complex"]


@dataclass
class QuestionAnalysis:
    """Result of analyzing a question"""
    complexity: ComplexityLevel
    needs_search: bool
    search_query: str  # Extracted search query if needs_search
    passes: int


# Pattern lists for classification
SIMPLE_PATTERNS = [
    r'\bwhat is\b',
    r'\bwho is\b', 
    r'\bwhen did\b',
    r'\bwhere is\b',
    r'\bhow many\b',
    r'\bdefine\b',
    r'\bwhat does .+ mean\b',
    r'\byes or no\b',
    r'\btrue or false\b',
]

# Patterns that indicate web search is needed
SEARCH_PATTERNS = [
    r'\bcurrent\b',
    r'\btoday\b',
    r'\blatest\b',
    r'\brecent\b',
    r'\bnews\b',
    r'\b20[2-3][0-9]\b',  # Years 2020-2039
    r'\bprice of\b',
    r'\bstock\b',
    r'\bweather\b',
    r'\bwho won\b',
    r'\bwhat happened\b',
    r'\btrending\b',
    r'\bupdate\b',
    r'\bannounced\b',
    r'\breleased\b',
    r'\blaunched\b',
]

# Topics that typically need current info
SEARCH_TOPICS = [
    'bitcoin', 'crypto', 'ethereum', 'stock market', 'nasdaq', 'dow jones',
    'election', 'president', 'prime minister', 'ceo of',
    'score', 'game', 'match', 'championship',
    'movie', 'album', 'release date',
]

COMPLEX_PATTERNS = [
    r'\bdesign\b',
    r'\barchitect\b',
    r'\bdebug\b',
    r'\bimplement\b',
    r'\bcreate a system\b',
    r'\bbuild a\b',
    r'\bcompare and contrast\b',
    r'\banalyze why\b',
    r'\bexplain in detail\b',
    r'\bwrite a .+ that\b',
    r'\brefactor\b',
    r'\boptimize\b',
    r'\btroubleshoot\b',
    r'\breview this code\b',
]

MEDIUM_PATTERNS = [
    r'\bexplain\b',
    r'\bhow does\b',
    r'\bwhy does\b',
    r'\bwhat are the\b',
    r'\bdescribe\b',
    r'\bsummarize\b',
    r'\blist\b',
]


def has_code_block(text: str) -> bool:
    """Check if text contains code blocks or code-like content"""
    indicators = [
        '```',           # Markdown code block
        'def ',          # Python function
        'function ',     # JavaScript function
        'class ',        # Class definition
        'import ',       # Import statement
        'const ',        # JavaScript const
        'let ',          # JavaScript let
        'var ',          # JavaScript var
        '() =>',         # Arrow function
        '() {',          # Function body
        'SELECT ',       # SQL
        'CREATE TABLE',  # SQL
    ]
    return any(indicator in text for indicator in indicators)


def count_questions(text: str) -> int:
    """Count number of question marks (multiple questions = more complex)"""
    return text.count('?')


def classify_complexity(question: str) -> ComplexityLevel:
    """
    Classify question complexity to determine pipeline depth.
    
    Args:
        question: The user's question/prompt
        
    Returns:
        "simple", "medium", or "complex"
    """
    question_lower = question.lower()
    word_count = len(question.split())
    
    # === SIMPLE INDICATORS ===
    
    # Very short questions are usually simple
    if word_count < 8:
        # Unless they contain complex patterns
        for pattern in COMPLEX_PATTERNS:
            if re.search(pattern, question_lower):
                return "medium"
        return "simple"
    
    # Simple pattern match with short length
    for pattern in SIMPLE_PATTERNS:
        if re.search(pattern, question_lower) and word_count < 15:
            return "simple"
    
    # === COMPLEX INDICATORS ===
    
    # Code blocks always complex
    if has_code_block(question):
        return "complex"
    
    # Complex pattern match
    for pattern in COMPLEX_PATTERNS:
        if re.search(pattern, question_lower):
            return "complex"
    
    # Very long questions are complex
    if word_count > 50:
        return "complex"
    
    # Multiple questions in one
    if count_questions(question) >= 3:
        return "complex"
    
    # === MEDIUM INDICATORS ===
    
    # Medium pattern match
    for pattern in MEDIUM_PATTERNS:
        if re.search(pattern, question_lower):
            return "medium"
    
    # Moderate length without other indicators
    if word_count > 20:
        return "medium"
    
    # Multiple questions but not many
    if count_questions(question) >= 2:
        return "medium"
    
    # Default to simple for efficiency
    return "simple"


def get_pass_count(complexity: ComplexityLevel) -> int:
    """Get number of passes for a complexity level"""
    return {
        "simple": 1,
        "medium": 3,  # understand → execute → critique
        "complex": 5  # understand → plan → execute → critique → refine
    }[complexity]


def needs_web_search(question: str) -> bool:
    """
    Determine if question requires current/real-time information.
    
    Args:
        question: The user's question/prompt
        
    Returns:
        True if web search would help answer the question
    """
    question_lower = question.lower()
    
    # Check search trigger patterns
    for pattern in SEARCH_PATTERNS:
        if re.search(pattern, question_lower):
            return True
    
    # Check search topics
    for topic in SEARCH_TOPICS:
        if topic in question_lower:
            return True
    
    return False


def extract_search_query(question: str) -> str:
    """
    Extract a good search query from the question.
    Removes filler words and focuses on key terms.
    """
    # Remove common question starters
    query = question.lower()
    starters = [
        "what is the ", "what's the ", "who is ", "who's ",
        "can you tell me ", "tell me about ", "what do you know about ",
        "search for ", "look up ", "find ", "google ",
        "i want to know ", "i need to know ",
    ]
    for starter in starters:
        if query.startswith(starter):
            query = query[len(starter):]
            break
    
    # Remove trailing question marks
    query = query.rstrip('?').strip()
    
    # Limit length for search API
    if len(query) > 100:
        query = query[:100]
    
    return query


def analyze_question(question: str) -> QuestionAnalysis:
    """
    Full analysis of a question for the agentic pipeline.
    
    Args:
        question: The user's question/prompt
        
    Returns:
        QuestionAnalysis with complexity, search needs, and pass count
    """
    complexity = classify_complexity(question)
    search_needed = needs_web_search(question)
    search_query = extract_search_query(question) if search_needed else ""
    passes = get_pass_count(complexity)
    
    return QuestionAnalysis(
        complexity=complexity,
        needs_search=search_needed,
        search_query=search_query,
        passes=passes
    )


# === TESTING ===

if __name__ == "__main__":
    print("=" * 70)
    print("Complexity Classifier Tests:")
    print("-" * 70)
    
    complexity_tests = [
        ("What is 2+2?", "simple"),
        ("Who is the president of France?", "simple"),
        ("Explain how neural networks learn", "medium"),
        ("What are the benefits of using TypeScript?", "medium"),
        ("Design a database schema for a social media app with 1M users", "complex"),
        ("Debug this code:\n```python\ndef foo():\n    return bar\n```", "complex"),
        ("Compare and contrast REST and GraphQL APIs, considering performance, developer experience, and use cases", "complex"),
    ]
    
    all_passed = True
    for question, expected in complexity_tests:
        result = classify_complexity(question)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_passed = False
        print(f"{status} Expected: {expected:8s} Got: {result:8s} | {question[:50]}...")
    
    print("-" * 70)
    print("Search Detection Tests:")
    print("-" * 70)
    
    search_tests = [
        ("What is the current price of Bitcoin?", True, "current price of bitcoin"),
        ("What's the weather like today?", True, "weather like today"),
        ("Who won the 2024 election?", True, "2024 election"),
        ("What is photosynthesis?", False, ""),
        ("Explain how recursion works", False, ""),
        ("What is the latest news about AI?", True, "latest news about ai"),
        ("Tell me about Ethereum", True, "ethereum"),
    ]
    
    for question, expected_search, _ in search_tests:
        result = needs_web_search(question)
        status = "✅" if result == expected_search else "❌"
        if result != expected_search:
            all_passed = False
        search_str = "SEARCH" if result else "NO SEARCH"
        expected_str = "SEARCH" if expected_search else "NO SEARCH"
        print(f"{status} Expected: {expected_str:10s} Got: {search_str:10s} | {question[:45]}...")
    
    print("-" * 70)
    print("Full Analysis Test:")
    print("-" * 70)
    
    analysis = analyze_question("What is the current price of Bitcoin?")
    print(f"Question: What is the current price of Bitcoin?")
    print(f"  Complexity: {analysis.complexity}")
    print(f"  Passes: {analysis.passes}")
    print(f"  Needs Search: {analysis.needs_search}")
    print(f"  Search Query: '{analysis.search_query}'")
    
    print("=" * 70)
    print("All tests passed!" if all_passed else "Some tests failed!")
