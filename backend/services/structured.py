"""
Trinity Backend - Structured Output Service
Guarantees valid JSON output from LLM using Outlines
"""

import json
import logging
from typing import Dict, Optional

from config import MODEL_NAME, LLAMA_SERVER_CHAT_PORT

logger = logging.getLogger(__name__)

# Lazy-load Outlines
_outlines_available = None


def check_outlines_available() -> bool:
    """Check if Outlines library is available."""
    global _outlines_available

    if _outlines_available is None:
        try:
            import outlines  # noqa: F401

            _outlines_available = True
            logger.info("✅ Outlines library available for structured output")
        except ImportError:
            _outlines_available = False
            logger.warning("⚠️ Outlines not installed, structured output unavailable")

    return _outlines_available


# Pre-defined schemas for common use cases
SCHEMAS = {
    "understanding": {
        "type": "object",
        "properties": {
            "question_type": {
                "type": "string",
                "enum": [
                    "factual",
                    "analytical",
                    "creative",
                    "code",
                    "design",
                    "debug",
                    "explanation",
                ],
            },
            "complexity": {"type": "integer", "minimum": 1, "maximum": 10},
            "domains": {"type": "array", "items": {"type": "string"}},
            "tools_needed": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "calculator",
                        "web_search",
                        "document_search",
                        "code_display",
                        "fact_check",
                    ],
                },
            },
            "key_concepts": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["question_type", "complexity"],
    },
    "plan": {
        "type": "object",
        "properties": {
            "goal": {"type": "string"},
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "step_number": {"type": "integer"},
                        "action": {"type": "string"},
                        "tool": {"type": "string"},
                    },
                    "required": ["step_number", "action"],
                },
            },
            "estimated_complexity": {"type": "string", "enum": ["simple", "medium", "complex"]},
        },
        "required": ["goal", "steps"],
    },
    "critique": {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 10},
            "strengths": {"type": "array", "items": {"type": "string"}},
            "weaknesses": {"type": "array", "items": {"type": "string"}},
            "suggestions": {"type": "array", "items": {"type": "string"}},
            "needs_refinement": {"type": "boolean"},
        },
        "required": ["score", "weaknesses", "needs_refinement"],
    },
    "tool_call": {
        "type": "object",
        "properties": {
            "tool": {
                "type": "string",
                "enum": [
                    "calculator",
                    "web_search",
                    "document_search",
                    "code_display",
                    "fact_check",
                ],
            },
            "parameters": {"type": "object"},
            "reasoning": {"type": "string"},
        },
        "required": ["tool", "parameters"],
    },
}


def generate_structured(prompt: str, schema: Dict, model_name: str = None) -> Optional[Dict]:
    """
    Generate structured JSON output from LLM.

    Uses Outlines to constrain the model's output to valid JSON
    matching the provided schema.

    Args:
        prompt: The prompt to send to the LLM
        schema: JSON Schema defining the expected output structure
        model_name: Model to use (defaults to configured MODEL_NAME)

    Returns:
        Parsed JSON dict, or None on failure
    """
    if not check_outlines_available():
        logger.warning("Outlines not available, falling back to unstructured")
        return None

    try:
        from outlines import generate, models

        model_name = model_name or MODEL_NAME

        # Connect to the LLM via OpenAI-compatible API (llama-server)
        base_url = f"http://localhost:{LLAMA_SERVER_CHAT_PORT}/v1"
        api_key = "no-key"

        model = models.openai(
            model_name,
            base_url=base_url,
            api_key=api_key,
        )

        # Create JSON generator with schema
        generator = generate.json(model, schema)

        # Generate
        result = generator(prompt)

        logger.info(f"Structured output generated successfully")
        return result

    except Exception as e:
        logger.error(f"Structured generation failed: {e}")
        return None


def generate_with_schema(prompt: str, schema_name: str, model_name: str = None) -> Optional[Dict]:
    """
    Generate structured output using a pre-defined schema.

    Args:
        prompt: The prompt
        schema_name: Name of pre-defined schema ('understanding', 'plan', 'critique', 'tool_call')
        model_name: Model to use

    Returns:
        Parsed JSON dict, or None on failure
    """
    if schema_name not in SCHEMAS:
        logger.error(f"Unknown schema: {schema_name}")
        return None

    return generate_structured(prompt, SCHEMAS[schema_name], model_name)


def validate_json_output(text: str, schema: Dict) -> Optional[Dict]:
    """
    Try to parse and validate JSON from text.

    Useful as a fallback when structured generation isn't available.

    Args:
        text: Text that might contain JSON
        schema: Schema to validate against

    Returns:
        Validated dict, or None if invalid
    """
    try:
        # Try to find JSON in the text
        import re

        # Look for JSON object
        json_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if not json_match:
            return None

        json_str = json_match.group()
        data = json.loads(json_str)

        # Basic schema validation (just check required fields)
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                logger.warning(f"Missing required field: {field}")
                return None

        return data

    except json.JSONDecodeError:
        return None
    except Exception as e:
        logger.error(f"JSON validation error: {e}")
        return None


def safe_structured_generate(prompt: str, schema: Dict, fallback_parser=None) -> Optional[Dict]:
    """
    Attempt structured generation with fallback to parsing.

    Args:
        prompt: The prompt
        schema: JSON schema
        fallback_parser: Optional function to parse unstructured output

    Returns:
        Dict result or None
    """
    # Try structured generation first
    result = generate_structured(prompt, schema)
    if result:
        return result

    # Fallback: generate unstructured and try to parse
    logger.info("Falling back to unstructured generation with parsing")

    try:
        from .provider_factory import get_provider

        provider = get_provider()
        text = provider.generate(
            prompt=prompt + "\n\nRespond with valid JSON only.",
            max_tokens=500,
            temperature=0.3,
            timeout=60,
        )

        if text:
            # Try to validate
            result = validate_json_output(text, schema)
            if result:
                return result

            # Try custom fallback parser
            if fallback_parser:
                return fallback_parser(text)

    except Exception as e:
        logger.error(f"Fallback generation failed: {e}")

    return None


# Module availability flag for graceful degradation
V4_STRUCTURED_AVAILABLE = True
