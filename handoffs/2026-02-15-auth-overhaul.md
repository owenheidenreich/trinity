# Handoff: Authentication System Overhaul

**Date:** February 15, 2026
**Status:** Specification complete. Implementation required.
**Priority:** Critical — current auth flow is non-functional for end users.
**Estimated Effort:** 3–5 days for an engineer familiar with Ed25519, ICP canisters, and React 19.

---

## Executive Summary

Trinity's authentication pipeline is broken. User testing on February 15, 2026 revealed that the current flow — which asks users to interact with cryptographic concepts (passphrase canaries, hex backup keys, browser-fingerprint encryption) — does not work and is fundamentally hostile to non-technical users.

**The decision:** Replace the entire auth UX with a standard **username + password** system (no email, no phone, no third-party identity provider). The password deterministically derives the user's Ed25519 keypair via Argon2id. Username uniqueness is enforced on-chain by the ICP canister. The underlying Ed25519 signed-request authentication and AES-256-GCM encrypted storage systems remain unchanged.

This aligns with Trinity's core values:
- **Self-custody:** Your password is your key. No one else holds it. No email recovery means no email to collect.
- **Decentralization:** Username registry lives on ICP (blockchain), not a database.
- **Privacy:** Zero personal information collected. No email, no phone, no IP logs.
- **Security:** Argon2id memory-hard KDF prevents brute-force. AES-256-GCM encrypts all data. Ed25519 signs every request.

---

## Problem Statement

### What Users Experience Today

1. User visits dubya.ai → sees "Welcome to Trinity"
2. Clicks "Get Started" → a random Ed25519 keypair is silently generated
3. Immediately prompted to "Set Your Password" (8+ chars, confirm) — **but user has no mental model for what this protects or why it's needed before they've even seen the app**
4. Password creates an encrypted "canary" blob on IPFS — but if IPFS upload fails, the user is stuck with no error message and "Setting up..." spins indefinitely
5. If the user refreshes, the passphrase status check may fail due to network errors, causing the app to show "Set Your Password" again to a returning user (overwriting their canary → 409 conflict → stuck)
6. A "Skip for now" option existed that created a passwordless identity with principal-based encryption — weaker security, and the user had no idea they'd chosen a degraded path
7. Returning users on a new device have no way back in without a 64-character hex string they were briefly shown once

### Root Causes

| Issue | Location | Detail |
|-------|----------|--------|
| Password prompt before any context | `WelcomeModal.tsx` L83–86 | `passphraseStatus === 'no_passphrase'` immediately transitions to setup step |
| Network error defaults to wrong state | `usePassphrase.ts` L64 | `checkStatus` catch block set `'no_passphrase'` (patched to `'locked'` but fundamentally flawed) |
| No fetch timeouts | `usePassphrase.ts` | All fetch calls had no timeout (patched with 15s AbortController) |
| 409 not handled | `usePassphrase.ts` L91 | Setup returns 409 if canary exists, not caught (patched) |
| IPFS failure = 500 in autosave | `chat.py` L155 | IPFS upload fail returned 500, frontend retried infinitely (patched to return 200 with warning) |
| Session volatility | `session_manager.py` | In-memory dict wiped on container restart, no persistence |
| Browser fingerprint fragility | `crypto.ts` L24 | localStorage key derived from userAgent+platform+screen (patched to stable components, but still device-bound) |
| Hex key backup as only recovery | `WelcomeModal.tsx` L157 | 64-char hex shown briefly, user expected to copy it — they won't |

### What Was Already Patched (February 15)

These patches are bandaids on a fundamentally broken design:

| Patch | File | What It Does |
|-------|------|-------------|
| Error fallback → `'locked'` | `usePassphrase.ts` L64 | Network errors assume returning user instead of new user |
| 15s fetch timeout | `usePassphrase.ts` L14–21 | `fetchWithTimeout()` wrapper prevents infinite hang |
| 409 handling | `usePassphrase.ts` L96–100 | Setup conflict transitions to unlock flow |
| IPFS failure graceful | `chat.py` L155–165 | Returns 200 with `warning` field instead of 500 |
| Autosave circuit breaker | `useAutosave.ts` L124–145 | Stops retrying after 5 failures |
| Metadata resilience | `storage.py` L296–310 | Returns defaults if passphrase missing instead of crashing |
| Stable fingerprint | `crypto.ts` L24–38 | Uses hardwareConcurrency/language/colorDepth instead of userAgent |
| Removed "Skip for now" | `WelcomeModal.tsx` | Password required, no degraded path |

---

## Target Architecture

### User Experience

| Scenario | What the User Sees |
|----------|-------------------|
| **First visit** | Two-field form: "Choose a username" + "Choose a password" + "Create Account" button. Below: "Already have an account? Sign In". Clear warning: "If you forget your password, your data cannot be recovered." |
| **Return visit (same browser)** | Nothing — auto-login from localStorage. Chat loads immediately. |
| **Return visit (new device)** | Two-field form: "Username" + "Password" + "Sign In" button. Below: "New here? Create Account". |
| **Wrong password** | "Incorrect password. Please try again." (derived principal doesn't match registered principal — the user is cryptographically a different person) |
| **Username taken** | "Username already taken. Please choose another." (live availability check via ICP canister query) |
| **Forgot password** | No recovery flow. Clear upfront warning. This is the explicit tradeoff for not collecting personal data. |

### How It Works — Technical Flow

```
┌─────────── Client (Browser) ───────────┐     ┌─── ICP Canister ───┐     ┌─── Akash Backend ───┐
│                                         │     │                     │     │                      │
│  1. User enters username + password     │     │                     │     │                      │
│                                         │     │                     │     │                      │
│  2. Derive seed:                        │     │                     │     │                      │
│     salt = "trinity:" + lower(username) │     │                     │     │                      │
│     seed = Argon2id(                    │     │                     │     │                      │
│       password, salt,                   │     │                     │     │                      │
│       memory=64MB, time=3, p=1          │     │                     │     │                      │
│     ) → 32 bytes                        │     │                     │     │                      │
│                                         │     │                     │     │                      │
│  3. Derive identity:                    │     │                     │     │                      │
│     keypair = Ed25519.fromSecretKey(    │     │                     │     │                      │
│       seed                              │     │                     │     │                      │
│     )                                   │     │                     │     │                      │
│     principal = keypair.getPrincipal()  │     │                     │     │                      │
│                                         │     │                     │     │                      │
│  ┌─── CREATE ACCOUNT ────────────────┐  │     │                     │     │                      │
│  │ 4a. Call canister:                │  │────▶│ register_username(  │     │                      │
│  │     register_username(            │  │     │   username,         │     │                      │
│  │       username, principal,        │  │     │   principal,        │     │                      │
│  │       pubkey, signature, ts       │  │     │   pubkey, sig, ts   │     │                      │
│  │     )                             │  │     │ )                   │     │                      │
│  │                                   │  │◀────│ → Ok / AlreadyTaken │     │                      │
│  └───────────────────────────────────┘  │     │                     │     │                      │
│                                         │     │                     │     │                      │
│  ┌─── SIGN IN ───────────────────────┐  │     │                     │     │                      │
│  │ 4b. Call canister:                │  │────▶│ lookup_username(    │     │                      │
│  │     lookup_username(username)     │  │     │   username          │     │                      │
│  │                                   │  │◀────│ ) → principal_id    │     │                      │
│  │ 5. Compare:                       │  │     │                     │     │                      │
│  │    derived_principal == stored?    │  │     │                     │     │                      │
│  │    Yes → authenticated            │  │     │                     │     │                      │
│  │    No  → "Incorrect password"     │  │     │                     │     │                      │
│  └───────────────────────────────────┘  │     │                     │     │                      │
│                                         │     │                     │     │                      │
│  6. Store encrypted key in localStorage │     │                     │     │                      │
│     (AES-256-GCM, key from Argon2id    │     │                     │     │                      │
│      of password + "trinity:storage:"  │     │                     │     │                      │
│      + username)                        │     │                     │     │                      │
│                                         │     │                     │     │                      │
│  7. Establish backend session:         │     │                     │     │                      │
│     POST /api/passphrase/setup (new)   │────▶│                     │────▶│ Create canary on IPFS│
│     POST /api/passphrase/unlock (ret)  │────▶│                     │────▶│ Store passphrase     │
│                                         │     │                     │     │   in session memory  │
│                                         │     │                     │     │                      │
│  8. All subsequent requests use         │     │                     │     │                      │
│     Ed25519 signed headers              │────▶│                     │────▶│ @require_auth        │
│     (unchanged from current system)     │     │                     │     │ verifies signature   │
│                                         │     │                     │     │                      │
└─────────────────────────────────────────┘     └─────────────────────┘     └──────────────────────┘
```

### Why This Is Secure — Threat Analysis

| Threat | Mitigation |
|--------|-----------|
| **Brute-force password guessing** | Argon2id with 64MB memory cost. Each guess takes ~0.5s on a GPU, 1000× slower than PBKDF2. A 12-char password has ~60 bits of entropy → 2^60 × 0.5s = 18 billion years. |
| **Two users register same username** | ICP canister enforces uniqueness atomically. Update calls are serialized by the subnet consensus. Race conditions are impossible. |
| **Attacker knows username, guesses password** | Wrong password → wrong seed → wrong keypair → wrong principal. The backend sees a completely different user with no access to the victim's directory, IPFS files, or metadata. |
| **Attacker intercepts principal from HTTP headers** | Principal alone cannot derive the password (one-way KDF). Principal cannot decrypt passphrase-encrypted data. The data requires the password as the Argon2id input. |
| **Server compromise** | All chat and memory data encrypted with AES-256-GCM. Key derived from user's password via Argon2id (128MB, t=6). Server never stores the password — only holds it in process memory during active sessions. |
| **Container restart / redeploy** | User re-enters password on next request. Canary on IPFS verifies correctness. Encrypted data on IPFS remains intact. |
| **IPFS node compromise** | Every IPFS file is AES-256-GCM encrypted. Without the password, the content is ciphertext. |
| **Username enumeration** | `lookup_username` returns principal or null. An attacker can discover usernames exist but gains nothing — they still need the password to derive the keypair. This is acceptable (most systems allow username enumeration via login/register). |
| **Canister data theft** | The canister stores `username → principal` (public mapping). No secrets. The principal is already transmitted in every HTTP header. |

### Why Password = Key Derivation Input Is Safe

The critical insight: **the password is not used to "authenticate to a server" — it's used to deterministically generate a cryptographic identity.** Wrong password = wrong keypair = wrong person. There is nothing to brute-force on the server side because the server never receives the password during login — it only receives Ed25519 signatures from the derived keypair.

The only brute-force vector is offline: derive keypairs for many passwords and check if any produce a known principal. Argon2id's memory-hardness makes this prohibitively expensive.

---

## Files to Modify

### Frontend (6 files to change, 1 to add)

| File | Lines | Action | Detail |
|------|-------|--------|--------|
| `trinity-icp/src-react/hooks/useAuth.ts` | 259 | **Rewrite** | Replace `login()` (random keypair) with `register(username, password)` and `signIn(username, password)`. Add deterministic key derivation via `hash-wasm` Argon2id. Keep `buildAuthHeaders()`, `signMessage()`, `getPublicKeyHex()` unchanged. Add ICP canister agent calls for `register_username` / `lookup_username`. Store username in localStorage alongside encrypted key. |
| `trinity-icp/src-react/hooks/usePassphrase.ts` | 186 | **Simplify** | Remove `checkStatus()`, `skipSetup()`. The login password IS the passphrase — call `setup()` or `unlock()` automatically after successful register/signIn. The hook becomes an internal implementation detail, not a user-facing flow. |
| `trinity-icp/src-react/components/modals/WelcomeModal.tsx` | 299 | **Rewrite** | Replace 6-step state machine (`loading/welcome/import/setup/unlock/backup`) with 2 forms: **CreateAccount** (username + password + confirm) and **SignIn** (username + password). Live username availability check via canister query. Clear "no recovery" warning. |
| `trinity-icp/src-react/components/layout/AppShell.tsx` | 471 | **Simplify** | Remove `needsWelcome` logic that checks passphrase status. Modal shown only when `!isAuthenticated`. Remove `showBackupKey` state. |
| `trinity-icp/src-react/utils/crypto.ts` | 98 | **Rewrite** | Replace browser-fingerprint PBKDF2 derivation with `Argon2id(password, "trinity:storage:" + username)`. Import `argon2id` from `hash-wasm`. The derived key protects the private key in localStorage. |
| `trinity-icp/src-react/store/index.ts` | 189 | **Minor** | Add `username: string | null` to store state. Update `setAuthenticated()` to accept username. |
| `trinity-icp/src-react/services/canister.ts` | **NEW** | **Create** | ICP canister agent client. Uses `@dfinity/agent` + `@dfinity/candid` to call `register_username`, `lookup_username`, `is_username_available` on the backend canister. |

### ICP Canister (2 files to modify)

| File | Lines | Action | Detail |
|------|-------|--------|--------|
| `trinity-icp/src/backend_canister/src/lib.rs` | 617 | **Add** | Add username registry with stable storage (`ic-stable-structures`). New endpoints: `register_username(username, principal, pubkey, signature, timestamp)` (update call, Ed25519-verified), `lookup_username(username)` (query, free), `is_username_available(username)` (query, free). Username rules: 3–20 chars, `[a-z0-9_]`, normalized to lowercase. Store bidirectional mappings: `username→principal` and `principal→username` in `StableBTreeMap`. |
| `trinity-icp/src/backend_canister/Cargo.toml` | 42 | **Add dep** | Add `ic-stable-structures = "0.6"` |

### Backend (3 files to modify, 0 new)

| File | Lines | Action | Detail |
|------|-------|--------|--------|
| `backend/routes/passphrase.py` | 185 | **No change** | The `setup`, `unlock`, `lock`, `status`, `change` endpoints work as-is. The frontend will call them automatically using the login password as the passphrase argument. |
| `backend/icp_auth.py` | 267 | **No change** | Signature verification works identically whether the keypair was randomly generated or deterministically derived. |
| `backend/encryption.py` | 253 | **No change** | All encryption/decryption functions work as-is. Passphrase-based encryption (v2.0 envelope) will be the primary path since all users have a password. |

### Dependencies to Add

| Package | Where | Version | Purpose |
|---------|-------|---------|---------|
| `hash-wasm` | `trinity-icp/package.json` | `^4.11.0` | Argon2id in WebAssembly, runs in all browsers, no native deps |
| `ic-stable-structures` | `Cargo.toml` (canister) | `0.6` | Persistent canister storage that survives upgrades |

### Dependencies That Already Exist (No Changes)

| Package | Where | Used For |
|---------|-------|----------|
| `@dfinity/agent` | `trinity-icp/package.json` | Canister calls (currently only used for `icp-auth.js` bundle) |
| `@dfinity/identity` | `trinity-icp/package.json` | Ed25519KeyIdentity |
| `@dfinity/principal` | `trinity-icp/package.json` | Principal derivation |
| `@dfinity/candid` | `trinity-icp/package.json` | Candid interface encoding |
| `argon2-cffi` | `backend/requirements.txt` | Server-side Argon2id (passphrase encryption) |
| `cryptography` | `backend/requirements.txt` | Ed25519 signature verification |
| `pycryptodome` | `backend/requirements.txt` | AES-256-GCM |
| `ed25519-dalek` | `Cargo.toml` (canister) | Ed25519 verification in canister |

---

## Files NOT to Modify

These are critical subsystems that must remain untouched:

| File | Why |
|------|-----|
| `backend/icp_auth.py` | Signature verification is identity-agnostic. Works with any valid Ed25519 keypair. |
| `backend/encryption.py` | All encryption primitives are correct and tested. |
| `backend/storage.py` | Directory structure (`/data/chats/{principal}/`) and encryption logic unchanged. |
| `backend/routes/chat.py` | Autosave, load, delete endpoints use `request.principal` — unchanged. |
| `backend/services/session_manager.py` | In-memory passphrase store works as-is. |
| `backend/routes/passphrase.py` | Canary system works as-is. Called automatically by frontend. |
| `backend/services/user_data_store.py` | IPFS persistence pipeline unchanged. |
| `backend/services/agent.py` | LLM agent pipeline has no auth dependency. |
| `backend/services/memory.py` | Memory system uses principal from `request.principal` — unchanged. |

---

## Existing Code Reference

### Current Authentication Chain (To Be Replaced)

**Frontend → Backend request lifecycle:**

1. **Identity creation** (`useAuth.ts` L131–157):
   ```typescript
   const identity = ICPAuth.Ed25519KeyIdentity.generate(); // Random keypair
   const principal = identity.getPrincipal().toText();
   const privateKeyHex = /* extract from keyPair.secretKey */;
   localStorage.setItem('trinity_identity_key', encryptForStorage(privateKeyHex));
   localStorage.setItem('trinity_principal', principal);
   ```

2. **Request signing** (`useAuth.ts` L54–78):
   ```typescript
   const message = `${principal}:${timestamp}:${endpoint}:${nonce}`;
   const signature = await identity.sign(encoder.encode(message));
   // Headers: ICP-Principal, ICP-Signature, ICP-Timestamp, ICP-PublicKey, ICP-Nonce
   ```

3. **Backend verification** (`icp_auth.py` L48–139):
   ```python
   # Reconstructs message, verifies Ed25519 signature against public key
   # Checks: timestamp within 60s, nonce not replayed, principal matches pubkey
   # Sets request.principal on success
   ```

4. **Passphrase flow** (`usePassphrase.ts` + `passphrase.py`):
   ```
   GET  /api/passphrase/status  → { has_passphrase, session_unlocked }
   POST /api/passphrase/setup   → creates IPFS canary, stores passphrase in session
   POST /api/passphrase/unlock  → verifies canary, stores passphrase in session
   ```

### New Authentication Chain (To Be Implemented)

**Frontend → Backend request lifecycle:**

1. **Identity derivation** (new `useAuth.ts`):
   ```typescript
   import { argon2id } from 'hash-wasm';
   const salt = new TextEncoder().encode('trinity:' + username.toLowerCase());
   const seed = await argon2id({
     password, salt,
     parallelism: 1, iterations: 3, memorySize: 65536, // 64MB
     hashLength: 32, outputType: 'binary'
   });
   const identity = ICPAuth.Ed25519KeyIdentity.fromSecretKey(seed);
   const principal = identity.getPrincipal().toText();
   ```

2. **Registration** (new `useAuth.ts` + new `canister.ts`):
   ```typescript
   // Verify username available
   const available = await canister.is_username_available(username); // query (free)
   if (!available) throw new Error('Username taken');

   // Register on-chain (proves ownership of keypair via signature)
   const sig = await signMessage(`register:${username}:${principal}:${timestamp}`);
   await canister.register_username(username, principal, publicKeyHex, sig, timestamp);

   // Store locally
   const storageKey = await deriveStorageKey(password, username);
   localStorage.setItem('trinity_identity_key', encrypt(privateKeyHex, storageKey));
   localStorage.setItem('trinity_principal', principal);
   localStorage.setItem('trinity_username', username);

   // Establish backend session (password = passphrase)
   const headers = await buildAuthHeaders('/api/passphrase/setup');
   await fetch('/api/passphrase/setup', { headers, body: { passphrase: password } });
   ```

3. **Sign-in** (new `useAuth.ts` + new `canister.ts`):
   ```typescript
   // Derive keypair from credentials
   const identity = deriveIdentity(username, password); // Argon2id → Ed25519
   const derivedPrincipal = identity.getPrincipal().toText();

   // Verify against on-chain registry
   const registeredPrincipal = await canister.lookup_username(username); // query (free)
   if (!registeredPrincipal) throw new Error('Username not found');
   if (derivedPrincipal !== registeredPrincipal) throw new Error('Incorrect password');

   // Store locally + establish backend session
   // ... same as registration step
   const headers = await buildAuthHeaders('/api/passphrase/unlock');
   await fetch('/api/passphrase/unlock', { headers, body: { passphrase: password } });
   ```

4. **Request signing** — unchanged from current system.

5. **Backend verification** — unchanged from current system.

### Crypto Parameters — Exact Values

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Client-side KDF (key derivation)** | Argon2id, memory=64MB, time=3, parallelism=1 | Must run in-browser in <2s on mobile. parallelism=1 because WASM is single-threaded. 64MB is the maximum practical for mobile browsers. |
| **Client-side salt (key derivation)** | `"trinity:" + username.toLowerCase()` | Username is globally unique (canister-enforced), ensuring different users with the same password get different keys. Lowercase normalization prevents `Alice` vs `alice` collisions. |
| **Client-side KDF (localStorage encryption)** | Argon2id, memory=64MB, time=3, parallelism=1, salt=`"trinity:storage:" + username` | Different salt than key derivation to produce a different key. Same cost parameters. |
| **Server-side KDF (data encryption)** | Argon2id, memory=128MB, time=6, parallelism=4 | Server has more resources. This encrypts user data at rest (chats, memory, metadata). Already implemented in `encryption.py` L139–148. |
| **Encryption algorithm** | AES-256-GCM, 12-byte IV, 16-byte auth tag | Already implemented. Industry standard authenticated encryption. |
| **Signature scheme** | Ed25519 | Already implemented. 128-bit security level. |
| **Username rules** | 3–20 chars, `[a-z0-9_]`, case-insensitive (stored lowercase) | Prevents homoglyph attacks, keeps URLs clean, aligns with standard conventions. |

---

## ICP Canister Username Registry — Specification

### Data Structures

```rust
use ic_stable_structures::{StableBTreeMap, memory_manager::*};

// Bidirectional mapping
type UsernameToInfo = StableBTreeMap<String, UserInfo, Memory>;  // username → info
type PrincipalToUsername = StableBTreeMap<String, String, Memory>; // principal → username

#[derive(CandidType, Deserialize, Serialize, Clone)]
struct UserInfo {
    principal: String,        // ICP principal text representation
    public_key_hex: String,   // Raw Ed25519 public key (32 bytes, hex)
    registered_at: u64,       // IC timestamp (nanoseconds)
}
```

### Endpoints

```rust
// Registration — update call (costs cycles, serialized by consensus)
#[update]
fn register_username(
    username: String,
    principal: String,
    public_key_hex: String,
    signature_hex: String,
    timestamp: String,
) -> Result<(), String> {
    // 1. Validate username format (3-20 chars, [a-z0-9_])
    // 2. Normalize to lowercase
    // 3. Check username not taken (StableBTreeMap::contains_key)
    // 4. Check principal not already registered (reverse map)
    // 5. Verify Ed25519 signature of "register:{username}:{principal}:{timestamp}"
    //    using the provided public_key_hex
    // 6. Verify principal matches public key (derive principal from pubkey, compare)
    // 7. Insert into both maps
    // 8. Return Ok(())
}

// Lookup — query call (free, no cycles)
#[query]
fn lookup_username(username: String) -> Option<String> {
    // Returns principal for the given username, or None
    // Normalize username to lowercase before lookup
}

// Availability check — query call (free, no cycles)
#[query]
fn is_username_available(username: String) -> bool {
    // Returns true if username is not taken
    // Normalize to lowercase
}

// Reverse lookup — query call (free, no cycles)
#[query]
fn get_username_for_principal(principal: String) -> Option<String> {
    // Returns username for the given principal, or None
}
```

### Security Requirements for Canister

1. **Signature verification on register**: The `register_username` call MUST verify the Ed25519 signature to prove the caller owns the keypair. Without this, an attacker could register a username pointing to someone else's principal.

2. **Principal-to-pubkey validation**: The canister MUST verify that the provided `public_key_hex` actually derives the claimed `principal`. ICP principals are deterministically derived from public keys — this is verifiable.

3. **One principal, one username**: The reverse map (`principal→username`) prevents a single keypair from claiming multiple usernames.

4. **No deletion**: Usernames cannot be deleted or transferred. This prevents name-squatting attacks and simplifies the security model. (Admin-only deletion can be added later if needed.)

5. **No enumeration endpoint**: Do not add a "list all usernames" endpoint. Individual lookups are fine.

---

## Migration Path

### Existing Users (Hex Key Backup)

Some users may have been through the current flow and exported their hex private key:

1. Keep `importKey(hexKey)` in `useAuth.ts` as a hidden settings option (not on the login screen)
2. After importing, prompt user to "Claim a username" which registers their existing principal in the canister
3. Their existing data (IPFS files, encrypted metadata) remains accessible because the principal is unchanged
4. Once they set a username + password, the old hex key is no longer needed

### Data Format Compatibility

No data migration needed:

| Data | Current Format | After Overhaul |
|------|---------------|---------------|
| Chat files on IPFS | AES-256-GCM encrypted, v1.1 (principal-based) or v2.0 (passphrase-based) | Same. `decrypt_auto()` handles both. New data uses v2.0. |
| Metadata on disk | AES-256-GCM encrypted | Same. Password used as passphrase for encryption. |
| IPFS canary | Encrypted blob proving passphrase correctness | Same. Created during registration, verified during sign-in. |
| IPFS filenames | `{principal[:16]}_*.json` | Same. Principal doesn't change. |
| Local directories | `/data/chats/{principal}/` | Same. |

---

## Known Issues to Address During Implementation

### 1. Canister Signature Format Mismatch

The canister `verify_signature()` at `lib.rs` L485 uses message format `{principal}:{timestamp}` while the frontend uses `{principal}:{timestamp}:{endpoint}:{nonce}`. The canister's registration endpoint should use its own format: `register:{username}:{principal}:{timestamp}`.

### 2. Timestamp Window Inconsistency

- `config.py` L93: `AUTH_TIMESTAMP_WINDOW_MS = 5 * 60 * 1000` (5 min) — **unused constant**
- `icp_auth.py` L89: hardcoded `60_000` ms (60s)
- `lib.rs` L434: `5 * 60 * 1_000_000_000` ns (5 min)

Recommendation: The canister registration endpoint should use a 5-minute window (account creation is latency-tolerant). The Flask backend should keep 60s for API requests (security-sensitive).

### 3. No Auth Brute-Force Protection

`icp_auth.py` has no rate limiting on failed signature verifications. The route-level `@rate_limit` decorator (30 req/window) helps but isn't auth-specific. Consider adding a per-principal lockout after N failed attempts.

### 4. `parallelism=1` for Client-Side Argon2id

WebAssembly is single-threaded. The `hash-wasm` library's Argon2id runs with `parallelism=1` regardless of what you specify. This is a known limitation. The 64MB memory cost is the primary defense, not parallelism.

---

## Testing Requirements

### Unit Tests (Backend)

No new backend tests needed — the existing 854 tests cover all encryption, auth verification, and storage flows. The only change is that the frontend sends a deterministically-derived keypair instead of a random one. The backend can't tell the difference.

Run: `cd backend && python3 -m pytest tests/ -q` — expect 854 passed, 4 known failures (TestChatPinFeature ordering issue).

### Integration Tests (Frontend)

New tests needed:

| Test | Description |
|------|-------------|
| `register() happy path` | Generate deterministic keypair, register with canister mock, verify localStorage populated |
| `signIn() happy path` | Derive keypair, lookup returns matching principal, verify auto-unlock |
| `signIn() wrong password` | Derive keypair, principal doesn't match canister lookup → error |
| `signIn() unknown username` | Canister returns null → error |
| `register() username taken` | Canister returns error → display message |
| `auto-restore from localStorage` | Set localStorage values, mount hook, verify auto-login |
| `deterministic derivation` | Same username+password always produces same principal |
| `different usernames, same password` | Different principals |
| `case insensitivity` | `Alice` and `alice` produce same principal |

### Canister Tests

```bash
cd trinity-icp && dfx canister call trinity_backend register_username '("testuser", "xxx-principal", "abcdef", "sig", "12345")'
cd trinity-icp && dfx canister call trinity_backend lookup_username '("testuser")'
cd trinity-icp && dfx canister call trinity_backend is_username_available '("testuser")'
```

### End-to-End Manual Tests

1. Fresh browser → Create Account → chat → close browser → reopen → auto-login
2. Incognito window → Sign In with same creds → same chat history loads
3. Try registering taken username → clear error
4. Try signing in with wrong password → clear error
5. Try signing in with nonexistent username → clear error
6. Deploy new container → visit site → re-enter password → data loads
7. Two users, different usernames → cannot see each other's data

---

## Deployment

### Canister Deployment

```bash
cd trinity-icp
dfx build trinity_backend
dfx canister install trinity_backend --mode upgrade  # Preserves stable storage
```

### Frontend Deployment

```bash
cd trinity-icp
npm run build
dfx deploy trinity_frontend  # Updates asset canister
```

### Backend Deployment

```bash
./scripts/trinity-deploy-production.sh production
```

The backend requires **no code changes** for this overhaul. Only frontend and canister are modified. However, if you add a `POST /api/auth/verify-principal` endpoint (optional server-side double-check), rebuild the Docker image.

---

## File Map — Quick Reference

```
trinity-icp/
├── src-react/
│   ├── hooks/
│   │   ├── useAuth.ts           ← REWRITE (deterministic key derivation, canister calls)
│   │   ├── usePassphrase.ts     ← SIMPLIFY (auto-call from login, remove user-facing flow)
│   │   └── useAutosave.ts       ← NO CHANGE
│   ├── components/
│   │   ├── modals/
│   │   │   └── WelcomeModal.tsx  ← REWRITE (username+password forms)
│   │   └── layout/
│   │       └── AppShell.tsx      ← SIMPLIFY (remove passphrase status checks)
│   ├── utils/
│   │   └── crypto.ts            ← REWRITE (Argon2id via hash-wasm)
│   ├── services/
│   │   └── canister.ts          ← NEW (ICP canister client)
│   ├── store/
│   │   └── index.ts             ← MINOR (add username to state)
│   └── types/
│       └── auth.ts              ← MINOR (add username fields)
│
├── src/backend_canister/
│   ├── src/lib.rs               ← ADD (username registry + stable storage)
│   └── Cargo.toml               ← ADD DEP (ic-stable-structures)
│
├── package.json                  ← ADD DEP (hash-wasm)
└── dfx.json                     ← NO CHANGE

backend/                          ← NO CHANGES REQUIRED
├── icp_auth.py                   (signature verification — works as-is)
├── encryption.py                 (all crypto — works as-is)
├── storage.py                    (data persistence — works as-is)
├── routes/passphrase.py          (passphrase endpoints — works as-is)
├── services/session_manager.py   (in-memory session store — works as-is)
└── config.py                     (constants — works as-is)
```

---

## Acceptance Criteria

- [ ] User can create an account with username + password (no email, no hex keys, no "canary" concepts visible)
- [ ] User can sign in from any device with username + password
- [ ] Same username + password always produces the same identity (deterministic)
- [ ] Username uniqueness enforced atomically by ICP canister
- [ ] Wrong password shows "Incorrect password" (not a crypto error)
- [ ] All chats and memory encrypted with user's password (AES-256-GCM + Argon2id)
- [ ] Auto-login from localStorage on return visits (same browser)
- [ ] Existing Ed25519 auth headers and backend verification unchanged
- [ ] Backend test suite passes: 854+ tests, 0 new failures
- [ ] Frontend builds clean: `tsc --noEmit` + `npm run build` + `eslint`
- [ ] No personal information collected (no email, no phone, no IP tracking)
- [ ] "Forgot password" is explicitly not supported, with clear upfront warning
