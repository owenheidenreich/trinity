"""
Services package.

Import concrete modules directly (for example: `from services.state_store import get_state_store`).
This file intentionally avoids broad re-exports to keep runtime imports deterministic
and prevent legacy modules from loading on hot paths.
"""

__all__ = []
