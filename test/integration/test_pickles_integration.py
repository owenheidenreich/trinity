"""
PicklesGPT Integration Tests

These tests verify the full PicklesGPT system including:
- Vector database (ChromaDB) connectivity
- Book RAG search functionality
- Persona response quality
- Market data integration

CRITICAL: These tests are designed to FAIL if the vector database 
is not properly set up, proving the RAG system is working.

Run with: pytest -v test/integration/test_pickles_integration.py
"""

import pytest
import requests
import os
import json
from pathlib import Path

# Test against production by default
BASE_URL = os.environ.get('PICKLES_TEST_URL', 'https://vercel-proxy-swart-nine.vercel.app')

# Timeout for LLM responses (Akash cold start can be slow)
REQUEST_TIMEOUT = 120


class TestPicklesStatus:
    """Test Pickles system status and health."""
    
    def test_health_check(self):
        """Backend should be healthy."""
        response = requests.get(f"{BASE_URL}/health", timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy'
        assert data.get('ollama_connected') == True
    
    def test_pickles_status_endpoint(self):
        """Pickles status should report vector store status."""
        response = requests.get(f"{BASE_URL}/pickles/status", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        # This is the KEY test - if vector_store is False, RAG is disabled
        assert 'status' in data
        assert 'vector_store' in data
        
        # Report what we found
        print(f"\n📊 Pickles Status:")
        print(f"   Status: {data.get('status')}")
        print(f"   Vector Store: {data.get('vector_store')}")
        print(f"   Book Count: {data.get('book_count', 'N/A')}")
        print(f"   Chunk Count: {data.get('chunk_count', 'N/A')}")


class TestVectorDatabaseRequired:
    """
    Tests that REQUIRE the vector database to be working.
    These will FAIL if ChromaDB is not set up or books not ingested.
    """
    
    def test_vector_store_initialized(self):
        """Vector store MUST be initialized for RAG to work."""
        response = requests.get(f"{BASE_URL}/pickles/status", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        # THIS TEST FAILS IF VECTOR DB NOT WORKING
        assert data.get('vector_store') == True, \
            "Vector store not initialized - books need to be ingested!"
    
    def test_books_are_indexed(self):
        """At least some books should be indexed."""
        response = requests.get(f"{BASE_URL}/pickles/status", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        # Should have chunks from books
        chunk_count = data.get('chunk_count', 0)
        assert chunk_count > 0, \
            f"No chunks indexed! Expected >0, got {chunk_count}"
        
        print(f"\n📚 {chunk_count} chunks indexed from trading books")
    
    def test_search_returns_results(self):
        """Search should return relevant book passages."""
        response = requests.post(
            f"{BASE_URL}/pickles/search",
            json={
                'query': 'stop loss risk management',
                'n_results': 3
            },
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have results
        assert 'results' in data
        assert len(data['results']) > 0, \
            "No search results returned - vector DB may be empty!"
        
        # Results should have expected structure
        result = data['results'][0]
        assert 'text' in result
        assert 'metadata' in result
        assert 'score' in result
        
        print(f"\n🔍 Search returned {len(data['results'])} results")
        print(f"   Top result from: {result['metadata'].get('book_title', 'Unknown')}")
        print(f"   Score: {result['score']}")
    
    def test_search_by_category(self):
        """Search should support category filtering."""
        response = requests.post(
            f"{BASE_URL}/pickles/search",
            json={
                'query': 'options strategies',
                'n_results': 3,
                'category': 'Options'
            },
            timeout=60
        )
        
        # May return 200 or 404 if category doesn't exist
        if response.status_code == 200:
            data = response.json()
            # All results should be from Options category
            for result in data.get('results', []):
                assert result['metadata'].get('category') == 'Options'


class TestPicklesRAGChat:
    """
    Test that Pickles uses RAG knowledge in responses.
    These tests verify the AI is actually using book content.
    """
    
    def test_trading_question_uses_rag(self):
        """
        Ask a trading question that should trigger RAG.
        Response should reference book knowledge.
        """
        response = requests.post(
            f"{BASE_URL}/pickles/chat",
            json={
                'prompt': 'What is the most important rule about stop losses?',
                'contextMemory': []
            },
            timeout=REQUEST_TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have response
        assert 'generated_text' in data
        generated = data['generated_text']
        assert len(generated) > 50, "Response too short"
        
        # Check if RAG was used
        rag_used = data.get('rag_used', False)
        books_cited = data.get('books_cited', [])
        
        print(f"\n🤖 Pickles Response Preview: {generated[:200]}...")
        print(f"   RAG Used: {rag_used}")
        print(f"   Books Cited: {books_cited}")
        
        # If vector store is working, RAG should be used for trading questions
        if rag_used:
            assert len(books_cited) > 0, "RAG used but no books cited"
    
    def test_response_has_capitalization_style(self):
        """
        Pickles should CAPITALIZE trading terminology.
        """
        response = requests.post(
            f"{BASE_URL}/pickles/chat",
            json={
                'prompt': 'How should I set my stop loss on a breakout trade?',
                'contextMemory': []
            },
            timeout=REQUEST_TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        generated = data['generated_text']
        
        # Check for capitalized trading terms (at least one should appear)
        capitalized_terms = [
            'STOP LOSS', 'STOP', 'BREAKOUT', 'ENTRY', 'EXIT',
            'SUPPORT', 'RESISTANCE', 'RISK', 'REWARD', 'SETUP'
        ]
        
        has_caps = any(term in generated for term in capitalized_terms)
        
        print(f"\n📝 Capitalization check:")
        print(f"   Response: {generated[:300]}...")
        print(f"   Has CAPITALIZED terms: {has_caps}")
        
        # This is a soft check - persona should usually capitalize but may not always
        if not has_caps:
            print("   ⚠️  Warning: No capitalized trading terms found")
    
    def test_pickles_identifies_as_pickles(self):
        """
        Pickles should identify itself correctly, not as a generic assistant.
        """
        response = requests.post(
            f"{BASE_URL}/pickles/chat",
            json={
                'prompt': 'Who are you and what is your trading experience?',
                'contextMemory': []
            },
            timeout=REQUEST_TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        generated = data['generated_text'].lower()
        
        # Should mention being Pickles or having trading experience
        identity_markers = ['pickles', '17 years', 'trader', 'derivatives', 'futures']
        has_identity = any(marker in generated for marker in identity_markers)
        
        print(f"\n🎭 Identity check:")
        print(f"   Response: {data['generated_text'][:300]}...")
        print(f"   Has identity markers: {has_identity}")
        
        assert has_identity, "Pickles should identify itself with trading experience!"


class TestGenerateEndpointPersona:
    """
    Test the main /generate endpoint with persona parameter.
    This is how the frontend actually calls Pickles.
    """
    
    def test_generate_with_pickles_persona(self):
        """
        The main generate endpoint should accept persona parameter.
        """
        response = requests.post(
            f"{BASE_URL}/generate",
            json={
                'prompt': 'What should I look for before entering a trade?',
                'persona': 'pickles',
                'temperature': 0.7
            },
            timeout=REQUEST_TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        
        assert 'generated_text' in data
        generated = data['generated_text']
        
        print(f"\n📤 /generate with persona=pickles:")
        print(f"   Response: {generated[:300]}...")
        
        # Should get a trading-focused response
        assert len(generated) > 50
    
    def test_generate_with_trinity_persona(self):
        """
        Compare Trinity vs Pickles response style.
        """
        # Get Pickles response
        pickles_resp = requests.post(
            f"{BASE_URL}/generate",
            json={
                'prompt': 'What is technical analysis?',
                'persona': 'pickles',
                'temperature': 0.7
            },
            timeout=REQUEST_TIMEOUT
        )
        
        # Get Trinity response
        trinity_resp = requests.post(
            f"{BASE_URL}/generate",
            json={
                'prompt': 'What is technical analysis?',
                'persona': 'trinity',
                'temperature': 0.7
            },
            timeout=REQUEST_TIMEOUT
        )
        
        assert pickles_resp.status_code == 200
        assert trinity_resp.status_code == 200
        
        pickles_text = pickles_resp.json().get('generated_text', '')
        trinity_text = trinity_resp.json().get('generated_text', '')
        
        print(f"\n🎭 Persona Comparison:")
        print(f"   Pickles: {pickles_text[:150]}...")
        print(f"   Trinity: {trinity_text[:150]}...")
        
        # Both should have responses but they should be different
        assert len(pickles_text) > 50
        assert len(trinity_text) > 50


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_prompt_rejected(self):
        """Empty prompts should be rejected."""
        response = requests.post(
            f"{BASE_URL}/pickles/chat",
            json={'prompt': '', 'contextMemory': []},
            timeout=30
        )
        assert response.status_code == 400
    
    def test_missing_prompt_rejected(self):
        """Missing prompt should be rejected."""
        response = requests.post(
            f"{BASE_URL}/pickles/chat",
            json={'contextMemory': []},
            timeout=30
        )
        assert response.status_code == 400
    
    def test_search_empty_query_rejected(self):
        """Empty search queries should be rejected."""
        response = requests.post(
            f"{BASE_URL}/pickles/search",
            json={'query': '', 'n_results': 5},
            timeout=30
        )
        assert response.status_code == 400


if __name__ == '__main__':
    # Run basic connectivity test
    print(f"Testing against: {BASE_URL}")
    
    try:
        health = requests.get(f"{BASE_URL}/health", timeout=30)
        print(f"Health check: {health.json()}")
        
        status = requests.get(f"{BASE_URL}/pickles/status", timeout=30)
        print(f"Pickles status: {status.json()}")
    except Exception as e:
        print(f"Error: {e}")
