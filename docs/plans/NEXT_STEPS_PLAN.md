# Trinity Next Steps Implementation Plan

> **Updated:** January 31, 2026  
> **Status:** Phases 1-3 implemented (Self-Identity, Reasoning, Web Search). Ready for deploy.

---

## Quick Tasks

- [ ] Point ICP canister to new domain (options: trinityai.ai $80/yr, trin.chat $6/yr)
- [ ] Pentest, security test, robust security checks
- [ ] Show CID after archive (30 min frontend fix)

---

## Phase 1: Self-Identity ✅ IMPLEMENTED
**Goal**: Give Trinity awareness of its decentralized architecture without exposing sensitive info.

**Changes Made**:
- Expanded `TRINITY_SYSTEM_PROMPT` in `backend/inference_server.py`
- Includes: model transparency, provider info (ICP/Akash/Filecoin), privacy values
- Excludes: API keys, wallet addresses, internal config

**Status**: Code complete, needs Docker rebuild + deploy

---

## Phase 2: Agentic Reasoning ✅ IMPLEMENTED
**Goal**: Add thinking/planning capability for complex questions.

**Changes Made**:
- Added `reasoning_mode` parameter to `/generate` endpoint
- Implemented ReAct-style loop with `<thinking>`, `<plan>`, `<answer>` tags
- Added `parse_reasoning_response()` to extract structured output
- Response includes `reasoning` object with thinking/plan/raw when enabled

**Status**: Code complete, needs Docker rebuild + deploy

---

## Phase 3: Web Search ✅ IMPLEMENTED
**Goal**: Allow Trinity to access real-time information.

**Changes Made**:
- Added `/tools/search` endpoint using Brave Search API
- Added `/tools/browse` endpoint for URL fetching with HTML-to-text extraction
- Added `/tools/search-and-summarize` combined endpoint
- Added `BRAVE_SEARCH_API_KEY` to `backend/config.py`

**Status**: Code complete, needs Docker rebuild + deploy + Brave API key

---

## Phase 4: Hardware Scaling 🔬 REQUIRES DEEP RESEARCH
**Goal**: Multi-GPU support for larger models (Llama 405B+).

**Research Needed**:
- Akash multi-GPU availability and pricing
- vLLM vs Ollama for tensor parallelism
- Model sharding strategies
- Cost-benefit analysis: 4x A100 vs multiple deployments

**Potential Changes**:
- Switch from Ollama to vLLM for tensor parallel inference
- Update Akash SDL for multi-GPU allocation
- Load balancer configuration

**Complexity**: High (infrastructure change)

---

## Phase 5: Make Trinity Useful 🔬 REQUIRES DEEP RESEARCH
**Goal**: Transform Trinity from chat wrapper to autonomous agent.

**Research Needed**:
- Tool framework design (code execution, file ops, API calls)
- Safety boundaries for autonomous actions
- Task planning and multi-step execution
- User permission model for sensitive operations

**Potential Features**:
- Code execution sandbox (Python, JS)
- Document summarization and analysis
- Task planning with checkpoints
- Calendar/reminder integration
- Memory search across all conversations

**Complexity**: Very High (full agent framework)

---

## Future: Monetization & Open Source
- Payment integration for private sessions
- Usage-based billing
- Open source deployment guide
- One-click ICP/Akash/Filecoin setup for self-hosting

---

## 🟢 Priority 2: Enhancements

### 2.1 PDF Document Parsing
**File:** `backend/inference_server.py`  
**Time:** 2 hours  
**Docker:** Yes

**Current:** Only text files supported (100KB limit).

**Add:**
```python
import fitz  # PyMuPDF - add to requirements.txt

def extract_text_from_pdf(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text[:50000]  # Limit context size
```

Update frontend to accept PDF in file input.

---

### 2.2 Live Market Data
**Files:** `backend/market_data.py` (new), `backend/inference_server.py`  
**Time:** 4 hours  
**Docker:** Yes  
**Dependencies:** yfinance, feedparser

Add endpoints:
- `GET /market/quote?symbols=BTC-USD,ETH-USD`
- `GET /market/news`

Integrate with `/generate` to detect market queries and inject live data.

---

## 🔵 Future Phases

### Memory System Upgrade
- Periodic fact extraction from conversations
- User preference storage
- Cross-conversation memory

### Monetization
- Donation addresses (ICP, AKT, ETH)
- Usage tracking per principal
- Tiered access (Free/Basic/Pro)

### Backend Refactoring (Deferred)
- Extract `metrics.py`, `auth.py`, `icp_cache.py`, `ollama.py`
- Split routes into Flask Blueprints
- *Reason for deferral: Current code works, higher priorities exist*

---

## ✅ Completed Work (Reference)

### Security Hardening (Jan 31, 2026)
- ✅ Backend input validation (`validate_chat_id`, `validate_principal_id`, `validate_cid`)
- ✅ Rate limiting on all `/generate*` endpoints (30 req/min per IP)
- ✅ Applied validation to all `/chat/*` endpoints

### Phase 11: Codebase Refactor (Jan 31, 2026)
- ✅ IndexedDB local-first storage (`trinity-icp/src/storage/indexedDB.js`)
- ✅ Autosave with local-first + cloud sync
- ✅ Backend module split: `config.py`, `encryption.py`, `storage.py`, `lighthouse.py`
- ✅ Full features re-enabled (`USE_SIMPLE_GENERATE: false`)

### Frontend Features
- ✅ About modal with architecture explanation
- ✅ Provider display (ICP → Akash → Filecoin chain)
- ✅ Client-side input validation (`trinity-icp/src/utils/validation.js`)
- ✅ Trinity system prompt with model info

### Infrastructure
- ✅ Custom domain setup (trinityai.cc DNS configured)
- ✅ Log spam fix (cache hits → DEBUG level)
- ✅ Prompt redaction (word count + hash only)

---

## Current Architecture

```
Frontend (ICP Canister)
├── indexedDB.js     # Local-first chat storage
├── autosave.js      # Debounced save with retry
├── validation.js    # Client-side input sanitization
└── app.js           # Sync retry on load

Backend (Akash + Ollama)
├── config.py        # Environment variables
├── encryption.py    # AES-256-GCM encryption
├── storage.py       # File operations
├── lighthouse.py    # IPFS/Filecoin integration
├── icp_auth.py      # Ed25519 authentication
└── inference_server.py  # Main Flask app (with rate limiting + validation)

Data Flow:
User → IndexedDB (instant) → Cloud sync → Akash storage
                                      ↓
                              Archive → Lighthouse → Filecoin
```

---

## Deployment Commands

```bash
# Deploy frontend only (ICP)
dfx deploy --ic trinity_frontend

# Full production deploy (Docker + Akash + ICP)
./scripts/trinity-deploy-production.sh 3  # Tier 3

# Test production
./test-prod

# Local development
./dev
```

