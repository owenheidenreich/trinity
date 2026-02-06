"""
Trinity Backend Test Configuration and Core Fixtures

This conftest.py provides shared fixtures for all test modules:
- Flask app and test client
- Ed25519 authentication fixtures  
- Mock Ollama responses
- Common test utilities

Created: February 5, 2026
Phase 1: Testing Foundation
"""

import pytest
import sys
import os
import time
import json
from pathlib import Path
from typing import Dict, Generator
from unittest.mock import MagicMock, patch

# Add backend to path for imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

# Import auth fixtures
from tests.fixtures.auth_fixtures import (
    test_keypair,
    second_keypair,
    create_signature,
    auth_headers,
    expired_auth_headers,
    future_auth_headers
)


# =============================================================================
# FLASK APP FIXTURES
# =============================================================================

@pytest.fixture
def app():
    """
    Flask test application with test configuration.
    
    Creates a test instance of the Trinity inference server with:
    - TESTING mode enabled
    - Isolated test chat directory
    - Debug mode disabled
    """
    # Import here to avoid circular imports
    from inference_server import app as flask_app
    
    flask_app.config['TESTING'] = True
    flask_app.config['DEBUG'] = False
    
    # Use temp directory for test chats
    test_chats_dir = Path('/tmp/trinity_test_chats')
    test_chats_dir.mkdir(exist_ok=True)
    
    yield flask_app
    
    # Cleanup after tests (optional - leave for debugging)
    # import shutil
    # shutil.rmtree(test_chats_dir, ignore_errors=True)


@pytest.fixture
def client(app):
    """
    Flask test client for making HTTP requests.
    
    Usage:
        response = client.get('/health')
        response = client.post('/generate', json={'prompt': 'test'})
    """
    return app.test_client()


@pytest.fixture
def app_context(app):
    """
    Flask application context for testing request-dependent code.
    """
    with app.app_context():
        yield


# =============================================================================
# MOCK OLLAMA FIXTURES
# =============================================================================

@pytest.fixture
def mock_ollama_response():
    """
    Standard mock response for Ollama API.
    """
    return {
        'response': 'This is a test response from the mocked Ollama API.',
        'done': True,
        'context': [1, 2, 3],
        'total_duration': 1000000000,
        'load_duration': 100000000,
        'prompt_eval_count': 10,
        'eval_count': 20
    }


@pytest.fixture
def mock_ollama(mock_ollama_response):
    """
    Mock the Ollama API to avoid actual LLM calls during tests.
    
    Usage:
        def test_generate(mock_ollama, client):
            response = client.post('/generate', json={'prompt': 'test'})
            # Response will use mocked Ollama data
    """
    with patch('requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_ollama_response
        mock_response.iter_lines.return_value = [
            json.dumps(mock_ollama_response).encode()
        ]
        mock_post.return_value = mock_response
        yield mock_post


@pytest.fixture
def mock_ollama_streaming():
    """
    Mock Ollama API for streaming responses.
    """
    def create_streaming_response(chunks: list):
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_lines.return_value = [
                json.dumps({'response': chunk, 'done': i == len(chunks) - 1}).encode()
                for i, chunk in enumerate(chunks)
            ]
            mock_post.return_value = mock_response
            return mock_post
    
    return create_streaming_response


# =============================================================================
# TIME MANIPULATION FIXTURES
# =============================================================================

@pytest.fixture
def frozen_time():
    """
    Fixture to freeze time for deterministic timestamp testing.
    
    Usage:
        with frozen_time.freeze('2026-02-05 12:00:00'):
            # time.time() will return frozen value
    """
    from freezegun import freeze_time
    return freeze_time


# =============================================================================
# TEST DATA FIXTURES
# =============================================================================

@pytest.fixture
def sample_chat_data():
    """
    Sample chat data for storage tests.
    """
    return {
        'id': 'test-chat-001',
        'title': 'Test Conversation',
        'messages': [
            {'role': 'user', 'content': 'Hello, Trinity!'},
            {'role': 'assistant', 'content': 'Hello! How can I help you today?'}
        ],
        'created': int(time.time() * 1000),
        'updated': int(time.time() * 1000)
    }


@pytest.fixture
def sample_user_memory():
    """
    Sample user memory data for memory tests.
    """
    return {
        'facts': [
            'User prefers Python over JavaScript',
            'User is working on a decentralized AI project'
        ],
        'preferences': {
            'language': 'Python',
            'verbosity': 'detailed'
        }
    }


# =============================================================================
# UTILITY FIXTURES
# =============================================================================

@pytest.fixture
def assert_response_ok():
    """
    Helper to assert common response properties.
    """
    def _assert_ok(response, expected_status=200):
        assert response.status_code == expected_status, \
            f"Expected {expected_status}, got {response.status_code}: {response.data}"
        return response.get_json()
    
    return _assert_ok


@pytest.fixture
def assert_response_error():
    """
    Helper to assert error response properties.
    """
    def _assert_error(response, expected_status, expected_error_contains=None):
        assert response.status_code == expected_status, \
            f"Expected {expected_status}, got {response.status_code}"
        
        data = response.get_json()
        assert 'error' in data or 'success' in data
        
        if expected_error_contains:
            error_msg = data.get('error', '') or data.get('details', '')
            assert expected_error_contains.lower() in error_msg.lower(), \
                f"Expected error to contain '{expected_error_contains}', got: {error_msg}"
        
        return data
    
    return _assert_error
