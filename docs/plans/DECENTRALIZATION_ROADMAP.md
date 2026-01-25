# Trinity Decentralization Roadmap
## Engineering Implementation Guide

> **Purpose:** Complete technical specification for eliminating centralized dependencies  
> **Target:** Pure ICP + Akash + Filecoin stack  
> **Author:** Claude Opus 4.5  
> **Date:** January 25, 2026  
> **Status:** Phase 1 Complete ✅ | Phase 2 Complete ✅ | Phase 3 Complete ✅ | Phase 4 Planned ⏳

---

## ⏰ ACTION REQUIRED: Filecoin Deal Verification

**If the current date is on or after Sunday, January 25, 2026 at 4:22 PM:**

Check Filecoin deal status for Phase 1 archives:
```bash
# Via backend endpoint
curl https://u2k74jdr358rt168vo6bmi8mas.ingress.akashprovid.com/chat/archive/status/<CID>

# Or via Lighthouse API directly
curl "https://api.lighthouse.storage/api/lighthouse/deal_status?cid=<CID>"
```

If deals are sealed, mark Phase 1.9 checklist item as complete and push update to GitHub.

---

Notes from the human: Ensure that for all new files, or edits you create, any modifications whatsoever made in /trinity, remember:

 you are to remain true to the principals of strong foundations of file sorting, nomenclature, and engineering. Always remember you are building for future engineers who will have to read your code. be clear, concise, organized. remain committed to future fault detection, and code commenting for crucial distinctions, and clarifications, and periodic testing and sanity checking.

 Before making any changes to storage, memory, networking, the akash backend, or website functionality -- always ensure you have a thorough understanding of how that is built. if it is built in a confusing way, then you are to re-design it to be sleek, and fast, and committed to our core values for Trinity.

---

## Executive Summary

This document provides step-by-step coding and deployment instructions to transform Trinity from a hybrid architecture (with Cloudflare and Pinata) to a purely decentralized stack.

### Current Architecture
```
User → Cloudflare Worker → Akash Backend → Ollama
              ↓
         Pinata → IPFS (no Filecoin)
```

### Target Architecture
```
User → ICP Canister → HTTPS Outcall → Akash Backend → Ollama
              ↓
         Lighthouse → IPFS + Filecoin (verified deals)
              ↓
         Handshake DNS (.trinity TLD)
```

---

# Phase 1: Lighthouse SDK Integration ✅ COMPLETE
## Replace Pinata with Direct Filecoin Storage

**Timeline:** 1-2 weeks → **Completed January 24, 2026**  
**Risk Level:** Low  
**Dependencies:** None

### Implementation Summary
- ✅ Lighthouse SDK installed (`@lighthouse-web3/sdk`)
- ✅ Backend `inference_server.py` migrated from Pinata to Lighthouse
- ✅ Frontend `lighthouse.js` module created for status checking
- ✅ Environment variables updated (`LIGHTHOUSE_API_KEY`)
- ✅ Akash deployment YAMLs updated with new API key
- ✅ Docker image rebuilt and deployed
- ✅ Archive functionality verified working in production

### 1.1 Prerequisites

```bash
# Get Lighthouse API key
# 1. Go to https://files.lighthouse.storage
# 2. Create account (free)
# 3. Generate API key from dashboard
# 4. Save as LIGHTHOUSE_API_KEY
```

### 1.2 Install Lighthouse SDK

```bash
cd trinity-icp
npm install @lighthouse-web3/sdk
```

### 1.3 Update Environment Configuration

**File:** `.env.example`

```diff
- # Pinata JWT token for Filecoin/IPFS archival
- FILECOIN_API_KEY=your_pinata_jwt_token_here

+ # Lighthouse API key for IPFS + Filecoin storage
+ # Get from: https://files.lighthouse.storage
+ LIGHTHOUSE_API_KEY=your_lighthouse_api_key_here
```

**File:** `trinity-icp/.env`

```bash
LIGHTHOUSE_API_KEY=your_actual_key_here
```

### 1.4 Create Lighthouse Storage Module

**File:** `trinity-icp/src/storage/lighthouse.js` (NEW)

```javascript
/**
 * Lighthouse Storage Module
 * Handles IPFS pinning + Filecoin deal creation
 * Replaces Pinata for permanent, verifiable storage
 */

import lighthouse from '@lighthouse-web3/sdk';

// API key from environment or config
const LIGHTHOUSE_API_KEY = import.meta.env.VITE_LIGHTHOUSE_API_KEY || '';

/**
 * Upload encrypted chat data to IPFS + Filecoin
 * @param {Object} chatData - The chat object to archive
 * @param {string} encryptedContent - AES-256-GCM encrypted content
 * @returns {Promise<{cid: string, size: number, gateways: string[]}>}
 */
export async function uploadToFilecoin(chatData, encryptedContent) {
    if (!LIGHTHOUSE_API_KEY) {
        throw new Error('Lighthouse API key not configured');
    }

    const filename = `trinity-archive-${chatData.id}-${Date.now()}.enc`;
    
    try {
        // Upload to IPFS (instant) + queue for Filecoin deal
        const response = await lighthouse.uploadText(
            encryptedContent,
            LIGHTHOUSE_API_KEY,
            filename
        );

        const cid = response.data.Hash;
        const size = response.data.Size;

        console.log(`✅ Uploaded to IPFS: ${cid}`);
        console.log(`📦 Size: ${size} bytes`);
        console.log(`⏳ Filecoin deal will be created automatically`);

        return {
            cid,
            size: parseInt(size),
            filename,
            gateways: [
                `https://gateway.lighthouse.storage/ipfs/${cid}`,
                `https://ipfs.io/ipfs/${cid}`,
                `https://dweb.link/ipfs/${cid}`,
                `https://cloudflare-ipfs.com/ipfs/${cid}`
            ],
            filecoinDealPending: true
        };
    } catch (error) {
        console.error('Lighthouse upload failed:', error);
        throw new Error(`Failed to upload to Filecoin: ${error.message}`);
    }
}

/**
 * Check Filecoin deal status for a CID
 * Deals typically take 1-24 hours to seal
 * @param {string} cid - IPFS content identifier
 * @returns {Promise<{dealStatus: string, deals: Array}>}
 */
export async function getFilecoinDealStatus(cid) {
    try {
        const response = await lighthouse.dealStatus(cid);
        
        if (!response.data || response.data.length === 0) {
            return {
                dealStatus: 'pending',
                message: 'Filecoin deal not yet created (can take 1-24 hours)',
                deals: []
            };
        }

        return {
            dealStatus: 'active',
            deals: response.data.map(deal => ({
                dealId: deal.dealId,
                storageProvider: deal.storageProvider,
                status: deal.dealStatus,
                startEpoch: deal.startEpoch,
                endEpoch: deal.endEpoch
            }))
        };
    } catch (error) {
        console.error('Failed to check deal status:', error);
        return {
            dealStatus: 'unknown',
            error: error.message,
            deals: []
        };
    }
}

/**
 * Retrieve content from IPFS via multiple gateways
 * Tries gateways in order until one succeeds
 * @param {string} cid - IPFS content identifier
 * @returns {Promise<string>} - The retrieved content
 */
export async function retrieveFromIPFS(cid) {
    const gateways = [
        `https://gateway.lighthouse.storage/ipfs/${cid}`,
        `https://ipfs.io/ipfs/${cid}`,
        `https://dweb.link/ipfs/${cid}`
    ];

    for (const gateway of gateways) {
        try {
            const response = await fetch(gateway, { 
                headers: { 'Accept': 'application/json, text/plain, */*' }
            });
            
            if (response.ok) {
                console.log(`✅ Retrieved from: ${gateway}`);
                return await response.text();
            }
        } catch (error) {
            console.warn(`Gateway failed: ${gateway}`, error.message);
            continue;
        }
    }

    throw new Error(`Failed to retrieve CID ${cid} from all gateways`);
}

/**
 * Get upload quota and usage info
 * @returns {Promise<{used: number, limit: number}>}
 */
export async function getStorageInfo() {
    try {
        const response = await lighthouse.getBalance(LIGHTHOUSE_API_KEY);
        return {
            dataUsed: response.data.dataUsed,
            dataLimit: response.data.dataLimit
        };
    } catch (error) {
        console.error('Failed to get storage info:', error);
        return { dataUsed: 0, dataLimit: 0 };
    }
}
```

### 1.5 Update Archive Module

**File:** `trinity-icp/src/modules/archive.js`

```diff
+ import { uploadToFilecoin, getFilecoinDealStatus, retrieveFromIPFS } from '../storage/lighthouse.js';

// In the archive function, replace Pinata upload with:

- // Old Pinata code
- const response = await fetch('https://api.pinata.cloud/pinning/pinJSONToIPFS', {
-     method: 'POST',
-     headers: {
-         'Content-Type': 'application/json',
-         'Authorization': `Bearer ${PINATA_JWT}`
-     },
-     body: JSON.stringify({ content: encryptedContent })
- });

+ // New Lighthouse code
+ const result = await uploadToFilecoin(chatData, encryptedContent);
+ const cid = result.cid;
+ 
+ // Store CID with gateway URLs for redundancy
+ return {
+     cid,
+     gateways: result.gateways,
+     filecoinPending: true,
+     archivedAt: new Date().toISOString()
+ };
```

### 1.6 Update Backend Archive Endpoint

**File:** `backend/inference_server.py`

```python
# Add new endpoint to check Filecoin deal status

@app.route('/chat/archive/status/<cid>', methods=['GET'])
def get_archive_status(cid):
    """
    Check if archived chat has been sealed in Filecoin deal.
    Deals typically take 1-24 hours to complete.
    """
    try:
        # Call Lighthouse API to check deal status
        response = requests.get(
            f'https://api.lighthouse.storage/api/lighthouse/deal_status?cid={cid}',
            headers={'Authorization': f'Bearer {os.environ.get("LIGHTHOUSE_API_KEY", "")}'
        })
        
        if response.status_code == 200:
            deals = response.json()
            return jsonify({
                'cid': cid,
                'status': 'active' if deals else 'pending',
                'deals': deals,
                'message': 'Stored on Filecoin' if deals else 'Awaiting Filecoin deal (1-24 hours)'
            })
        else:
            return jsonify({'cid': cid, 'status': 'unknown', 'deals': []})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

### 1.7 Update Vite Configuration

**File:** `trinity-icp/vite.config.js`

```javascript
export default defineConfig({
  // ... existing config
  define: {
    'import.meta.env.VITE_LIGHTHOUSE_API_KEY': JSON.stringify(process.env.LIGHTHOUSE_API_KEY)
  }
});
```

### 1.8 Testing Phase 1

```bash
# 1. Set environment variable
export LIGHTHOUSE_API_KEY="your_key_here"

# 2. Build frontend
cd trinity-icp && npm run build

# 3. Test upload manually
node -e "
const lighthouse = require('@lighthouse-web3/sdk');
lighthouse.uploadText('test content', process.env.LIGHTHOUSE_API_KEY, 'test.txt')
    .then(r => console.log('CID:', r.data.Hash))
    .catch(e => console.error(e));
"

# 4. Test in browser
# - Create a chat
# - Click Archive button
# - Verify CID is returned
# - Check deal status after 1-24 hours
```

### 1.9 Phase 1 Completion Checklist

- [x] Lighthouse SDK installed
- [x] lighthouse.js module created
- [x] archive.js updated to use Lighthouse
- [x] Backend endpoint for deal status added
- [x] Environment variables configured
- [x] Manual upload test successful
- [x] Archive button works in UI
- [x] Multiple gateway retrieval works
- [ ] Deal status check works (after 24 hours) - *Pending: Filecoin deals take 1-24 hours to seal*

---

# Phase 2: ICP Backend Canister ✅ COMPLETE
## Replace Cloudflare with ICP HTTPS Outcalls

**Timeline:** 3-6 weeks → **Completed January 25, 2026**  
**Risk Level:** Medium  
**Dependencies:** Phase 1 complete ✅

### Implementation Summary
- ✅ Rust canister created (`trinity-icp/src/backend_canister/`)
- ✅ HTTPS Outcalls to Akash backend working
- ✅ Ed25519 signature verification in canister
- ✅ Deterministic `/health/icp` endpoint for ICP consensus
- ✅ Idempotency cache with `X-Request-ID` header
- ✅ Candid interface properly defined
- ✅ Canister deployed to mainnet (`au5zq-2qaaa-aaaal-qtowa-cai`)
- ✅ Health check verified working through canister
- ✅ Deployment script created (`./icp-deploy`)

### Key Technical Challenges Solved

**ICP Consensus Problem:**
All 13 subnet replicas make identical HTTP requests. If responses differ (timestamps, CPU stats), consensus fails with "Replicas had different responses" error.

**Solution:**
1. Created `/health/icp` endpoint that returns ONLY static data (no timestamps, no dynamic metrics)
2. Added `@icp_idempotent` decorator in Flask that caches responses by `X-Request-ID` header
3. Canister generates deterministic request IDs using time buckets (10-second windows)

### Files Created/Modified
- `trinity-icp/src/backend_canister/src/lib.rs` - Main Rust canister (550 lines)
- `trinity-icp/src/backend_canister/Cargo.toml` - Rust dependencies
- `trinity-icp/src/backend_canister/trinity_backend.did` - Candid interface
- `trinity-icp/Cargo.toml` - Workspace config
- `trinity-icp/dfx.json` - Added backend canister
- `trinity-icp/src/api/canister-client.js` - Frontend actor client
- `trinity-icp/src/api/backend-router.js` - A/B testing router
- `backend/inference_server.py` - Added `/health/icp` + `@icp_idempotent`
- `./icp-deploy` - Deployment script for both canisters

### Deployment Commands
```bash
# Deploy both canisters (backend first, then frontend)
./icp-deploy

# Deploy only frontend (for UI changes)
./icp-deploy frontend

# Deploy only backend canister (for Rust changes)
./icp-deploy backend

# Verify deployment
dfx canister --network ic call trinity_backend health
dfx canister --network ic call trinity_backend get_canister_info
```

### 2.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     ICP SUBNET (13 replicas)                     │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              TRINITY BACKEND CANISTER                     │   │
│  │                                                           │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │   │
│  │  │ Auth Module │  │ HTTP Outcall│  │ Response Cache  │   │   │
│  │  │ (Ed25519)   │  │ (to Akash)  │  │ (Idempotency)   │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘   │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│          All 13 replicas make identical HTTP request             │
└──────────────────────────────┼───────────────────────────────────┘
                               ▼
                    ┌─────────────────────┐
                    │   AKASH BACKEND     │
                    │  (Flask + Ollama)   │
                    └─────────────────────┘
```

### 2.2 Prerequisites

```bash
# Install Rust and IC SDK
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
sh -ci "$(curl -fsSL https://internetcomputer.org/install.sh)"

# Add wasm target
rustup target add wasm32-unknown-unknown

# Install candid-extractor
cargo install candid-extractor
```

### 2.3 Create Backend Canister Structure

```bash
cd trinity-icp

# Create backend canister directory
mkdir -p src/backend_canister/src
```

### 2.4 Backend Canister - Cargo.toml

**File:** `trinity-icp/src/backend_canister/Cargo.toml`

```toml
[package]
name = "trinity_backend"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]

[dependencies]
candid = "0.10"
ic-cdk = "0.13"
ic-cdk-macros = "0.9"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
sha2 = "0.10"
ed25519-dalek = { version = "2", features = ["rand_core"] }
hex = "0.4"
base64 = "0.21"

[profile.release]
lto = true
opt-level = 'z'
```

### 2.5 Backend Canister - Main Implementation

**File:** `trinity-icp/src/backend_canister/src/lib.rs`

```rust
use candid::{CandidType, Deserialize, Principal};
use ic_cdk::api::management_canister::http_request::{
    http_request, CanisterHttpRequestArgument, HttpHeader, HttpMethod, HttpResponse,
    TransformArgs, TransformContext, TransformFunc,
};
use ic_cdk_macros::{init, query, update};
use serde::Serialize;
use std::cell::RefCell;
use std::collections::HashMap;

// ============================================================================
// TYPES
// ============================================================================

#[derive(CandidType, Deserialize, Clone, Debug)]
pub struct GenerateRequest {
    pub prompt: String,
    pub model: Option<String>,
    pub context_messages: Option<Vec<Message>>,
}

#[derive(CandidType, Deserialize, Serialize, Clone, Debug)]
pub struct Message {
    pub role: String,
    pub content: String,
}

#[derive(CandidType, Deserialize, Clone, Debug)]
pub struct AuthHeaders {
    pub principal: String,
    pub timestamp: String,
    pub signature: String,
    pub public_key: String,
}

#[derive(CandidType, Serialize, Clone, Debug)]
pub struct GenerateResponse {
    pub response: String,
    pub model: String,
    pub provider_id: String,
    pub done: bool,
}

#[derive(CandidType, Serialize, Clone, Debug)]
pub struct HealthResponse {
    pub status: String,
    pub provider_id: String,
    pub model: String,
    pub backend: String,
}

#[derive(CandidType, Serialize, Clone, Debug)]
pub struct ErrorResponse {
    pub error: String,
    pub code: u16,
}

// ============================================================================
// STATE
// ============================================================================

thread_local! {
    // Akash backend URL - updateable by controller
    static AKASH_URL: RefCell<String> = RefCell::new(
        "https://your-akash-ingress.com".to_string()
    );
    
    // Response cache for idempotency (request_id -> response)
    static RESPONSE_CACHE: RefCell<HashMap<String, (String, u64)>> = RefCell::new(HashMap::new());
}

// ============================================================================
// INITIALIZATION
// ============================================================================

#[init]
fn init(akash_url: Option<String>) {
    if let Some(url) = akash_url {
        AKASH_URL.with(|u| *u.borrow_mut() = url);
    }
}

// ============================================================================
// CONFIGURATION
// ============================================================================

#[update]
fn set_akash_url(url: String) -> Result<(), String> {
    let caller = ic_cdk::caller();
    if !ic_cdk::api::is_controller(&caller) {
        return Err("Unauthorized: only controller can update Akash URL".to_string());
    }
    
    AKASH_URL.with(|u| *u.borrow_mut() = url);
    Ok(())
}

#[query]
fn get_akash_url() -> String {
    AKASH_URL.with(|u| u.borrow().clone())
}

// ============================================================================
// HEALTH CHECK
// ============================================================================

#[update]
async fn health() -> Result<HealthResponse, ErrorResponse> {
    let url = AKASH_URL.with(|u| format!("{}/health", u.borrow()));
    
    let request = CanisterHttpRequestArgument {
        url,
        method: HttpMethod::GET,
        body: None,
        max_response_bytes: Some(10_000),
        transform: Some(TransformContext {
            function: TransformFunc(candid::Func {
                principal: ic_cdk::id(),
                method: "transform_health".to_string(),
            }),
            context: vec![],
        }),
        headers: vec![],
    };

    let cycles: u128 = 500_000_000;

    match http_request(request, cycles).await {
        Ok((response,)) => {
            let body = String::from_utf8(response.body)
                .unwrap_or_else(|_| "{}".to_string());
            
            match serde_json::from_str::<HealthResponse>(&body) {
                Ok(health) => Ok(health),
                Err(_) => Err(ErrorResponse {
                    error: "Failed to parse health response".to_string(),
                    code: 500,
                }),
            }
        }
        Err((code, msg)) => Err(ErrorResponse {
            error: format!("HTTP request failed: {} - {}", code as u32, msg),
            code: 502,
        }),
    }
}

// ============================================================================
// LLM GENERATION
// ============================================================================

#[update]
async fn generate(
    request: GenerateRequest,
    auth: AuthHeaders,
    request_id: String,
) -> Result<GenerateResponse, ErrorResponse> {
    
    // 1. Verify Ed25519 signature
    if !verify_signature(&auth) {
        return Err(ErrorResponse {
            error: "Invalid signature".to_string(),
            code: 401,
        });
    }

    // 2. Check cache for idempotency
    let cached = RESPONSE_CACHE.with(|cache| {
        let cache = cache.borrow();
        if let Some((response, timestamp)) = cache.get(&request_id) {
            let now = ic_cdk::api::time();
            let ttl = 60_000_000_000u64; // 60 seconds
            if now - timestamp < ttl {
                return Some(response.clone());
            }
        }
        None
    });

    if let Some(cached_response) = cached {
        match serde_json::from_str::<GenerateResponse>(&cached_response) {
            Ok(resp) => return Ok(resp),
            Err(_) => {}
        }
    }

    // 3. Build request to Akash backend
    let url = AKASH_URL.with(|u| format!("{}/generate", u.borrow()));
    
    let body = serde_json::json!({
        "prompt": request.prompt,
        "model": request.model.unwrap_or_else(|| "llama3.1:70b".to_string()),
        "context": request.context_messages,
        "stream": false
    });

    let request_body = serde_json::to_vec(&body)
        .map_err(|e| ErrorResponse {
            error: format!("Failed to serialize request: {}", e),
            code: 400,
        })?;

    let http_request_arg = CanisterHttpRequestArgument {
        url,
        method: HttpMethod::POST,
        body: Some(request_body),
        max_response_bytes: Some(100_000),
        transform: Some(TransformContext {
            function: TransformFunc(candid::Func {
                principal: ic_cdk::id(),
                method: "transform_generate".to_string(),
            }),
            context: vec![],
        }),
        headers: vec![
            HttpHeader {
                name: "Content-Type".to_string(),
                value: "application/json".to_string(),
            },
            HttpHeader {
                name: "X-Request-ID".to_string(),
                value: request_id.clone(),
            },
            HttpHeader {
                name: "X-ICP-Principal".to_string(),
                value: auth.principal.clone(),
            },
            HttpHeader {
                name: "X-ICP-Timestamp".to_string(),
                value: auth.timestamp.clone(),
            },
            HttpHeader {
                name: "X-ICP-Signature".to_string(),
                value: auth.signature.clone(),
            },
            HttpHeader {
                name: "X-ICP-PublicKey".to_string(),
                value: auth.public_key.clone(),
            },
        ],
    };

    // 2B cycles ≈ $0.002 per request
    let cycles: u128 = 2_000_000_000;

    match http_request(http_request_arg, cycles).await {
        Ok((response,)) => {
            let body_str = String::from_utf8(response.body.clone())
                .unwrap_or_else(|_| "{}".to_string());

            // Cache response for idempotency
            RESPONSE_CACHE.with(|cache| {
                let mut cache = cache.borrow_mut();
                cache.insert(request_id, (body_str.clone(), ic_cdk::api::time()));
                
                // Cleanup old entries
                let now = ic_cdk::api::time();
                let ttl = 60_000_000_000u64;
                cache.retain(|_, (_, ts)| now - ts < ttl);
            });

            match serde_json::from_str::<GenerateResponse>(&body_str) {
                Ok(gen_response) => Ok(gen_response),
                Err(e) => Err(ErrorResponse {
                    error: format!("Failed to parse response: {}", e),
                    code: 500,
                }),
            }
        }
        Err((code, msg)) => Err(ErrorResponse {
            error: format!("Akash request failed: {} - {}", code as u32, msg),
            code: 502,
        }),
    }
}

// ============================================================================
// SIGNATURE VERIFICATION
// ============================================================================

fn verify_signature(auth: &AuthHeaders) -> bool {
    use ed25519_dalek::{Signature, VerifyingKey};
    use sha2::{Sha256, Digest};

    // Check timestamp is within 5 minutes
    let timestamp: i64 = match auth.timestamp.parse() {
        Ok(ts) => ts,
        Err(_) => return false,
    };
    
    let now_ms = (ic_cdk::api::time() / 1_000_000) as i64;
    let five_minutes_ms = 5 * 60 * 1000;
    
    if (now_ms - timestamp).abs() > five_minutes_ms {
        return false;
    }

    // Decode public key
    let public_key_bytes = match hex::decode(&auth.public_key) {
        Ok(bytes) => bytes,
        Err(_) => return false,
    };

    let public_key = match VerifyingKey::from_bytes(
        public_key_bytes.as_slice().try_into().unwrap_or(&[0u8; 32])
    ) {
        Ok(pk) => pk,
        Err(_) => return false,
    };

    // Decode signature
    let signature_bytes = match hex::decode(&auth.signature) {
        Ok(bytes) => bytes,
        Err(_) => return false,
    };

    let signature = match Signature::from_bytes(
        signature_bytes.as_slice().try_into().unwrap_or(&[0u8; 64])
    ) {
        Ok(sig) => sig,
        Err(_) => return false,
    };

    // Verify
    let message = format!("{}:{}", auth.principal, auth.timestamp);
    let mut hasher = Sha256::new();
    hasher.update(message.as_bytes());
    let message_hash = hasher.finalize();

    public_key.verify_strict(&message_hash, &signature).is_ok()
}

// ============================================================================
// TRANSFORM FUNCTIONS
// ============================================================================

#[query]
fn transform_health(args: TransformArgs) -> HttpResponse {
    HttpResponse {
        status: args.response.status,
        headers: vec![],
        body: args.response.body,
    }
}

#[query]
fn transform_generate(args: TransformArgs) -> HttpResponse {
    HttpResponse {
        status: args.response.status,
        headers: vec![],
        body: args.response.body,
    }
}

// Export Candid interface
ic_cdk::export_candid!();
```

### 2.6 Candid Interface File

**File:** `trinity-icp/src/backend_canister/trinity_backend.did`

```candid
type Message = record {
    role : text;
    content : text;
};

type GenerateRequest = record {
    prompt : text;
    model : opt text;
    context_messages : opt vec Message;
};

type AuthHeaders = record {
    principal : text;
    timestamp : text;
    signature : text;
    public_key : text;
};

type GenerateResponse = record {
    response : text;
    model : text;
    provider_id : text;
    done : bool;
};

type HealthResponse = record {
    status : text;
    provider_id : text;
    model : text;
    backend : text;
};

type ErrorResponse = record {
    error : text;
    code : nat16;
};

type Result_Generate = variant {
    Ok : GenerateResponse;
    Err : ErrorResponse;
};

type Result_Health = variant {
    Ok : HealthResponse;
    Err : ErrorResponse;
};

service : (opt text) -> {
    set_akash_url : (text) -> (variant { Ok; Err : text });
    get_akash_url : () -> (text) query;
    health : () -> (Result_Health);
    generate : (GenerateRequest, AuthHeaders, text) -> (Result_Generate);
    transform_health : (record { response : record { status : nat; headers : vec record { name : text; value : text }; body : vec nat8 }; context : vec nat8 }) -> (record { status : nat; headers : vec record { name : text; value : text }; body : vec nat8 }) query;
    transform_generate : (record { response : record { status : nat; headers : vec record { name : text; value : text }; body : vec nat8 }; context : vec nat8 }) -> (record { status : nat; headers : vec record { name : text; value : text }; body : vec nat8 }) query;
}
```

### 2.7 Update dfx.json

**File:** `trinity-icp/dfx.json`

```json
{
  "canisters": {
    "trinity_frontend": {
      "type": "assets",
      "source": ["dist"]
    },
    "trinity_backend": {
      "type": "rust",
      "package": "trinity_backend",
      "candid": "src/backend_canister/trinity_backend.did"
    }
  },
  "defaults": {
    "build": {
      "args": "",
      "packtool": ""
    }
  },
  "version": 1
}
```

### 2.8 Frontend API Client

**File:** `trinity-icp/src/api/canister-client.js` (NEW)

```javascript
/**
 * ICP Canister Client
 * Replaces Cloudflare Worker for backend communication
 */

import { Actor, HttpAgent } from '@dfinity/agent';
import { AuthManager } from '../auth/authManager.js';

// Canister ID - update after deployment
const BACKEND_CANISTER_ID = 'xxxxx-xxxxx-xxxxx-xxxxx-cai';

let agent = null;
let backendActor = null;

async function getActor() {
    if (backendActor) return backendActor;
    
    const host = window.location.hostname.includes('localhost') 
        ? 'http://localhost:4943' 
        : 'https://ic0.app';
    
    agent = new HttpAgent({ host });
    
    if (host.includes('localhost')) {
        await agent.fetchRootKey();
    }
    
    // IDL factory would be generated by dfx build
    backendActor = Actor.createActor(idlFactory, {
        agent,
        canisterId: BACKEND_CANISTER_ID,
    });
    
    return backendActor;
}

/**
 * Generate LLM response via ICP canister
 */
export async function generateViaCanister(prompt, contextMessages = []) {
    const actor = await getActor();
    const identity = AuthManager.getIdentity();
    
    if (!identity) {
        throw new Error('Not authenticated');
    }
    
    const timestamp = Date.now().toString();
    const principal = identity.getPrincipal().toString();
    const message = `${principal}:${timestamp}`;
    const signature = await AuthManager.signMessage(message);
    const publicKey = AuthManager.getPublicKeyHex();
    
    const requestId = `${principal}-${timestamp}-${Math.random().toString(36).slice(2)}`;
    
    const request = {
        prompt,
        model: [],
        context_messages: contextMessages.length > 0 
            ? [contextMessages.map(m => ({ role: m.role, content: m.content }))]
            : [],
    };
    
    const auth = {
        principal,
        timestamp,
        signature,
        public_key: publicKey,
    };
    
    try {
        const result = await actor.generate(request, auth, requestId);
        
        if ('Ok' in result) {
            return result.Ok;
        } else {
            throw new Error(result.Err.error);
        }
    } catch (error) {
        console.error('Canister generate failed:', error);
        throw error;
    }
}

/**
 * Health check via ICP canister
 */
export async function healthCheckViaCanister() {
    const actor = await getActor();
    
    try {
        const result = await actor.health();
        
        if ('Ok' in result) {
            return result.Ok;
        } else {
            throw new Error(result.Err.error);
        }
    } catch (error) {
        console.error('Canister health check failed:', error);
        throw error;
    }
}
```

### 2.9 Update Akash Backend for Idempotency

**File:** `backend/inference_server.py` (additions)

```python
import redis
import hashlib

# Initialize Redis for response caching
redis_client = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)

def get_cached_response(request_id):
    """Check if we've already processed this request"""
    try:
        cached = redis_client.get(f"trinity:response:{request_id}")
        if cached:
            return json.loads(cached)
    except Exception as e:
        print(f"Redis cache miss: {e}")
    return None

def cache_response(request_id, response, ttl=60):
    """Cache response for 60 seconds"""
    try:
        redis_client.setex(
            f"trinity:response:{request_id}",
            ttl,
            json.dumps(response)
        )
    except Exception as e:
        print(f"Redis cache write failed: {e}")

@app.route('/generate', methods=['POST'])
def generate():
    request_id = request.headers.get('X-Request-ID', '')
    
    # Check cache first (idempotency for ICP's 13 replicas)
    if request_id:
        cached = get_cached_response(request_id)
        if cached:
            print(f"🔄 Returning cached response for request {request_id[:16]}...")
            return jsonify(cached)
    
    # ... existing generation logic ...
    
    response_data = {
        'response': generated_text,
        'model': model_name,
        'provider_id': provider_id,
        'done': True
    }
    
    if request_id:
        cache_response(request_id, response_data)
    
    return jsonify(response_data)
```

### 2.10 Add Redis to Akash Deployment

**File:** `deploy/akash/deploy-llama70.yaml` (additions)

```yaml
services:
  redis:
    image: redis:alpine
    expose:
      - port: 6379
        as: 6379
        to:
          - service: trinity-backend
    
  trinity-backend:
    image: ghcr.io/your-org/trinity-backend:latest
    depends_on:
      - redis
    env:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
```

### 2.11 Build and Deploy Backend Canister

```bash
cd trinity-icp

# Build the canister
dfx build trinity_backend

# Deploy to mainnet
dfx deploy trinity_backend --ic --argument '(opt "https://your-akash-ingress.com")'

# Get the canister ID
dfx canister id trinity_backend --ic
# Output: xxxxx-xxxxx-xxxxx-xxxxx-cai

# Update canister-client.js with this ID
```

### 2.12 Phase 2 Completion Checklist

- [x] Rust canister code written
- [x] Candid interface defined
- [x] dfx.json updated
- [x] Frontend canister client created
- [x] Akash backend updated with idempotency cache (in-memory, no Redis needed)
- [x] `/health/icp` endpoint added for deterministic responses
- [x] Canister built successfully
- [x] Canister deployed to IC mainnet (`au5zq-2qaaa-aaaal-qtowa-cai`)
- [x] Health check works via canister
- [x] Generate works via canister
- [x] Latency measured and acceptable
- [x] Deployment script created (`./icp-deploy`)

**Note:** Redis was not required. In-memory caching with `@icp_idempotent` decorator 
and deterministic endpoints solved the ICP consensus problem more elegantly.

---

# Phase 3: Cloudflare Removal ✅ COMPLETE
## Direct ICP Canister Routing

**Timeline:** 1 day → **Completed January 25, 2026**  
**Risk Level:** Low  

### Implementation Summary

Since there are no production users yet, we skipped the gradual A/B rollout and went 
directly to 100% ICP canister routing. This is the simplest and most decentralized path.

**Changes Made:**
- ✅ `app.js` now imports `canister-client.js` directly
- ✅ `API.generate()` routes through ICP canister when `CONFIG.USE_CANISTER = true`
- ✅ `Actions.checkConnection()` uses canister health check
- ✅ `CONFIG.USE_CANISTER` flag added (default: `true`)
- ✅ `cloudflare/` directory deleted
- ✅ `backend-router.js` not needed (kept for reference but unused)

### 3.1 Architecture (Final)

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend      │     │  ICP Backend    │     │  Akash Backend  │
│   (ICP Asset)   │ ──▶ │   Canister      │ ──▶ │  (Flask+Ollama) │
│                 │     │  HTTPS Outcall  │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
     Browser              au5zq-2qaaa...          GPU Inference
```

**Data Flow:**
1. User types prompt in browser
2. `app.js` calls `generateViaCanister(prompt, context)`
3. ICP canister receives call, verifies Ed25519 signature
4. Canister makes HTTPS outcall to Akash backend
5. Akash runs LLM inference, returns response
6. Canister returns response to frontend
7. Frontend displays AI message

### 3.2 Key Files Modified

**`trinity-icp/src/config.js`:**
```javascript
// ICP Canister routing - Phase 3 Complete
USE_CANISTER: true,
BACKEND_CANISTER_ID: 'au5zq-2qaaa-aaaal-qtowa-cai',
```

**`trinity-icp/src/app.js`:**
```javascript
import { generateViaCanister, healthCheckViaCanister, isCanisterConfigured } from './api/canister-client.js';

// In API.generate():
if (CONFIG.USE_CANISTER && isCanisterConfigured()) {
    const result = await generateViaCanister(prompt, contextMessages);
    return { generated_text: result.response, ... };
}
```

### 3.3 Fallback Option

If canister routing ever needs to be disabled (debugging, etc.):

```javascript
// In browser console:
localStorage.setItem('trinity_use_canister', 'false');
location.reload();

// Or edit config.js:
USE_CANISTER: false,  // Falls back to direct HTTP
```

### 3.4 Phase 3 Completion Checklist

- [x] `app.js` wired to use `generateViaCanister()` directly
- [x] `checkConnection()` uses canister health check
- [x] `CONFIG.USE_CANISTER` flag added and enabled
- [x] Cloudflare workers deleted (`rm -rf cloudflare/`)
- [x] A/B testing infrastructure skipped (not needed)
- [x] Documentation updated

**Note:** The `backend-router.js` file was kept but is not imported anywhere.
It can be deleted or kept as reference for future A/B testing if users grow.

---

# Phase 4: Handshake DNS
## Truly Decentralized Domain Name

**Timeline:** 1-2 weeks (can be done anytime)  
**Risk Level:** Low (optional enhancement)

### 4.1 What is Handshake?

Handshake (HNS) is a **decentralized, permissionless naming protocol** that replaces ICANN DNS.

**Key differences:**
- No central authority (ICANN controls traditional DNS)
- Own your TLD forever (no yearly renewals)
- Names stored on blockchain (censorship resistant)
- No registrar lock-in

### 4.2 Acquire .trinity TLD

**Option A: Namebase Marketplace (Easiest)**

```bash
# 1. Go to https://namebase.io
# 2. Create account
# 3. Search for "trinity" TLD
# 4. If available, purchase directly (~$50-200)
# 5. If taken, make an offer to current owner
```

**Option B: Direct Auction**

```bash
# 1. Install HNS node or use Bob Wallet
# 2. Fund with HNS tokens
# 3. Open auction for "trinity"
# 4. Bidding period: ~5 days
# 5. Reveal period: ~10 days
# 6. Winner owns TLD forever
```

### 4.3 Configure DNS Records

```dns
# Point to ICP boundary nodes
app.trinity. CNAME icp1.io.

# Or direct IP
app.trinity. A 193.118.59.140
```

### 4.4 Access Methods

| Method | URL | Browser Support |
|--------|-----|-----------------|
| Bridge | app.trinity.hns.to | All browsers |
| Native | app.trinity | HNS-enabled only |
| Resolver DNS | app.trinity | Set DNS to 103.196.38.38 |

### 4.5 User Documentation

Create user guide explaining:
1. Bridge access (works everywhere): `https://app.trinity.hns.to`
2. Native access with browser extensions (LinkFrame, Puma)
3. System DNS configuration for native resolution

### 4.6 Phase 4 Completion Checklist

- [ ] .trinity TLD acquired
- [ ] DNS records configured
- [ ] Bridge access working (app.trinity.hns.to)
- [ ] Native access working (app.trinity)
- [ ] ICP canister updated with allowed origins
- [ ] Frontend config updated
- [ ] User documentation written

---

# Summary: Final Architecture

```
     ╔═══════════════╗     ╔═══════════════╗     ╔═══════════════╗
     ║      ICP      ║     ║     AKASH     ║     ║   FILECOIN    ║
     ║   Identity    ║     ║    Compute    ║     ║    Storage    ║
     ╚═══════════════╝     ╚═══════════════╝     ╚═══════════════╝
     
         Frontend           GPU + LLM            Permanent
         Auth (Ed25519)     Inference            Archives
         HTTPS Outcalls     Hot Storage          Verified Deals
         
               ┌──────────── Handshake DNS ────────────┐
               │         app.trinity (TLD)             │
               └───────────────────────────────────────┘
```

## Centralized Dependencies Eliminated

| Was | Now | Phase |
|-----|-----|-------|
| Cloudflare Workers | ICP HTTPS Outcalls | 2 |
| Pinata | Lighthouse + Filecoin | 1 |
| ICANN DNS | Handshake | 4 |

## Cost: ~$55-70/month

| Component | Cost |
|-----------|------|
| Akash GPU | $50-60/mo |
| ICP Cycles | $5-10/mo |
| Lighthouse | ~$0 (pay per GB) |
| Handshake TLD | $0 (one-time) |
| Domain (trinityai.cc) | $8/year |

---

*Document Version: 1.0*  
*Last Updated: January 24, 2026*  
*Author: Claude Opus 4.5*
