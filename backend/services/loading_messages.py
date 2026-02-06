"""
Trinity Agentic Pipeline - Whimsical Loading Messages

Generates fun, rotating "verb+ing the noun" style loading messages
to keep users entertained during deep thinking.
"""

import random
from typing import Dict, List

# ============================================================================
# WHIMSICAL LOADING PHRASES
# ============================================================================

# Format: { "phase": [(verb_present, noun), ...] }
# These create messages like "Pondering the question..." or "Brewing the answer..."

LOADING_PHRASES = {
    "classifying": [
        ("Examining", "question"),
        ("Pondering", "complexity"),
        ("Measuring", "depths"),
        ("Sensing", "nuances"),
        ("Calibrating", "response"),
    ],
    "searching": [
        ("Scouring", "web"),
        ("Exploring", "internet"),
        ("Hunting", "sources"),
        ("Mining", "data"),
        ("Consulting", "oracles"),
        ("Diving into", "archives"),
        ("Querying", "databases"),
        ("Surfing", "information waves"),
    ],
    "understanding": [
        ("Pondering", "question"),
        ("Untangling", "meaning"),
        ("Deciphering", "intent"),
        ("Absorbing", "context"),
        ("Contemplating", "puzzle"),
        ("Grasping", "essence"),
        ("Meditating on", "problem"),
        ("Processing", "inquiry"),
    ],
    "planning": [
        ("Drafting", "blueprint"),
        ("Mapping", "approach"),
        ("Charting", "course"),
        ("Sketching", "strategy"),
        ("Weaving", "plan"),
        ("Plotting", "solution"),
        ("Architecting", "response"),
        ("Orchestrating", "thoughts"),
    ],
    "executing": [
        ("Brewing", "answer"),
        ("Crafting", "response"),
        ("Forging", "solution"),
        ("Weaving", "words"),
        ("Painting", "picture"),
        ("Composing", "symphony"),
        ("Building", "masterpiece"),
        ("Assembling", "thoughts"),
        ("Writing", "story"),
        ("Creating", "magic"),
    ],
    "critiquing": [
        ("Polishing", "prose"),
        ("Inspecting", "work"),
        ("Reviewing", "craftsmanship"),
        ("Examining", "details"),
        ("Questioning", "assumptions"),
        ("Testing", "logic"),
        ("Scrutinizing", "reasoning"),
        ("Evaluating", "quality"),
    ],
    "refining": [
        ("Perfecting", "response"),
        ("Enhancing", "answer"),
        ("Elevating", "prose"),
        ("Sharpening", "edge"),
        ("Polishing", "gem"),
        ("Refining", "gold"),
        ("Buffing", "brilliance"),
        ("Distilling", "essence"),
    ],
}

# Default fallback phrases
DEFAULT_PHRASES = [
    ("Processing", "request"),
    ("Working on", "task"),
    ("Thinking about", "problem"),
    ("Considering", "options"),
    ("Computing", "solution"),
]


def get_loading_message(phase: str, index: int = None) -> str:
    """
    Get a whimsical loading message for a given phase.

    Args:
        phase: The current pipeline phase (understanding, planning, etc.)
        index: Optional specific index for consistent sequences

    Returns:
        A message like "Pondering the question..."
    """
    phrases = LOADING_PHRASES.get(phase, DEFAULT_PHRASES)

    if index is not None:
        phrase = phrases[index % len(phrases)]
    else:
        phrase = random.choice(phrases)

    verb, noun = phrase
    return f"{verb} the {noun}..."


def get_loading_sequence(phase: str, count: int = 5) -> List[str]:
    """
    Get a sequence of loading messages for a phase.
    Useful for long operations where messages should rotate.

    Args:
        phase: The pipeline phase
        count: Number of messages to generate

    Returns:
        List of unique loading messages
    """
    phrases = LOADING_PHRASES.get(phase, DEFAULT_PHRASES)

    # Shuffle and take up to count (or repeat if needed)
    shuffled = list(phrases)
    random.shuffle(shuffled)

    messages = []
    for i in range(count):
        verb, noun = shuffled[i % len(shuffled)]
        messages.append(f"{verb} the {noun}...")

    return messages


def format_phase_update(phase: str, message: str = None) -> Dict:
    """
    Format a phase update for SSE streaming.

    Args:
        phase: The current phase name
        message: Optional custom message, or auto-generate whimsical one

    Returns:
        Dict ready for SSE: {"phase": "...", "message": "..."}
    """
    if message is None:
        message = get_loading_message(phase)

    return {"phase": phase, "message": message}


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Whimsical Loading Messages Test")
    print("=" * 60)

    phases = [
        "classifying",
        "searching",
        "understanding",
        "planning",
        "executing",
        "critiquing",
        "refining",
    ]

    for phase in phases:
        print(f"\n{phase.upper()}:")
        for msg in get_loading_sequence(phase, 3):
            print(f"  • {msg}")

    print("\n" + "=" * 60)
    print("Random sampling (10 messages):")
    print("=" * 60)

    for _ in range(10):
        phase = random.choice(phases)
        msg = get_loading_message(phase)
        print(f"  [{phase:12}] {msg}")
