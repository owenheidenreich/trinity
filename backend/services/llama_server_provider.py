"""
llama-server LLM Provider — wraps llama.cpp HTTP server behind LLMProvider ABC.

Uses the OpenAI-compatible API exposed by llama-server:
  - /v1/chat/completions  (chat)
  - /v1/completions       (text generation)
  - /health               (connection check)

Streaming uses SSE format (data: {json}\n\n) instead of Ollama's NDJSON.
"""

import json
import logging
from typing import Dict, Generator, List, Optional

import requests

from .llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class LlamaServerProvider(LLMProvider):
    """LLMProvider implementation targeting llama-server's OpenAI-compatible API.

    Endpoints used:
        GET  /health                — connection / readiness check
        POST /v1/completions        — raw-prompt completion
        POST /v1/chat/completions   — chat-message completion
    """

    def __init__(
        self,
        host: str = "http://localhost:8081",
        model: str = "qwen3-32b",
        num_ctx: int = 65536,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx

    # ── Text-completion ───────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 30,
        **kwargs,
    ) -> str:
        """Non-streaming text completion via /v1/completions."""
        try:
            from config import DEFAULT_MIN_P, DEFAULT_TOP_K, DEFAULT_TOP_P

            payload = {
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": kwargs.get("top_p", DEFAULT_TOP_P),
                "top_k": kwargs.get("top_k", DEFAULT_TOP_K),
                "min_p": kwargs.get("min_p", DEFAULT_MIN_P),
                "stream": False,
                "cache_prompt": True,
            }
            response = requests.post(
                f"{self.host}/v1/completions",
                json=payload,
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"llama-server error: {response.status_code}")
                return ""

            data = response.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("text", "")
            return ""

        except requests.exceptions.Timeout:
            logger.warning(f"llama-server timeout after {timeout}s")
            return ""
        except Exception as e:
            logger.error(f"llama-server error: {e}")
            return ""

    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 60,
        **kwargs,
    ) -> Generator:
        """Streaming text completion via /v1/completions (SSE)."""
        try:
            from config import DEFAULT_MIN_P, DEFAULT_TOP_K, DEFAULT_TOP_P

            payload = {
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": kwargs.get("top_p", DEFAULT_TOP_P),
                "top_k": kwargs.get("top_k", DEFAULT_TOP_K),
                "min_p": kwargs.get("min_p", DEFAULT_MIN_P),
                "stream": True,
                "cache_prompt": True,
            }
            response = requests.post(
                f"{self.host}/v1/completions",
                json=payload,
                stream=True,
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"llama-server error: {response.status_code}")
                return

            for line in response.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                if not line_str.startswith("data: "):
                    continue
                payload = line_str[6:]
                if payload.strip() == "[DONE]":
                    yield {"__done_reason": "stop"}
                    break
                try:
                    chunk = json.loads(payload)
                    choices = chunk.get("choices", [])
                    if choices:
                        text = choices[0].get("text", "")
                        if text:
                            yield text
                        finish = choices[0].get("finish_reason")
                        if finish:
                            yield {"__done_reason": finish}
                            break
                except json.JSONDecodeError:
                    continue

        except requests.exceptions.Timeout:
            logger.warning(f"llama-server stream timeout after {timeout}s")
        except Exception as e:
            logger.error(f"llama-server stream error: {e}")

    # ── Chat-completion ───────────────────────────────────────────

    def chat(
        self,
        messages: List[Dict],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 60,
        tools: Optional[List[Dict]] = None,
        raw_message: bool = False,
        **kwargs,
    ) -> str:
        """Non-streaming chat completion via /v1/chat/completions."""
        try:
            from config import DEFAULT_MIN_P, DEFAULT_TOP_K, DEFAULT_TOP_P

            payload = {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": kwargs.get("top_p", DEFAULT_TOP_P),
                "top_k": kwargs.get("top_k", DEFAULT_TOP_K),
                "min_p": kwargs.get("min_p", DEFAULT_MIN_P),
                "stream": False,
                "cache_prompt": True,
            }
            if tools:
                payload["tools"] = tools

            response = requests.post(
                f"{self.host}/v1/chat/completions",
                json=payload,
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"llama-server chat error: {response.status_code}")
                return {} if raw_message else ""

            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                return {} if raw_message else ""

            message = choices[0].get("message", {})
            if raw_message:
                return message
            return message.get("content", "") or ""

        except requests.exceptions.Timeout:
            logger.warning(f"llama-server chat timeout after {timeout}s")
            return {} if raw_message else ""
        except Exception as e:
            logger.error(f"llama-server chat error: {e}")
            return {} if raw_message else ""

    def chat_stream(
        self,
        messages: List[Dict],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 60,
        **kwargs,
    ) -> Generator:
        """Streaming chat completion via /v1/chat/completions (SSE)."""
        try:
            from config import DEFAULT_MIN_P, DEFAULT_TOP_K, DEFAULT_TOP_P

            payload = {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": kwargs.get("top_p", DEFAULT_TOP_P),
                "top_k": kwargs.get("top_k", DEFAULT_TOP_K),
                "min_p": kwargs.get("min_p", DEFAULT_MIN_P),
                "stream": True,
                "cache_prompt": True,
            }

            response = requests.post(
                f"{self.host}/v1/chat/completions",
                json=payload,
                stream=True,
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"llama-server chat stream error: {response.status_code}")
                return

            for line in response.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                if not line_str.startswith("data: "):
                    continue
                payload_str = line_str[6:]
                if payload_str.strip() == "[DONE]":
                    yield {"__done_reason": "stop"}
                    break
                try:
                    chunk = json.loads(payload_str)
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            yield token
                        finish = choices[0].get("finish_reason")
                        if finish:
                            yield {"__done_reason": finish}
                            break
                except json.JSONDecodeError:
                    continue

        except requests.exceptions.Timeout:
            logger.warning(f"llama-server chat stream timeout after {timeout}s")
        except Exception as e:
            logger.error(f"llama-server chat stream error: {e}")

    # ── Lifecycle ─────────────────────────────────────────────────

    def check_connection(self) -> bool:
        """Check llama-server is running and ready."""
        try:
            response = requests.get(f"{self.host}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "")
                return status in ("ok", "no slot available")
            return False
        except Exception as e:
            logger.error(f"llama-server connection check failed: {e}")
            return False

    def warmup(self) -> bool:
        """Warm up the model with a short chat request."""
        logger.info(f"Warming up llama-server model: {self.model}")
        try:
            response = requests.post(
                f"{self.host}/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 10,
                    "temperature": 0.7,
                    "stream": False,
                },
                timeout=300,
            )

            if response.status_code == 200:
                logger.info("Model warmed up successfully")
                return True
            else:
                logger.warning(f"Warmup request failed with status {response.status_code}")
                return False

        except requests.Timeout:
            logger.error("Model warmup timed out")
            return False
        except Exception as e:
            logger.error(f"Model warmup failed: {e}")
            return False
