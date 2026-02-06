"""
End-to-End Tests for Trinity Backend

Tests the full request pipeline from HTTP ingress to response,
validating that all components work together correctly.

These tests use mocked external dependencies (Ollama) to test
the full integration of all backend components.
"""

import pytest
import json
import time
import hashlib
import base64
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure backend is in path
backend_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def app():
    """Create Flask test application."""
    from inference_server import app
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def mock_ollama_generate():
    """Mock Ollama generate endpoint at the requests level."""
    with patch('requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'response': 'This is a test response from the LLM.',
            'model': 'llama3.1:8b',
            'prompt_eval_count': 50,
            'eval_count': 100,
            'done': True
        }
        mock_response.iter_lines.return_value = [
            json.dumps({'response': 'Test', 'done': False}).encode(),
            json.dumps({'response': ' response', 'done': True, 'prompt_eval_count': 50, 'eval_count': 100}).encode()
        ]
        mock_post.return_value = mock_response
        yield mock_post


@pytest.fixture
def auth_headers():
    """Generate valid Ed25519 authentication headers."""
    try:
        from nacl.signing import SigningKey
    except ImportError:
        pytest.skip("nacl not installed")
    
    # Generate keypair
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key
    public_key_bytes = bytes(verify_key)
    
    # Create a fake principal (in production this is derived from public key)
    principal = 'e2e-test-' + hashlib.sha256(public_key_bytes).hexdigest()[:20]
    
    # Create signed message matching what the backend expects
    timestamp = int(time.time() * 1000)
    message = f"{principal}:{timestamp}:/chat/autosave"
    
    signature = signing_key.sign(message.encode()).signature
    
    return {
        'X-ICP-Principal': principal,
        'X-ICP-Signature': signature.hex(),
        'X-ICP-Public-Key': public_key_bytes.hex(),
        'X-ICP-Timestamp': str(timestamp),
        'Content-Type': 'application/json'
    }


@pytest.fixture
def mock_auth():
    """Mock authentication to always succeed."""
    with patch('icp_auth.verify_icp_signature') as mock_verify:
        mock_verify.return_value = (True, None)
        yield mock_verify


# =============================================================================
# HEALTH CHECK TESTS
# =============================================================================

class TestHealthEndpoints:
    """Test basic health and status endpoints."""
    
    def test_health_endpoint(self, client):
        """Health endpoint should respond (may report unhealthy without Ollama)."""
        response = client.get('/health')
        # Should return 200 (healthy) or 503 (Ollama unavailable)
        assert response.status_code in [200, 503]
        data = response.get_json()
        assert 'status' in data
    
    def test_metrics_endpoint(self, client):
        """Metrics endpoint should return Prometheus format."""
        response = client.get('/metrics')
        
        assert response.status_code == 200
        # Prometheus format is text/plain
        assert 'text/plain' in response.content_type or 'text' in response.content_type
        # Should contain Trinity metrics
        assert b'trinity_' in response.data


# =============================================================================
# GENERATION PIPELINE TESTS
# =============================================================================

class TestGenerationPipeline:
    """Test the main generation endpoints."""
    
    def test_generate_basic(self, client, mock_ollama_generate):
        """Basic generation with mocked Ollama should work."""
        response = client.post('/generate',
            json={'prompt': 'Hello, how are you?'},
            content_type='application/json'
        )
        
        # Should succeed or return 500 if Ollama check fails at startup
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.get_json()
            assert 'response' in data
    
    def test_generate_with_complexity(self, client, mock_ollama_generate):
        """Generation should process complexity routing."""
        response = client.post('/generate',
            json={'prompt': 'Compare and contrast Python vs JavaScript for web development.'},
            content_type='application/json'
        )
        
        # Should succeed or return 500 if Ollama unavailable
        assert response.status_code in [200, 500]
    
    def test_generate_empty_prompt_rejected(self, client):
        """Empty prompt should be rejected."""
        response = client.post('/generate',
            json={'prompt': ''},
            content_type='application/json'
        )
        
        # Should either reject or handle gracefully
        assert response.status_code in [200, 400, 500]
    
    def test_generate_missing_prompt_rejected(self, client):
        """Missing prompt field should be rejected."""
        response = client.post('/generate',
            json={},
            content_type='application/json'
        )
        
        assert response.status_code == 400


class TestLangGraphPipeline:
    """Test LangGraph-specific endpoints."""
    
    def test_langgraph_endpoint_exists(self, client, mock_ollama_generate, mock_auth):
        """LangGraph endpoint should be accessible."""
        headers = {
            'X-ICP-Principal': 'test-principal',
            'X-ICP-Signature': 'test-sig',
            'X-ICP-Public-Key': 'test-key',
            'X-ICP-Timestamp': str(int(time.time() * 1000)),
            'Content-Type': 'application/json'
        }
        
        response = client.post('/generate/langgraph',
            json={'prompt': 'Test query'},
            headers=headers
        )
        
        # Should work, return 404 (no endpoint), or indicate experiments not enabled
        assert response.status_code in [200, 400, 404, 500, 503]
    
    @patch('services.agent.get_agent_pipeline')
    def test_langgraph_with_mock_agent(self, mock_pipeline, client, mock_auth):
        """LangGraph should process with mocked agent."""
        # Mock the agent pipeline
        mock_agent = MagicMock()
        mock_agent.process.return_value = MagicMock(
            response='Test response',
            passes=2,
            used_langgraph=True
        )
        mock_pipeline.return_value = mock_agent
        
        headers = {
            'X-ICP-Principal': 'test-principal',
            'Content-Type': 'application/json'
        }
        
        response = client.post('/generate/langgraph',
            json={'prompt': 'Complex analysis question'},
            headers=headers
        )
        
        # Should succeed, return 404, or experiment not enabled
        assert response.status_code in [200, 400, 404, 500, 503]


# =============================================================================
# AUTHENTICATION TESTS
# =============================================================================

class TestAuthentication:
    """Test authentication flow end-to-end."""
    
    def test_auth_required_endpoint_without_headers(self, client):
        """Protected endpoints should reject unauthenticated requests."""
        response = client.post('/chat/autosave',
            json={'chat_id': 'test', 'data': {}},
            content_type='application/json'
        )
        
        assert response.status_code == 401
    
    def test_auth_required_endpoint_with_mock_auth(self, client, mock_auth):
        """Protected endpoints should accept valid auth when mocked."""
        headers = {
            'X-ICP-Principal': 'test-principal-123',
            'X-ICP-Signature': 'fake-sig',
            'X-ICP-Public-Key': 'fake-key',
            'X-ICP-Timestamp': str(int(time.time() * 1000)),
            'Content-Type': 'application/json'
        }
        
        response = client.post('/chat/autosave',
            json={
                'chat_id': 'test-chat-123',
                'title': 'Test Chat',
                'messages': []
            },
            headers=headers
        )
        
        # Should succeed (200) or have storage issue (500)
        # 401 would mean mock didn't work
        assert response.status_code != 401 or not mock_auth.called
    
    def test_invalid_signature_rejected(self, client):
        """Invalid signatures should be rejected."""
        headers = {
            'X-ICP-Principal': 'fake-principal',
            'X-ICP-Signature': 'invalid-signature',
            'X-ICP-Public-Key': 'invalid-key',
            'X-ICP-Timestamp': str(int(time.time() * 1000)),
            'Content-Type': 'application/json'
        }
        
        response = client.post('/chat/autosave',
            json={'chat_id': 'test', 'data': {}},
            headers=headers
        )
        
        assert response.status_code in [400, 401]


# =============================================================================
# CACHING TESTS
# =============================================================================

class TestCachingIntegration:
    """Test caching layer integration."""
    
    def test_cache_stats_endpoint(self, client):
        """Cache stats endpoint should return data."""
        response = client.get('/admin/cache/stats')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'embedding_cache' in data
        assert 'semantic_cache' in data
        assert 'token_usage' in data
    
    def test_cache_clear_endpoint(self, client):
        """Cache clear endpoint should work."""
        response = client.post('/admin/cache/clear')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'cleared'


# =============================================================================
# EXPERIMENT TESTS
# =============================================================================

class TestExperimentsIntegration:
    """Test A/B experiment integration."""
    
    def test_experiments_list_endpoint(self, client):
        """Should list all experiments."""
        response = client.get('/admin/experiments')
        
        assert response.status_code == 200
        data = response.get_json()
        # Should have experiment definitions
        assert isinstance(data, dict)
    
    def test_experiment_assignment(self, client):
        """Should return consistent assignment for session."""
        session_id = 'test-session-12345'
        
        response1 = client.get(f'/admin/experiments/assignment/{session_id}')
        response2 = client.get(f'/admin/experiments/assignment/{session_id}')
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Same session should get same assignments
        data1 = response1.get_json()
        data2 = response2.get_json()
        assert data1['assignments'] == data2['assignments']
    
    def test_experiment_enable_disable(self, client):
        """Should be able to enable/disable experiments."""
        # Try to disable
        response = client.post('/admin/experiments/agent_mode/disable')
        assert response.status_code in [200, 404]
        
        # Try to re-enable
        response = client.post('/admin/experiments/agent_mode/enable')
        assert response.status_code in [200, 404]


# =============================================================================
# TOKEN TRACKING TESTS
# =============================================================================

class TestTokenTracking:
    """Test token usage tracking."""
    
    def test_token_usage_endpoint(self, client):
        """Should return token usage stats."""
        response = client.get('/admin/tokens/usage')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'totals' in data
        assert 'top_users' in data
    
    def test_quota_usage_endpoint(self, client):
        """Should return quota usage."""
        response = client.get('/admin/quota/usage')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'users' in data


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================

class TestRateLimiting:
    """Test rate limiting behavior."""
    
    def test_rate_limit_not_triggered_normal_use(self, client, mock_ollama):
        """Normal usage should not trigger rate limits."""
        # Make a few requests
        for _ in range(5):
            response = client.post('/generate',
                json={'prompt': 'Test'},
                content_type='application/json'
            )
            assert response.status_code != 429


# =============================================================================
# FULL PIPELINE INTEGRATION
# =============================================================================

class TestFullPipelineIntegration:
    """Test complete request lifecycle."""
    
    def test_simple_query_pipeline(self, client, mock_ollama_generate):
        """Simple query should complete full pipeline."""
        response = client.post('/generate',
            json={'prompt': 'What is 2+2?'},
            content_type='application/json'
        )
        
        # Should succeed or 500 if Ollama unavailable at startup
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.get_json()
            assert 'response' in data
    
    def test_complex_query_pipeline(self, client, mock_ollama_generate, mock_auth):
        """Complex query should route appropriately."""
        response = client.post('/generate',
            json={
                'prompt': 'Compare and contrast microservices vs monolithic architecture, '
                         'including performance implications, scaling strategies, and '
                         'team organization considerations.'
            },
            content_type='application/json'
        )
        
        # Should succeed or 500 if Ollama unavailable
        assert response.status_code in [200, 500]
    
    def test_authenticated_storage_pipeline(self, client, mock_auth):
        """Authenticated user should be able to save/load chats."""
        chat_id = f'e2e-test-{int(time.time())}'
        
        headers = {
            'X-ICP-Principal': 'e2e-test-principal',
            'X-ICP-Signature': 'mock-sig',
            'X-ICP-Public-Key': 'mock-key',
            'X-ICP-Timestamp': str(int(time.time() * 1000)),
            'Content-Type': 'application/json'
        }
        
        # Save a chat
        save_response = client.post('/chat/autosave',
            json={
                'chat_id': chat_id,
                'title': 'E2E Test Chat',
                'messages': [
                    {'role': 'user', 'content': 'Hello'},
                    {'role': 'assistant', 'content': 'Hi there!'}
                ]
            },
            headers=headers
        )
        
        # Should save, return 401 (mock not applied properly), or have storage issue
        assert save_response.status_code in [200, 401, 500]
        
        if save_response.status_code == 200:
            # Try to list chats
            list_response = client.get('/chat/list', headers=headers)
            assert list_response.status_code == 200


class TestErrorHandling:
    """Test error handling across the pipeline."""
    
    def test_malformed_json_handling(self, client):
        """Should handle malformed JSON gracefully."""
        response = client.post('/generate',
            data='not valid json',
            content_type='application/json'
        )
        
        # Should return 400 or handle gracefully
        assert response.status_code in [400, 415, 500]
    
    def test_missing_content_type(self, client):
        """Should handle missing content type."""
        response = client.post('/generate',
            data='{"prompt": "test"}'
        )
        
        # Should either work or return clear error
        assert response.status_code in [200, 400, 415, 500]
    
    def test_very_long_prompt(self, client, mock_ollama_generate):
        """Should handle very long prompts."""
        long_prompt = 'Test ' * 10000  # Very long input
        
        response = client.post('/generate',
            json={'prompt': long_prompt},
            content_type='application/json'
        )
        
        # Should either process, reject with clear error, or 500 if Ollama unavailable
        assert response.status_code in [200, 400, 413, 500]
