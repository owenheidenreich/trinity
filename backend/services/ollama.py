"""
Trinity Backend - Ollama Service
LLM inference via Ollama API

Phase 5: Integrated with TokenTracker for cost optimization.
"""

import requests
import logging
from typing import Dict, Optional, Generator, Tuple
from config import OLLAMA_HOST, MODEL_NAME

logger = logging.getLogger(__name__)

# Lazy-load token tracker to avoid circular imports
_token_tracker = None


def _get_token_tracker():
    """Lazy-load the token tracker."""
    global _token_tracker
    if _token_tracker is None:
        try:
            from services.caching import get_token_tracker
            _token_tracker = get_token_tracker()
        except ImportError:
            logger.warning("Caching module not available - tokens will not be tracked")
    return _token_tracker


def check_ollama_connection() -> bool:
    """Check if Ollama is running and accessible"""
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            return any(m['name'].startswith(MODEL_NAME) for m in models)
        return False
    except Exception as e:
        logger.error(f"Ollama connection check failed: {e}")
        return False


def warmup_model() -> bool:
    """
    Warm up the model by making a test request.
    This pre-loads the model into memory so the first user request doesn't have to wait.
    """
    logger.info(f"🔥 Warming up model: {MODEL_NAME} - this may take a few minutes on first run...")
    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": "Hello, this is a warmup request.",
                "stream": False,
                "options": {
                    "num_predict": 10,  # Only generate a few tokens
                    "temperature": 0.7,
                }
            },
            timeout=300  # 5 minute timeout for model download
        )
        
        if response.status_code == 200:
            logger.info(f"✓ Model warmed up successfully! Ready to serve requests.")
            return True
        else:
            logger.warning(f"⚠ Warmup request failed with status {response.status_code}")
            return False
            
    except requests.Timeout:
        logger.error("❌ Model warmup timed out - model may still be downloading")
        logger.error("   First user request may be slow while model finishes loading")
        return False
    except Exception as e:
        logger.error(f"❌ Model warmup failed: {e}")
        return False


def call_ollama(
    prompt: str,
    max_tokens: int = 500,
    temperature: float = 0.7,
    stream: bool = False,
    user_id: Optional[str] = None
) -> Dict:
    """
    Call Ollama API for text generation.
    
    Args:
        prompt: The formatted prompt to send
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature (0.1-2.0)
        stream: Whether to stream the response
        user_id: Optional user ID for token tracking
        
    Returns:
        Dict with 'response' key containing generated text,
        plus token usage info when available
    """
    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": stream,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature,
                }
            },
            timeout=120  # 2 minute timeout
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # Extract token usage from Ollama response
            prompt_tokens = result.get('prompt_eval_count', 0)
            completion_tokens = result.get('eval_count', 0)
            
            # Track tokens if available
            if prompt_tokens > 0 or completion_tokens > 0:
                tracker = _get_token_tracker()
                if tracker:
                    usage = tracker.record(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        model=MODEL_NAME,
                        user_id=user_id
                    )
                    # Add token info to result
                    result['token_usage'] = {
                        'prompt_tokens': prompt_tokens,
                        'completion_tokens': completion_tokens,
                        'total_tokens': prompt_tokens + completion_tokens,
                        'estimated_cost_usd': usage.estimated_cost_usd
                    }
            
            return result
        else:
            logger.error(f"Ollama returned status {response.status_code}")
            return {'error': f'Ollama error: {response.status_code}'}
            
    except requests.Timeout:
        logger.error("Ollama request timed out")
        return {'error': 'Request timed out'}
    except Exception as e:
        logger.error(f"Ollama call failed: {e}")
        return {'error': str(e)}


def call_ollama_stream(
    prompt: str,
    max_tokens: int = 500,
    temperature: float = 0.7
) -> Generator[str, None, None]:
    """
    Call Ollama API with streaming response.
    
    Yields JSON strings for each token generated.
    """
    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature,
                }
            },
            stream=True,
            timeout=120
        )
        
        if response.status_code == 200:
            for line in response.iter_lines():
                if line:
                    yield line.decode('utf-8')
        else:
            yield f'{{"error": "Ollama error: {response.status_code}"}}'
            
    except requests.Timeout:
        yield '{"error": "Request timed out"}'
    except Exception as e:
        yield f'{{"error": "{str(e)}"}}'
