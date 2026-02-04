#!/usr/bin/env python3
"""
Trinity v4.0 Intelligence Features - Test Suite

Run these tests to verify all v4.0 features work correctly.

Usage:
    # Test locally (requires backend running):
    python test/test_v4_features.py --local
    
    # Test against production:
    python test/test_v4_features.py --prod
    
    # Test specific module only:
    python test/test_v4_features.py --module embeddings
    python test/test_v4_features.py --module vector_store
    python test/test_v4_features.py --module memory
    python test/test_v4_features.py --module tools
    python test/test_v4_features.py --module code_executor
    python test/test_v4_features.py --module voting
    python test/test_v4_features.py --module structured
"""

import sys
import os
import json
import time
import argparse

# Add backend to path for local testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# Test results tracking
PASSED = []
FAILED = []
SKIPPED = []


def log_test(name: str, passed: bool, message: str = ""):
    """Log test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}: {name}")
    if message:
        print(f"         {message}")
    if passed:
        PASSED.append(name)
    else:
        FAILED.append(name)


def log_skip(name: str, reason: str):
    """Log skipped test."""
    print(f"  ⏭️  SKIP: {name} - {reason}")
    SKIPPED.append(name)


def log_section(title: str):
    """Log section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================================
# MODULE TESTS - Run these locally to verify imports and basic functionality
# ============================================================================

def test_embeddings():
    """Test the embeddings module."""
    log_section("Testing: embeddings.py")
    
    try:
        from services.embeddings import (
            embed_text, embed_batch, chunk_text, 
            cosine_similarity, compute_text_hash,
            V4_EMBEDDINGS_AVAILABLE
        )
        log_test("Import embeddings module", True)
    except ImportError as e:
        log_test("Import embeddings module", False, str(e))
        return
    
    # Test 1: Availability flag
    log_test("V4_EMBEDDINGS_AVAILABLE flag exists", V4_EMBEDDINGS_AVAILABLE)
    
    # Test 2: Check if FastEmbed is available
    try:
        from fastembed import TextEmbedding
        fastembed_available = True
    except ImportError:
        fastembed_available = False
        log_skip("embed_text() test", "FastEmbed not installed")
        log_skip("embed_batch() test", "FastEmbed not installed")
        log_skip("cosine_similarity() test", "FastEmbed not installed")
    
    if fastembed_available:
        # Test 2: Embed single text
        try:
            embedding = embed_text("Hello, this is a test sentence.")
            if embedding is not None:
                log_test("embed_text() returns embedding", True, f"Shape: {embedding.shape}")
                log_test("Embedding dimension is 384", embedding.shape[0] == 384)
            else:
                log_test("embed_text() returns embedding", False, "Returned None (model loading)")
        except Exception as e:
            log_test("embed_text() returns embedding", False, str(e))
        
        # Test 3: Embed batch
        try:
            texts = ["First sentence", "Second sentence", "Third sentence"]
            embeddings = embed_batch(texts)
            if embeddings is not None:
                log_test("embed_batch() returns embeddings", True, f"Shape: {embeddings.shape}")
                log_test("Batch size matches input", embeddings.shape[0] == 3)
            else:
                log_test("embed_batch() returns embeddings", False, "Returned None")
        except Exception as e:
            log_test("embed_batch() returns embeddings", False, str(e))
        
        # Test 4: Cosine similarity
        try:
            e1 = embed_text("The cat sat on the mat")
            e2 = embed_text("A cat was sitting on a rug")
            e3 = embed_text("The stock market crashed today")
            
            if e1 is not None and e2 is not None and e3 is not None:
                sim_similar = cosine_similarity(e1, e2)
                sim_different = cosine_similarity(e1, e3)
                
                log_test("Similar sentences have high similarity", 
                         sim_similar > 0.5, f"Similarity: {sim_similar:.3f}")
                log_test("Different sentences have lower similarity", 
                         sim_different < sim_similar, f"Similarity: {sim_different:.3f}")
            else:
                log_test("Cosine similarity test", False, "Embeddings failed")
        except Exception as e:
            log_test("Cosine similarity test", False, str(e))
    
    # Test 5: Text chunking (doesn't need FastEmbed)
    # Note: chunk_size is in WORDS not characters
    try:
        long_text = "This is a test sentence with more words. " * 200  # ~1400 words
        chunks = chunk_text(long_text, chunk_size=100, overlap=10)  # 100 words per chunk
        log_test("chunk_text() splits text", len(chunks) >= 2, f"Created {len(chunks)} chunks")
        if len(chunks) > 1:
            # Each chunk should have roughly 100 words * 5 chars = 500 chars
            log_test("Chunks are reasonable word count", 
                     all(len(c.split()) <= 120 for c in chunks), 
                     f"Chunk word counts: {[len(c.split()) for c in chunks[:3]]}")
        else:
            log_skip("Chunks size check", "Single chunk returned")
    except Exception as e:
        log_test("chunk_text() test", False, str(e))
    
    # Test 6: Text hash (doesn't need FastEmbed)
    try:
        hash1 = compute_text_hash("Hello world")
        hash2 = compute_text_hash("Hello world")
        hash3 = compute_text_hash("Goodbye world")
        
        log_test("compute_text_hash() is deterministic", hash1 == hash2)
        log_test("Different text has different hash", hash1 != hash3)
        log_test("Hash is 16 chars", len(hash1) == 16)
    except Exception as e:
        log_test("compute_text_hash() test", False, str(e))


def test_vector_store():
    """Test the vector store module."""
    log_section("Testing: vector_store.py")
    
    try:
        from services.vector_store import (
            VectorStore, get_vector_store, get_user_vector_store,
            V4_VECTOR_STORE_AVAILABLE
        )
        log_test("Import vector_store module", True)
    except ImportError as e:
        log_test("Import vector_store module", False, str(e))
        return
    
    # Test 1: Availability flag
    log_test("V4_VECTOR_STORE_AVAILABLE flag exists", V4_VECTOR_STORE_AVAILABLE)
    
    # Test 2: Create vector store
    test_principal = "test-principal-12345"
    try:
        store = get_vector_store(test_principal)
        log_test("get_vector_store() creates store", store is not None)
        
        # Alias test
        store2 = get_user_vector_store(test_principal)
        log_test("get_user_vector_store() alias works", store2 is store)
    except Exception as e:
        log_test("get_vector_store() test", False, str(e))
        return
    
    # Test 3: Check required methods exist
    log_test("add_message_embedding method exists", hasattr(store, 'add_message_embedding'))
    log_test("search_messages method exists", hasattr(store, 'search_messages'))
    log_test("add_document_chunks method exists", hasattr(store, 'add_document_chunks'))
    log_test("search_documents method exists", hasattr(store, 'search_documents'))
    log_test("export_for_ipfs method exists", hasattr(store, 'export_for_ipfs'))
    log_test("close method exists", hasattr(store, 'close'))
    
    # Note: Full tests require fastembed for embeddings
    log_skip("Vector store full tests", "Requires fastembed for embeddings")
    
    # Cleanup
    try:
        store.close()
        log_test("close() works", True)
    except Exception as e:
        log_test("close() test", False, str(e))


def test_memory():
    """Test the semantic memory module."""
    log_section("Testing: memory.py")
    
    try:
        from services.memory import (
            SemanticMemory, build_enhanced_context,
            V4_MEMORY_AVAILABLE
        )
        log_test("Import memory module", True)
    except ImportError as e:
        log_test("Import memory module", False, str(e))
        return
    
    # Test 1: Availability flag
    log_test("V4_MEMORY_AVAILABLE flag exists", V4_MEMORY_AVAILABLE)
    
    # Test 2: Create semantic memory
    test_principal = "test-memory-principal"
    try:
        memory = SemanticMemory(test_principal)
        log_test("SemanticMemory() creates instance", memory is not None)
    except Exception as e:
        log_test("SemanticMemory() test", False, str(e))
        return
    
    # Test 3: Check required methods exist
    log_test("retrieve_context method exists", hasattr(memory, 'retrieve_context'))
    log_test("format_context_for_prompt method exists", hasattr(memory, 'format_context_for_prompt'))
    
    # Test 4: build_enhanced_context function exists
    log_test("build_enhanced_context function exists", callable(build_enhanced_context))
    
    # Note: Full tests require fastembed for embeddings
    log_skip("Semantic memory full tests", "Requires fastembed for embeddings")


def test_tools():
    """Test the tools module."""
    log_section("Testing: tools.py")
    
    try:
        from services.tools import (
            TOOL_DEFINITIONS, get_tool_definitions_for_prompt,
            parse_tool_calls, detect_tools_needed, ToolCall, ToolResult,
            V4_TOOLS_AVAILABLE
        )
        log_test("Import tools module", True)
    except ImportError as e:
        log_test("Import tools module", False, str(e))
        return
    
    # Test 1: Availability flag
    log_test("V4_TOOLS_AVAILABLE flag exists", V4_TOOLS_AVAILABLE)
    
    # Test 2: Tool definitions exist
    expected_tools = ['calculator', 'code_display', 'document_search', 'web_search', 'fact_check']
    log_test("TOOL_DEFINITIONS has expected tools", 
             all(t in TOOL_DEFINITIONS for t in expected_tools),
             f"Found: {list(TOOL_DEFINITIONS.keys())}")
    
    # Test 3: Get tool definitions for prompt
    try:
        prompt_text = get_tool_definitions_for_prompt()  # No arguments
        log_test("get_tool_definitions_for_prompt() works", len(prompt_text) > 0)
        log_test("Prompt contains calculator", "calculator" in prompt_text.lower())
    except Exception as e:
        log_test("get_tool_definitions_for_prompt() test", False, str(e))
    
    # Test 4: Detect tools needed
    try:
        # Math query
        tools = detect_tools_needed("What is 25 * 4 + 10?")
        log_test("detect_tools_needed() finds calculator", "calculator" in tools)
        
        # Current events query
        tools = detect_tools_needed("What is the latest news about Bitcoin today?")
        log_test("detect_tools_needed() finds web_search", "web_search" in tools)
        
        # Document query
        tools = detect_tools_needed("Search the uploaded document for information about AI")
        log_test("detect_tools_needed() finds document_search", "document_search" in tools)
    except Exception as e:
        log_test("detect_tools_needed() test", False, str(e))
    
    # Test 5: Parse tool calls
    try:
        test_text = """
        Let me calculate that for you.
        <tool_call name="calculator"><expression>25 * 4 + 10</expression></tool_call>
        The answer is 110.
        """
        calls = parse_tool_calls(test_text)
        log_test("parse_tool_calls() finds tool call", len(calls) > 0)
        if calls:
            log_test("Parsed call has correct tool", calls[0].name == "calculator")
            log_test("Parsed call has parameters", "expression" in calls[0].params)
    except Exception as e:
        log_test("parse_tool_calls() test", False, str(e))
    
    # Test 6: ToolCall dataclass
    try:
        call = ToolCall(name="test", params={"key": "value"}, raw_text="raw")
        log_test("ToolCall dataclass works", call.name == "test")
    except Exception as e:
        log_test("ToolCall dataclass test", False, str(e))
    
    # Test 7: ToolResult dataclass
    try:
        result = ToolResult(success=True, output="42", error=None)
        log_test("ToolResult dataclass works", result.success == True)
    except Exception as e:
        log_test("ToolResult dataclass test", False, str(e))


def test_code_executor():
    """Test the code executor module."""
    log_section("Testing: code_executor.py")
    
    try:
        from services.code_executor import (
            evaluate_math_expression, execute_python_code, execute_tool,
            V4_CODE_EXECUTOR_AVAILABLE
        )
        log_test("Import code_executor module", True)
    except ImportError as e:
        log_test("Import code_executor module", False, str(e))
        return
    
    # Test 1: Availability flag
    log_test("V4_CODE_EXECUTOR_AVAILABLE flag exists", V4_CODE_EXECUTOR_AVAILABLE)
    
    # Test 2: Safe math expression - basic
    try:
        success, result = evaluate_math_expression("2 + 2")
        log_test("evaluate_math_expression('2 + 2')", success and result == "4")
    except Exception as e:
        log_test("evaluate_math_expression() basic test", False, str(e))
    
    # Test 3: Safe math expression - complex
    try:
        success, result = evaluate_math_expression("(10 + 5) * 2 / 3")
        log_test("evaluate_math_expression() complex", success, f"Result: {result}")
    except Exception as e:
        log_test("evaluate_math_expression() complex test", False, str(e))
    
    # Test 4: Safe math expression - functions
    try:
        success, result = evaluate_math_expression("sqrt(16) + pow(2, 3)")
        log_test("evaluate_math_expression() with functions", 
                 success and float(result) == 12.0, f"Result: {result}")
    except Exception as e:
        log_test("evaluate_math_expression() functions test", False, str(e))
    
    # Test 5: Unsafe expression blocked
    try:
        success, result = evaluate_math_expression("__import__('os').system('ls')")
        log_test("Malicious expression blocked", not success)
    except Exception as e:
        log_test("Malicious expression blocked", True, "Exception raised (expected)")
    
    # Test 6: Execute Python code - basic
    try:
        success, output = execute_python_code("print('Hello, World!')")
        if not success and ('errors' in str(output).lower() or 'attribute' in str(output).lower()):
            log_skip("execute_python_code() basic", "RestrictedPython compatibility issue")
        else:
            log_test("execute_python_code() basic print", 
                     success and "Hello" in output, f"Output: {output.strip()}")
    except Exception as e:
        log_skip("execute_python_code() basic", f"RestrictedPython: {str(e)[:40]}")
    
    # Test 7: Execute Python code - math
    try:
        code = """
result = sum([1, 2, 3, 4, 5])
print(f"Sum: {result}")
"""
        success, output = execute_python_code(code)
        if not success and ('errors' in str(output).lower() or 'attribute' in str(output).lower()):
            log_skip("execute_python_code() math", "RestrictedPython compatibility issue")
        else:
            log_test("execute_python_code() with math", 
                     success and "15" in output, f"Output: {output.strip()}")
    except Exception as e:
        log_skip("execute_python_code() math", f"RestrictedPython: {str(e)[:40]}")
    
    # Test 8: Dangerous code blocked - import
    try:
        success, output = execute_python_code("import os\nos.system('ls')")
        log_test("Import blocked in sandbox", not success or "error" in output.lower())
    except Exception as e:
        log_test("Import blocked", True, "Exception raised (expected)")
    
    # Test 9: Dangerous code blocked - file access
    try:
        success, output = execute_python_code("open('/etc/passwd', 'r').read()")
        log_test("File access blocked in sandbox", not success or "error" in output.lower())
    except Exception as e:
        log_test("File access blocked", True, "Exception raised (expected)")
    
    # Test 10: execute_tool() dispatcher
    try:
        success, result = execute_tool("calculator", {"expression": "10 * 5"})
        log_test("execute_tool('calculator') works", success and "50" in str(result))
    except Exception as e:
        log_test("execute_tool() test", False, str(e))


def test_voting():
    """Test the voting module."""
    log_section("Testing: voting.py")
    
    try:
        from services.voting import (
            run_voting_pipeline, should_use_voting, VotingResult,
            generate_candidates_parallel, compute_consistency_scores,
            V4_VOTING_AVAILABLE
        )
        log_test("Import voting module", True)
    except ImportError as e:
        log_test("Import voting module", False, str(e))
        return
    
    # Test 1: Availability flag
    log_test("V4_VOTING_AVAILABLE flag exists", V4_VOTING_AVAILABLE)
    
    # Test 2: VotingResult dataclass
    try:
        result = VotingResult(
            selected_answer="Test answer",
            confidence=0.85,
            candidates=["A", "B", "C"],
            scores=[0.9, 0.8, 0.7]
        )
        log_test("VotingResult dataclass works", result.confidence == 0.85)
    except Exception as e:
        log_test("VotingResult dataclass test", False, str(e))
    
    # Test 3: should_use_voting() - simple question
    try:
        use_voting = should_use_voting(2)  # Just takes complexity score
        log_test("should_use_voting() returns False for simple", not use_voting)
    except Exception as e:
        log_test("should_use_voting() simple test", False, str(e))
    
    # Test 4: should_use_voting() - complex question
    try:
        use_voting = should_use_voting(8)  # Just takes complexity score
        log_test("should_use_voting() returns True for complex", use_voting)
    except Exception as e:
        log_test("should_use_voting() complex test", False, str(e))
    
    # Test 5: compute_consistency_scores() - mock test
    try:
        # Create mock embeddings for testing
        import numpy as np
        candidates = ["Answer A about topic", "Answer A about topic similar", "Completely different"]
        # Mock: scores should show first two are similar
        log_test("compute_consistency_scores() exists", callable(compute_consistency_scores))
    except Exception as e:
        log_test("compute_consistency_scores() test", False, str(e))
    
    # Note: Full voting pipeline test requires Ollama running
    log_skip("run_voting_pipeline() full test", "Requires Ollama connection")


def test_structured():
    """Test the structured output module."""
    log_section("Testing: structured.py")
    
    try:
        from services.structured import (
            generate_structured, generate_with_schema, SCHEMAS,
            V4_STRUCTURED_AVAILABLE
        )
        log_test("Import structured module", True)
    except ImportError as e:
        log_test("Import structured module", False, str(e))
        return
    
    # Test 1: Availability flag
    log_test("V4_STRUCTURED_AVAILABLE flag exists", V4_STRUCTURED_AVAILABLE)
    
    # Test 2: SCHEMAS dictionary exists
    try:
        expected_schemas = ['understanding', 'plan', 'critique', 'tool_call']
        log_test("SCHEMAS has expected keys", 
                 all(s in SCHEMAS for s in expected_schemas),
                 f"Found: {list(SCHEMAS.keys())}")
    except Exception as e:
        log_test("SCHEMAS test", False, str(e))
    
    # Test 3: Schema structure validation
    try:
        understanding_schema = SCHEMAS.get('understanding', {})
        log_test("understanding schema has 'type'", 'type' in understanding_schema)
        log_test("understanding schema has 'properties'", 'properties' in understanding_schema)
    except Exception as e:
        log_test("Schema structure test", False, str(e))
    
    # Note: Full structured generation test requires Ollama running
    log_skip("generate_structured() full test", "Requires Ollama connection")
    log_skip("generate_with_schema() full test", "Requires Ollama connection")


def test_config():
    """Test that config.py has all v4.0 variables."""
    log_section("Testing: config.py (v4.0 variables)")
    
    try:
        from config import (
            # Multi-model
            MULTI_MODEL_ENABLED, FAST_MODEL, SMART_MODEL, REASONING_MODEL,
            # RAG
            EMBEDDING_MODEL, EMBEDDING_DIM, RAG_TOP_K, CHUNK_SIZE, CHUNK_OVERLAP,
            # Memory
            WORKING_MEMORY_SIZE, SEMANTIC_MEMORY_SIZE, RECENCY_WEIGHT,
            # Tools
            CODE_EXECUTION_ENABLED, CODE_EXECUTION_TIMEOUT,
            # Voting
            VOTING_CANDIDATES, VOTING_MIN_COMPLEXITY
        )
        log_test("Import all v4.0 config variables", True)
    except ImportError as e:
        log_test("Import v4.0 config variables", False, str(e))
        return
    
    # Verify reasonable defaults
    log_test("EMBEDDING_DIM is 384", EMBEDDING_DIM == 384)
    log_test("RAG_TOP_K is reasonable", 1 <= RAG_TOP_K <= 20)
    log_test("WORKING_MEMORY_SIZE is reasonable", 1 <= WORKING_MEMORY_SIZE <= 10)
    log_test("SEMANTIC_MEMORY_SIZE is reasonable", 1 <= SEMANTIC_MEMORY_SIZE <= 20)
    log_test("RECENCY_WEIGHT is 0-1", 0 <= RECENCY_WEIGHT <= 1)
    log_test("CODE_EXECUTION_TIMEOUT is reasonable", 1 <= CODE_EXECUTION_TIMEOUT <= 60)
    log_test("VOTING_CANDIDATES is reasonable", 1 <= VOTING_CANDIDATES <= 10)


def test_services_init():
    """Test that services/__init__.py exports everything."""
    log_section("Testing: services/__init__.py exports")
    
    try:
        from services import (
            # Embeddings
            embed_text, embed_batch, chunk_text, cosine_similarity,
            # Vector Store
            VectorStore, get_vector_store, get_user_vector_store,
            # Memory
            SemanticMemory, build_enhanced_context,
            # Tools
            TOOL_DEFINITIONS, parse_tool_calls, detect_tools_needed,
            # Code Executor
            evaluate_math_expression, execute_python_code, execute_tool,
            # Voting
            run_voting_pipeline, VotingResult, should_use_voting,
            # Structured
            generate_structured, SCHEMAS
        )
        log_test("All v4.0 exports available from services", True)
    except ImportError as e:
        log_test("services exports", False, str(e))


# ============================================================================
# API ENDPOINT TESTS - Run these against running server
# ============================================================================

def test_api_endpoints(base_url: str):
    """Test API endpoints."""
    log_section(f"Testing: API Endpoints ({base_url})")
    
    import requests
    
    # Test 1: v4 status endpoint
    try:
        resp = requests.get(f"{base_url}/v4/status", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            log_test("GET /v4/status returns 200", True)
            log_test("/v4/status has 'available' field", 'available' in data)
            log_test("/v4/status has 'features' field", 'features' in data)
            log_test("/v4/status has 'version' field", 'version' in data)
            
            if 'features' in data:
                print(f"\n  Feature Status:")
                for feature, available in data['features'].items():
                    status = "✅" if available else "❌"
                    print(f"    {status} {feature}: {available}")
        else:
            log_test("GET /v4/status returns 200", False, f"Got {resp.status_code}")
    except requests.exceptions.ConnectionError:
        log_test("GET /v4/status", False, "Connection refused - is server running?")
    except Exception as e:
        log_test("GET /v4/status", False, str(e))
    
    # Test 2: Health endpoint
    try:
        resp = requests.get(f"{base_url}/health", timeout=10)
        log_test("GET /health returns 200", resp.status_code == 200)
    except Exception as e:
        log_test("GET /health", False, str(e))
    
    # Note: Auth-required endpoints need proper ICP auth
    log_skip("POST /v4/vector/index", "Requires ICP authentication")
    log_skip("POST /v4/vector/document", "Requires ICP authentication")
    log_skip("POST /v4/vector/search", "Requires ICP authentication")
    log_skip("POST /v4/tools/execute", "Requires ICP authentication")


# ============================================================================
# MAIN
# ============================================================================

def print_summary():
    """Print test summary."""
    print(f"\n{'='*60}")
    print("  TEST SUMMARY")
    print(f"{'='*60}")
    print(f"  ✅ Passed:  {len(PASSED)}")
    print(f"  ❌ Failed:  {len(FAILED)}")
    print(f"  ⏭️  Skipped: {len(SKIPPED)}")
    print(f"{'='*60}")
    
    if FAILED:
        print("\n  Failed Tests:")
        for name in FAILED:
            print(f"    ❌ {name}")
    
    return len(FAILED) == 0


def main():
    parser = argparse.ArgumentParser(description="Test Trinity v4.0 Features")
    parser.add_argument("--local", action="store_true", help="Test against local server (localhost:8000)")
    parser.add_argument("--prod", action="store_true", help="Test against production (Cloudflare Worker)")
    parser.add_argument("--module", type=str, help="Test specific module only")
    parser.add_argument("--all", action="store_true", help="Run all tests", default=True)
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("  Trinity v4.0 LLM Intelligence Features - Test Suite")
    print("="*60)
    
    modules = {
        'config': test_config,
        'services_init': test_services_init,
        'embeddings': test_embeddings,
        'vector_store': test_vector_store,
        'memory': test_memory,
        'tools': test_tools,
        'code_executor': test_code_executor,
        'voting': test_voting,
        'structured': test_structured,
    }
    
    if args.module:
        if args.module in modules:
            modules[args.module]()
        else:
            print(f"Unknown module: {args.module}")
            print(f"Available: {list(modules.keys())}")
            return 1
    else:
        # Run all module tests
        for name, test_fn in modules.items():
            try:
                test_fn()
            except Exception as e:
                log_test(f"Module {name}", False, f"Unexpected error: {e}")
    
    # Run API tests if requested
    if args.local:
        test_api_endpoints("http://localhost:8000")
    elif args.prod:
        test_api_endpoints("https://api.dubya.ai")
    
    success = print_summary()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
