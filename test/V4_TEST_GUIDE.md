# Trinity v4.0 LLM Intelligence Upgrade - Test Guide

## Quick Start

```bash
# Run Python tests (local module testing)
cd /Users/owenheidenreich/Documents/Trinity/Trinity
source .venv/bin/activate
python test/test_v4_features.py

# Run curl tests against production
./test/test_v4_curl.sh

# Test specific module only
python test/test_v4_features.py --module embeddings
python test/test_v4_features.py --module code_executor
```

---

## What Was Added (Summary)

| Feature | Purpose | Files |
|---------|---------|-------|
| **FastEmbed Embeddings** | Convert text to vectors for similarity search | `embeddings.py` |
| **SQLite-VSS Vector Store** | Store & search embeddings per user | `vector_store.py` |
| **Semantic Memory** | Retrieve relevant past conversations | `memory.py` |
| **Tool Framework** | Calculator, code, search tools | `tools.py` |
| **Code Executor** | Safe sandboxed Python/math execution | `code_executor.py` |
| **Self-Consistency Voting** | Multiple answers, pick best one | `voting.py` |
| **Structured Output** | JSON schemas for LLM responses | `structured.py` |

---

## Feature Tests (Detailed)

### 1. Embeddings (`embeddings.py`)
**What it does**: Converts text into 384-dimensional vectors using FastEmbed (BAAI/bge-small-en-v1.5)

**Test it**:
```python
# In Python (with backend in path)
from services.embeddings import embed_text, cosine_similarity

# Embed text
vec1 = embed_text("The cat sat on the mat")
vec2 = embed_text("A feline rested on the rug")
vec3 = embed_text("Stock prices crashed today")

# Similar sentences should have high similarity
print(f"Cat sentences: {cosine_similarity(vec1, vec2):.3f}")  # Should be > 0.7
print(f"Different topics: {cosine_similarity(vec1, vec3):.3f}")  # Should be < 0.3
```

**Expected**: Similar sentences score > 0.5, different topics score < 0.3

---

### 2. Vector Store (`vector_store.py`)
**What it does**: SQLite database with vector search for each user. Stores message history and documents.

**Test it**:
```python
from services.vector_store import get_vector_store

# Create store for user
store = get_vector_store("test-user-123")

# Add a message
store.add_message_embedding(
    content="I love Python programming",
    role="user",
    timestamp=1234567890
)

# Search for similar
results = store.search_messages("coding in Python", top_k=5)
print(results)  # Should find the message
```

**Expected**: Search returns relevant messages with similarity scores

---

### 3. Semantic Memory (`memory.py`)
**What it does**: Combines recent messages (working memory) with semantically similar past messages

**Test it**:
```python
from services.memory import build_enhanced_context

# Build context for a query
enhanced_messages, semantic_hits = build_enhanced_context(
    principal_id="test-user",
    query="Tell me about machine learning",
    recent_messages=[{"role": "user", "content": "Hello"}]
)

print(f"Enhanced: {len(enhanced_messages)} messages")
print(f"Semantic hits: {semantic_hits}")
```

**Expected**: Returns combined context from working + semantic memory

---

### 4. Tools Framework (`tools.py`)
**What it does**: Detects when user needs tools (calculator, search, etc.) and parses tool calls from LLM output

**Test it**:
```python
from services.tools import detect_tools_needed, parse_tool_calls

# Detection
tools = detect_tools_needed("What is 25 * 4 + 10?")
print(f"Detected tools: {tools}")  # Should include 'calculator'

tools = detect_tools_needed("What's the latest news on Bitcoin?")
print(f"Detected tools: {tools}")  # Should include 'web_search'

# Parsing (from LLM output)
llm_output = """
<tool_call>
tool: calculator
expression: 25 * 4 + 10
</tool_call>
"""
calls = parse_tool_calls(llm_output)
print(f"Parsed: {calls}")  # Should extract tool and params
```

**Expected**: Correctly identifies calculator/search needs and parses tool calls

---

### 5. Code Executor (`code_executor.py`)
**What it does**: Safely evaluates math expressions and runs sandboxed Python code

**Test it**:
```python
from services.code_executor import evaluate_math_expression, execute_python_code

# Safe math
success, result = evaluate_math_expression("sqrt(16) + pow(2, 3)")
print(f"Math result: {result}")  # Should be 12.0

# Safe Python
success, output = execute_python_code("""
numbers = [1, 2, 3, 4, 5]
print(f"Sum: {sum(numbers)}")
print(f"Average: {sum(numbers)/len(numbers)}")
""")
print(f"Python output: {output}")

# Dangerous code should be blocked
success, error = execute_python_code("import os; os.system('rm -rf /')")
print(f"Blocked: {not success}")  # Should be True (blocked)
```

**Expected**: Math works, safe Python works, dangerous code is blocked

---

### 6. Voting (`voting.py`)
**What it does**: For complex questions, generates multiple answers and picks the most consistent one

**Test it**:
```python
from services.voting import should_use_voting, VotingResult

# Check if voting should be used
use_voting = should_use_voting("What is 2+2?", complexity_score=2)
print(f"Simple question: {use_voting}")  # False

use_voting = should_use_voting(
    "Explain quantum entanglement and its implications for computing",
    complexity_score=9
)
print(f"Complex question: {use_voting}")  # True
```

**Expected**: Simple questions skip voting, complex ones use it

---

### 7. Structured Output (`structured.py`)
**What it does**: Forces LLM to output valid JSON matching a schema

**Test it**:
```python
from services.structured import SCHEMAS

# Check available schemas
print(f"Available schemas: {list(SCHEMAS.keys())}")

# View understanding schema
import json
print(json.dumps(SCHEMAS['understanding'], indent=2))
```

**Expected**: Schemas exist for understanding, plan, critique, tool_call

---

## API Endpoint Tests

### Check v4.0 Status
```bash
curl -s https://api.dubya.ai/v4/status | jq .
```

**Expected Response**:
```json
{
  "available": true,
  "features": {
    "embeddings": true,
    "vector_store": true,
    "semantic_memory": true,
    "tools": true,
    "code_executor": true,
    "voting": true,
    "structured": true
  },
  "version": "4.0.0"
}
```

### Test Agent Pipeline (with v4.0)
```bash
curl -s -X POST https://api.dubya.ai/generate/agent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Calculate 25 * 4 + 10 and explain the steps"}' | head -100
```

**Expected**: Should stream thinking phases then answer with calculation

---

## Deployment Status

v4.0 features require the new Docker image to be deployed:

```bash
# Build and deploy
cd deploy/docker
./build.sh  # Creates v4-intelligence image
docker push gdubx/trinity-inference:v4-intelligence

# Update Akash deployment
./scripts/trinity-deploy-production.sh 2  # For Tier 2 with multi-model
```

The Akash YAMLs have been updated with new environment variables:
- `MULTI_MODEL_ENABLED=true` (Tier 2/3 only)
- `FAST_MODEL=phi3:mini`
- `SMART_MODEL=llama3.1:8b`
- `REASONING_MODEL=qwen2.5:14b` (Tier 2) or `qwen2.5:32b` (Tier 3)

---

## Troubleshooting

### "V4 features not available"
The backend is running but couldn't import v4 modules. Check:
1. `requirements.txt` has fastembed, sqlite-vss, RestrictedPython
2. Docker image was rebuilt with new dependencies
3. Check container logs: `provider-services lease-logs`

### "Import error: fastembed"
FastEmbed not installed. In container:
```bash
pip install fastembed==0.7.4
```

### "sqlite-vss not found"
SQLite extension not loaded. This needs the sqlite-vss wheel installed.

### Embeddings returning None
Model not downloaded yet. First call triggers download (~33MB).
Check logs for "Loading embedding model" message.
