"""
Trinity Backend Test Configuration and Core Fixtures

Shared fixtures for all test modules:
- Flask app and test client
- Ed25519 authentication fixtures
"""

import sys
from pathlib import Path

import pytest

# Add backend to path for imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

# Import auth fixtures for re-export (noqa prevents autoflake removal)
from tests.fixtures.auth_fixtures import (  # noqa: F401
    auth_headers,
    create_signature,
    expired_auth_headers,
    future_auth_headers,
    second_keypair,
    test_keypair,
)

# =============================================================================
# FLASK APP FIXTURES
# =============================================================================


def _register_test_blueprints():
    """Register opt-in blueprints (e.g. diagnostic) at import time,
    before any test triggers Flask's setup-finished lock."""
    from inference_server import app as flask_app
    if "diagnostic" not in flask_app.blueprints:
        try:
            from routes.diagnostic import diagnostic_bp
            flask_app.register_blueprint(diagnostic_bp)
        except Exception:
            pass

_register_test_blueprints()


@pytest.fixture
def app():
    """Flask test application with test configuration."""
    from inference_server import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["DEBUG"] = False

    test_chats_dir = Path("/tmp/trinity_test_chats")
    test_chats_dir.mkdir(exist_ok=True)

    yield flask_app

    import shutil
    shutil.rmtree(test_chats_dir, ignore_errors=True)


@pytest.fixture
def client(app):
    """Flask test client for making HTTP requests."""
    return app.test_client()
