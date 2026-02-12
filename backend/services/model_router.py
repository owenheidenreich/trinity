"""
Model Router — Two-model task-based routing
=============================================
Routes requests to the appropriate model based on task type:
  - qwen2.5:3b  — fast mode for general chat / quick questions
  - qwen2.5:14b — quality mode for code, debugging, complex reasoning

Usage:
    from services.model_router import select_model
    model = select_model(user_message, task_hints=["code"])
"""

from config import MODEL_NAME, logger

# Default models for two-model setup
FAST_MODEL = "qwen2.5:3b"
QUALITY_MODEL = "qwen2.5:14b"

# Quality mode triggers (use 14B)
QUALITY_KEYWORDS = [
    "code", "debug", "refactor", "implement", "fix bug",
    "analyze", "review", "architect", "design", "algorithm",
    "optimize", "benchmark", "security", "vulnerability",
    "write a function", "write a class", "unit test", "test case",
]

# Fast mode triggers (use 3B)
FAST_KEYWORDS = [
    "explain", "summarize", "translate", "define",
    "what is", "how do i", "quick question", "hello",
    "thanks", "hi", "hey", "yes", "no", "ok",
]

# Context length threshold — long prompts get the quality model
QUALITY_CONTEXT_THRESHOLD = 2000


def select_model(message: str, task_hints: list = None) -> str:
    """
    Route to appropriate model based on task type.

    Args:
        message: The user's message text
        task_hints: Optional list of hints like ['code', 'debug', 'simple']

    Returns:
        Model name string (e.g. 'qwen2.5:14b' or 'qwen2.5:3b')
    """
    # If running a single model (dev/test), always return it
    if MODEL_NAME not in (FAST_MODEL, QUALITY_MODEL, "auto"):
        return MODEL_NAME

    message_lower = message.lower().strip()

    # Check task hints first (explicit overrides)
    if task_hints:
        if any(h in ("code", "debug", "complex", "quality") for h in task_hints):
            logger.debug(f"🔀 Model router: quality (hint)")
            return QUALITY_MODEL
        if any(h in ("chat", "simple", "fast") for h in task_hints):
            logger.debug(f"🔀 Model router: fast (hint)")
            return FAST_MODEL

    # Check quality keywords
    if any(kw in message_lower for kw in QUALITY_KEYWORDS):
        logger.debug(f"🔀 Model router: quality (keyword match)")
        return QUALITY_MODEL

    # Check fast keywords
    if any(kw in message_lower for kw in FAST_KEYWORDS):
        logger.debug(f"🔀 Model router: fast (keyword match)")
        return FAST_MODEL

    # Context length check — long messages get quality model
    if len(message) > QUALITY_CONTEXT_THRESHOLD:
        logger.debug(f"🔀 Model router: quality (long context: {len(message)} chars)")
        return QUALITY_MODEL

    # Default to fast model
    logger.debug(f"🔀 Model router: fast (default)")
    return FAST_MODEL
