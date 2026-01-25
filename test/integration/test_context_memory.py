#!/usr/bin/env python3
"""
Test Suite: Context Memory Module
Tests the context memory functionality
"""

import sys

def build_prompt_with_context(user_prompt: str, context_messages: list) -> str:
    """
    Build a prompt that includes conversation context for the LLM.
    (Copied from inference_server.py for standalone testing)
    """
    if not context_messages or len(context_messages) == 0:
        return user_prompt
    
    conversation_parts = []
    conversation_parts.append("Previous conversation:")
    
    for msg in context_messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        if role == 'user':
            conversation_parts.append(f"User: {content}")
        elif role == 'assistant':
            conversation_parts.append(f"Assistant: {content}")
    
    conversation_parts.append(f"\nCurrent user message: {user_prompt}")
    conversation_parts.append("\nAssistant:")
    
    return "\n".join(conversation_parts)

def test_empty_context():
    """Test with no context messages"""
    user_prompt = "Hello Trinity!"
    context = []
    result = build_prompt_with_context(user_prompt, context)
    assert result == "Hello Trinity!", f"Expected just the prompt, got: {result}"
    print("✅ Test 1 passed: Empty context returns just the prompt")

def test_single_exchange():
    """Test with one previous exchange"""
    user_prompt = "Can you explain that more?"
    context = [
        {"role": "user", "content": "What is recursion?"},
        {"role": "assistant", "content": "Recursion is when a function calls itself."}
    ]
    result = build_prompt_with_context(user_prompt, context)
    
    assert "Previous conversation:" in result
    assert "User: What is recursion?" in result
    assert "Assistant: Recursion is when a function calls itself." in result
    assert "Current user message: Can you explain that more?" in result
    print("✅ Test 2 passed: Single exchange formatted correctly")
    print(f"Generated prompt:\n{result}\n")

def test_multiple_exchanges():
    """Test with multiple exchanges (6 messages = 3 exchanges)"""
    user_prompt = "Show me code"
    context = [
        {"role": "user", "content": "What is recursion?"},
        {"role": "assistant", "content": "Recursion is when a function calls itself."},
        {"role": "user", "content": "Can you give an example?"},
        {"role": "assistant", "content": "Sure! Fibonacci is a classic example."},
        {"role": "user", "content": "How does the base case work?"},
        {"role": "assistant", "content": "The base case prevents infinite recursion."}
    ]
    result = build_prompt_with_context(user_prompt, context)
    
    # Verify all messages are included (Note: "Assistant:" appears in context AND at the end)
    user_count = result.count("User:")
    # Count only the assistant messages from context (not the final "Assistant:" prompt)
    assistant_in_context = sum(1 for msg in context if msg['role'] == 'assistant')
    
    assert user_count == 3, f"Expected 3 user messages, got {user_count}"
    assert "Show me code" in result
    assert "What is recursion?" in result
    assert "base case prevents infinite recursion" in result
    print("✅ Test 3 passed: Multiple exchanges formatted correctly")
    print(f"Context includes {len(context)} messages\n")

def test_context_ordering():
    """Test that messages appear in correct chronological order"""
    user_prompt = "Continue"
    context = [
        {"role": "user", "content": "First message"},
        {"role": "assistant", "content": "Second message"},
        {"role": "user", "content": "Third message"},
        {"role": "assistant", "content": "Fourth message"}
    ]
    result = build_prompt_with_context(user_prompt, context)
    
    # Find positions
    first_pos = result.find("First message")
    second_pos = result.find("Second message")
    third_pos = result.find("Third message")
    fourth_pos = result.find("Fourth message")
    current_pos = result.find("Continue")
    
    assert first_pos < second_pos < third_pos < fourth_pos < current_pos
    print("✅ Test 4 passed: Messages are in chronological order")

def test_special_characters():
    """Test with special characters and code blocks"""
    user_prompt = "Explain this code"
    context = [
        {"role": "user", "content": "What is Python?"},
        {"role": "assistant", "content": "Python is a language.\n\nExample:\n```python\nprint('hello')\n```"}
    ]
    result = build_prompt_with_context(user_prompt, context)
    
    assert "```python" in result
    assert "print('hello')" in result
    print("✅ Test 5 passed: Special characters and code blocks preserved")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("Context Memory Module Tests")
    print("="*60 + "\n")
    
    try:
        test_empty_context()
        test_single_exchange()
        test_multiple_exchanges()
        test_context_ordering()
        test_special_characters()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED (5/5)")
        print("="*60 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        sys.exit(1)
