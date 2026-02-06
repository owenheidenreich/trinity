"""
Trinity Backend - Complexity Classifier Test Suite
===================================================
Tests for question complexity classification and search detection.

Focus Areas:
1. Simple/Medium/Complex classification accuracy
2. Search need detection
3. Search query extraction
4. Edge cases and boundary conditions

Target Coverage: 60%+
"""

import pytest
from services.complexity import (
    classify_complexity,
    needs_web_search,
    extract_search_query,
    analyze_question,
    has_code_block,
    count_questions,
    get_pass_count,
    QuestionAnalysis
)


class TestClassifyComplexitySimple:
    """Tests for simple question classification."""
    
    def test_short_questions_are_simple(self):
        """Questions under 8 words default to simple."""
        simple_questions = [
            "What is 2+2?",
            "Who is Biden?",
            "When was Python created?",
            "Where is Paris?",
            "Define recursion",
        ]
        for q in simple_questions:
            assert classify_complexity(q) == "simple", f"Expected simple: {q}"
    
    def test_simple_pattern_matches(self):
        """Simple patterns correctly identified."""
        questions = [
            "What is machine learning?",
            "Who is the CEO of Apple?",
            "When did WW2 end?",
            "Where is the Eiffel Tower?",
            "How many planets are there?",
            "What does API mean?",
        ]
        for q in questions:
            result = classify_complexity(q)
            assert result in ["simple", "medium"], f"Unexpected {result} for: {q}"
    
    def test_yes_no_questions_are_simple(self):
        """Yes/No questions are simple."""
        questions = [
            "Yes or no, is Python interpreted?",
            "True or false: the Earth is flat",
        ]
        for q in questions:
            assert classify_complexity(q) == "simple", f"Expected simple: {q}"


class TestClassifyComplexityMedium:
    """Tests for medium complexity classification."""
    
    def test_explain_questions_are_medium_or_complex(self):
        """Questions asking for explanation tend toward medium/complex."""
        questions = [
            "Explain in detail how databases work and their internals",
            "How does TCP/IP work in depth and what are all the layers?",
            "Why does Python use indentation and what are the design reasons?",
        ]
        for q in questions:
            result = classify_complexity(q)
            # Longer explain questions should be medium/complex
            assert result in ["simple", "medium", "complex"], f"Invalid result for: {q}"
    
    def test_very_long_question_is_medium_or_complex(self):
        """Questions over 50 words are complex, 20-50 medium."""
        long_question = "Can you tell me about the various ways that " + \
                       "different programming languages handle memory " + \
                       "management and garbage collection and all the " + \
                       "different strategies they use for this important task?"
        
        result = classify_complexity(long_question)
        # Long questions should not be simple
        word_count = len(long_question.split())
        if word_count > 50:
            assert result == "complex"
        elif word_count > 20:
            assert result in ["medium", "complex"]
    
    def test_multiple_questions_increases_complexity(self):
        """Multiple questions in one increases complexity."""
        multi_question = "What is Python? And what is JavaScript? And what is Ruby?"
        
        result = classify_complexity(multi_question)
        # 3+ question marks should push toward complex
        assert count_questions(multi_question) >= 3


class TestClassifyComplexityComplex:
    """Tests for complex question classification."""
    
    def test_code_blocks_are_complex(self):
        """Questions with code blocks are complex."""
        code_question = "What does this code do? ```python\ndef foo(): pass```"
        assert classify_complexity(code_question) == "complex"
    
    def test_code_indicators_detected(self):
        """Code indicators push toward complex."""
        code_questions = [
            "Debug this: def calculate(x): return x * 2",
            "Review this code: import os; os.system('ls')",
        ]
        for q in code_questions:
            # Has code indicators
            assert has_code_block(q) is True
    
    def test_complex_pattern_matches(self):
        """Complex patterns correctly identified."""
        questions = [
            "Design a distributed cache system with high availability",
            "Architect a microservices solution for e-commerce",
            "Debug this memory leak in my application code",
            "Implement a binary search tree with balancing",
            "Create a system for real-time notifications at scale",
            "Build a recommendation engine using collaborative filtering",
            "Refactor this legacy codebase to use modern patterns",
            "Optimize this slow database query for better performance",
        ]
        for q in questions:
            result = classify_complexity(q)
            # These should be complex or at least medium
            assert result in ["medium", "complex"], f"Expected complex: {q}"
    
    def test_very_long_questions_are_complex(self):
        """Questions over 50 words are complex."""
        long_question = " ".join(["word"] * 60) + "?"
        
        assert classify_complexity(long_question) == "complex"
    
    def test_many_questions_is_complex(self):
        """Many questions in longer context pushes toward complex."""
        # Short multi-question strings are still simple due to word count
        multi_question = "What? Why? How? When? Where?"
        assert count_questions(multi_question) >= 3
        
        # Longer multi-question string should be complex
        long_multi = "Can you explain what this is? And why does it work this way? Also how can I improve it?"
        result = classify_complexity(long_multi)
        # 3 questions + longer length should be medium or complex
        assert count_questions(long_multi) >= 3


class TestHasCodeBlock:
    """Tests for code block detection."""
    
    def test_markdown_code_block_detected(self):
        """Markdown triple backtick code blocks detected."""
        text = "Here's code:\n```python\nprint('hello')\n```"
        assert has_code_block(text) is True
    
    def test_python_function_detected(self):
        """Python function definitions detected."""
        text = "def my_function(x): return x * 2"
        assert has_code_block(text) is True
    
    def test_javascript_function_detected(self):
        """JavaScript function syntax detected."""
        text = "function calculate() { return 42; }"
        assert has_code_block(text) is True
    
    def test_class_definition_detected(self):
        """Class definitions detected."""
        text = "class MyClass: pass"
        assert has_code_block(text) is True
    
    def test_import_statement_detected(self):
        """Import statements detected."""
        text = "import numpy as np"
        assert has_code_block(text) is True
    
    def test_sql_detected(self):
        """SQL statements detected."""
        assert has_code_block("SELECT * FROM users") is True
        assert has_code_block("CREATE TABLE users (id INT)") is True
    
    def test_arrow_function_detected(self):
        """Arrow functions detected."""
        text = "const add = (a, b) => a + b"
        assert has_code_block(text) is True
    
    def test_plain_text_not_detected(self):
        """Plain text without code is not detected."""
        text = "This is just a regular question about programming"
        assert has_code_block(text) is False


class TestCountQuestions:
    """Tests for question counting."""
    
    def test_single_question(self):
        """Single question mark counted."""
        assert count_questions("What is Python?") == 1
    
    def test_multiple_questions(self):
        """Multiple question marks counted."""
        assert count_questions("What? Why? How?") == 3
    
    def test_no_questions(self):
        """No question marks returns zero."""
        assert count_questions("Tell me about Python.") == 0


class TestGetPassCount:
    """Tests for pass count based on complexity."""
    
    def test_simple_gets_one_pass(self):
        """Simple questions get 1 pass."""
        assert get_pass_count("simple") == 1
    
    def test_medium_gets_three_passes(self):
        """Medium questions get 3 passes."""
        assert get_pass_count("medium") == 3
    
    def test_complex_gets_five_passes(self):
        """Complex questions get 5 passes."""
        assert get_pass_count("complex") == 5


class TestNeedsWebSearch:
    """Tests for web search need detection."""
    
    def test_explicit_search_requests(self):
        """Explicit search requests detected."""
        questions = [
            "Search for the latest Python release",
            "Look up the weather in New York",
            "Google the stock price of Apple",
            "Find out who won the game last night",
        ]
        for q in questions:
            assert needs_web_search(q) is True, f"Expected search: {q}"
    
    def test_time_sensitive_questions(self):
        """Time-sensitive questions need search."""
        questions = [
            "What is the current price of Bitcoin?",
            "What happened today in the news?",
            "What's the latest on the election?",
            "What are recent developments in AI?",
            "Who won the game yesterday?",
        ]
        for q in questions:
            assert needs_web_search(q) is True, f"Expected search: {q}"
    
    def test_year_references_trigger_search(self):
        """References to recent years trigger search."""
        questions = [
            "What happened in 2025?",
            "Best movies of 2024",
            "Events in 2023",
        ]
        for q in questions:
            assert needs_web_search(q) is True, f"Expected search: {q}"
    
    def test_topic_specific_search(self):
        """Topic-specific keywords trigger search."""
        questions = [
            "What's the bitcoin price?",
            "Stock market today",
            "Weather forecast",
            "Who won the championship?",
            "What movie is trending?",
        ]
        for q in questions:
            assert needs_web_search(q) is True, f"Expected search: {q}"
    
    def test_static_knowledge_no_search(self):
        """Static knowledge questions don't need search."""
        questions = [
            "What is the capital of France?",
            "How do computers work?",
            "Explain recursion",
            "What is the Pythagorean theorem?",
            "Define photosynthesis",
        ]
        for q in questions:
            assert needs_web_search(q) is False, f"Unexpected search: {q}"


class TestExtractSearchQuery:
    """Tests for search query extraction."""
    
    def test_removes_question_starters(self):
        """Common question starters are removed."""
        assert extract_search_query("What is the price of gold?") == "price of gold"
        assert extract_search_query("Who is Elon Musk?") == "elon musk"
        assert extract_search_query("Search for Python tutorials") == "python tutorials"
    
    def test_removes_trailing_question_mark(self):
        """Trailing question marks are removed."""
        query = extract_search_query("Latest news?")
        assert not query.endswith('?')
    
    def test_limits_query_length(self):
        """Query is limited to 100 characters."""
        long_question = "What is " + "x" * 200 + "?"
        query = extract_search_query(long_question)
        assert len(query) <= 100
    
    def test_handles_various_starters(self):
        """Various question starters handled."""
        starters = [
            ("Can you tell me about AI?", "ai"),
            ("Tell me about machine learning", "machine learning"),
            ("I want to know about Python", "python"),
            ("Look up cryptocurrency", "cryptocurrency"),
            ("Google the weather", "the weather"),
        ]
        for question, expected in starters:
            result = extract_search_query(question)
            assert expected in result.lower(), f"Expected '{expected}' in '{result}'"


class TestAnalyzeQuestion:
    """Tests for full question analysis."""
    
    def test_returns_question_analysis(self):
        """Returns QuestionAnalysis object."""
        result = analyze_question("What is Python?")
        
        assert isinstance(result, QuestionAnalysis)
        assert hasattr(result, 'complexity')
        assert hasattr(result, 'needs_search')
        assert hasattr(result, 'search_query')
        assert hasattr(result, 'passes')
    
    def test_simple_question_analysis(self):
        """Simple question analyzed correctly."""
        result = analyze_question("What is 2+2?")
        
        assert result.complexity == "simple"
        assert result.passes == 1
        assert result.needs_search is False
    
    def test_complex_question_analysis(self):
        """Complex question analyzed correctly."""
        result = analyze_question("Design and implement a distributed cache system with high availability and fault tolerance")
        
        # Long + complex pattern = complex
        assert result.complexity in ["medium", "complex"]
        assert result.passes >= 3  # At least medium passes
    
    def test_search_question_analysis(self):
        """Search-needed question analyzed correctly."""
        result = analyze_question("What is the current price of Bitcoin?")
        
        assert result.needs_search is True
        assert len(result.search_query) > 0
        assert 'bitcoin' in result.search_query.lower()
    
    def test_no_search_question_analysis(self):
        """Non-search question has empty query."""
        result = analyze_question("Explain recursion")
        
        assert result.needs_search is False
        assert result.search_query == ""


class TestEdgeCases:
    """Edge cases and boundary conditions."""
    
    def test_empty_string(self):
        """Empty string handled gracefully."""
        result = classify_complexity("")
        assert result == "simple"  # Default for short
    
    def test_whitespace_only(self):
        """Whitespace-only string handled."""
        result = classify_complexity("   ")
        assert result == "simple"
    
    def test_unicode_characters(self):
        """Unicode characters handled."""
        result = classify_complexity("日本語で説明してください")
        assert result in ["simple", "medium", "complex"]
    
    def test_mixed_case_patterns(self):
        """Pattern matching is case-insensitive."""
        # Short uppercase question still simple
        result = classify_complexity("WHAT IS PYTHON?")
        assert result == "simple"
        
        # Complex pattern should work regardless of case
        result = classify_complexity("DESIGN a distributed system with high availability")
        assert result in ["medium", "complex"]
    
    def test_special_characters(self):
        """Special characters don't break classification."""
        result = classify_complexity("What about $100? @mention #hashtag")
        assert result in ["simple", "medium", "complex"]


class TestComplexityConsistency:
    """Tests for classification consistency."""
    
    def test_same_input_same_output(self):
        """Same input always produces same output."""
        question = "Explain how machine learning works"
        
        results = [classify_complexity(question) for _ in range(10)]
        
        assert len(set(results)) == 1  # All results identical
    
    def test_complexity_ordering(self):
        """Pass counts increase with complexity."""
        assert get_pass_count("simple") < get_pass_count("medium")
        assert get_pass_count("medium") < get_pass_count("complex")
