# Trinity Next Steps Implementation Plan

> **Updated:** January 31, 2026  
> **Status:** v3.7.0 - Security audit complete. Prioritizing security fixes.  
> **Priority:** 🔴 SECURITY FIRST, then performance, then features

---

## 📋 IMPLEMENTATION ORDER

| Priority | Item | Time | Complexity | Status |
|----------|------|------|------------|--------|
| 🔴 1 | S1.1 Rate limit storage endpoints | 30 min | Low | ⬜ |
| 🔴 2 | S1.2 Prompt length validation | 30 min | Low | ⬜ |
| 🔴 3 | S1.3 SSRF protection for /tools/browse | 1 hr | Medium | ⬜ |
| 🔴 4 | S1.4 Encrypt private keys in localStorage | 2 hr | Medium | ⬜ |
| ⚡ 5 | P1.1 Fix typing animation thrash | 1 hr | Low | ⬜ |
| ⚡ 6 | P1.3 Memory leak prevention | 30 min | Low | ⬜ |
| 🟡 7 | S2.3 Restrict CORS origins | 30 min | Low | ⬜ |
| ⚡ 8 | P1.2 Connection pooling | 30 min | Low | ⬜ |
| 📦 9 | U1.1 Upgrade cryptography | 15 min | Low | ⬜ |
| 📦 10 | U1.4 Add response compression | 30 min | Low | ⬜ |
| 🟡 11 | S2.2 Constant-time signatures | 30 min | Low | ⬜ |
| 🟡 12 | S2.1 Nonce-based CSP | 2 hr | High | ⬜ |
| 📦 13 | U1.2 Argon2id migration | 2 hr | Medium | ⬜ |
| 📦 14 | U1.3 BeautifulSoup HTML parsing | 1 hr | Low | ⬜ |

**Total estimated time:** ~12 hours

---

## 🔴 PHASE S1: HIGH PRIORITY SECURITY (Do Now)

### S1.1 Rate Limit on Storage Endpoints
**Severity:** HIGH  
**Time:** 30 minutes  
**Files:** `backend/inference_server.py`  
**Docker Rebuild:** Yes

**Problem:** `/chat/autosave`, `/chat/list`, `/chat/<id>` have `@require_auth` but no `@rate_limit`. An attacker with valid credentials could flood storage with thousands of requests.

**Implementation:**
```python
# In inference_server.py, add rate_limit decorator to all storage endpoints:

@app.route('/chat/autosave', methods=['POST'])
@rate_limit(requests_per_minute=30)  # ADD THIS
@require_auth
def autosave_chat():
    ...

@app.route('/chat/list', methods=['GET'])
@rate_limit(requests_per_minute=60)  # ADD THIS
@require_auth
def list_chats():
    ...

@app.route('/chat/<chat_id>', methods=['GET', 'DELETE'])
@rate_limit(requests_per_minute=60)  # ADD THIS
@require_auth
def chat_by_id(chat_id):
    ...

@app.route('/user/memory', methods=['GET', 'POST'])
@rate_limit(requests_per_minute=30)  # ADD THIS
@require_auth
def user_memory():
    ...
```

**Verification:** Run `curl` in a loop, verify 429 after limit exceeded.

---

### S1.2 Unbounded Prompt Length DoS
**Severity:** HIGH  
**Time:** 30 minutes  
**Files:** `backend/inference_server.py`  
**Docker Rebuild:** Yes

**Problem:** `/generate` accepts arbitrarily large prompts. A 100MB prompt could crash the server or exhaust memory.

**Implementation:**
```python
# At top of inference_server.py, add constant:
MAX_PROMPT_LENGTH = 50000  # 50KB - generous but safe

# In generate() and generate_agent(), add check:
@app.route('/generate', methods=['POST'])
@rate_limit(requests_per_minute=30)
def generate():
    data = request.get_json()
    user_prompt = data.get('prompt', '')
    
    # ADD: Prompt length validation
    if len(user_prompt) > MAX_PROMPT_LENGTH:
        return jsonify({
            'error': f'Prompt too long: {len(user_prompt)} chars (max {MAX_PROMPT_LENGTH})'
        }), 400
    
    # ... rest of function
```

**Verification:** Send 100KB prompt, verify 400 error returned.

---

### S1.3 SSRF Vulnerability in /tools/browse
**Severity:** HIGH  
**Time:** 1 hour  
**Files:** `backend/inference_server.py`  
**Docker Rebuild:** Yes

**Problem:** `/tools/browse` fetches arbitrary URLs. An attacker could request:
- `http://localhost:11434/api/...` (Ollama internal API)
- `http://169.254.169.254/latest/meta-data/` (Cloud metadata - AWS/GCP credentials)
- `http://192.168.1.1/admin` (Internal network resources)

**Implementation:**
```python
import ipaddress
from urllib.parse import urlparse
import socket

def is_url_safe(url: str) -> tuple[bool, str]:
    """Check if URL is safe to fetch (not internal/private)"""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        
        if not hostname:
            return False, "Invalid URL: no hostname"
        
        # Block common internal hostnames
        blocked_hostnames = ['localhost', '127.0.0.1', 'metadata', 'internal', '0.0.0.0']
        if hostname.lower() in blocked_hostnames:
            return False, f"Blocked hostname: {hostname}"
        
        # Resolve hostname to IP
        try:
            ip = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip)
            
            # Block private, loopback, and link-local ranges
            if ip_obj.is_private:
                return False, f"Private IP blocked: {ip}"
            if ip_obj.is_loopback:
                return False, f"Loopback IP blocked: {ip}"
            if ip_obj.is_link_local:
                return False, f"Link-local IP blocked: {ip}"
            if ip_obj.is_reserved:
                return False, f"Reserved IP blocked: {ip}"
                
            # Block cloud metadata endpoints
            if ip == '169.254.169.254':
                return False, "Cloud metadata endpoint blocked"
                
        except socket.gaierror:
            # Can't resolve - could be internal DNS
            return False, f"Cannot resolve hostname: {hostname}"
        
        return True, "OK"
        
    except Exception as e:
        return False, f"URL validation error: {e}"

# In browse_url() endpoint:
@app.route('/tools/browse', methods=['POST'])
@rate_limit(requests_per_minute=20)
def browse_url():
    data = request.get_json()
    url = data.get('url', '')
    
    # ADD: SSRF protection
    is_safe, reason = is_url_safe(url)
    if not is_safe:
        logger.warning(f"🚫 SSRF attempt blocked: {url} - {reason}")
        return jsonify({'error': f'URL blocked: {reason}'}), 403
    
    # ... rest of function
```

**Verification:** Test with `http://localhost:11434`, `http://169.254.169.254`, verify 403.

---

### S1.4 Private Key XSS Vulnerability
**Severity:** HIGH  
**Time:** 2 hours  
**Files:** `trinity-icp/src/auth/authManager.js`  
**Docker Rebuild:** No (frontend only)

**Problem:** Ed25519 private keys stored in localStorage as plain hex. Any XSS vulnerability (even from a CDN compromise) could exfiltrate keys.

**Implementation (Password-encrypted keys):**
```javascript
// In authManager.js, add key encryption before storage:

async function encryptKeyForStorage(privateKeyHex, password) {
    const encoder = new TextEncoder();
    const keyData = encoder.encode(password);
    
    // Derive key from password
    const baseKey = await crypto.subtle.importKey(
        'raw', keyData, 'PBKDF2', false, ['deriveKey']
    );
    
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const derivedKey = await crypto.subtle.deriveKey(
        { name: 'PBKDF2', salt, iterations: 100000, hash: 'SHA-256' },
        baseKey,
        { name: 'AES-GCM', length: 256 },
        false,
        ['encrypt']
    );
    
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const encrypted = await crypto.subtle.encrypt(
        { name: 'AES-GCM', iv },
        derivedKey,
        encoder.encode(privateKeyHex)
    );
    
    // Store salt + iv + ciphertext
    return btoa(JSON.stringify({
        salt: Array.from(salt),
        iv: Array.from(iv),
        data: Array.from(new Uint8Array(encrypted))
    }));
}

async function decryptKeyFromStorage(encryptedBlob, password) {
    const encoder = new TextEncoder();
    const decoder = new TextDecoder();
    const { salt, iv, data } = JSON.parse(atob(encryptedBlob));
    
    const baseKey = await crypto.subtle.importKey(
        'raw', encoder.encode(password), 'PBKDF2', false, ['deriveKey']
    );
    
    const derivedKey = await crypto.subtle.deriveKey(
        { name: 'PBKDF2', salt: new Uint8Array(salt), iterations: 100000, hash: 'SHA-256' },
        baseKey,
        { name: 'AES-GCM', length: 256 },
        false,
        ['decrypt']
    );
    
    const decrypted = await crypto.subtle.decrypt(
        { name: 'AES-GCM', iv: new Uint8Array(iv) },
        derivedKey,
        new Uint8Array(data)
    );
    
    return decoder.decode(decrypted);
}

// On first use, prompt user for password to protect key
// On subsequent loads, prompt for password to decrypt
```

**UX Flow:**
1. First time: Generate key → Prompt "Create a password to protect your key" → Encrypt → Store
2. Return visit: Prompt "Enter your key password" → Decrypt → Use

**Verification:** Inspect localStorage, verify key is encrypted blob, not plain hex.

---

## 🟡 PHASE S2: MEDIUM PRIORITY SECURITY (Plan for Later)

### S2.1 Tighten Content Security Policy
**Severity:** MEDIUM  
**Time:** 2 hours  
**Files:** `trinity-icp/src/.ic-assets.json5`  
**Docker Rebuild:** No

**Problem:** CSP includes `'unsafe-inline'` in script-src, weakening XSS protection.

**Implementation:**
1. Generate nonces for inline scripts during build
2. Update CSP to use `'nonce-{random}'` instead of `'unsafe-inline'`
3. Add nonce attribute to all `<script>` tags

```json
{
  "Content-Security-Policy": "default-src 'self'; script-src 'self' 'nonce-{BUILD_NONCE}' https://cdn.jsdelivr.net; ..."
}
```

**Complexity:** Requires build pipeline changes to inject nonces.

---

### S2.2 Constant-Time Signature Verification
**Severity:** MEDIUM  
**Time:** 30 minutes  
**Files:** `backend/icp_auth.py`  
**Docker Rebuild:** Yes

**Problem:** `nacl.signing.VerifyKey.verify()` may leak timing information about how much of the signature matched before failing.

**Implementation:**
```python
import time
import random

def verify_signature_constant_time(verify_key, signed_message):
    """Wrap signature verification with timing attack mitigation"""
    try:
        # The actual verification
        result = verify_key.verify(signed_message)
        # Add random delay to mask timing
        time.sleep(random.uniform(0.001, 0.005))
        return result
    except nacl.exceptions.BadSignatureError:
        # Same delay on failure
        time.sleep(random.uniform(0.001, 0.005))
        raise
```

**Note:** nacl library already has some timing protection, but this adds defense-in-depth.

---

### S2.3 Restrict CORS Origins
**Severity:** MEDIUM  
**Time:** 30 minutes  
**Files:** `backend/inference_server.py`  
**Docker Rebuild:** Yes

**Problem:** `Access-Control-Allow-Origin: *` allows any website to call API.

**Implementation:**
```python
ALLOWED_ORIGINS = [
    'https://trinityai.cc',
    'https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io',
    'https://zc67k-kiaaa-aaaal-qtmiq-cai.raw.icp0.io',
    'http://localhost:3000',  # Local dev
    'http://127.0.0.1:3000',
]

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin', '')
    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
    # Don't set header if origin not in whitelist
    return response
```

---

## ⚡ PHASE P1: PERFORMANCE OPTIMIZATIONS

### P1.1 Fix Typing Animation Layout Thrash
**Severity:** HIGH (UX impact)  
**Time:** 1 hour  
**Files:** `trinity-icp/src/app.js`  
**Docker Rebuild:** No

**Problem:** `innerHTML` + `renderKatex()` called every 15ms causes layout reflow on every frame. On mobile, this can cause janky scrolling and high CPU usage.

**Implementation:**
```javascript
// Throttle KaTeX rendering to every 500ms instead of every frame
let lastKatexRender = 0;
const KATEX_RENDER_INTERVAL = 500;

typingInterval = setInterval(() => {
    // ... typing logic ...
    
    // Throttled KaTeX
    const now = Date.now();
    if (now - lastKatexRender > KATEX_RENDER_INTERVAL) {
        renderKatex();
        lastKatexRender = now;
    }
}, 15);
```

**Verification:** Profile in Chrome DevTools, verify fewer layout recalculations.

---

### P1.2 Connection Pooling for Ollama
**Severity:** MEDIUM  
**Time:** 30 minutes  
**Files:** `backend/inference_server.py`  
**Docker Rebuild:** Yes

**Problem:** Each request to Ollama creates a new HTTP connection. For high traffic, this wastes resources.

**Implementation:**
```python
# At module level, create persistent session:
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Connection pool for Ollama
ollama_session = requests.Session()
retry_strategy = Retry(total=3, backoff_factor=0.5)
adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=retry_strategy)
ollama_session.mount('http://', adapter)

# In generate functions, use session instead of requests:
response = ollama_session.post(
    f"{OLLAMA_HOST}/api/generate",
    json=payload,
    stream=True,
    timeout=300
)
```

---

### P1.3 Memory Leak Prevention (Page Unload)
**Severity:** MEDIUM  
**Time:** 30 minutes  
**Files:** `trinity-icp/src/app.js`  
**Docker Rebuild:** No

**Problem:** If user navigates away during streaming, `typingInterval` may not be cleared.

**Implementation:**
```javascript
// At module level, track active intervals
let activeTypingInterval = null;

// In typing animation:
activeTypingInterval = setInterval(() => { ... }, 15);

// Add cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (activeTypingInterval) {
        clearInterval(activeTypingInterval);
        activeTypingInterval = null;
    }
});

// Also cleanup on new chat:
function newChat() {
    if (activeTypingInterval) {
        clearInterval(activeTypingInterval);
        activeTypingInterval = null;
    }
    // ... rest of newChat
}
```

---

## 📦 PHASE U1: RECOMMENDED UPGRADES

### U1.1 Upgrade cryptography Package
**Severity:** LOW (security maintenance)  
**Time:** 15 minutes  
**Files:** `backend/requirements.txt`  
**Docker Rebuild:** Yes

**Change:**
```
cryptography>=42.0.0  # Was >=41.0.0
```

**Reason:** Security fixes in 42.x series.

---

### U1.2 Consider Argon2id for Key Derivation
**Severity:** LOW (future-proofing)  
**Time:** 2 hours  
**Files:** `backend/encryption.py`  
**Docker Rebuild:** Yes

**Current:** PBKDF2 with 100k iterations (acceptable but aging)  
**Recommended:** Argon2id (memory-hard, resistant to GPU attacks)

**Implementation:**
```python
from argon2.low_level import hash_secret_raw, Type

def derive_key_argon2(password: str, salt: bytes) -> bytes:
    """Derive encryption key using Argon2id"""
    return hash_secret_raw(
        secret=password.encode(),
        salt=salt,
        time_cost=3,
        memory_cost=65536,  # 64MB
        parallelism=4,
        hash_len=32,
        type=Type.ID
    )
```

**Note:** Requires adding `argon2-cffi` to requirements.txt

---

### U1.3 Replace Regex HTML Parsing with BeautifulSoup
**Severity:** LOW (code quality)  
**Time:** 1 hour  
**Files:** `backend/inference_server.py`  
**Docker Rebuild:** Yes

**Current:** Manual regex for HTML text extraction (fragile)  
**Recommended:** BeautifulSoup (robust, handles edge cases)

```python
from bs4 import BeautifulSoup

def extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove script, style, nav elements
    for tag in soup(['script', 'style', 'head', 'nav', 'footer']):
        tag.decompose()
    
    return soup.get_text(separator=' ', strip=True)[:10000]
```

**Note:** Requires adding `beautifulsoup4` to requirements.txt

---

### U1.4 Add Response Compression
**Severity:** LOW (bandwidth optimization)  
**Time:** 30 minutes  
**Files:** `backend/inference_server.py`, `backend/requirements.txt`  
**Docker Rebuild:** Yes

**Implementation:**
```python
from flask_compress import Compress

app = Flask(__name__)
Compress(app)  # Automatically gzip responses > 500 bytes
```

**Note:** Requires adding `flask-compress` to requirements.txt

---

## ✅ Completed Security Work (Reference)

### January 31, 2026 - v3.7.0
- ✅ **CRITICAL:** Removed TEST_MODE auth bypass (was in `@require_auth`)
- ✅ **CRITICAL:** Added path traversal protection in `storage.py`
- ✅ Backend input validation (`validate_chat_id`, `validate_principal_id`, `validate_cid`)
- ✅ Rate limiting on `/generate*` endpoints (30 req/min per IP)
- ✅ Applied validation to all `/chat/*` endpoints

### Previously Completed
- ✅ Ed25519 signature verification for authenticated endpoints
- ✅ AES-256-GCM encryption for all stored data
- ✅ PBKDF2 key derivation with 100k iterations
- ✅ TLS 1.3 via Vercel proxy
- ✅ CSP headers (with `unsafe-inline` - to be tightened)

---

## 🔵 DEFERRED PHASES (After Security)

### Phase 4: Hardware Scaling
**Goal**: Multi-GPU support for larger models (Llama 405B+).
**Status**: Deferred until security hardening complete.

### Phase 5: Agent Framework
**Goal**: Transform Trinity from chat wrapper to autonomous agent.
**Status**: Deferred until security hardening complete.

### PDF Document Parsing
**Goal**: Support PDF uploads in chat.
**Status**: Deferred - security first.

### Live Market Data
**Goal**: Real-time crypto/stock prices.
**Status**: Deferred - security first.

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

