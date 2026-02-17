"""
Ollama LLM Provider — wraps existing Ollama HTTP calls behind LLMProvider ABC.

Migrated from:
  - services/agent.py::OllamaClient  (chat, chat_stream, generate, generate_stream)
  - services/ollama.py               (check_ollama_connection, warmup_model, call_ollama)

All Ollama-specific HTTP details live here.  Nothing outside this file
should import requests and hit /api/generate or /api/chat directly.
"""

import json
import logging
from typing import Dict, Generator, List, Optional

import requests

from .llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """LLMProvider implementation targeting Ollama's REST API.

    Endpoints used:
        GET  /api/tags       — connection / model check
        POST /api/generate   — raw-prompt completion
        POST /api/chat       — chat-message completion
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "qwen3:32b",
        num_ctx: int = 65536,
    ):
        self.host = host
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
        """Non-streaming prompt completion via /api/generate."""
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                        "num_ctx": self.num_ctx,
                    },
                },
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"Ollama error: {response.status_code}")
                return ""

            return response.json().get("response", "")

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama timeout after {timeout}s")
            return ""
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return ""

    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 60,
        **kwargs,
    ) -> Generator:
        """Streaming prompt completion via /api/generate (NDJSON)."""
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                        "num_ctx": self.num_ctx,
                    },
                },
                stream=True,
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"Ollama error: {response.status_code}")
                return

            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            yield {"__done_reason": chunk.get("done_reason", "stop")}
                            break
                    except json.JSONDecodeError:
                        continue

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama stream timeout after {timeout}s")
        except Exception as e:
            logger.error(f"Ollama stream error: {e}")

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
        """Non-streaming chat completion via /api/chat."""
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature,
                    "num_ctx": self.num_ctx,
                },
            }
            if tools:
                payload["tools"] = tools

            response = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"Ollama chat error: {response.status_code}")
                return {} if raw_message else ""

            message = response.json().get("message", {})
            return message if raw_message else message.get("content", "")

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama chat timeout after {timeout}s")
            return {} if raw_message else ""
        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
            return {} if raw_message else ""

    def chat_stream(
        self,
        messages: List[Dict],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        timeout: int = 60,
        **kwargs,
    ) -> Generator:
        """Streaming chat completion via /api/chat (NDJSON)."""
        try:
            response = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                        "num_ctx": self.num_ctx,
                    },
                },
                stream=True,
                timeout=timeout,
            )

            if response.status_code != 200:
                logger.error(f"Ollama chat stream error: {response.status_code}")
                return

            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            yield {"__done_reason": chunk.get("done_reason", "stop")}
                            break
                    except json.JSONDecodeError:
                        continue

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama chat stream timeout after {timeout}s")
        except Exception as e:
            logger.error(f"Ollama chat stream error: {e}")

    # ── Lifecycle ─────────────────────────────────────────────────

    def check_connection(self) -> bool:
        """Check Ollama is running and the configured model is loaded."""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return any(m["name"].startswith(self.model) for m in models)
            return False
        except Exception as e:
            logger.error(f"Ollama connection check failed: {e}")
            return False

    def warmup(self) -> bool:
        """Warm up the model with a short generation request."""
        logger.info(f"🔥 Warming up model: {self.model} — this may take a few minutes on first run...")
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "Hello, this is a warmup request.",
                    "stream": False,
                    "options": {"num_predict": 10, "temperature": 0.7},
                },
                timeout=300,
            )

            if response.status_code == 200:
                logger.info("✓ Model warmed up successfully! Ready to serve requests.")
                return True
            else:
                logger.warning(f"⚠ Warmup request failed with status {response.status_code}")
                return False

        except requests.Timeout:
            logger.error("❌ Model warmup timed out — model may still be downloading")
            return False
        except Exception as e:
            logger.error(f"❌ Model warmup failed: {e}")
            return False
