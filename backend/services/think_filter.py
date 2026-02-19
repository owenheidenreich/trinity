"""Streaming think-block filter and code-fence helpers.

Extracts all think-block filtering and code-fence detection logic from the
former god-module ``agent.py`` into a focused, stateless utility module.

Public API
----------
* ``filter_think_blocks(token_stream, accumulator)`` — generator filter
* ``contains_fenced_code(text)`` / ``looks_like_code(text)``
* ``wrap_code_block(text, language)``
* ``estimate_tokens(text)``

Code-generation classification and language inference live in
``query_classifier.py`` (canonical location).
"""

from __future__ import annotations

import logging
import re
from typing import Generator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex constants
# ---------------------------------------------------------------------------
_THINK_OPEN = re.compile(r"<think>", re.IGNORECASE)
_THINK_CLOSE = re.compile(r"</think>", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Think-block streaming filter
# ---------------------------------------------------------------------------

# ~20k tokens; triggers safety flush before model output budget is exhausted
_THINK_CHAR_LIMIT = 80_000


def filter_think_blocks(
    token_stream: Generator,
    accumulator: list,
) -> Generator[str, None, None]:
    """Filter ``<think>...</think>`` blocks from a streaming token generator.

    Qwen3 (and some other models) emit ``<think>reasoning</think>`` before
    the actual answer.  These must be stripped so the frontend never sees
    raw XML tags.

    Parameters
    ----------
    token_stream:
        Generator yielding ``str`` tokens or ``dict`` metadata.
    accumulator:
        Mutable list — clean text is appended for the caller to read back.

    Yields
    ------
    str
        Tokens with think blocks removed.
    dict
        Metadata tokens (e.g. ``__done_reason``) are yielded unchanged.
    """
    inside_think = False
    buf = ""
    think_chars = 0

    for token in token_stream:
        # Pass through non-string (metadata) tokens unchanged.
        if isinstance(token, dict):
            yield token
            continue

        buf += token

        while buf:
            if inside_think:
                close_match = _THINK_CLOSE.search(buf)
                if close_match:
                    buf = buf[close_match.end():]
                    inside_think = False
                    think_chars = 0
                    continue
                else:
                    # Keep a tail large enough that a split ``</think>``
                    # tag is never lost.  ``</think>`` is 8 chars so we
                    # keep 16 for safety.
                    think_chars += max(0, len(buf) - 16)
                    if len(buf) > 16:
                        buf = buf[-16:]

                    # Safety: if we've been inside <think> for way too
                    # long, the close tag was probably never emitted.
                    if think_chars > _THINK_CHAR_LIMIT:
                        logger.warning(
                            "Think block exceeded %d chars without closing "
                            "— flushing remaining text to user.",
                            _THINK_CHAR_LIMIT,
                        )
                        inside_think = False
                        think_chars = 0
                        continue
                    break
            else:
                open_match = _THINK_OPEN.search(buf)
                if open_match:
                    before = buf[: open_match.start()]
                    if before:
                        accumulator.append(before)
                        yield before
                    buf = buf[open_match.end():]
                    inside_think = True
                    think_chars = 0
                    continue
                else:
                    # ``<think>`` is 7 chars — keep that many in the
                    # buffer so a split tag is never missed.
                    if len(buf) > 7:
                        safe = buf[:-7]
                        buf = buf[-7:]
                        accumulator.append(safe)
                        yield safe
                    break

    # Flush remaining buffer.
    if buf:
        if inside_think:
            logger.warning(
                "Stream ended inside unclosed <think> block "
                "— flushing %d chars.",
                len(buf),
            )
        accumulator.append(buf)
        yield buf


# ---------------------------------------------------------------------------
# Code-fence helpers
# ---------------------------------------------------------------------------

def contains_fenced_code(text: str) -> bool:
    """Return True if *text* contains at least one complete fenced code block."""
    return bool(text and text.count("```") >= 2)


def looks_like_code(text: str) -> bool:
    """Heuristic: does *text* look like source code even without fences?"""
    if not text:
        return False
    code_markers = (
        "def ",
        "class ",
        "function ",
        "const ",
        "let ",
        "var ",
        "import ",
        "console.log",
        "print(",
        "{",
        "}",
        "<html",
        "SELECT ",
        "#include",
        "public static",
    )
    snippet = text.strip()
    if any(marker in snippet for marker in code_markers):
        return True
    lines = [line for line in snippet.splitlines() if line.strip()]
    return len(lines) >= 3 and any(
        ("=" in line or ":" in line) for line in lines[:6]
    )


def wrap_code_block(text: str, language: str) -> str:
    """Wrap *text* in a Markdown fenced code block."""
    body = (text or "").strip()
    return f"```{language}\n{body}\n```" if body else f"```{language}\n\n```"


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)
