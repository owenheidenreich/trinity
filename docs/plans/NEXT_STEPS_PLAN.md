# Trinity Next Steps Implementation Plan

> **Created:** January 25, 2026  
> **Status:** Planning  
> **Estimated Total Effort:** 10-12 hours  
> **Order:** Easiest → Hardest (minimal troubleshooting first)

---

## Overview

Tasks are ordered by confidence level and expected troubleshooting. Low-hanging fruit first, complex architectural changes last.

| Phase | Tasks | Effort | Supervision Needed |
|-------|-------|--------|-------------------|
| **Phase 1** | Log fixes, prompt redaction | 1 hour | ❌ None |
| **Phase 2** | System prompt, UI tweaks | 2-3 hours | ❌ Minimal |
| **Phase 3** | About page, provider details | 2-3 hours | ⚠️ Review |
| **Phase 4** | Security hardening | 2 hours | ⚠️ Review |
| **Phase 5** | Memory system upgrade | 3-4 hours | ✅ Collaboration |

---

## Phase 1: Quick Fixes (No Troubleshooting Expected)

### 1.1 Fix ICP Health Check Log Spam
**File:** `backend/inference_server.py`  
**Time:** 15 minutes  
**Risk:** None

**Problem:** Cache hits logged 6-13 times per health check cycle.
```
[trinity]: 🎯 ICP cache hit for request_id: health-au5zq-2qaaa-aaaal-qtowa-cai-176939537
[trinity]: 🎯 ICP cache hit for request_id: health-au5zq-2qaaa-aaaal-qtowa-cai-176939537
[trinity]: 🎯 ICP cache hit for request_id: health-au5zq-2qaaa-aaaal-qtowa-cai-176939537
```

**Solution:** Change log level from INFO to DEBUG for cache hits, or skip logging entirely for health endpoints.

```python
# Before
logger.info(f"🎯 ICP cache hit for request_id: {request_id}")

# After - Option A: Debug level
logger.debug(f"🎯 ICP cache hit for request_id: {request_id}")

# After - Option B: Skip health endpoint logging
if not request_id.startswith('health-'):
    logger.info(f"🎯 ICP cache hit for request_id: {request_id}")
```

**Verification:** Check Akash logs after deployment - should see 90%+ reduction in log volume.

---

### 1.2 Redact User Prompts from Logs
**File:** `backend/inference_server.py`  
**Time:** 30 minutes  
**Risk:** None

**Problem:** First 50 characters of user prompts visible in logs.
```
Generating response for: Tell me about my bank account...
```

**Solution:** Log word count and hash only.

```python
import hashlib

def log_prompt_safely(prompt: str, context_count: int):
    word_count = len(prompt.split())
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:8]
    logger.info(f"[{PROVIDER_ID}] Processing: {word_count} words, hash:{prompt_hash}, context:{context_count} msgs")

# Replace current logging:
# logger.info(f"[{PROVIDER_ID}] Generating response for: {user_prompt[:50]}...")
# With:
log_prompt_safely(user_prompt, len(context_memory))
```

**Also redact context message logging:**
```python
# Before
logger.info(f"  [{i+1}] {role}: {content[:50]}...")

# After
logger.info(f"  [{i+1}] {role}: {len(content.split())} words")
```

**Verification:** Deploy, send test message, confirm logs show word counts not content.

---

## Phase 2: Identity & Personality (Low Troubleshooting)

### 2.1 Add Trinity System Prompt
**File:** `backend/inference_server.py`  
**Time:** 45 minutes  
**Risk:** Low - only affects prompt construction

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
Day 1 (Phase 1 + 2): ~2-3 hours
├── 1.1 Fix log spam (15 min)
├── 1.2 Redact prompts (30 min)
├── 2.1 Add system prompt (45 min)
└── 2.2 Show CID after archive (30 min)

Day 2 (Phase 3): ~2-3 hours
├── 3.1 About page/modal (1.5 hours)
└── 3.2 Real provider details (1 hour)

Day 3 (Phase 4): ~2 hours
├── 4.1 Input validation (45 min)
└── 4.2 Rate limit /generate (1 hour)

Day 4+ (Phase 5): ~3-4 hours (collaborative)
└── 5.1 Memory system upgrade
```

---

## Verification Checklist

After each phase, verify:

### Phase 1
- [ ] Akash logs no longer spammed with cache hits
- [ ] Prompts not visible in logs (only word counts)

### Phase 2
- [ ] Ask "What are you?" - Trinity responds with identity
- [ ] Ask "What model are you using?" - correct model name
- [ ] Archive chat - CID visible in success message

### Phase 3
- [ ] About link visible in upper right
- [ ] Modal shows ICP/AKT/FIL explanation
- [ ] Provider details show GPU type

### Phase 4
- [ ] `../../../etc/passwd` as chat_id → rejected with 400
- [ ] Normal chat IDs still work
- [ ] Rapid requests get rate limited (429)

### Phase 5
- [ ] Trinity remembers facts across conversations
- [ ] User can see/manage their stored memories

---

## Notes for Claude

- **Phase 1 & 2:** Proceed without supervision. These are safe, isolated changes.
- **Phase 3:** May need input on About page content/styling. Otherwise proceed.
- **Phase 4:** Test thoroughly before deploying. Have rollback plan.
- **Phase 5:** Stop and discuss architecture before implementing.
