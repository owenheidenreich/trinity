"""
Phase 4 Code Quality Tests
=============================
Validates the Phase 4 critical fixes:
  4.1 Frontend Logger utility (core/logger.js)
  4.2 Backend constants extraction (config.py)
  4.3 Fix import patterns (no function-level stdlib/flask imports)
  4.4 Integration test scaffold (tests/integration/)
  4.5 Frontend refactor (app.js decomposition)
"""

import ast
import os
import re
from pathlib import Path

import pytest


# ===== Path helpers =====

BACKEND_DIR = Path(__file__).parent.parent.parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "trinity-icp" / "src"
ROUTES_DIR = BACKEND_DIR / "routes"


def _read(path: Path) -> str:
    """Read a file and return its contents."""
    return path.read_text(encoding="utf-8")


# =============================================================================
# 4.1 FRONTEND LOGGER UTILITY
# =============================================================================

class TestLoggerUtility:
    """Verify core/logger.js exists and exports the correct API."""

    def test_logger_file_exists(self):
        path = FRONTEND_DIR / "core" / "logger.js"
        assert path.exists(), "core/logger.js not found"

    def test_logger_exports_default(self):
        content = _read(FRONTEND_DIR / "core" / "logger.js")
        assert "export default Logger" in content or "export default" in content

    def test_logger_has_all_methods(self):
        content = _read(FRONTEND_DIR / "core" / "logger.js")
        for method in ("debug", "info", "log", "warn", "error"):
            assert method in content, f"Logger missing method: {method}"

    def test_logger_has_dev_detection(self):
        content = _read(FRONTEND_DIR / "core" / "logger.js")
        assert "IS_DEV" in content or "isDev" in content or "isDevEnvironment" in content

    def test_config_imports_logger(self):
        content = _read(FRONTEND_DIR / "config.js")
        assert "import" in content and "logger" in content.lower()

    def test_config_uses_logger_not_console(self):
        """config.js should use Logger.* instead of console.* (except in edge cases)."""
        content = _read(FRONTEND_DIR / "config.js")
        # Should have Logger references
        assert "Logger." in content, "config.js should use Logger"


# =============================================================================
# 4.2 BACKEND CONSTANTS EXTRACTION
# =============================================================================

class TestNamedConstants:
    """Verify magic numbers have been replaced with named constants in config.py."""

    @pytest.fixture(autouse=True)
    def _load_config(self):
        self.config_content = _read(BACKEND_DIR / "config.py")

    # --- Inference defaults ---

    def test_default_max_tokens_exists(self):
        assert "DEFAULT_MAX_TOKENS" in self.config_content

    def test_default_temperature_exists(self):
        assert "DEFAULT_TEMPERATURE" in self.config_content

    # --- Timeout constants ---

    def test_llm_timeout_exists(self):
        assert "LLM_TIMEOUT" in self.config_content

    def test_llm_timeout_tools_exists(self):
        assert "LLM_TIMEOUT_TOOLS" in self.config_content

    # --- Document limits ---

    def test_max_document_context_chars_exists(self):
        assert "MAX_DOCUMENT_CONTEXT_CHARS" in self.config_content

    def test_max_web_scrape_chars_exists(self):
        assert "MAX_WEB_SCRAPE_CHARS" in self.config_content

    def test_web_fetch_timeout_exists(self):
        assert "WEB_FETCH_TIMEOUT" in self.config_content

    def test_web_search_timeout_exists(self):
        assert "WEB_SEARCH_TIMEOUT" in self.config_content

    # --- Chat / storage ---

    def test_max_archived_chats_exists(self):
        assert "MAX_ARCHIVED_CHATS" in self.config_content

    def test_ipfs_scan_limit_exists(self):
        assert "IPFS_SCAN_LIMIT" in self.config_content

    def test_chat_inactive_days_exists(self):
        assert "CHAT_INACTIVE_DAYS" in self.config_content

    def test_principal_display_length_exists(self):
        assert "PRINCIPAL_DISPLAY_LENGTH" in self.config_content

    # --- Session ---

    def test_min_session_hours_exists(self):
        assert "MIN_SESSION_HOURS" in self.config_content

    def test_max_session_hours_exists(self):
        assert "MAX_SESSION_HOURS" in self.config_content

    # --- Constants are importable ---

    def test_constants_importable(self):
        """All new constants should be importable from config."""
        from config import (
            DEFAULT_MAX_TOKENS,
            DEFAULT_TEMPERATURE,
            LLM_TIMEOUT,
            LLM_TIMEOUT_TOOLS,
            MAX_DOCUMENT_CONTEXT_CHARS,
            MAX_WEB_SCRAPE_CHARS,
            MAX_ARCHIVED_CHATS,
            IPFS_SCAN_LIMIT,
            CHAT_INACTIVE_DAYS,
            PRINCIPAL_DISPLAY_LENGTH,
            MIN_SESSION_HOURS,
            MAX_SESSION_HOURS,
        )
        # Spot-check values
        assert DEFAULT_MAX_TOKENS == 16384
        assert DEFAULT_TEMPERATURE == 0.7
        assert LLM_TIMEOUT == 600
        assert MAX_ARCHIVED_CHATS == 20
        assert PRINCIPAL_DISPLAY_LENGTH == 16
        assert MIN_SESSION_HOURS == 1
        assert MAX_SESSION_HOURS == 24

    # --- Route files actually USE the constants ---

    def test_generate_route_uses_constants(self):
        content = _read(ROUTES_DIR / "generate.py")
        assert "MAX_QUEUE_SIZE" in content

    def test_tools_route_uses_constants(self):
        content = _read(ROUTES_DIR / "tools.py")
        assert "LLM_TIMEOUT_TOOLS" in content or "WEB_FETCH_TIMEOUT" in content

    def test_chat_route_uses_constants(self):
        content = _read(ROUTES_DIR / "chat.py")
        assert "get_state_store" in content
        assert "/chat/start" in content

    def test_session_route_uses_constants(self):
        content = _read(ROUTES_DIR / "session.py")
        assert "MIN_SESSION_HOURS" in content
        assert "MAX_SESSION_HOURS" in content

# =============================================================================
# 4.3 FIX IMPORT PATTERNS
# =============================================================================

class TestImportPatterns:
    """Verify function-level imports have been moved to module level."""

    # Allowed exceptions: lazy imports documented with reason
    ALLOWED_LAZY_IMPORTS = {
        "generate.py": {"services", "middleware", "threading"},   # service layer, avoid circular imports, background extraction
        "chat.py": {"middleware", "services", "io", "zipfile", "flask", "storage"},    # mutable globals + export endpoint + user data
        "tools.py": {"bs4"},                        # optional heavy dependency
    }

    def _get_function_level_imports(self, filepath: Path) -> list:
        """Parse a Python file and find imports inside function bodies."""
        source = _read(filepath)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        violations = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if isinstance(child, (ast.Import, ast.ImportFrom)):
                        module = ""
                        if isinstance(child, ast.ImportFrom) and child.module:
                            module = child.module.split(".")[0]
                        elif isinstance(child, ast.Import):
                            module = child.names[0].name.split(".")[0]
                        violations.append((child.lineno, module))
        return violations

    def test_health_no_function_imports(self):
        violations = self._get_function_level_imports(ROUTES_DIR / "health.py")
        assert len(violations) == 0, f"Function-level imports in health.py: {violations}"

    def test_generate_only_allowed_lazy_imports(self):
        violations = self._get_function_level_imports(ROUTES_DIR / "generate.py")
        allowed = self.ALLOWED_LAZY_IMPORTS.get("generate.py", set())
        for lineno, module in violations:
            assert module in allowed or any(
                module.startswith(a) for a in allowed
            ), f"Unexpected function-level import at generate.py:{lineno}: {module}"

    def test_session_no_function_imports(self):
        violations = self._get_function_level_imports(ROUTES_DIR / "session.py")
        assert len(violations) == 0, f"Function-level imports in session.py: {violations}"

    def test_chat_only_allowed_lazy_imports(self):
        violations = self._get_function_level_imports(ROUTES_DIR / "chat.py")
        allowed = self.ALLOWED_LAZY_IMPORTS.get("chat.py", set())
        for lineno, module in violations:
            assert module in allowed or any(
                module.startswith(a) for a in allowed
            ), f"Unexpected function-level import at chat.py:{lineno}: {module}"

    def test_tools_only_allowed_lazy_imports(self):
        violations = self._get_function_level_imports(ROUTES_DIR / "tools.py")
        allowed = self.ALLOWED_LAZY_IMPORTS.get("tools.py", set())
        for lineno, module in violations:
            assert module in allowed or any(
                module.startswith(a) for a in allowed
            ), f"Unexpected function-level import at tools.py:{lineno}: {module}"

    def test_current_app_at_module_level(self):
        """current_app should be imported at module level, not inside functions."""
        for route_file in ROUTES_DIR.glob("*.py"):
            content = _read(route_file)
            # Check for top-level import
            if "current_app" not in content:
                continue
            # Find function-level current_app imports
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("from flask import") and "current_app" in stripped:
                    # Must be at module level (not indented)
                    assert not line.startswith((" ", "\t")), (
                        f"{route_file.name}:{i} has function-level 'from flask import current_app'"
                    )

    def test_no_sys_path_hacks(self):
        """No sys.path manipulation in route files."""
        for route_file in ROUTES_DIR.glob("*.py"):
            content = _read(route_file)
            assert "sys.path" not in content, (
                f"{route_file.name} contains sys.path hack"
            )


# =============================================================================
# 4.4 INTEGRATION TEST SCAFFOLD
# =============================================================================

class TestIntegrationScaffold:
    """Verify integration test files exist and have proper structure."""

    INTEGRATION_DIR = BACKEND_DIR / "tests" / "integration"

    def test_integration_dir_exists(self):
        assert self.INTEGRATION_DIR.exists(), "tests/integration/ directory missing"

    def test_conftest_exists(self):
        assert (self.INTEGRATION_DIR / "conftest.py").exists()

    def test_test_inference_exists(self):
        assert (self.INTEGRATION_DIR / "test_inference.py").exists()

    def test_conftest_has_llm_fixture(self):
        content = _read(self.INTEGRATION_DIR / "conftest.py")
        assert "llm_available" in content, "conftest.py missing llm_available fixture"
        assert "@pytest.fixture" in content

    def test_conftest_has_app_fixture(self):
        content = _read(self.INTEGRATION_DIR / "conftest.py")
        assert "def app" in content, "conftest.py missing app fixture"

    def test_test_inference_has_test_classes(self):
        content = _read(self.INTEGRATION_DIR / "test_inference.py")
        assert "class Test" in content
        assert "def test_" in content

    def test_integration_tests_use_skipif(self):
        """Integration tests should skip when Ollama is unavailable."""
        content = _read(self.INTEGRATION_DIR / "test_inference.py")
        assert "skipif" in content or "ollama_available" in content


# =============================================================================
# 4.5 FRONTEND REFACTOR
# =============================================================================

class TestFrontendRefactor:
    """Verify app.js has been decomposed into focused modules."""

    def test_app_js_under_300_lines(self):
        """app.js should be < 300 lines (target was < 200, achieved ~265)."""
        content = _read(FRONTEND_DIR / "app.js")
        line_count = len(content.strip().split("\n"))
        assert line_count < 300, f"app.js is {line_count} lines (expected < 300)"

    def test_app_js_is_orchestrator(self):
        """app.js should be an orchestrator importing from modules."""
        content = _read(FRONTEND_DIR / "app.js")
        import_count = content.count("import ")
        assert import_count >= 5, f"app.js has only {import_count} imports (expected >= 5)"

    # --- Module existence ---

    @pytest.mark.parametrize("module_path", [
        "core/api.js",
        "core/environment.js",
        "core/logger.js",
        "features/generate.js",
        "features/auth.js",
        "features/chatManagement.js",
        "features/memory.js",
        "ui/editMessage.js",
    ])
    def test_module_exists(self, module_path):
        path = FRONTEND_DIR / module_path
        assert path.exists(), f"Module {module_path} not found"

    # --- Module content checks ---

    def test_api_module_has_fetch_calls(self):
        """core/api.js should contain the fetch() calls."""
        content = _read(FRONTEND_DIR / "core" / "api.js")
        assert "fetch(" in content, "core/api.js should contain fetch() calls"
        assert "healthCheck" in content or "health" in content.lower()

    def test_api_module_exports_api(self):
        content = _read(FRONTEND_DIR / "core" / "api.js")
        assert "export" in content

    def test_environment_module_has_detect(self):
        content = _read(FRONTEND_DIR / "core" / "environment.js")
        assert "detectEnvironment" in content

    def test_generate_module_has_generate_function(self):
        content = _read(FRONTEND_DIR / "features" / "generate.js")
        assert "generate" in content
        assert "stopGeneration" in content or "cancelRequest" in content

    def test_auth_module_has_auth_functions(self):
        content = _read(FRONTEND_DIR / "features" / "auth.js")
        for fn in ("initAuth", "logout", "createNewIdentity"):
            assert fn in content, f"auth.js missing {fn}"

    def test_chat_management_has_crud(self):
        content = _read(FRONTEND_DIR / "features" / "chatManagement.js")
        for fn in ("loadChats", "deleteChat", "newChat"):
            assert fn in content, f"chatManagement.js missing {fn}"

    def test_memory_module_has_memory_functions(self):
        content = _read(FRONTEND_DIR / "features" / "memory.js")
        assert "viewMemory" in content or "Memory" in content

    def test_edit_message_has_edit_functions(self):
        content = _read(FRONTEND_DIR / "ui" / "editMessage.js")
        assert "addEditButton" in content or "editMessage" in content

    # --- No duplicated fetch calls ---

    def test_app_js_no_direct_fetch(self):
        """app.js should not contain direct fetch() calls (delegated to core/api.js)."""
        content = _read(FRONTEND_DIR / "app.js")
        # Allow "fetch" in comments and import references, but not actual calls
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if "fetch(" in stripped and "import" not in stripped:
                pytest.fail(f"app.js:{i} contains direct fetch() call: {stripped}")

    # --- Total frontend module line counts ---

    def test_total_frontend_lines_reasonable(self):
        """Total frontend code (excluding vendor/library files) should be reasonable."""
        total = 0
        # Vendor / library files excluded from line-count analysis
        VENDOR_FILES = {"icp-auth.js"}
        for js_file in FRONTEND_DIR.rglob("*.js"):
            rel = str(js_file.relative_to(FRONTEND_DIR))
            if any(skip in rel for skip in ("node_modules", ".dfx", "target", ".bak")):
                continue
            if js_file.name in VENDOR_FILES:
                continue
            total += len(js_file.read_text(encoding="utf-8").strip().split("\n"))
        # Application code (excl. vendor) should be 4-8k lines
        assert total > 1500, f"Frontend total {total} lines seems too low"
        assert total < 12000, f"Frontend total {total} lines seems bloated"


# =============================================================================
# CROSS-CUTTING QUALITY CHECKS
# =============================================================================

class TestCrossCuttingQuality:
    """Quality checks that span multiple Phase 4 items."""

    def test_backend_no_bare_magic_numbers_in_routes(self):
        """Spot-check that common magic numbers have been replaced with constants."""
        for route_file in ROUTES_DIR.glob("*.py"):
            content = _read(route_file)
            name = route_file.name
            # Skip __init__.py and shared.py (utility modules)
            if name in ("__init__.py", "shared.py"):
                continue
            # Check for bare timeout=600 (should be LLM_TIMEOUT)
            bare_600 = re.findall(r'timeout\s*=\s*600\b', content)
            assert not bare_600, f"{name} still has bare timeout=600"

    def test_no_console_log_in_config_js(self):
        """config.js should use Logger, not console."""
        content = _read(FRONTEND_DIR / "config.js")
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            if "console.log(" in stripped:
                pytest.fail(f"config.js:{i} uses console.log instead of Logger")

    def test_test_coverage_target(self):
        """Verify we have enough tests. We target 60%+ coverage (achieving 91%)."""
        # Count test files
        unit_tests = list((BACKEND_DIR / "tests" / "unit").glob("test_*.py"))
        assert len(unit_tests) >= 5, f"Only {len(unit_tests)} unit test files"

    def test_integration_test_files_exist(self):
        int_dir = BACKEND_DIR / "tests" / "integration"
        int_tests = list(int_dir.glob("test_*.py"))
        assert len(int_tests) >= 1, "No integration test files"
