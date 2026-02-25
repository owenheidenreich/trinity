#!/usr/bin/env python3
"""Quick check of current classifier predictions on failing test prompts."""
from services.tiny_classifier import detect_tools, _softmax, _get_tool_model, TOOL_CLASSES
import numpy as np

model = _get_tool_model()

test_prompts = [
    ("basic_001", "What is 2 + 2?"),
    ("tool_001", "What is 847 * 293? Use your calculator tool."),
    ("tool_002", "Search the web for today's Bitcoin price."),
    ("tool_003", "Remember that my favorite programming language is Rust."),
    ("tool_004", "What do you know about me? Check your memory."),
    ("ctx_003", "What is my favorite color?"),
    ("ctx_004", "What do I do for work?"),
    ("neg_chat", "How are you doing today?"),
    ("neg_fact", "What is photosynthesis?"),
    ("calc_nat", "What is fifteen percent of two hundred?"),
]

for tid, prompt in test_prompts:
    logits = model.forward(prompt)
    probs = _softmax(logits)
    top3_idx = np.argsort(probs)[-3:][::-1]
    tools = detect_tools(prompt)
    print(f"{tid}: detected={tools}")
    for i in top3_idx:
        print(f"  {TOOL_CLASSES[i]:20s} {probs[i]:.4f}")
    print()
