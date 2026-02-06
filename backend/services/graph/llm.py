"""
Trinity LangGraph LLM Wrapper

LangChain-compatible wrapper for Ollama that integrates with Trinity's
existing multi-model configuration.
"""

import logging
from typing import Any, Iterator, List, Optional

import requests
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.language_models.llms import BaseLLM
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import Generation, LLMResult

logger = logging.getLogger(__name__)


# Import Trinity's model configuration
try:
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from config import (
        FAST_MODEL,
        MODEL_NAME,
        MULTI_MODEL_ENABLED,
        OLLAMA_HOST,
        REASONING_MODEL,
        SMART_MODEL,
    )
except ImportError:
    # Fallback defaults
    OLLAMA_HOST = "http://localhost:11434"
    MODEL_NAME = "llama3.1:8b"
    MULTI_MODEL_ENABLED = False
    FAST_MODEL = None
    SMART_MODEL = None
    REASONING_MODEL = None


class TrinityLLM(BaseLLM):
    """
    LangChain-compatible LLM that wraps Trinity's Ollama integration.

    Supports multi-model routing:
    - 'fast': Quick classification/routing (phi3:mini or similar)
    - 'smart': Standard generation (llama3.1:8b)
    - 'reasoning': Complex analysis (qwen2.5:32b or larger)
    """

    model_type: str = "smart"
    ollama_host: str = OLLAMA_HOST
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 120

    class Config:
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        return "trinity_ollama"

    @property
    def _identifying_params(self) -> dict:
        return {
            "model_type": self.model_type,
            "model_name": self._get_model_name(),
            "ollama_host": self.ollama_host,
        }

    def _get_model_name(self) -> str:
        """Get the appropriate model based on model_type."""
        if not MULTI_MODEL_ENABLED:
            return MODEL_NAME

        if self.model_type == "fast":
            return FAST_MODEL or MODEL_NAME
        elif self.model_type == "reasoning":
            return REASONING_MODEL or SMART_MODEL or MODEL_NAME
        else:  # 'smart' or default
            return SMART_MODEL or MODEL_NAME

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Execute LLM call via Ollama."""
        model = self._get_model_name()

        try:
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": self.max_tokens,
                        "temperature": self.temperature,
                        "stop": stop or [],
                    },
                },
                timeout=self.timeout,
            )

            if response.status_code != 200:
                logger.error(f"Ollama error: {response.status_code} - {response.text}")
                return f"Error: Ollama returned status {response.status_code}"

            result = response.json()
            return result.get("response", "")

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama timeout after {self.timeout}s for model {model}")
            return "Error: Request timed out"
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return f"Error: {str(e)}"

    def _generate(
        self,
        prompts: List[str],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> LLMResult:
        """Generate responses for multiple prompts."""
        generations = []
        for prompt in prompts:
            text = self._call(prompt, stop, run_manager, **kwargs)
            generations.append([Generation(text=text)])
        return LLMResult(generations=generations)

    def invoke(
        self,
        input: LanguageModelInput,
        config: Optional[Any] = None,
        **kwargs: Any,
    ) -> AIMessage:
        """
        Invoke the LLM with messages or a string prompt.

        Args:
            input: Either a string prompt or list of messages
            config: Optional config (ignored for now)

        Returns:
            AIMessage with the response
        """
        # Convert messages to prompt string
        if isinstance(input, str):
            prompt = input
        elif isinstance(input, list):
            prompt = self._messages_to_prompt(input)
        else:
            prompt = str(input)

        response = self._call(prompt, **kwargs)
        return AIMessage(content=response)

    def _messages_to_prompt(self, messages: List[BaseMessage]) -> str:
        """Convert LangChain messages to a prompt string."""
        prompt_parts = []

        for msg in messages:
            if msg.type == "system":
                prompt_parts.append(f"System: {msg.content}")
            elif msg.type == "human":
                prompt_parts.append(f"User: {msg.content}")
            elif msg.type == "ai":
                prompt_parts.append(f"Assistant: {msg.content}")
            else:
                prompt_parts.append(msg.content)

        prompt_parts.append("Assistant:")
        return "\n\n".join(prompt_parts)

    def stream(
        self,
        input: LanguageModelInput,
        config: Optional[Any] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """
        Stream response tokens.

        Args:
            input: Either a string prompt or list of messages
            config: Optional config

        Yields:
            Response tokens as they're generated
        """
        if isinstance(input, str):
            prompt = input
        elif isinstance(input, list):
            prompt = self._messages_to_prompt(input)
        else:
            prompt = str(input)

        model = self._get_model_name()

        try:
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "num_predict": self.max_tokens,
                        "temperature": self.temperature,
                    },
                },
                stream=True,
                timeout=self.timeout,
            )

            if response.status_code != 200:
                yield f"Error: Ollama returned status {response.status_code}"
                return

            import json

            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

        except requests.exceptions.Timeout:
            yield "Error: Request timed out"
        except Exception as e:
            yield f"Error: {str(e)}"


# Pre-configured LLM instances
def get_fast_llm() -> TrinityLLM:
    """Get LLM configured for fast routing/classification."""
    return TrinityLLM(model_type="fast", temperature=0.3, max_tokens=500)


def get_smart_llm() -> TrinityLLM:
    """Get LLM configured for standard generation."""
    return TrinityLLM(model_type="smart", temperature=0.7, max_tokens=4096)


def get_reasoning_llm() -> TrinityLLM:
    """Get LLM configured for complex reasoning."""
    return TrinityLLM(model_type="reasoning", temperature=0.5, max_tokens=8192, timeout=300)
