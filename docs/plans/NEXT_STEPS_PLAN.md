# Trinity Next Steps Implementation Plan

> **Created:** January 25, 2026  
> **Updated:** January 26, 2026  
> **Status:** In Progress - Phase 2  
> **Estimated Total Effort:** 30-40 hours  
> **Order:** Frontend-only first → Backend (Docker) updates batched at end

---

## Overview

Tasks reordered to minimize Akash redeployments. **All frontend/ICP-only tasks first**, then batch all backend changes into a single Docker build at the end.

| Phase | Tasks | Docker Update? | Status |
|-------|-------|----------------|--------|
| **Phase 1** | About page, CID display, UI tweaks | ❌ No | ✅ COMPLETE |
| **Phase 1.5** | trinityai.cc custom domain | ❌ No | 🟢 DNS Working, SSL Pending |
| **Phase 2** | Security (input validation - frontend) | ❌ No | 🔄 In Progress |
| **Phase 3** | All backend changes (batched) | ✅ Yes (once) | ⏳ Pending |
| **Phase 4** | Memory system upgrade | ✅ Yes | ⏳ Pending |
| **Phase 5** | Local Testing Tools | ❌ No | ⏳ Pending |
| **Phase 6** | Document Attachments | ✅ Yes | 🟢 85% Done |
| **Phase 7** | Audio Transcription | ✅ Yes | 🟡 60% Done |
| **Phase 8** | Akash Provider Research | ❌ No | 🔴 Manual |
| **Phase 9** | Scaling/Stress Testing | ❌ No | 🟡 Basic |
| **Phase 10** | Monetization | ❌/✅ | 🔴 Not Started |

---

## Phase 1: Frontend-Only Changes ✅ COMPLETE

> **Deployed:** January 25, 2026  
> **Commit:** `6978f28` - "Phase 1: Frontend transparency features"

### 1.1 ✅ Add About Link & Modal
- Added "About" link next to Trinity title in sidebar
- Modal explains ICP/Akash/Filecoin architecture with visual flow
- Links to each project's website

### 1.2 ✅ Show CID After Archive
- Success notification shows truncated CID
- Clickable "View on IPFS" link to Lighthouse gateway
- Extended notification duration to 8 seconds

### 1.3 ✅ Improve Provider Display
- Production: Shows `ICP → Akash → Filecoin` colored chain
- Local dev: Shows `⚠️ Local Dev (no storage)` warning

---

## Phase 1.5: Custom Domain Setup 🟢

> **Status:** DNS WORKING, SSL certificate pending issuance

### 1.5.1 trinityai.cc Custom Domain
**Goal:** Replace long canister URL with `https://trinityai.cc`

**✅ Completed:**
- [x] `.well-known/ic-domains` file created with `trinityai.cc` and `www.trinityai.cc`
- [x] post-build.js updated to copy `.well-known` to dist
- [x] ICP frontend deployed with ic-domains file
- [x] Cloudflare DNS records configured (all 3 records)
- [x] Proxy OFF (grey cloud) on all records

**DNS Verification (January 26, 2026):**
```
✅ trinityai.cc → 23.142.184.129 (CNAME flattened to A)
✅ _canister-id.trinityai.cc TXT → "zc67k-kiaaa-aaaal-qtmiq-cai"
✅ _acme-challenge.trinityai.cc → _acme-challenge.trinityai.cc.icp2.io
```

**⏳ Pending:**
- [ ] SSL certificate issuance by ICP (5-30 min after deploy)
- Error: `SSL: no alternative certificate subject name matches target host name 'trinityai.cc'`

**Root Cause:** ICP hasn't generated the SSL cert yet. Redeploying frontend triggers certificate issuance.

**Fix Applied:** `dfx deploy --ic trinity_frontend` (January 26, 2026 6:20 PM)

**Validation Commands:**
```bash
# Test SSL certificate
curl -I https://trinityai.cc

# Force test with resolved IP
curl --resolve trinityai.cc:443:23.142.184.129 -I https://trinityai.cc
```

**Note:** ENS (trinityai.eth) was deprecated due to 30-60s IPFS gateway latency.

---

## Phase 2: Frontend Security (No Docker Update)

### 2.1 Add Client-Side Input Validation
**File:** `trinity-icp/src/storage/autosave.js`  
**Time:** 30 minutes  

Add validation before sending chat IDs to backend:
```javascript
function validateChatId(chatId) {
    return /^[a-zA-Z0-9_-]{1,64}$/.test(chatId);
}
```

---

## Phase 3: Backend Changes (Single Docker Update)

> **BATCH ALL THESE TOGETHER** - One Docker build, one Akash update.

### 3.1 ✅ COMPLETE: Fix ICP Health Check Log Spam
Changed cache hit logs from INFO to DEBUG.

### 3.2 ✅ COMPLETE: Redact User Prompts from Logs
Now logs word count + hash only, not prompt content.

### 3.3 Add Trinity System Prompt
**File:** `backend/inference_server.py`  
**Time:** 45 minutes

**Current state:** No system prompt. Messages sent raw to Ollama.

**Solution:** Add dynamic system prompt that includes current model info.

```python
def get_system_prompt():
    return f"""You are Trinity, a decentralized AI assistant.

Current configuration:
- Model: {MODEL_NAME}
- Provider: {PROVIDER_ID}
- GPU: {os.getenv('GPU_TYPE', 'Unknown')}

Your architecture:
- Frontend hosted on Internet Computer (ICP) - censorship-resistant
- Compute powered by Akash Network (AKT) - decentralized cloud
- Archives stored on Filecoin via IPFS - permanent storage
- Domain: trinityai.eth via Ethereum Name Service (ENS)

You value privacy, decentralization, and user sovereignty. Your conversations are encrypted and users control their own keys.

If users ask about how you work, explain enthusiastically but concisely. Invite them to learn more about your decentralized stack. Don't explain everything upfront - let them ask.

Be helpful, clear, and slightly curious about the future of decentralized AI."""
```

**Inject into prompt building (around line 730-780):**
```python
# Build full prompt with system instruction
system_prompt = get_system_prompt()
full_prompt = f"{system_prompt}\n\n{context_section}\n\nUser: {user_prompt}\nAssistant:"
```

**Verification:** Ask Trinity "What are you?" or "What model are you using?" - should respond accurately.

---

### 2.2 Show CID After Archive (Success Notification)
**File:** `trinity-icp/src/modules/archive.js`  
**Time:** 30 minutes  
**Risk:** Low - UI only

**Problem:** CID only logged to console, not shown to user.

**Solution:** Include CID in success notification with copy functionality.

```javascript
// Before
UI.showSuccess(`Chat archived to Filecoin! (${response.archivedCount}/10)`);

// After
const shortCid = response.cid.substring(0, 12) + '...' + response.cid.substring(response.cid.length - 6);
const verifyUrl = `https://gateway.lighthouse.storage/ipfs/${response.cid}`;
UI.showSuccess(`Archived! CID: ${shortCid} (${response.archivedCount}/10)`, {
    action: 'Verify',
    actionUrl: verifyUrl
});
```

**Note:** May need to update `UI.showSuccess` to support action buttons. If not supported, just show the CID inline.

**Verification:** Archive a chat, confirm CID appears in notification.

---

## Phase 3: Transparency Features (Some UI Work)

### 3.1 Add About Link (Upper Right)
**Files:** `trinity-icp/src/index.html`, `trinity-icp/src/styles.css`, `trinity-icp/src/app.js`  
**Time:** 1.5 hours  
**Risk:** Low - additive UI

**Implementation:**

1. **Add About link to header** (index.html or via JS):
```html
<div class="header-right">
    <a href="#" id="about-link" class="about-link">About Trinity</a>
</div>
```

2. **Create About modal content:**
```javascript
function showAboutModal() {
    const content = `
        <h2>About Trinity</h2>
        <p>Trinity is a fully decentralized AI assistant.</p>
        
        <h3>🌐 How It Works</h3>
        <div class="about-section">
            <h4>Internet Computer (ICP)</h4>
            <p>Your interface runs on ICP canisters - censorship-resistant smart contracts that serve the frontend globally.</p>
        </div>
        
        <div class="about-section">
            <h4>Akash Network (AKT)</h4>
            <p>AI inference runs on Akash's decentralized cloud. Your conversations are processed on GPU nodes worldwide, with no central authority.</p>
        </div>
        
        <div class="about-section">
            <h4>Filecoin (FIL)</h4>
            <p>When you archive chats, they're stored permanently on Filecoin via IPFS. Content-addressed storage means your data is verifiable and immutable.</p>
        </div>
        
        <h3>🔗 The Flow</h3>
        <pre>
You → ICP Frontend → ICP Backend Canister
         ↓
    Vercel Proxy (SSL)
         ↓
    Akash Backend (GPU + Ollama)
         ↓
    Archive → Lighthouse → IPFS + Filecoin
        </pre>
        
        <h3>📚 Learn More</h3>
        <ul>
            <li><a href="https://internetcomputer.org" target="_blank">Internet Computer</a></li>
            <li><a href="https://akash.network" target="_blank">Akash Network</a></li>
            <li><a href="https://filecoin.io" target="_blank">Filecoin</a></li>
            <li><a href="https://ens.domains" target="_blank">ENS Domains</a></li>
        </ul>
        
        <h3>🔐 Your Keys, Your Data</h3>
        <p>Trinity uses Ed25519 keypairs for authentication. You own your private key - we never see it. Export it anytime from the sidebar.</p>
    `;
    
    Modals.show('about', content);
}
```

3. **Style the about modal** (styles.css)

**Verification:** Click About link, confirm modal opens with correct content.

---

### 3.2 Show Real Provider Details
**Files:** `backend/inference_server.py`, `trinity-icp/src/ui/sidebar.js`  
**Time:** 1 hour  
**Risk:** Low

**Backend change:** Add more details to /health response.
```python
return jsonify({
    'status': 'healthy',
    'provider_id': PROVIDER_ID,
    'model': MODEL_NAME,
    'gpu_type': os.getenv('GPU_TYPE', 'Unknown'),
    'build_timestamp': BUILD_TIMESTAMP,
    'ollama_connected': ollama_ok,
    # New fields:
    'akash_provider': os.getenv('AKASH_PROVIDER', 'Unknown'),  # Set in deployment
    'version': '2.6.1',
})
```

**Frontend change:** Display fuller info.
```javascript
// Instead of just provider_id, show more:
const providerInfo = `${data.model} on ${data.gpu_type}`;
```

**Note:** Akash doesn't automatically expose provider domain to container. Could be set manually in YAML or derived from ingress URL.

---

## Phase 4: Security Hardening (Careful Testing Needed)

### 4.1 Input Validation for chat_id and principal_id
**File:** `backend/inference_server.py`  
**Time:** 45 minutes  
**Risk:** Medium - could break existing functionality if too strict

**Problem:** Path traversal possible via malicious chat_id like `../../etc/passwd`.

**Solution:** Add validation function and apply to all endpoints.

```python
import re

def validate_chat_id(chat_id: str) -> bool:
    """Validate chat_id format - alphanumeric, dash, underscore only."""
    if not chat_id or len(chat_id) > 64:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', chat_id))

def validate_principal_id(principal_id: str) -> bool:
    """Validate ICP principal format."""
    if not principal_id or len(principal_id) > 64:
        return False
    # ICP principals are base32-ish with dashes
    return bool(re.match(r'^[a-z0-9-]+$', principal_id.lower()))

# Apply at endpoint entry:
@app.route('/chat/autosave', methods=['POST'])
@require_auth
def autosave_chat():
    chat_id = data.get('chatId')
    if not validate_chat_id(chat_id):
        return jsonify({'error': 'Invalid chat ID format'}), 400
    # ... rest of function
```

**Testing required:**
- [ ] Existing chats still load
- [ ] New chats save correctly
- [ ] Malicious IDs rejected with 400

---

### 4.2 Rate Limit /generate Endpoint
**File:** `backend/inference_server.py`  
**Time:** 1 hour  
**Risk:** Medium - could affect legitimate users if too aggressive

**Problem:** `/generate` has no authentication - anyone can consume GPU resources.

**Solution options:**

**Option A: Simple rate limit by IP (recommended for now)**
```python
from functools import wraps
from collections import defaultdict
import time

# Simple in-memory rate limiter
request_counts = defaultdict(list)
RATE_LIMIT = 10  # requests
RATE_WINDOW = 60  # seconds

def rate_limit(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        ip = request.remote_addr
        now = time.time()
        
        # Clean old requests
        request_counts[ip] = [t for t in request_counts[ip] if now - t < RATE_WINDOW]
        
        if len(request_counts[ip]) >= RATE_LIMIT:
            return jsonify({'error': 'Rate limit exceeded. Try again later.'}), 429
        
        request_counts[ip].append(now)
        return f(*args, **kwargs)
    return decorated

@app.route('/generate', methods=['POST'])
@rate_limit
def generate():
    # ... existing code
```

**Option B: Require auth for /generate (more secure but breaking change)**
- Would require frontend changes
- Could offer both authenticated (unlimited) and unauthenticated (rate limited)

**Recommendation:** Start with Option A (rate limit), consider Option B later.

---

## Phase 5: Memory System Enhancement (Collaborative)

### 5.1 Enhance User Memory Extraction
**Files:** `backend/inference_server.py`, `trinity-icp/src/state/contextMemory.js`  
**Time:** 3-4 hours  
**Risk:** Higher - affects core AI behavior

**Current state:**
- `user_memory.json` exists per user
- Basic fact storage
- No structured extraction

**Proposed enhancement:**

1. **Memory extraction prompt** - Ask LLM to identify memorable facts:
```python
MEMORY_EXTRACTION_PROMPT = """
Review this conversation and extract any important facts about the user that should be remembered for future conversations. 

Focus on:
- Preferences (communication style, topics of interest)
- Facts about them (profession, location, projects they're working on)
- Context (what they're trying to accomplish)

Return as JSON: {"facts": ["fact 1", "fact 2"]}
If no memorable facts, return: {"facts": []}
"""
```

2. **Periodic extraction** - After every N messages, run extraction.

3. **User confirmation (optional)** - "Should I remember that you prefer concise answers?"

**This requires discussion:**
- How often to extract?
- User consent model?
- Storage limits per user?
- How to handle conflicting facts?

---

## Implementation Order Summary

```
TODAY - Frontend Only (No Docker):
├── 1.1 About page/modal (1.5 hours) ← ICP deploy only
├── 1.2 Show CID after archive (30 min) ← ICP deploy only
├── 1.3 Improve provider display (30 min) ← ICP deploy only
└── 2.1 Client-side input validation (30 min) ← ICP deploy only

LATER - Backend Batch (Single Docker Update):
├── 3.1 ✅ Log spam fix (DONE - awaiting deploy)
├── 3.2 ✅ Prompt redaction (DONE - awaiting deploy)
├── 3.3 System prompt / Trinity identity (45 min)
├── 3.4 Input validation on backend (45 min)
├── 3.5 Rate limit /generate (1 hour)
└── Docker build + Akash update (once)

COLLABORATIVE - Memory System:
└── 4.1 Memory system upgrade (3-4 hours, discussion first)
```

---

## Verification Checklist

### After Frontend Deploy (Phase 1-2)
- [ ] About link visible in upper right
- [ ] Modal shows ICP/AKT/FIL explanation with links
- [ ] Archive chat → CID visible in success message
- [ ] Provider shows model + GPU type

### After Backend Deploy (Phase 3)
- [ ] Akash logs no longer spammed with cache hits
- [ ] Prompts not visible in logs (only word counts)
- [ ] Ask "What are you?" → Trinity responds with identity
- [ ] Ask "What model are you using?" → correct model name
- [ ] `../../../etc/passwd` as chat_id → rejected with 400
- [ ] Rapid requests get rate limited (429)

### After Memory Upgrade (Phase 4)
- [ ] Trinity remembers facts across conversations
- [ ] User can see/manage their stored memories

---

## Notes for Claude

- **Phase 1-2 (Frontend):** Proceed now. ICP deploy only, no Docker needed.
- **Phase 3 (Backend):** Batch ALL backend changes, single Docker build.
- **Phase 4 (Memory):** Stop and discuss architecture before implementing.

---

## Phase 5: Local Testing Tools 🧪

> **Status:** 🟡 Partially Implemented

**The Problem:**
> "Any time inference_server.py is updated, we need to re-deploy. It takes 20-30 minutes each time."

**What Exists:**
- `./dev` script for local backend (Python only, no Docker)
- `test/local/start-local.sh` with Docker compose

### 5.1 Create Local Docker Test Script
**File:** `scripts/test-docker-local.sh`

```bash
#!/bin/bash
# Test Docker build locally before pushing to Akash

set -e

echo "🐳 Building Docker image for AMD64 (matching Akash)..."
docker build --platform linux/amd64 \
  -t trinity-test:local \
  -f deploy/docker/Dockerfile .

echo "🚀 Starting local container..."
docker run -it --rm \
  -p 8000:8000 \
  -e MODEL_NAME=tinyllama:1.1b \
  -e PROVIDER_ID=docker-local-test \
  trinity-test:local
```

### 5.2 Create Pre-Deploy Validation Script
**File:** `scripts/validate-before-deploy.sh`

```bash
#!/bin/bash
# Run before Akash deployment

echo "🔍 Validating before deploy..."

# 1. Check Python syntax
python3 -m py_compile backend/inference_server.py

# 2. Check YAML syntax
for yaml in deploy/akash/*.yaml; do
  python3 -c "import yaml; yaml.safe_load(open('$yaml'))"
done

# 3. Build Docker locally
docker build --platform linux/amd64 -t validate-test:local -f deploy/docker/Dockerfile .

# 4. Quick smoke test
docker run -d --name validate-container -p 8099:8000 validate-test:local
sleep 10
curl -f http://localhost:8099/health
docker rm -f validate-container

echo "✅ All validations passed!"
```

**Estimated Time:** 4-6 hrs  
**Dependencies:** Docker Desktop

---

## Phase 6: Document Attachments 📄

> **Status:** 🟢 85% Complete

**What Already Exists:**
- File upload handling in `trinity-icp/src/tools.js`
- 100KB limit for text files
- Attachment preview UI
- Backend accepts context parameter

**What Needs Improvement:**
- PDF/DOCX parsing (currently text-only)
- Large file chunking (>100KB)
- Better prompts for document analysis

### 6.1 Add PDF Parsing to Backend
**File:** `backend/inference_server.py`

```python
import fitz  # PyMuPDF - already in requirements

def extract_text_from_pdf(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text[:50000]  # Limit context size
```

### 6.2 Update Frontend File Handling
**File:** `trinity-icp/src/tools.js`

```javascript
const ALLOWED_TYPES = ['.txt', '.md', '.json', '.pdf', '.py', '.js'];
const MAX_SIZE = 500 * 1024;  // Increase to 500KB for PDFs
```

**Estimated Time:** 2-4 hrs  
**Dependencies:** PyMuPDF (already installed)

---

## Phase 7: Audio Transcription 🎤

> **Status:** 🟡 60% Complete

**What Exists:**
- Audio file detection in frontend
- `/transcribe` endpoint skeleton
- 25MB file limit

**What's Broken:**
- Local Whisper DISABLED (adds 3GB PyTorch)
- No cloud API integration

### 7.1 Use Groq Whisper API (FREE - 20 hrs/day)
**File:** `backend/inference_server.py`

```python
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    if not GROQ_API_KEY:
        return jsonify({'error': 'Transcription not configured'}), 503
    
    audio_file = request.files.get('audio')
    if not audio_file:
        return jsonify({'error': 'No audio file provided'}), 400
    
    response = requests.post(
        'https://api.groq.com/openai/v1/audio/transcriptions',
        headers={'Authorization': f'Bearer {GROQ_API_KEY}'},
        files={'file': (audio_file.filename, audio_file.read())},
        data={'model': 'whisper-large-v3'}
    )
    
    if response.ok:
        return jsonify({'text': response.json()['text']})
    else:
        return jsonify({'error': 'Transcription failed'}), 500
```

### 7.2 Add Environment Variable to Akash YAML
```yaml
env:
  - GROQ_API_KEY=gsk_xxxxxxxxxxxx
```

**Estimated Time:** 4-6 hrs  
**Dependencies:** Groq API key (free at console.groq.com)

---

## Phase 8: Akash Provider Research 🔍

> **Status:** 🔴 Manual/Ad-hoc

**The Problem:**
> "We're throwing random YAMLs out there and seeing what works."

### Known Provider Rules

| Pattern | Status | Notes |
|---------|--------|-------|
| `*.akash.pub` | ✅ GOOD | Reliable ingress |
| `*.akashprovid.com` | ✅ GOOD | Current production |
| `*.akashgpu.com` | ✅ GOOD | GPU providers |
| `*.akash-palmito.org` | ✅ GOOD | Current ingest |
| `*.leet.haus` | ❌ AVOID | Broken networking |

### 8.1 Create Provider Blacklist
**File:** `deploy/akash/provider-blacklist.txt`

```
# Providers to avoid - broken ingress networking
*.leet.haus
```

### 8.2 Create Deployment Rules Doc
**File:** `docs/AKASH_DEPLOYMENT_RULES.md`
- GPU requirements by tier
- Provider selection criteria
- YAML templates with comments
- Cost optimization strategies

### 8.3 Create Provider Analyzer
**File:** `scripts/akash-provider-analyzer.py`
- Query Akash API for provider stats
- Score providers on reliability, price, GPU
- Output recommended providers list

**Estimated Time:** 6-8 hrs  
**Dependencies:** Akash CLI or API access

---

## Phase 9: Scaling/Stress Testing 📊

> **Status:** 🟡 Basic Only

**What Exists:**
- `test/integration/benchmark_models.py` - Single-user benchmarks

**What's Missing:**
- Concurrent user simulation
- Load testing (multiple requests)
- Stress testing (find breaking point)

### 9.1 Create Load Test Suite
**File:** `test/stress/load_test.py`

```python
#!/usr/bin/env python3
import asyncio
import aiohttp
import time
import statistics

async def simulate_user(session, url, user_id, results):
    prompts = ["Hello", "Write code", "Explain ML"]
    
    for prompt in prompts:
        start = time.time()
        try:
            async with session.post(f"{url}/generate", json={"prompt": prompt}) as resp:
                latency = (time.time() - start) * 1000
                results.append({'user': user_id, 'status': resp.status, 'latency_ms': latency})
        except Exception as e:
            results.append({'user': user_id, 'error': str(e)})

async def run_load_test(url, num_users):
    results = []
    async with aiohttp.ClientSession() as session:
        tasks = [simulate_user(session, url, i, results) for i in range(num_users)]
        await asyncio.gather(*tasks)
    
    latencies = [r['latency_ms'] for r in results if 'latency_ms' in r]
    print(f"P50: {statistics.median(latencies):.0f}ms")
    print(f"P95: {sorted(latencies)[int(len(latencies)*0.95)]:.0f}ms")

# Usage: python load_test.py --users 10 --url https://api.trinityai.cc
```

**Estimated Time:** 6-8 hrs  
**Dependencies:** aiohttp (dev dependency)

---

## Phase 10: Monetization 💰

> **Status:** 🔴 Not Started

### 10.1 Donations (2 hrs)
```javascript
// trinity-icp/src/ui/donate.js
const DONATION_ADDRESSES = {
    ICP: 'account-id-here',
    AKT: 'akash1...address',
    ETH: '0x...address'
};
```

### 10.2 Usage Tracking (4-6 hrs)
- Track queries per principal ID
- Display usage stats in UI

### 10.3 Tiered Access (16-24 hrs)
- Free tier: TinyLlama, 100 queries/day
- Basic ($10/mo): Llama 8B, unlimited
- Pro ($50/mo): Llama 70B, priority

**Recommendation:** Start with donations only.

---

## Dependencies Checklist

### API Keys Needed
- [ ] Groq API key (free) - for audio transcription

### Access Required
- [ ] Cloudflare dashboard - for DNS fixes
- [ ] Akash Console - for deployments

---

## Related Documents

- [CLAUDE.md](../CLAUDE.md) - Main architecture reference

---

## Future: Financial Library Integration

**Goal:** Develop a useful way to utilize a vast library of financial media (280+ trading books) that does not exhaust all resources, cost a lot, or slow down the LLM. How can we make the library a useful tool?

**Considerations:**
- ChromaDB + sentence-transformers adds ~2.5GB to Docker image (too heavy)
- Filecoin download on cold start adds 1-2 minutes (too slow)
- Full RAG requires GPU memory that competes with LLM inference

**Potential Approaches:**
1. Pre-baked tips in system prompt (~2KB, zero dependencies)
2. Lightweight keyword matching with JSON file (~100KB)
3. External RAG service (separate container, on-demand)
4. ICP canister for vector storage (permanent, ~$5/GB/year)

---

## Phase 11: Live Internet Features (Stock Data, News)

> **Status:** 🔴 Not Started  
> **Dependencies:** yfinance, feedparser (small ~5MB)  
> **Docker Update:** Yes (once)

### 11.1 Add Market Data Module
**File:** `backend/market_data.py` (new)  
**Time:** 2-3 hours

Create caching layer for market data:
```python
CACHE_TTL = {
    'quotes': 60,        # 1 minute - stock/crypto prices
    'news': 300,         # 5 minutes - headlines
    'calendar': 3600,    # 1 hour - economic events
}

_cache = {}

def get_quote(symbols: list) -> dict:
    """Fetch stock/crypto quotes via yfinance with caching."""
    import yfinance as yf
    cache_key = f"quote:{','.join(sorted(symbols))}"
    if cache_key in _cache and time.time() - _cache[cache_key]['ts'] < CACHE_TTL['quotes']:
        return _cache[cache_key]['data']
    
    data = yf.download(symbols, period='1d', progress=False)
    # Format as dict with price, change, volume
    result = format_quotes(data)
    _cache[cache_key] = {'data': result, 'ts': time.time()}
    return result
```

### 11.2 Add `/market/quote` Endpoint
**File:** `backend/inference_server.py`  
**Time:** 1 hour

```python
@app.route('/market/quote', methods=['GET'])
def market_quote():
    """Get real-time stock/crypto quotes."""
    symbols = request.args.get('symbols', 'BTC-USD').split(',')
    quotes = market_data.get_quote(symbols)
    return jsonify(quotes)
```

### 11.3 Add `/market/news` Endpoint
**File:** `backend/inference_server.py`  
**Time:** 1 hour

```python
@app.route('/market/news', methods=['GET'])
def market_news():
    """Get aggregated financial news from RSS feeds."""
    import feedparser
    feeds = [
        'https://feeds.finance.yahoo.com/rss/2.0/headline',
        'https://www.coindesk.com/arc/outboundfeeds/rss/',
    ]
    # Aggregate and dedupe headlines
    return jsonify(market_data.get_news(feeds))
```

### 11.4 Integrate with /generate (Tool Calling)
**File:** `backend/inference_server.py`  
**Time:** 2 hours

When user asks about stock prices, Trinity fetches live data:
```python
# Detect market queries
if any(kw in user_prompt.lower() for kw in ['price of', 'trading at', 'stock', 'btc', 'eth']):
    # Extract symbols and fetch quotes
    quotes = market_data.get_quote(extracted_symbols)
    # Inject into prompt
    prompt += f"\n[Live Market Data]\n{format_as_markdown_table(quotes)}\n"
```

### 11.5 Add Dependencies
**File:** `backend/requirements.txt`

```
yfinance>=0.2.0
feedparser>=6.0.0
```

**Verification:** Ask Trinity "What's Bitcoin trading at?" → Should return live price.

