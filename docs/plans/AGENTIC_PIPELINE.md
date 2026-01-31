# Trinity Agentic Multi-Pass Pipeline

> **Status:** Implementation in Progress  
> **Created:** January 31, 2026  
> **Goal:** Make Trinity feel genuinely intelligent by using multi-pass reasoning

---

## Overview

**This is the DEFAULT for all prompts.** No special commands needed.

The agent automatically:
- Detects question complexity
- Decides if web search is needed
- Thinks deeply when warranted
- Critiques and refines when quality is low

```
User Question
     ↓
[Complexity Check] → Simple? → Direct answer (1-2s)
     ↓ Complex
[Tool Detection] → Needs current info? → Web Search
     ↓
[Pass 1: Understand] → What's being asked? (2-3s)
     ↓
[Pass 2: Plan] → How should I approach this? (3-5s)
     ↓
[Pass 3: Execute] → Generate thorough response (5-15s)
     ↓
[Pass 4: Critique] → Find 3 weaknesses (3-5s)
     ↓
[Pass 5: Refine] → Fix weaknesses if score < 7 (5-10s)
     ↓
Final Response (15-45 seconds total)
```

---

## Data Persistence (What Gets Saved)

**IMPORTANT:** Only the final user-visible output is saved. Intermediate thinking is ephemeral.

| Data Type | Saved? | Where |
|-----------|--------|-------|
| User's original prompt | ✅ Yes | `chatHistory` → Autosave → IPFS |
| Final AI answer | ✅ Yes | `chatHistory` → Autosave → IPFS |
| Understanding analysis | ❌ No | Ephemeral (used internally, then discarded) |
| Plan steps | ❌ No | Ephemeral (used internally, then discarded) |
| Critique score/weaknesses | ❌ No | Ephemeral (logged to console only) |
| Web search results | ❌ No | Used in prompt context, not saved |
| Phase messages ("Pondering...") | ❌ No | UI-only, never stored |

This keeps IPFS storage lean - no bloat from internal reasoning chains.

---

## Removed Features

These are REPLACED by the agentic pipeline:

| Old | Replaced By |
|-----|-------------|
| `/think` command | Automatic complexity detection |
| `/search` command | Automatic tool detection |
| `/generate` endpoint | `/generate/agent` is now default |
| `/generate/stream` endpoint | Kept for backwards compat, routes to agent |

---

## Tool Detection (Automatic)

The agent analyzes each question and decides if tools are needed:

### Web Search Triggers
- Questions about current events, news, recent info
- "What's the latest...", "Current...", "Today's..."
- Asking about prices, stocks, weather
- Questions that require up-to-date information
- Anything the LLM's training data wouldn't cover

### No Search Needed
- Conceptual explanations ("What is recursion?")
- Code generation ("Write a Python function...")
- Analysis ("Compare REST vs GraphQL")
- Creative writing
- Math problems

---

## Files Created

| File | Purpose |
|------|---------|
| `backend/services/complexity.py` | Question classifier (simple/medium/complex) + tool detection |
| `backend/services/agent_prompts.py` | Pass-specific prompts with XML tags |
| `backend/services/agent.py` | Pipeline orchestrator with timeouts + tool use |

---

## Complexity Classification

### Routing Rules

| Complexity | Passes | Triggers |
|------------|--------|----------|
| Simple | 1 (direct) | "what is", "who is", < 10 words, factual |
| Medium | 3 (understand → execute → critique) | 10-50 words, "explain", "how does" |
| Complex | 5 (full pipeline) | "design", "debug", code blocks, > 50 words |

### Heuristics

```python
simple_patterns = ['what is', 'who is', 'when did', 'where is', 'how many', 'define']
complex_patterns = ['design', 'architect', 'debug', 'implement', 'create a system',
                    'build a', 'compare and contrast', 'analyze why']
```

---

## Pass Prompts

### Pass 1: Understand
- Classify question type
- Identify knowledge domains
- Rate complexity 1-10
- Summarize what's being asked

### Pass 2: Plan
- Create 3-5 step plan
- Consider multiple approaches
- Note potential pitfalls

### Pass 3: Execute
- Follow the plan
- Be thorough, not fast
- Include reasoning

### Pass 4: Critique
- MUST find 3 weaknesses
- Be specific and actionable
- Score 1-10

### Pass 5: Refine (if score < 7)
- Address each weakness
- Improve weak sections
- Max 2 refinement attempts

---

## Failure Guards

| Risk | Guard |
|------|-------|
| Token explosion | Summary-only between passes (100 words max) |
| Timeout spiral | Per-pass timeouts (10-30s), graceful degradation |
| Bad self-critique | Force 3 weaknesses, re-critique if finds 0 |
| XML parsing failure | Fuzzy parsing with 3 fallback patterns |
| Infinite refine loop | Max 2 refinements, stop if score improves < 1 |
| Simple Q over-processed | Complexity classifier routes correctly |

### Timeout Configuration

```python
PASS_TIMEOUTS = {
    'understand': 10,
    'plan': 10,
    'execute': 30,
    'critique': 15,
    'refine': 20
}
```

---

## API Endpoint

### `/generate/agent` (POST)

**Request:**
```json
{
  "prompt": "Design a database schema...",
  "contextMemory": [...],
  "principal": "abc-123",
  "force_mode": null  // "simple", "medium", "complex", or null for auto
}
```

**Response (SSE stream):**
```
data: {"phase": "classifying", "message": "🔍 Analyzing question..."}
data: {"phase": "understanding", "message": "🤔 Understanding request..."}
data: {"phase": "planning", "message": "📋 Creating plan..."}
data: {"phase": "executing", "message": "✍️ Writing response..."}
data: {"token": "Here"}
data: {"token": " is"}
data: {"token": " my"}
...
data: {"phase": "critiquing", "message": "🔍 Reviewing quality..."}
data: {"phase": "refining", "message": "✨ Improving response..."}
data: {"done": true, "passes": 5, "complexity": "complex", "critique_score": 8}
```

---

## Frontend Integration

### Progress Display
- Show phase indicator during processing
- Stream tokens during Execute phase
- Optionally show thinking/critique (toggle in settings)

### User Commands
- `/quick` - Force single-pass mode
- `/deep` - Force full 5-pass pipeline
- Default - Auto-detect complexity

---

## Testing Checklist

- [ ] Simple question routes to 1 pass
- [ ] Complex question uses full pipeline
- [ ] Timeouts trigger graceful fallback
- [ ] XML parsing handles edge cases
- [ ] Critique actually finds real issues
- [ ] Refinement improves response quality
- [ ] Progress streams correctly to frontend

---

## Deployment

After implementation:
1. Docker build with new files
2. Push to Docker Hub
3. Redeploy to Akash
4. Test with real questions

---

*This pipeline makes Trinity feel intelligent by taking time to think, not just respond.*
