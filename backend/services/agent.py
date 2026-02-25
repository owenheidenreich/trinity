"""
Trinity — Agent Pipeline (backwards-compatibility wrapper)

This module preserves the public API that callers depend on while
delegating all logic to the new focused modules:

  - query_classifier.py   → disclosure detection, temperature routing
  - think_filter.py        → streaming think-block filter + code contract
  - pipeline.py            → StreamingPipeline (process_streaming)
  - prompt_assembler.py    → message building

Public API preserved for callers:
  - AgentPipeline           (class)
  - AgentResponse           (dataclass)
  - get_agent_pipeline()    (singleton)
  - reset_agent_pipeline()
  - is_personal_disclosure()

Former size: 1 086 lines → now ~130 lines (thin wrapper).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Re-exports (used by generate.py, tests, other callers)
# ---------------------------------------------------------------------------

from .query_classifier import (  # noqa: F401, E402
    is_personal_disclosure,
)

from .pipeline import (  # noqa: F401, E402
    PipelineResponse as AgentResponse,
    StreamingPipeline,
)


# ---------------------------------------------------------------------------
# AgentPipeline — thin wrapper
# ---------------------------------------------------------------------------


class AgentPipeline:
    """
    Backwards-compatible wrapper around StreamingPipeline.

    Preserves the old call signature used by generate.py and tests:
        AgentPipeline(provider=...).process_streaming(question, ...)

    All logic is delegated to StreamingPipeline.
    """

    def __init__(self, provider=None, **kwargs):
        if provider is not None:
            self._pipeline = StreamingPipeline(provider=provider)
        else:
            from .provider_factory import get_provider

            self._pipeline = StreamingPipeline(provider=get_provider())

    @property
    def client(self):
        """Backwards-compat alias: pipeline.client → underlying provider."""
        return self._pipeline.client

    def _filter_think_blocks(self, stream, accumulator):
        """Backwards-compat: delegate to think_filter module."""
        from .think_filter import filter_think_blocks
        return filter_think_blocks(stream, accumulator)

    def process_streaming(
        self,
        question: str,
        context_messages: List[Dict] = None,
        user_memory: Dict = None,
        semantic_context: List[Dict] = None,
        graph_context: List[Dict] = None,
        principal_id: str = None,
        **kwargs,
    ) -> Generator[Dict, None, None]:
        """Stream a response (old signature → new pipeline)."""
        from .prompt_assembler import PromptAssembler

        disclosure_path = is_personal_disclosure(question)

        # Build messages with the new assembler
        assembler = PromptAssembler()

        # Convert old-style memory + semantic + graph into knowledge block
        memory_block = ""
        if user_memory and isinstance(user_memory, dict):
            facts = user_memory.get("facts", [])
            active = [f for f in facts if isinstance(f, dict) and not f.get("deleted", False)]
            if active:
                # Filter identity/preferences on non-personal queries
                if not disclosure_path and not is_personal_disclosure(question):
                    q_lower = question.lower()
                    _personal_keywords = ("my ", "me ", "about me", "know about", "my name", "who am i")
                    is_personal = any(kw in q_lower for kw in _personal_keywords)
                    if not is_personal:
                        active = [f for f in active if f.get("category") not in ("identity", "preferences")]
                lines = []
                for f in active[:25]:
                    text = f.get("text") or f.get("fact") or str(f)
                    if text:
                        lines.append(f"- {text}")
                memory_block = "\n".join(lines)

        # Add semantic context as additional knowledge
        semantic_block = ""
        if semantic_context:
            sem_lines = []
            for item in semantic_context:
                content = item.get("content", "")
                if content:
                    sem_lines.append(content)
            if sem_lines:
                semantic_block = "\n".join(sem_lines)

        # Add graph context
        graph_block = ""
        if graph_context:
            g_lines = []
            for triple in graph_context:
                subj = triple.get("subject", "")
                pred = triple.get("predicate", "")
                obj = triple.get("object", "")
                if pred and obj:
                    g_lines.append(f"{subj} {pred} {obj}")
            if g_lines:
                graph_block = "\n".join(g_lines)

        # Combine all knowledge into the user_memory field
        combined_memory = "\n".join(filter(None, [memory_block, semantic_block, graph_block]))

        messages = assembler.assemble(
            question=question,
            context_messages=context_messages or [],
            knowledge_items=[],
            conversation_summary="",
            search_context="",
            tools_active=False,
            extra_context=combined_memory,
        )

        yield from self._pipeline.process_streaming(
            question=question,
            messages=messages,
            principal_id=principal_id,
            tools_needed=kwargs.get("tools_needed", []),
            chat_id=kwargs.get("chat_id"),
        )


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------

_pipeline_instance: Optional[AgentPipeline] = None


def get_agent_pipeline(provider=None, **kwargs):
    """Get or create the agent pipeline singleton."""
    global _pipeline_instance

    if _pipeline_instance is None:
        if provider is not None:
            _pipeline_instance = AgentPipeline(provider=provider)
        else:
            from .provider_factory import get_provider

            _pipeline_instance = AgentPipeline(provider=get_provider())

    return _pipeline_instance


def reset_agent_pipeline():
    """Reset the pipeline singleton (for testing or config changes)."""
    global _pipeline_instance
    _pipeline_instance = None
