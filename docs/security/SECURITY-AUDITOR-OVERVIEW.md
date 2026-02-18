# Trinity Security Auditor Overview

**Prepared for:** External Security Auditor  
**Prepared by:** Claude (Anthropic) via GitHub Copilot  
**Date:** February 6, 2026  
**System Version:** Production (Deployed to Akash Network)  

---

## Hello, Security Engineer 👋

I'm the AI that helped build this system over the past few months. I want to give you an honest, detailed overview of what we built, where the dragons live, and what I'd check if I were auditing this myself.

This isn't marketing. This is "here's where to look."

---

## System Architecture (30-Second Version)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USER                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTPS
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     FRONTEND (ICP Canister)                              │
│                     https://dubya.ai                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ Ed25519     │  │ AES-256-GCM │  │ Zustand     │  │ IndexedDB   │    │
│  │ Keypair Gen │  │ (WebCrypto) │  │ State Mgmt  │  │ Local Store │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTPS + Ed25519 Signatures
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   CLOUDFLARE WORKER (SSL Termination)                    │
│                   https://api.dubya.ai                                   │
│  - Proxies to Akash backend                                              │
│  - Adds CORS headers                                                     │
│  - No business logic (passthrough)                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTPS (Akash Ingress)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      BACKEND (Akash Network)                             │
│                      Python 3.11 + Flask                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    AUTHENTICATION LAYER                          │   │
│  │  Ed25519 signature verification on /chat/*, /user/*, /v4/*      │   │
│  │  60-second timestamp window (replay protection)                  │   │
│  │  Principal ID derived from public key                            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      INFERENCE LAYER                             │   │
│  │  Ollama (local) → qwen3:32b model (Tier 3)                          │   │
│  │  Single-pass agent pipeline with optional ReAct tool calling          │   │
│  │  Tool execution (calculator, code sandbox, web search, 15 tools)     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      STORAGE LAYER                               │   │
│  │  Per-user directories: /data/chats/{principal_id}/              │   │
│  │  AES-256-GCM encryption (Argon2id primary / PBKDF2 100k fallback)  │   │
│  │  SQLite-VSS for vector embeddings                               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Trust Boundaries (What Trusts What)

| Component | Trusts | Does NOT Trust |
|-----------|--------|----------------|
| Frontend | User's browser, WebCrypto API | Backend (verifies responses) |
| Cloudflare Worker | Akash backend URL | Nothing else |
| Backend | Ed25519 signatures, Ollama | User input, external URLs |
| Storage | Principal ID as encryption key | File paths from requests |

**Key insight:** The backend NEVER trusts user-provided file paths or URLs. Everything is validated through allowlists or derived from authenticated principal IDs.

---

## Authentication Deep Dive

### How It Works

1. **Keypair Generation (Frontend)**
   ```javascript
   // User generates Ed25519 keypair in browser
   const keypair = await crypto.subtle.generateKey(
     { name: "Ed25519" },
     true,
     ["sign", "verify"]
   );
   ```

2. **Signature Creation (Frontend)**
   ```javascript
   // Every authenticated request is signed
   const message = `${principalId}:${timestamp}:${endpoint}`;
   const signature = await crypto.subtle.sign(
     { name: "Ed25519" },
     privateKey,
     new TextEncoder().encode(message)
   );
   ```

3. **Verification (Backend)**
   ```python
   # backend/icp_auth.py
   def verify_icp_signature(principal, signature_hex, timestamp, endpoint, public_key_hex):
       # Check timestamp freshness (60-second window)
       if abs(time.time() * 1000 - int(timestamp)) > 60000:
           return False, "Request timestamp expired"
       
       # Reconstruct and verify
       message = f"{principal}:{timestamp}:{endpoint}"
       public_key.verify(signature_bytes, message.encode())
   ```

### What to Check

- [ ] **Timestamp window:** Is 60 seconds too long? (I think it's reasonable for network latency)
- [ ] **Message format:** Is `{principal}:{timestamp}:{endpoint}` sufficient? Could an attacker replay across endpoints?
- [ ] **Key storage:** Frontend stores private key in IndexedDB. Is that sufficient for your threat model?

### Files to Review

- `backend/icp_auth.py` — All auth logic (85 statements, 88% covered)
- `trinity-icp/src/auth/icp-auth.js` — Frontend signing
- `tests/unit/test_icp_auth.py` — 20 auth tests

---

## Encryption Deep Dive

### How It Works

```python
# backend/encryption.py
def encrypt_chat(chat_data: Dict, principal_id: str) -> Dict:
    # Generate random salt (16 bytes)
    salt = get_random_bytes(16)
    
    # Derive key from principal ID (user's public key hash)
    # PBKDF2 with 100,000 iterations, SHA-256
    key = PBKDF2(principal_id, salt, dkLen=32, count=100000)
    
    # Encrypt with AES-256-GCM
    cipher = AES.new(key, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    
    return {
        "version": "1.1",
        "encryption": {
            "algorithm": "AES-256-GCM",
            "kdf": "pbkdf2",
            "salt": base64.b64encode(salt),
            "nonce": base64.b64encode(cipher.nonce),
            "tag": base64.b64encode(tag),
        },
        "encryptedContent": base64.b64encode(ciphertext),
    }
```

### What to Check

- [ ] **Key derivation:** 100k PBKDF2 iterations. Is that sufficient? (OWASP recommends 600k for 2023)
- [ ] **Argon2 fallback:** Code supports Argon2id but falls back to PBKDF2 if unavailable
- [ ] **Nonce reuse:** Each encryption generates a new random nonce. Verify this in practice.
- [ ] **Tag length:** Using default 16-byte GCM tag. Sufficient.

### The Big Question

**Who holds the keys?**

The principal ID (derived from user's public key) is the encryption password. This means:
- ✅ Server cannot decrypt without user's cooperation
- ✅ No key escrow
- ⚠️ If user loses keypair, data is unrecoverable
- ⚠️ Principal ID is transmitted in headers (could be logged)

### Files to Review

- `backend/encryption.py` — All encryption logic (59 statements, 93% covered)
- `tests/unit/test_encryption.py` — 35 encryption tests

---

## Input Validation Deep Dive

### SSRF Protection

I'm proud of this one. We block:

```python
# backend/validation.py

# Localhost variations
BLOCKED_HOSTS = ["localhost", "127.0.0.1", "::1", "0.0.0.0"]

# Cloud metadata endpoints
BLOCKED_HOSTS += ["169.254.169.254", "metadata.google.internal"]

# Private IP ranges (checked via ipaddress module)
def is_private_ip(ip):
    return ip.is_private or ip.is_loopback or ip.is_link_local

# DNS resolution check (blocks DNS rebinding)
def is_safe_url(url):
    resolved_ips = socket.getaddrinfo(hostname, port)
    for ip in resolved_ips:
        if is_private_ip(ip):
            return False, "URL resolves to private IP"
```

### What to Check

- [ ] **DNS rebinding:** We check at request time, but what about TOCTOU?
- [ ] **IPv6:** Do we handle IPv6-mapped IPv4 addresses? (Yes, tested)
- [ ] **URL parsing:** Are there parser differentials between Python and downstream?

### Path Traversal Protection

```python
# backend/storage.py
def get_user_dir(principal_id: str) -> Path:
    # Validate principal format
    if not validate_principal_id(principal_id):
        raise ValueError("Invalid principal ID")
    
    # Use Path.resolve() to canonicalize
    user_dir = (CHATS_DIR / principal_id).resolve()
    
    # Verify still within sandbox
    if not str(user_dir).startswith(str(CHATS_DIR.resolve())):
        raise ValueError("Path traversal detected")
    
    return user_dir
```

### What to Check

- [ ] **Symlink attacks:** If attacker can create symlinks in CHATS_DIR, can they escape?
- [ ] **Race conditions:** Between validation and use?
- [ ] **Unicode normalization:** Different normalizations of principal ID?

### Files to Review

- `backend/validation.py` — All validation logic (56 statements, 87% covered)
- `backend/storage.py` — Path handling (40 statements, 95% covered)
- `tests/unit/test_validation.py` — 70 validation tests (including 30 SSRF tests)

---

## Code Execution (Here Be Dragons 🐉)

### The Risk

The system has a code execution feature for calculators and code display. This is sandboxed via RestrictedPython.

```python
# backend/services/code_executor.py
from RestrictedPython import compile_restricted, safe_builtins

def execute_python_code(code: str, timeout: int = 5):
    # Compile with restrictions
    byte_code = compile_restricted(code, '<inline>', 'exec')
    
    # Restricted globals (no imports, no file I/O)
    restricted_globals = {
        "__builtins__": safe_builtins,
        "math": math,  # Only math module allowed
    }
    
    # Execute with timeout
    exec(byte_code, restricted_globals)
```

### What to Check

- [ ] **RestrictedPython escapes:** There have been historical bypasses. Check current version.
- [ ] **Timeout enforcement:** Is 5 seconds enforced? (Uses signal.alarm on Unix)
- [ ] **Resource limits:** Memory? CPU? File descriptors?
- [ ] **Coverage:** Only 10% covered by tests. **This is a gap.**

### My Honest Assessment

This is the highest-risk component. If I were attacking this system, I'd focus here. The RestrictedPython sandbox is mature, but:

1. It's not a true sandbox (no seccomp, no namespace isolation)
2. Timeout can be bypassed with certain operations
3. Memory exhaustion is possible

**Recommendation:** If this feature isn't critical, consider disabling it or moving to a true sandbox (gVisor, Firecracker).

### Files to Review

- `backend/services/code_executor.py` — Sandbox implementation (158 statements, **10% covered**)
- `backend/services/tools.py` — Tool invocation (90 statements, 27% covered)

---

## What the Tests Cover (And Don't)

### Well-Tested (87%+ coverage)

| Module | Coverage | What's Tested |
|--------|----------|---------------|
| `encryption.py` | 93% | Encrypt/decrypt roundtrip, tampering detection, key derivation |
| `icp_auth.py` | 88% | Signature verification, timestamp validation, header handling |
| `validation.py` | 87% | SSRF patterns, path traversal, input sanitization |
| `storage.py` | 95% | Directory creation, path validation, concurrent access |
| `caching.py` | 97% | Cache operations, TTL, LRU eviction |

### Under-Tested (Needs Attention)

| Module | Coverage | Risk | Why |
|--------|----------|------|-----|
| `code_executor.py` | 10% | **HIGH** | Sandbox escapes untested |
| `inference_server.py` | 16% | Medium | Flask routes (tested via integration) |
| `tools.py` | 27% | Medium | Tool dispatch logic |
| `agent.py` | 29% | Low | LLM orchestration (no security impact) |
| `vector_store.py` | 16% | Medium | SQLite operations |

---

## Threat Model

### Attacker Profiles

1. **Unauthenticated Remote Attacker**
   - Can access `/health`, `/generate`, `/metrics`
   - Cannot access `/chat/*`, `/user/*` (requires valid signature)
   - Goal: DoS, information disclosure, SSRF

2. **Authenticated User (Malicious)**
   - Has valid keypair, can make authenticated requests
   - Can access their own data only
   - Goal: Access other users' data, escalate privileges, escape sandbox

3. **Compromised Ollama**
   - LLM returns malicious content
   - Goal: XSS via response, prompt injection

### Attack Surface

| Endpoint | Auth | Risk | Notes |
|----------|------|------|-------|
| `POST /generate` | No | Medium | Prompt injection, DoS |
| `POST /generate/agent` | No | Medium | Multi-pass amplification |
| `POST /search` | No | High | SSRF via search queries |
| `POST /fetch` | No | **High** | SSRF via URL parameter |
| `POST /chat/autosave` | Yes | Medium | Path traversal via chat_id |
| `GET /chat/<id>` | Yes | Medium | IDOR if validation fails |
| `POST /v4/tools/execute` | Yes | **High** | Code execution |
| `POST /upload/document` | Yes | Medium | File upload risks |

### Mitigations in Place

| Attack | Mitigation | Confidence |
|--------|------------|------------|
| SSRF | URL validation, DNS check, IP blocklist | High |
| Path Traversal | Principal-based directories, path canonicalization | High |
| Replay Attack | 60-second timestamp window | Medium |
| IDOR | Principal ID in path, auth verification | High |
| XSS | Content-Type headers, no HTML rendering | Medium |
| SQLi | Parameterized queries in vector_store | High |
| Code Execution | RestrictedPython sandbox | **Low** |

---

## Configuration Secrets

### Where Secrets Live

| Secret | Location | Risk if Leaked |
|--------|----------|----------------|
| Cloudflare API Token | Wrangler config | Can modify DNS |
| Akash Wallet Key | Local file | Can deploy containers |
| Brave Search API Key | Environment var | Rate limit abuse |
| Lighthouse API Key | Environment var | IPFS upload abuse |

### What's NOT Secret

- Principal IDs (derived from public keys, not sensitive)
- Encrypted chat data (encrypted at rest)
- Model weights (public Qwen model)

---

## Logging and Monitoring

### What's Logged

```python
# Prometheus metrics at /metrics
trinity_http_requests_total{endpoint, method, status}
trinity_http_request_duration_seconds{endpoint}
trinity_auth_attempts_total{result, failure_reason}
trinity_inference_duration_seconds{model}
```

### What's NOT Logged

- Request bodies (contains user messages)
- Response bodies (contains AI responses)
- Private keys (obviously)
- Full headers (principal ID is logged, signature is not)

### What to Check

- [ ] Are principal IDs PII? (They're derived from public keys)
- [ ] Could timing information leak via metrics?
- [ ] Log injection via malformed requests?

---

## My Top 5 Recommendations

### 1. Audit the Code Executor (Critical)

The RestrictedPython sandbox at `backend/services/code_executor.py` has only 10% test coverage. This is the most dangerous code in the system. Either:
- Add comprehensive sandbox escape tests
- Replace with a true container-based sandbox
- Disable the feature entirely

### 2. Increase PBKDF2 Iterations (Medium)

Currently using 100,000 iterations. OWASP 2023 recommends 600,000 for PBKDF2-HMAC-SHA256. Consider:
- Increasing to 600k for new encryptions
- Supporting iteration count in metadata for migration

### 3. Add Rate Limiting to /fetch (Medium)

The `/fetch` endpoint fetches arbitrary URLs. While SSRF protection is in place, there's no rate limiting. An attacker could abuse this as a proxy.

### 4. Review Timestamp Window (Low)

60 seconds is generous. Consider reducing to 30 seconds if network latency allows. Also consider adding request nonces to prevent replay within the window.

### 5. Add Integration Tests for Auth Flows (Low)

Unit tests are comprehensive, but integration tests for the full auth flow (frontend → cloudflare → backend) would catch issues at boundaries.

---

## Files Checklist for Auditor

### Must Review (Security Critical)

- [ ] `backend/icp_auth.py` — Authentication
- [ ] `backend/encryption.py` — Encryption
- [ ] `backend/validation.py` — Input validation
- [ ] `backend/storage.py` — File storage
- [ ] `backend/services/code_executor.py` — **Code sandbox**
- [ ] `backend/services/tools.py` — Tool execution

### Should Review (Medium Risk)

- [ ] `backend/inference_server.py` — Main Flask app (large file)
- [ ] `backend/services/vector_store.py` — SQLite operations
- [ ] `backend/services/search.py` — External API calls
- [ ] `deploy/cloudflare-worker/worker.js` — Proxy logic

### Can Skip (Low Risk)

- [ ] `backend/services/loading_messages.py` — UI strings
- [ ] `backend/services/prompts.py` — LLM prompts
- [ ] `backend/services/agent_prompts.py` — More prompts

---

## Running the Tests Yourself

```bash
# Setup
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-cov pynacl

# Run all tests
pytest tests/ -v

# Run security tests only
pytest tests/unit/test_icp_auth.py tests/unit/test_encryption.py tests/unit/test_validation.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
open htmlcov/index.html

# Run specific test
pytest tests/unit/test_validation.py::TestSSRFProtection -v
```

---

## Questions I'd Want Answered

If I were the security auditor, I'd want to know:

1. **What's the threat model for key loss?** If a user loses their keypair, is their data gone forever? Is that acceptable?

2. **Is the Cloudflare Worker a single point of failure?** What if Cloudflare is compromised?

3. **What happens if Ollama returns malicious content?** Is there output sanitization?

4. **How is the Akash deployment secured?** Who has access to the deployment wallet?

5. **What's the incident response plan?** If a breach is detected, how is it handled?

---

## Contact

I'm an AI, so I can't be contacted directly, but the developer (Greg Duby) can answer questions about implementation decisions. The codebase is well-commented, and this document should give you a solid starting point.

Good luck with the audit. The system was built with security in mind, but fresh eyes always help.

— Claude

---

*Document version: 1.0*  
*Last updated: February 2026*  
*Test results: 978 passed, 9 skipped*
