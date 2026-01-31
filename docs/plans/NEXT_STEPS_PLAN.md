# Trinity Next Steps Implementation Plan

> **Updated:** January 31, 2026  
> **Status:** Security hardening complete. Moving to quick wins.

---

## Quick Reference

| Priority | Task | Effort | Docker? |
|----------|------|--------|---------|
| 🟡 MED | Show CID after archive | 30 min | ❌ No |
| 🟡 MED | trinityai.cc SSL certificate | 5 min | ❌ No |
| 🟢 LOW | PDF document parsing | 2 hrs | ✅ Yes |
| 🟢 LOW | Live market data | 4 hrs | ✅ Yes |
| 🔵 FUTURE | Memory system upgrade | 4 hrs | ✅ Yes |
| 🔵 FUTURE | Monetization | 16+ hrs | ✅ Yes |

---

## 🟡 Priority 1: Quick Wins

### 1.1 Show CID After Archive
**File:** `trinity-icp/src/modules/archive.js`  
**Time:** 30 minutes  
**Docker:** No (frontend only)

**Problem:** Archive success notification doesn't show the CID. Users must check console.

**Current:**
```javascript
UI.showSuccess(`Chat archived to Filecoin! (${response.archivedCount}/10)`);
```

**Fix:**
```javascript
const shortCid = response.cid.substring(0, 12) + '...' + response.cid.slice(-6);
UI.showSuccess(`Archived! CID: ${shortCid} (${response.archivedCount}/10)`);
console.log(`Full CID: ${response.cid}`);
console.log(`Verify: https://gateway.lighthouse.storage/ipfs/${response.cid}`);
```

---

### 1.2 trinityai.cc SSL Certificate
**Status:** DNS working, SSL pending  
**Time:** 5 minutes (just redeploy)

**Fix:**
```bash
dfx deploy --ic trinity_frontend
```

**Verify:**
```bash
curl -I https://trinityai.cc
```

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

