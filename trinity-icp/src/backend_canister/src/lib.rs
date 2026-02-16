// ============================================================================
// Trinity Backend Canister - lib.rs
// ============================================================================
//
// PURPOSE:
// This ICP canister replaces Cloudflare Workers as the HTTPS proxy between
// the frontend and the Akash backend. It provides:
//
// 1. HTTPS Outcalls to Akash backend (LLM inference, storage)
// 2. Ed25519 signature verification (same as current backend)
// 3. Response caching for idempotency (ICP runs 13 replicas)
// 4. Decentralized, censorship-resistant infrastructure
//
// ARCHITECTURE:
// Frontend (ICP) → This Canister → HTTPS Outcall → Akash Backend → Ollama
//
// WHY 13 REPLICAS MATTER:
// ICP runs each update call on 13 subnet nodes. All 13 make the same HTTP
// request to Akash. The Akash backend must handle this idempotently.
// We use X-Request-ID header and response caching to ensure only one
// LLM inference runs per user request.
//
// COST:
// Each HTTPS outcall costs ~2B cycles ≈ $0.002
// Health checks cost ~500M cycles ≈ $0.0005
// ============================================================================

use candid::{CandidType, Deserialize};
use ic_cdk::api::management_canister::http_request::{
    http_request, CanisterHttpRequestArgument, HttpHeader, HttpMethod, HttpResponse,
    TransformArgs, TransformContext, TransformFunc,
};
use ic_stable_structures::memory_manager::{MemoryId, MemoryManager, VirtualMemory};
use ic_stable_structures::{DefaultMemoryImpl, StableBTreeMap, Storable, storable::Bound};
use serde::Serialize;
use std::borrow::Cow;
use std::cell::RefCell;
use std::collections::HashMap;

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

/// Request structure for LLM generation
#[derive(CandidType, Deserialize, Clone, Debug)]
pub struct GenerateRequest {
    pub prompt: String,
    pub model: Option<String>,
    pub context_messages: Option<Vec<Message>>,
}

/// Chat message (user/assistant role + content)
#[derive(CandidType, Deserialize, Serialize, Clone, Debug)]
pub struct Message {
    pub role: String,
    pub content: String,
}

/// Authentication headers from frontend
/// Must match the Ed25519 signature scheme in authManager.js
#[derive(CandidType, Deserialize, Clone, Debug)]
pub struct AuthHeaders {
    pub principal_id: String,
    pub timestamp: String,
    pub signature: String,
    pub public_key: String,
}

/// Response from LLM generation
#[derive(CandidType, Deserialize, Serialize, Clone, Debug)]
pub struct GenerateResponse {
    pub response: String,
    pub model: String,
    pub provider_id: String,
    pub done: bool,
}

/// Health check response from Akash backend /health endpoint
/// Contains deterministic fields for ICP consensus
/// Note: Some fields are optional for backwards compatibility with older backends
#[derive(CandidType, Deserialize, Serialize, Clone, Debug)]
pub struct HealthResponse {
    pub status: String,
    pub provider_id: String,
    pub model: String,
    pub gpu_type: String,
    pub ollama_connected: bool,
    // Optional fields - may not exist on older backend images
    #[serde(default)]
    pub build_timestamp: Option<String>,
    #[serde(default)]
    pub version: Option<String>,
    #[serde(default)]
    pub icp_compatible: Option<bool>,
}

/// Error response structure
#[derive(CandidType, Serialize, Clone, Debug)]
pub struct ErrorResponse {
    pub error: String,
    pub code: u16,
}

// ============================================================================
// USERNAME REGISTRY TYPES (Stable Storage)
// ============================================================================

/// Memory IDs for stable storage partitions
const MEMORY_ID_USERNAME_TO_INFO: MemoryId = MemoryId::new(0);
const MEMORY_ID_PRINCIPAL_TO_USERNAME: MemoryId = MemoryId::new(1);

type Memory = VirtualMemory<DefaultMemoryImpl>;

/// Max key sizes for StableBTreeMap
const MAX_USERNAME_LEN: u32 = 20;
const MAX_PRINCIPAL_LEN: u32 = 64; // ICP principal text is ~27-63 chars
const MAX_USER_INFO_LEN: u32 = 256; // serialized UserInfo

/// Wrapper for String keys in StableBTreeMap
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
struct StableString(String);

impl Storable for StableString {
    fn to_bytes(&self) -> Cow<[u8]> {
        Cow::Owned(self.0.as_bytes().to_vec())
    }

    fn from_bytes(bytes: Cow<[u8]>) -> Self {
        StableString(String::from_utf8(bytes.to_vec()).unwrap_or_default())
    }

    const BOUND: Bound = Bound::Bounded {
        max_size: MAX_PRINCIPAL_LEN,
        is_fixed_size: false,
    };
}

/// User registration info stored on-chain
#[derive(CandidType, Deserialize, Serialize, Clone, Debug)]
pub struct UserInfo {
    pub principal: String,
    pub public_key_hex: String,
    pub registered_at: u64,
}

impl Storable for UserInfo {
    fn to_bytes(&self) -> Cow<[u8]> {
        let bytes = serde_json::to_vec(self).unwrap_or_default();
        Cow::Owned(bytes)
    }

    fn from_bytes(bytes: Cow<[u8]>) -> Self {
        serde_json::from_slice(&bytes).unwrap_or(UserInfo {
            principal: String::new(),
            public_key_hex: String::new(),
            registered_at: 0,
        })
    }

    const BOUND: Bound = Bound::Bounded {
        max_size: MAX_USER_INFO_LEN,
        is_fixed_size: false,
    };
}

// ============================================================================
// CANISTER STATE
// ============================================================================

thread_local! {
    /// Akash backend URL - configurable by canister controller
    /// Default points to Cloudflare Worker (handles SSL for Akash)
    static AKASH_URL: RefCell<String> = RefCell::new(
        "https://api.dubya.ai".to_string()
    );

    /// Response cache for idempotency
    /// Key: request_id, Value: (JSON response, timestamp_ns)
    /// TTL: 60 seconds - long enough for ICP consensus + Akash response
    static RESPONSE_CACHE: RefCell<HashMap<String, (String, u64)>> = RefCell::new(HashMap::new());

    /// Cache TTL in nanoseconds (60 seconds)
    static CACHE_TTL_NS: u64 = 60_000_000_000;

    /// Stable storage memory manager
    static MEMORY_MANAGER: RefCell<MemoryManager<DefaultMemoryImpl>> = RefCell::new(
        MemoryManager::init(DefaultMemoryImpl::default())
    );

    /// Username → UserInfo (bidirectional mapping, part 1)
    static USERNAME_TO_INFO: RefCell<StableBTreeMap<StableString, UserInfo, Memory>> =
        RefCell::new(StableBTreeMap::init(
            MEMORY_MANAGER.with(|m| m.borrow().get(MEMORY_ID_USERNAME_TO_INFO))
        ));

    /// Principal → Username (bidirectional mapping, part 2)
    static PRINCIPAL_TO_USERNAME: RefCell<StableBTreeMap<StableString, StableString, Memory>> =
        RefCell::new(StableBTreeMap::init(
            MEMORY_MANAGER.with(|m| m.borrow().get(MEMORY_ID_PRINCIPAL_TO_USERNAME))
        ));
}

// ============================================================================
// INITIALIZATION
// ============================================================================

/// Initialize canister with optional custom Akash URL
#[ic_cdk::init]
fn init(akash_url: Option<String>) {
    if let Some(url) = akash_url {
        AKASH_URL.with(|u| *u.borrow_mut() = url);
        ic_cdk::println!("Trinity Backend initialized with Akash URL: {}", 
            AKASH_URL.with(|u| u.borrow().clone()));
    } else {
        ic_cdk::println!("Trinity Backend initialized with default Akash URL");
    }
}

/// Handle canister upgrades - preserve state
#[ic_cdk::post_upgrade]
fn post_upgrade(akash_url: Option<String>) {
    init(akash_url);
}

// ============================================================================
// CONFIGURATION (Controller-only)
// ============================================================================

/// Update Akash backend URL (controller only)
/// Use this when Akash deployment changes
#[ic_cdk::update]
fn set_akash_url(url: String) -> Result<(), String> {
    let caller = ic_cdk::caller();
    if !ic_cdk::api::is_controller(&caller) {
        return Err("Unauthorized: only controller can update Akash URL".to_string());
    }
    
    AKASH_URL.with(|u| *u.borrow_mut() = url.clone());
    ic_cdk::println!("Akash URL updated to: {}", url);
    Ok(())
}

/// Get current Akash backend URL
#[ic_cdk::query]
fn get_akash_url() -> String {
    AKASH_URL.with(|u| u.borrow().clone())
}

/// Get canister info for debugging
#[ic_cdk::query]
fn get_canister_info() -> String {
    format!(
        "Trinity Backend Canister v0.1.0\nAkash URL: {}\nCache entries: {}",
        AKASH_URL.with(|u| u.borrow().clone()),
        RESPONSE_CACHE.with(|c| c.borrow().len())
    )
}

/// Get the canister's current cycle balance
/// Used by frontend to display funding transparency
#[ic_cdk::query]
fn get_cycle_balance() -> u128 {
    ic_cdk::api::canister_balance128()
}

/// Get cycle balance with additional context
#[ic_cdk::query]
fn get_funding_info() -> String {
    let cycles = ic_cdk::api::canister_balance128();
    let trillion: u128 = 1_000_000_000_000;
    let cycles_t = cycles as f64 / trillion as f64;
    
    // Rough estimate: 1T cycles ≈ $1.30 USD
    // Average cost per request: ~2B cycles
    // Estimate remaining requests
    let cost_per_request: u128 = 2_000_000_000; // 2B cycles
    let remaining_requests = cycles / cost_per_request;
    
    format!(
        "{{\"cycles\": {}, \"cycles_trillion\": {:.4}, \"estimated_usd\": {:.2}, \"estimated_requests_remaining\": {}}}",
        cycles,
        cycles_t,
        cycles_t * 1.30,
        remaining_requests
    )
}

// ============================================================================
// HEALTH CHECK
// ============================================================================

/// Generate a deterministic request ID based on canister ID and current time bucket
/// Using 10-second buckets so all 13 replicas generate the same ID within the window
fn generate_request_id(prefix: &str) -> String {
    let time_ns = ic_cdk::api::time();
    // 10-second bucket (10 billion nanoseconds)
    let time_bucket = time_ns / 10_000_000_000;
    let canister_id = ic_cdk::id().to_string();
    format!("{}-{}-{}", prefix, canister_id, time_bucket)
}

/// Health check - forwards to Akash backend's health endpoint
/// Uses transform function to extract only deterministic fields for consensus
#[ic_cdk::update]
async fn health() -> Result<HealthResponse, ErrorResponse> {
    // Use the standard health endpoint (fallback from /health/icp)
    let url = AKASH_URL.with(|u| format!("{}/health", u.borrow()));
    
    // Generate deterministic request ID for caching
    let request_id = generate_request_id("health");
    
    let request = CanisterHttpRequestArgument {
        url: url.clone(),
        method: HttpMethod::GET,
        body: None,
        max_response_bytes: Some(10_000),
        transform: Some(TransformContext {
            function: TransformFunc(candid::Func {
                principal: ic_cdk::id(),
                method: "transform_response".to_string(),
            }),
            context: vec![],
        }),
        headers: vec![
            HttpHeader {
                name: "Accept".to_string(),
                value: "application/json".to_string(),
            },
            // Include request ID so Akash can cache the response
            HttpHeader {
                name: "X-Request-ID".to_string(),
                value: request_id,
            },
        ],
    };

    // 500M cycles ≈ $0.0005 per health check
    let cycles: u128 = 500_000_000;

    match http_request(request, cycles).await {
        Ok((response,)) => {
            let body = String::from_utf8(response.body)
                .unwrap_or_else(|_| "{}".to_string());
            
            match serde_json::from_str::<HealthResponse>(&body) {
                Ok(health) => Ok(health),
                Err(e) => Err(ErrorResponse {
                    error: format!("Failed to parse health response: {}", e),
                    code: 500,
                }),
            }
        }
        Err((code, msg)) => Err(ErrorResponse {
            error: format!("HTTP request failed: {:?} - {}", code, msg),
            code: 502,
        }),
    }
}

// ============================================================================
// LLM GENERATION (Main Endpoint)
// ============================================================================

/// Generate LLM response via Akash backend
/// 
/// This is the main endpoint that replaces the Cloudflare Worker proxy.
/// Includes Ed25519 signature verification and response caching for idempotency.
///
/// # Arguments
/// * `request` - Generation parameters (prompt, model, context)
/// * `auth` - Authentication headers (principal, timestamp, signature, public_key)
/// * `request_id` - Unique ID for idempotency (frontend generates this)
///
/// # Returns
/// * `Ok(GenerateResponse)` - LLM response
/// * `Err(ErrorResponse)` - Error with code
#[ic_cdk::update]
async fn generate(
    request: GenerateRequest,
    auth: AuthHeaders,
    request_id: String,
) -> Result<GenerateResponse, ErrorResponse> {
    
    // 1. Verify Ed25519 signature
    if !verify_signature(&auth) {
        return Err(ErrorResponse {
            error: "Invalid or expired signature".to_string(),
            code: 401,
        });
    }

    // 2. Check cache for idempotency (handles 13 replica requests)
    if let Some(cached) = get_cached_response(&request_id) {
        ic_cdk::println!("Cache hit for request_id: {}...", &request_id[..16.min(request_id.len())]);
        match serde_json::from_str::<GenerateResponse>(&cached) {
            Ok(resp) => return Ok(resp),
            Err(_) => {} // Cache corrupted, continue with fresh request
        }
    }

    // 3. Build request to Akash backend
    let url = AKASH_URL.with(|u| format!("{}/generate", u.borrow()));
    
    // Generate deterministic seed from request_id for ICP consensus
    // All 13 replicas use the same seed = same LLM output = consensus achieved
    let seed = request_id.bytes().fold(0u64, |acc, b| acc.wrapping_add(b as u64).wrapping_mul(31));
    
    let body = serde_json::json!({
        "prompt": request.prompt,
        "model": request.model.unwrap_or_else(|| "llama3.1:70b".to_string()),
        "context": request.context_messages,
        "stream": false,
        "options": {
            "seed": seed,
            "temperature": 0.0  // Fully deterministic with seed
        }
    });

    let request_body = serde_json::to_vec(&body)
        .map_err(|e| ErrorResponse {
            error: format!("Failed to serialize request: {}", e),
            code: 400,
        })?;

    let http_request_arg = CanisterHttpRequestArgument {
        url: url.clone(),
        method: HttpMethod::POST,
        body: Some(request_body),
        max_response_bytes: Some(100_000), // 100KB max response
        transform: Some(TransformContext {
            function: TransformFunc(candid::Func {
                principal: ic_cdk::id(),
                method: "transform_response".to_string(),
            }),
            context: vec![],
        }),
        headers: vec![
            HttpHeader {
                name: "Content-Type".to_string(),
                value: "application/json".to_string(),
            },
            HttpHeader {
                name: "Accept".to_string(),
                value: "application/json".to_string(),
            },
            // Pass request ID for Akash-side idempotency
            HttpHeader {
                name: "X-Request-ID".to_string(),
                value: request_id.clone(),
            },
            // Pass auth headers so Akash can verify too
            HttpHeader {
                name: "X-ICP-Principal".to_string(),
                value: auth.principal_id.clone(),
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

    // 2B cycles ≈ $0.002 per LLM request
    let cycles: u128 = 2_000_000_000;

    match http_request(http_request_arg, cycles).await {
        Ok((response,)) => {
            let body_str = String::from_utf8(response.body.clone())
                .unwrap_or_else(|_| "{}".to_string());

            // Cache response for idempotency
            cache_response(&request_id, &body_str);

            match serde_json::from_str::<GenerateResponse>(&body_str) {
                Ok(gen_response) => Ok(gen_response),
                Err(e) => Err(ErrorResponse {
                    error: format!("Failed to parse Akash response: {} - Body: {}", e, &body_str[..100.min(body_str.len())]),
                    code: 500,
                }),
            }
        }
        Err((code, msg)) => Err(ErrorResponse {
            error: format!("Akash request failed: {:?} - {}", code, msg),
            code: 502,
        }),
    }
}

// ============================================================================
// ED25519 SIGNATURE VERIFICATION
// ============================================================================

/// Verify Ed25519 signature from frontend
/// 
/// This matches the signing scheme in trinity-icp/src/auth/authManager.js
/// Message format: "{principal}:{timestamp}"
/// Signature is hex-encoded
fn verify_signature(auth: &AuthHeaders) -> bool {
    use ed25519_dalek::{Signature, VerifyingKey};
    use sha2::{Sha256, Digest};

    // 1. Check timestamp is within 5 minutes (replay protection)
    let timestamp: i64 = match auth.timestamp.parse() {
        Ok(ts) => ts,
        Err(_) => {
            ic_cdk::println!("Invalid timestamp format: {}", auth.timestamp);
            return false;
        }
    };
    
    let now_ms = (ic_cdk::api::time() / 1_000_000) as i64;
    let five_minutes_ms: i64 = 5 * 60 * 1000;
    
    if (now_ms - timestamp).abs() > five_minutes_ms {
        ic_cdk::println!("Timestamp expired: {} vs now {}", timestamp, now_ms);
        return false;
    }

    // 2. Decode public key (hex string → 32 bytes)
    let public_key_bytes = match hex::decode(&auth.public_key) {
        Ok(bytes) if bytes.len() == 32 => bytes,
        Ok(bytes) => {
            ic_cdk::println!("Invalid public key length: {} bytes", bytes.len());
            return false;
        }
        Err(e) => {
            ic_cdk::println!("Failed to decode public key: {}", e);
            return false;
        }
    };

    let public_key = match VerifyingKey::from_bytes(
        public_key_bytes.as_slice().try_into().unwrap_or(&[0u8; 32])
    ) {
        Ok(pk) => pk,
        Err(e) => {
            ic_cdk::println!("Invalid public key: {}", e);
            return false;
        }
    };

    // 3. Decode signature (hex string → 64 bytes)
    let signature_bytes = match hex::decode(&auth.signature) {
        Ok(bytes) if bytes.len() == 64 => bytes,
        Ok(bytes) => {
            ic_cdk::println!("Invalid signature length: {} bytes", bytes.len());
            return false;
        }
        Err(e) => {
            ic_cdk::println!("Failed to decode signature: {}", e);
            return false;
        }
    };

    // Convert to fixed-size array for Signature
    let sig_array: [u8; 64] = match signature_bytes.as_slice().try_into() {
        Ok(arr) => arr,
        Err(_) => {
            ic_cdk::println!("Failed to convert signature to array");
            return false;
        }
    };
    let signature = Signature::from_bytes(&sig_array);

    // 4. Verify signature
    // Message format matches authManager.js: "{principal}:{timestamp}"
    // Ed25519 standard: sign raw message bytes (algorithm does internal hashing)
    let message = format!("{}:{}", auth.principal_id, auth.timestamp);

    match public_key.verify_strict(message.as_bytes(), &signature) {
        Ok(_) => true,
        Err(e) => {
            ic_cdk::println!("Signature verification failed: {}", e);
            false
        }
    }
}

// ============================================================================
// RESPONSE CACHING (Idempotency)
// ============================================================================

/// Get cached response if still valid
fn get_cached_response(request_id: &str) -> Option<String> {
    RESPONSE_CACHE.with(|cache| {
        let cache = cache.borrow();
        if let Some((response, timestamp)) = cache.get(request_id) {
            let now = ic_cdk::api::time();
            let ttl = 60_000_000_000u64; // 60 seconds in nanoseconds
            if now - timestamp < ttl {
                return Some(response.clone());
            }
        }
        None
    })
}

/// Cache response with current timestamp
fn cache_response(request_id: &str, response: &str) {
    RESPONSE_CACHE.with(|cache| {
        let mut cache = cache.borrow_mut();
        let now = ic_cdk::api::time();
        
        // Insert new entry
        cache.insert(request_id.to_string(), (response.to_string(), now));
        
        // Cleanup old entries (older than 60 seconds)
        let ttl = 60_000_000_000u64;
        cache.retain(|_, (_, ts)| now - *ts < ttl);
        
        // Prevent unbounded growth (max 1000 entries)
        if cache.len() > 1000 {
            // Remove oldest entries
            let mut entries: Vec<_> = cache.iter()
                .map(|(k, (_, ts))| (k.clone(), *ts))
                .collect();
            entries.sort_by_key(|(_, ts)| *ts);
            
            for (key, _) in entries.iter().take(cache.len() - 500) {
                cache.remove(key);
            }
        }
    });
}

/// Clear cache (controller only, for debugging)
#[ic_cdk::update]
fn clear_cache() -> Result<usize, String> {
    let caller = ic_cdk::caller();
    if !ic_cdk::api::is_controller(&caller) {
        return Err("Unauthorized: only controller can clear cache".to_string());
    }
    
    let count = RESPONSE_CACHE.with(|cache| {
        let len = cache.borrow().len();
        cache.borrow_mut().clear();
        len
    });
    
    Ok(count)
}

// ============================================================================
// TRANSFORM FUNCTIONS
// ============================================================================

/// Transform HTTP response for consensus
/// ICP requires deterministic responses across all 13 replicas
/// We strip headers AND remove any non-deterministic fields from body
/// NOTE: gpu_type is kept as it's static per deployment and needed for HealthResponse
#[ic_cdk::query]
fn transform_response(args: TransformArgs) -> HttpResponse {
    // Parse body and remove any remaining non-deterministic fields
    let body = if let Ok(body_str) = String::from_utf8(args.response.body.clone()) {
        if let Ok(mut json) = serde_json::from_str::<serde_json::Value>(&body_str) {
            // Remove non-deterministic fields that might cause consensus failure
            // NOTE: gpu_type is deterministic (static per deployment) so we keep it
            if let Some(obj) = json.as_object_mut() {
                // Time-varying fields
                obj.remove("timestamp");
                obj.remove("latency_ms");
                obj.remove("tokens_generated");
                obj.remove("prompt");
                // Health endpoint specific dynamic fields
                obj.remove("metrics");      // Contains uptime, request counts, etc.
                obj.remove("system");       // Contains cpu_percent, memory stats
                obj.remove("queue_size");   // Current queue length
                obj.remove("max_queue_size"); // This is static but not needed
            }
            serde_json::to_vec(&json).unwrap_or(args.response.body)
        } else {
            args.response.body
        }
    } else {
        args.response.body
    };

    HttpResponse {
        status: args.response.status,
        headers: vec![], // Strip headers for determinism
        body,
    }
}

// ============================================================================
// USERNAME REGISTRY
// ============================================================================

/// Validate username format: 3-20 chars, [a-z0-9_], normalized to lowercase
fn validate_username(username: &str) -> Result<String, String> {
    let normalized = username.to_lowercase();

    if normalized.len() < 3 {
        return Err("Username must be at least 3 characters".to_string());
    }
    if normalized.len() > 20 {
        return Err("Username must be at most 20 characters".to_string());
    }
    if !normalized.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_') {
        return Err("Username may only contain lowercase letters, digits, and underscores".to_string());
    }
    if normalized.starts_with('_') || normalized.ends_with('_') {
        return Err("Username cannot start or end with an underscore".to_string());
    }

    Ok(normalized)
}

/// Verify Ed25519 signature for registration
/// Message format: "register:{username}:{principal}:{timestamp}"
fn verify_registration_signature(
    username: &str,
    principal: &str,
    public_key_hex: &str,
    signature_hex: &str,
    timestamp: &str,
) -> bool {
    use ed25519_dalek::{Signature, VerifyingKey};

    // Check timestamp within 5 minutes
    let ts: i64 = match timestamp.parse() {
        Ok(ts) => ts,
        Err(_) => return false,
    };
    let now_ms = (ic_cdk::api::time() / 1_000_000) as i64;
    if (now_ms - ts).abs() > 5 * 60 * 1000 {
        return false;
    }

    // Decode public key
    let pk_bytes = match hex::decode(public_key_hex) {
        Ok(bytes) if bytes.len() == 32 => bytes,
        _ => return false,
    };
    let verifying_key = match VerifyingKey::from_bytes(
        pk_bytes.as_slice().try_into().unwrap_or(&[0u8; 32])
    ) {
        Ok(pk) => pk,
        Err(_) => return false,
    };

    // Decode signature
    let sig_bytes = match hex::decode(signature_hex) {
        Ok(bytes) if bytes.len() == 64 => bytes,
        _ => return false,
    };
    let sig_array: [u8; 64] = match sig_bytes.as_slice().try_into() {
        Ok(arr) => arr,
        Err(_) => return false,
    };
    let signature = Signature::from_bytes(&sig_array);

    // Verify: "register:{username}:{principal}:{timestamp}"
    let message = format!("register:{}:{}:{}", username, principal, timestamp);
    verifying_key.verify_strict(message.as_bytes(), &signature).is_ok()
}

/// Register a username → principal mapping on-chain.
/// Requires Ed25519 signature proving ownership of the keypair.
/// One principal can only have one username (enforced bidirectionally).
#[ic_cdk::update]
fn register_username(
    username: String,
    principal: String,
    public_key_hex: String,
    signature_hex: String,
    timestamp: String,
) -> Result<(), String> {
    // 1. Validate username format
    let normalized = validate_username(&username)?;

    // 2. Verify Ed25519 signature
    if !verify_registration_signature(
        &normalized,
        &principal,
        &public_key_hex,
        &signature_hex,
        &timestamp,
    ) {
        return Err("Invalid or expired signature".to_string());
    }

    // 3. Check username not taken
    let username_taken = USERNAME_TO_INFO.with(|map| {
        map.borrow().contains_key(&StableString(normalized.clone()))
    });
    if username_taken {
        return Err("Username already taken".to_string());
    }

    // 4. Check principal not already registered
    let principal_taken = PRINCIPAL_TO_USERNAME.with(|map| {
        map.borrow().contains_key(&StableString(principal.clone()))
    });
    if principal_taken {
        return Err("This identity already has a username".to_string());
    }

    // 5. Store bidirectional mapping
    let user_info = UserInfo {
        principal: principal.clone(),
        public_key_hex,
        registered_at: ic_cdk::api::time(),
    };

    USERNAME_TO_INFO.with(|map| {
        map.borrow_mut().insert(StableString(normalized.clone()), user_info);
    });

    PRINCIPAL_TO_USERNAME.with(|map| {
        map.borrow_mut().insert(
            StableString(principal),
            StableString(normalized.clone()),
        );
    });

    ic_cdk::println!("Username registered: {}", normalized);
    Ok(())
}

/// Look up the principal for a given username (query, free).
#[ic_cdk::query]
fn lookup_username(username: String) -> Option<String> {
    let normalized = username.to_lowercase();
    USERNAME_TO_INFO.with(|map| {
        map.borrow().get(&StableString(normalized)).map(|info| info.principal.clone())
    })
}

/// Check if a username is available (query, free).
#[ic_cdk::query]
fn is_username_available(username: String) -> Result<bool, String> {
    let normalized = validate_username(&username)?;
    let taken = USERNAME_TO_INFO.with(|map| {
        map.borrow().contains_key(&StableString(normalized))
    });
    Ok(!taken)
}

/// Reverse lookup: get the username for a principal (query, free).
#[ic_cdk::query]
fn get_username_for_principal(principal: String) -> Option<String> {
    PRINCIPAL_TO_USERNAME.with(|map| {
        map.borrow().get(&StableString(principal)).map(|s| s.0.clone())
    })
}

// ============================================================================
// CANDID INTERFACE EXPORT
// ============================================================================

// Generate the Candid interface from Rust types
ic_cdk::export_candid!();
