"""
Trinity Backend - Repo Map V1 (Regex-Based)

Extracts def/class/function/const signatures from workspace files
to provide a structural overview of a codebase. Injected into LLM
context when the user references a project.

~80% of tree-sitter's value for ~10% of the effort.
Upgrade to tree-sitter later based on usage data.

Reference: INTELLIGENCE-OVERHAUL.md §5.4
"""

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from config import WORKSPACE_MAX_DEPTH, WORKSPACE_ROOT

logger = logging.getLogger(__name__)

# File extensions we understand
LANGUAGE_PATTERNS: Dict[str, List[re.Pattern]] = {
    ".py": [
        re.compile(r"^(class\s+\w+.*?:)", re.MULTILINE),
        re.compile(r"^\s*(def\s+\w+\(.*?\).*?:)", re.MULTILINE),
        re.compile(r"^(\w+)\s*=\s*(?:os\.getenv|int\(|str\(|bool\(|Path\()", re.MULTILINE),
    ],
    ".js": [
        re.compile(r"^(?:export\s+)?(?:default\s+)?class\s+(\w+)", re.MULTILINE),
        re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)", re.MULTILINE),
        re.compile(r"^(?:export\s+)?const\s+(\w+)\s*=", re.MULTILINE),
    ],
    ".ts": [
        re.compile(r"^(?:export\s+)?(?:default\s+)?class\s+(\w+)", re.MULTILINE),
        re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)", re.MULTILINE),
        re.compile(r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*[=:]", re.MULTILINE),
        re.compile(r"^(?:export\s+)?interface\s+(\w+)", re.MULTILINE),
        re.compile(r"^(?:export\s+)?type\s+(\w+)", re.MULTILINE),
    ],
    ".rs": [
        re.compile(r"^(?:pub\s+)?struct\s+(\w+)", re.MULTILINE),
        re.compile(r"^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", re.MULTILINE),
        re.compile(r"^(?:pub\s+)?enum\s+(\w+)", re.MULTILINE),
        re.compile(r"^(?:pub\s+)?trait\s+(\w+)", re.MULTILINE),
    ],
    ".go": [
        re.compile(r"^type\s+(\w+)\s+struct", re.MULTILINE),
        re.compile(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)", re.MULTILINE),
        re.compile(r"^type\s+(\w+)\s+interface", re.MULTILINE),
    ],
}

# Directories to always skip
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", "target", "dist",
    "build", ".venv", "venv", "env", ".tox", ".mypy_cache",
    "htmlcov", ".pytest_cache", ".next",
}

# Max file size to scan (256KB)
MAX_FILE_SIZE = 256 * 1024

# Max total entries in repo map
MAX_ENTRIES = 200


def generate_repo_map(
    workspace_path: Optional[str] = None,
    max_depth: Optional[int] = None,
) -> str:
    """
    Generate a structural map of the workspace.

    Scans files for class/function/const definitions and returns
    a formatted overview suitable for LLM context injection.

    Args:
        workspace_path: Root directory to scan (default: WORKSPACE_ROOT)
        max_depth: Maximum directory depth to scan (default: WORKSPACE_MAX_DEPTH)

    Returns:
        Formatted string with file → symbols mapping
    """
    root = Path(workspace_path or WORKSPACE_ROOT).resolve()
    depth_limit = max_depth if max_depth is not None else WORKSPACE_MAX_DEPTH

    if not root.exists():
        return ""

    file_symbols: Dict[str, List[str]] = {}
    total_entries = 0

    for dirpath, dirnames, filenames in os.walk(str(root)):
        # Skip noise directories
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        # Depth check
        rel_depth = Path(dirpath).relative_to(root).parts
        if len(rel_depth) > depth_limit:
            dirnames.clear()
            continue

        for filename in sorted(filenames):
            ext = Path(filename).suffix
            if ext not in LANGUAGE_PATTERNS:
                continue

            filepath = Path(dirpath) / filename

            # Skip large files
            try:
                if filepath.stat().st_size > MAX_FILE_SIZE:
                    continue
            except OSError:
                continue

            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")
            except (PermissionError, OSError):
                continue

            symbols = _extract_symbols(content, ext)
            if symbols:
                rel_path = str(filepath.relative_to(root))
                file_symbols[rel_path] = symbols
                total_entries += len(symbols)

                if total_entries >= MAX_ENTRIES:
                    break

        if total_entries >= MAX_ENTRIES:
            break

    if not file_symbols:
        return ""

    # Format output
    lines = ["## Workspace Structure (auto-generated repo map)\n"]
    for filepath, symbols in sorted(file_symbols.items()):
        lines.append(f"### {filepath}")
        for symbol in symbols:
            lines.append(f"  {symbol}")
        lines.append("")

    if total_entries >= MAX_ENTRIES:
        lines.append(f"(truncated at {MAX_ENTRIES} entries)")

    return "\n".join(lines)


def _extract_symbols(content: str, ext: str) -> List[str]:
    """Extract symbol signatures from file content."""
    patterns = LANGUAGE_PATTERNS.get(ext, [])
    symbols = []
    seen = set()

    for pattern in patterns:
        for match in pattern.finditer(content):
            # Use the full match for Python (preserves signatures),
            # first group for other languages (just the name)
            if ext == ".py":
                symbol = match.group(1).rstrip()
                # Truncate long signatures
                if len(symbol) > 100:
                    symbol = symbol[:97] + "..."
            else:
                symbol = match.group(1) if match.lastindex else match.group(0)

            if symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)

    return symbols
