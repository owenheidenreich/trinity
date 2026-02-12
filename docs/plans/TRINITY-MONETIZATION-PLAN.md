# Trinity Product Plan

> **Created:** February 10, 2026  
> **Updated:** February 11, 2026  
> **Status:** Active — Definitive Product Plan (v2)  
> **Author:** Gduby + Strategic Analysis  
> **Supersedes:** All prior monetization, B2B pivot, and packaging docs  
> **Reference:** [cost-analysis-research.md](cost-analysis-research.md), [CRITICAL-FIXES-ROADMAP.md](CRITICAL-FIXES-ROADMAP.md)

---

## Executive Summary

Trinity is a private AI chat application. The free website (dubya.ai) runs a shared Qwen model to attract users. Users who want the full experience pay **$30/year** (collected upfront) for the **Trinity Package** — a subscription that grants unlimited access to the shared dubya.ai model, plus the ability to download the Trinity app and optionally spin up private Akash GPU instances for more powerful models on demand.

**Two revenue streams:**
1. **$30/year subscription** — annual upfront, unlimited access to the shared model on dubya.ai and the downloadable app
2. **Private instance markup** — 15% margin on USD payments when users deploy their own Akash GPU (undisclosed spread)

**Platform rollout (in order of priority):**
1. Website (now) — free funnel at dubya.ai
2. iOS app (months 3-4) — React Native
3. Android app (months 4-5) — React Native (shared codebase with iOS)
4. macOS app (months 5-6) — Electron
5. Windows app (months 6-7) — Electron (shared codebase with macOS)
6. Linux app (months 7-8) — Electron (shared codebase)

**Source model:** Closed source. All updates pushed directly by Gduby. Users receive compiled binaries only.

---

## Product Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    FREE FUNNEL                           │
│                                                          │
│  dubya.ai (ICP website)                                  │
│  ├── Qwen 7B on shared Akash GPU (~$86/mo, you absorb)  │
│  ├── 15 messages per random 2-6hr window (IP-limited)    │
│  ├── No auth, no memory, no history                      │
│  ├── Example prompt cards on first visit                 │
│  └── Upgrade CTA after message 10                        │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                    PAID PRODUCT                           │
│                                                          │
│  Trinity Package ($30/year)                               │
│  ├── Unlimited access to shared dubya.ai model            │
│  │   ├── Via dubya.ai (web)                              │
│  │   └── Via downloadable app (iOS/Android/Desktop)      │
│  ├── Full memory system, RAG, agent tools                │
│  ├── Encrypted chat history, file attachments            │
│  └── OPTIONAL: Spin up private Akash GPU instance        │
│       ├── Any model (Qwen 3B → 72B, Llama, etc)         │
│       ├── Model download progress + Akash logs in-app    │
│       ├── USD payment via Stripe (15% markup, hidden)    │
│       ├── You deploy from master AKT wallet on behalf    │
│       └── Direct connection to their Akash provider URI  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## Part 1: Free Tier — dubya.ai

### 1.1 Purpose

Loss leader. Proves the product works, builds trust, funnels to paid. Cheap to run.

### 1.2 Infrastructure

| Component | Spec | Cost |
|-----------|------|------|
| Model | Qwen 2.5 7B | — |
| GPU | NVIDIA T4 (16GB VRAM) on Akash | $0.12/hr |
| CPU / RAM / Disk | 4 cores / 16Gi / 30Gi | included |
| Monthly cost | ~$86/mo | You absorb |
| Cloudflare Worker | SSL proxy | $0 |
| ICP Frontend canister | Asset hosting | ~$5/mo |
| **Total** | | **~$91/mo** |

**Akash YAML:** New `deploy/akash/deploy-free-tier.yaml`.  
Env vars: `MODEL_NAME=qwen2.5:7b`, `MULTI_MODEL_ENABLED=false`, `VOTING_ENABLED=false`, `CODE_EXECUTION_ENABLED=false`, `RAG_TOP_K=0`, `TIER_TYPE=free`, `GUEST_MESSAGE_LIMIT=15`.

### 1.3 Guest Rate Limiting (15 messages per random 2-6hr window)

**CRITICAL PREREQUISITE:** The Cloudflare Worker at `deploy/cloudflare-worker/worker.js` currently **strips `CF-Connecting-IP` and `X-Forwarded-For`** before forwarding to the backend. This means `request.remote_addr` in Flask sees only the Worker's IP — all users share one rate limit bucket. **This must be fixed before any per-user rate limiting works.**

**Fix:**
1. Cloudflare Worker: Forward `CF-Connecting-IP` as `X-Real-IP`
2. Rate limit middleware: Read `request.headers.get('X-Real-IP', request.remote_addr)`

**Randomized window behavior:**
- On first request from an IP, backend generates a random reset interval between 2 and 6 hours
- User gets 15 messages within that window
- Messages 1–9: Normal response
- Messages 10–14: Response includes `"remaining_messages": N`. Frontend shows countdown badge
- Message 15: Return `429` with upgrade CTA and `resets_at` timestamp
- When the window expires, counter resets and a NEW random interval (2-6hr) is generated
- Counter increments on request **received** (not response complete) — stopping generation still costs a message
- Persist counts to disk: `{ip: {count, reset_at, interval_hours}}`
- Cross-browser: Same IP = same bucket. VPN reset is an acceptable edge case
- Unpredictable reset times prevent users from gaming the system (can't just wait for a fixed midnight reset)

### 1.4 Feature Matrix

| Feature | Guest (free) | Subscriber ($30/yr) | Subscriber + Private Instance |
|---------|-------------|---------------------|-------------------------------|
| Chat messages | 15 per 2-6hr window | Unlimited | Unlimited |
| Model | Qwen 7B (shared) | Qwen 7B (shared) | Any model (own GPU) |
| Memory system | None | Full user memory | Full user memory |
| RAG / embeddings | None | Full pipeline | Full pipeline |
| Agent tools | None | Full agent pipeline | Full agent pipeline |
| Chat history | Lost on refresh | Encrypted, persistent | Encrypted, persistent |
| File attachments | None | Yes | Yes |
| Code execution | None | Yes | Yes |
| Streaming | Yes | Yes | Yes |
| Math rendering (KaTeX) | Yes | Yes | Yes |
| Private GPU | No | Optional (pay per hour) | Active |
| Akash logs in-app | No | No | Yes |

### 1.5 Example Prompts (First Visit)

Replace the empty `<div class="empty-state">` with clickable prompt cards. 6 cards:

| Card | Prompt | Demonstrates |
|------|--------|-------------|
| Explain It Simply | "Explain how blockchain works in simple terms" | Conversational clarity |
| Write Code | "Write a Python function that finds prime numbers up to N" | Code generation |
| Solve Math | "Solve: $\frac{d}{dx}(x^3 \sin x)$" | KaTeX rendering |
| Analyze a Decision | "Compare renting vs. buying a home in 2026" | Analytical reasoning |
| Draft Something | "Write a professional email declining a meeting politely" | Practical writing |
| Get Creative | "Write a short sci-fi story about an AI that discovers music" | Creative ability |

Clicking a card sends the prompt immediately. Cards disappear when `chatStarted` becomes true. Cards reappear on "New Chat."

### 1.6 Upgrade Nudges

- At message 10: Countdown badge appears ("5 remaining")
- At message 15: Modal: *"You've used all 15 free messages. Get unlimited access to Trinity for $2.50/month."* CTA: "Get Trinity — $30/year"
- After every 5th message: Subtle footer on AI response linking to upgrade
- When guest tries a gated feature (file attach, memory): Tooltip explaining it's paid
- On the downloadable app: Login screen shows "Subscribe for $30/year" with feature comparison

---

## Part 2: Paid Product — Trinity Package

### 2.1 What the User Gets

The $30/year subscription unlocks two things:

1. **Unlimited shared model access** — The same Qwen model running on dubya.ai, but with no message limits. Works in the browser AND in the downloadable app. Full Trinity features: memory, RAG, agents, code execution, encrypted history, file attachments.

2. **Optional private Akash GPU instances** — Available only in the downloadable app. User selects a model from a catalog, pays per hour via Stripe, and you deploy a dedicated Akash GPU on their behalf from a master wallet. They see real-time Akash logs and model download progress directly in the app. Once ready, the app connects directly to their private provider URI.

### 2.2 Pricing

| | Detail |
|---|---|
| **Price** | $30/year (displayed as "$2.50/month") |
| **Billing** | Full year collected at checkout via Stripe. No monthly option. |
| **Legal** | Fine print shows transparency: "Annual subscription of $30 billed at purchase" |
| **Renewal** | Manual re-purchase after 1 year |
| **What's included** | Unlimited access to shared model + app download + 1 year of access + software updates |
| **Not included** | Private Akash GPU instances (paid separately per hour) |

### 2.3 Auth System

> **⚠️ TBD — Requires dedicated Auth Plan (see Phase -1 in Implementation Roadmap)**
>
> The auth system must be seamless across dubya.ai (web) and all downloadable apps (React Native + Electron). The current Ed25519 self-custody system built by a lesser model has critical gaps:
>
> - **No principal-key binding verification** — Backend accepts any public key for any claimed principal. An attacker can create a new keypair, claim someone else's principal, and access their data. The `principal_to_public_key()` function is a stub that raises `NotImplementedError`.
> - **Browser-fingerprint-dependent key encryption** — Private keys in localStorage are encrypted with a key derived from `userAgent + screenSize + origin`. Changing browsers, OS updates, or different screen resolutions break decryption.
> - **`localStorage` fragility** — Clearing browser data, incognito mode, or Safari ITP wipes keys entirely.
> - **8,579-line bundled Dfinity library** — Heavyweight dependency (`icp-auth.js`) for what amounts to basic Ed25519 operations.
>
> A new auth architecture will be designed in a separate Auth Plan before app development begins. Options under consideration:
>
> 1. **Improved self-custody** — Password-derived deterministic keypairs (same password → same Ed25519 keys on any device), server-side key registry to prevent principal spoofing, swap Dfinity bundle for lightweight Ed25519 lib (~200 lines). More "normie-friendly" UX while preserving self-custody principles.
> 2. **Traditional accounts + managed auth** — Email/password with JWT sessions, server stores credentials, password reset possible. Options: hand-rolled (Flask-Login + bcrypt), or managed (Supabase Auth, Clerk, Auth0).
> 3. **Passkeys/WebAuthn** — Modern OS-level auth, cross-platform, phishing-resistant. More complex backend but future-proof.
>
> **Key constraint:** Whatever approach is chosen must work identically across ICP web frontend, React Native (iOS/Android), and Electron (macOS/Windows/Linux) with a single account.

### 2.4 Private Akash GPU Instances (On-Demand)

Separate from the $30/yr subscription. Available only in the downloadable app. Users pay per hour for dedicated compute.

**Master wallet architecture:**
- You maintain a funded AKT master wallet
- User selects model + GPU → sees total cost → pays USD via Stripe (Apple Pay / Google Pay / card)
- Your backend receives Stripe webhook → deploys to Akash from master wallet
- 15% markup applied at the Stripe checkout price (user sees e.g. $1.73/hr for an A100 that costs $1.50/hr)
- The markup is **never disclosed** — USD is positioned as the standard price
- Deployment lifecycle managed server-side: create → monitor → teardown on balance exhaustion

**User experience:**
1. Open "Private Instance" tab in app
2. Browse model catalog — cards showing: model name, parameter count, GPU required, quality rating, $/hr
3. Select model + duration (minimum 1 hour)
4. See total cost upfront → pay via Stripe
5. Deployment kicks off → app shows real-time Akash container logs via SSE
6. Model downloads → progress bar with whimsical loading messages
7. Ready → app switches connection from shared model to private Akash provider URI
8. Timer/balance display shows remaining time
9. Low balance warning at <30 minutes remaining
10. Can stop early → unused time credited to account balance
11. Tap to return to shared model at any time

**Pricing (what USD users see — includes 15% markup):**

| Model | GPU Required | $/hr (Akash cost) | $/hr (user pays) | $/mo equiv (24/7) |
|-------|-------------|-------------------|------------------|-------------------|
| Qwen 3B | T4 (16GB) | $0.12 | $0.14 | $101 |
| Qwen 7B | T4 (16GB) | $0.12 | $0.14 | $101 |
| Qwen 14B | T4 (16GB) | $0.12 | $0.14 | $101 |
| Qwen 32B | RTX 4090 (24GB) | $0.39 | $0.45 | $324 |
| Llama 70B | A100 (80GB) | $1.24 | $1.43 | $1,030 |
| Qwen 72B | A100 (80GB) | $1.24 | $1.43 | $1,030 |

*Prices sourced from live Akash GPU marketplace, February 2026.*

**Why users spin up private instances:**
- Need a more powerful model than the shared Qwen 7B (e.g. coding with 72B)
- Want extra privacy — their own isolated GPU, not shared infrastructure
- Want to run the same model as dubya.ai but with dedicated throughput (no contention)
- Occasional use case: day-to-day on shared model, spin up 72B for complex projects

### 2.5 Model Selection & Download Progress

**Model picker UI (in-app only):**
- Card grid showing available models grouped by capability tier
- Each card: model name, parameter count, VRAM requirement, quality rating, hourly cost
- "Same as dubya.ai" badge on the shared model for clarity
- Selecting a model shows estimated download time and total cost calculator

**Download progress streaming:**
- New backend endpoint: `GET /deploy/logs` — streams Akash container logs via SSE
- Includes Ollama model pull progress (parsed from container stdout)
- Progress display: *"Downloading qwen2.5:14b... 3.2GB / 8.1GB (39%)"*
- Whimsical loading messages while waiting (reuse `backend/services/loading_messages.py`)
- Once `/health` returns `model_loaded: true`, transition to chat view

---

## Part 3: Platform Development & Distribution

### 3.1 Platform Priority & Rollout

| Priority | Platform | Tech Stack | Distribution | Auto-Update Mechanism | Timeline |
|----------|----------|-----------|-------------|----------------------|----------|
| — | Web (dubya.ai) | Vanilla JS on ICP | ICP canister | `dfx deploy` (instant) | Shipped |
| 1 | iOS | React Native | App Store | App Store auto-update | Months 3-4 |
| 2 | Android | React Native | Google Play | Play Store auto-update | Months 4-5 |
| 3 | macOS | Electron | Direct download (.dmg), notarized | `electron-updater` | Months 5-6 |
| 4 | Windows | Electron | Direct download (.exe), code-signed | `electron-updater` | Months 6-7 |
| 5 | Linux | Electron | AppImage / Snap | `electron-updater` | Months 7-8 |

### 3.2 Closed Source & Auto-Update Strategy

**The software is closed source.** Private GitHub repository. Users receive compiled binaries only.

**Update flow — the user doesn't think about updates:**

| Platform | How Updates Work |
|----------|-----------------|
| **Web** | You run `dfx deploy`. All visitors get the new version instantly. |
| **iOS** | Push update to App Store. Apple review (1-3 days). Users get auto-update via iOS settings. |
| **Android** | Push update to Google Play. Review (~hours). Users get auto-update via Play Store. |
| **Desktop** | `electron-updater` checks a release feed (GitHub Releases or S3 bucket) on app launch. Downloads update silently, shows "Update available — restarting..." notification. User sees new version on next launch. |

**Key principle:** User downloads the app, logs in, and it works. Updates happen automatically. No manual action, no version selection, no opt-out. You push, they receive.

### 3.3 Why React Native for Mobile

| Factor | React Native | Flutter | Capacitor | Native |
|--------|-------------|---------|-----------|--------|
| LLM familiarity | Highest (JS/TS, massive training corpus) | Medium (Dart is niche) | High (wraps existing web) | Split (Swift + Kotlin) |
| Community / packages | Largest | Growing | Medium | Platform-specific |
| Native feel | Good | Excellent | Adequate | Best |
| Code reuse with web | High (JS ecosystem) | None | Highest (same code) | None |
| Akash SDK integration | `@akashnetwork/akashjs` works directly | Needs bridge | Needs bridge | Needs bridge |
| Dev velocity | Fast | Fast | Fastest (but limited) | Slowest (2x work) |

**Decision: React Native.** Best balance of LLM buildability, native quality, JS ecosystem reuse, and direct Akash SDK compatibility. iOS and Android share ~90% of the codebase.

### 3.4 Mobile App Architecture (React Native — iOS + Android)

```
React Native App
├── Screens/
│   ├── Login / Register / Subscribe
│   ├── Chat (main experience — default: shared model)
│   ├── Private Instance (model catalog, deploy, logs)
│   ├── Settings (account, preferences, subscription status)
│   └── Top Up (Stripe payment for private instances)
├── Services/
│   ├── AuthService (login, register — TBD auth approach)
│   ├── ChatService (SSE streaming, abort support)
│   ├── DeployService (request private instance, poll status, stream logs)
│   ├── PaymentService (Stripe, balance tracking)
│   └── SubscriptionService (validate annual subscription status)
├── State/ (Zustand — same lib as web frontend)
├── Config/
│   ├── endpoints.js (api.dubya.ai for shared, dynamic URI for private)
│   └── models.js (model catalog with pricing)
└── Native Modules/
    ├── Keychain (secure credential storage — iOS Keychain / Android Keystore)
    └── Notifications (low balance, deployment ready, subscription expiry)
```

**Connection routing:**
- Shared model: App → `api.dubya.ai` (Cloudflare Worker) → your Akash backend
- Private instance: App → directly to user's Akash provider URI (no middleman)
- Switching is seamless — user taps between shared and private in the UI

### 3.5 Desktop App Architecture (Electron — macOS + Windows + Linux)

Electron wraps a bundled frontend (NOT the ICP canister) in a Chromium shell. 100% shared across all three desktop platforms.

```
Electron App
├── main/ (Node.js main process)
│   ├── auto-updater.js (electron-updater, checks on launch)
│   ├── tray.js (system tray for deployment monitoring)
│   └── ipc.js (IPC bridge to renderer)
├── renderer/ (bundled frontend — React or vanilla JS)
│   ├── Same screens as mobile app
│   └── Additional: native file dialogs for attachments
├── Config/
│   └── Same endpoint/model config as mobile
└── Build/
    ├── mac/ (DMG, notarized with Apple Developer cert)
    ├── win/ (NSIS installer, code-signed)
    └── linux/ (AppImage + Snap)
```

**Desktop-specific capabilities:**
- System tray icon: shows deployment status (green = running, yellow = deploying, grey = stopped)
- `electron-updater`: silent background update check + install on launch
- Native file dialogs for attachments (vs. web file picker)
- No Akash CLI dependency — all deployment management via HTTP API to your backend

### 3.6 ICP Canister Decision

The ICP canister (`zc67k-kiaaa-aaaal-qtmiq-cai`) remains the **web-only frontend** for dubya.ai. Downloadable apps have their own bundled frontend — they do NOT load from the canister.

- **No per-user canisters.** All users share your single ICP canister for web access.
- **App users don't need ICP at all.** The app bundles its frontend and connects to `api.dubya.ai` for the shared model or directly to Akash for private instances.
- This keeps infrastructure simple and costs fixed (~$5/mo for the one canister).

### 3.7 App UX Flow — Complete User Journey

1. **Download** → iOS: App Store. Android: Google Play. Desktop: dubya.ai download page (detects OS, serves correct binary)
2. **Create account** → Auth flow TBD (see Phase -1). Single account works across web + all apps.
3. **Subscribe** → $30/year via Stripe (Apple Pay on iOS, Google Pay on Android, card on desktop). Immediate access.
4. **Default: shared model** → Immediately ready. Chat interface identical to dubya.ai. Full features unlocked (memory, RAG, agents, etc.)
5. **Optional: spin up private instance** →
   - Tap "Private Instance" tab
   - Browse model catalog (cards: model name, params, GPU, quality, $/hr)
   - Select model + duration (min 1 hour)
   - See total cost → pay via Stripe
   - Deployment kicks off → app streams real-time Akash container logs
   - Model downloads → progress bar with whimsical loading messages
   - Ready → app auto-switches to private endpoint
   - Timer shows remaining hours
   - Low balance warning at <30 minutes
   - Can stop early → unused time credited to account
6. **Switch back** → Tap to return to shared model at any time. Seamless.

---

## Part 4: Backend — Production Readiness

### 4.1 CI/CD Pipeline (Stop Pushing Broken Code)

**Problem:** Every new idea goes straight to the production Akash backend. No testing, no gates.

**Solution — Branch Workflow:**

| Branch | Purpose | CI | Deploy |
|--------|---------|------|--------|
| `develop` | All work lands here | Full test suite on push | Never auto-deploys |
| `main` | Production-ready only | Must pass CI | Manual deploy via script |

**CI Fixes** (`.github/workflows/test.yml`):
1. Fix `test/` → `tests/` path (line 52 — currently wrong)
2. Remove all `|| echo "... skipping"` — failures must block the build
3. Add `py_compile` for all files in `backend/services/` and `backend/routes/`
4. Add `pytest --cov=backend --cov-fail-under=85`
5. Add `docker build` step (no push) to catch Dockerfile issues before merge

**Local Docker Smoke Test:**
- `docker-compose.dev.yml`: Builds container with `tinyllama:1.1b` (tiny, CPU-ok)
- Tests: build → start → `curl /health` → run pytest against it → teardown
- Cost: $0. Catches import errors, route registration issues, Dockerfile problems

**Deploy gate:** `scripts/trinity-deploy-production.sh` only runs from `main`. Refuses to deploy from `develop` or feature branches.

### 4.2 Security Fixes (Pre-Launch)

From `CRITICAL-FIXES-ROADMAP.md`, the items that must be fixed before users:

| Fix | Priority | Status |
|-----|----------|--------|
| Forward client IPs through Cloudflare Worker | P0 | Required for guest rate limiting |
| Admin endpoint auth (`@require_admin`) | P0 | Currently open to anyone |
| Encrypt user memory storage | P0 | Currently plaintext |
| Disable code execution in prod | P0 | RCE vulnerability |
| Fix principal-key binding (auth spoofing) | P0 | Backend trusts any key for any principal |
| Nonce-based replay protection | P1 | 60s replay window |

### 4.3 New Backend Routes & Services

**New route blueprints:**

| Route | Auth | Purpose |
|-------|------|---------|
| `POST /account/register` | None | Create new account |
| `POST /account/login` | None | Authenticate, return session |
| `GET /account/profile` | `@require_auth` | Get account info + subscription status |
| `POST /account/subscribe` | `@require_auth` | Stripe checkout for $30/yr |
| `GET /models` | None | List available models with GPU/cost info |
| `POST /deploy/create` | `@require_subscription` | Request private Akash instance (triggers Stripe payment + deployment) |
| `GET /deploy/status` | `@require_subscription` | Deployment status (deploying/downloading/ready/stopped) |
| `GET /deploy/logs` | `@require_subscription` | SSE stream of Akash container logs |
| `POST /deploy/stop` | `@require_subscription` | Teardown private instance, credit unused time |
| `GET /deploy/balance` | `@require_subscription` | Remaining hours/credit for private instances |

**New backend services:**

| File | Purpose |
|------|---------|
| `backend/routes/account.py` | Registration, login, profile, subscription management |
| `backend/routes/deploy.py` | Create/stop/status/logs for private Akash instances |
| `backend/services/accounts.py` | User account CRUD, auth (TBD approach), subscription tracking |
| `backend/services/deployment_manager.py` | Wraps `akash_deploy.py` as API service — manages master wallet deployments |
| `backend/services/payments.py` | Stripe integration, webhook handling, balance tracking, credit system |
| `backend/middleware/subscription.py` | `@require_subscription` decorator — verifies active $30/yr subscription |

### 4.4 Auth Tiers

| Decorator | Who | Used On |
|-----------|-----|---------|
| (none) | Guests, anyone | `/health`, `/models`, `/generate` (with rate limit) |
| `@require_auth` | Any account holder (free or paid) | `/chat/*`, `/account/profile` |
| `@require_subscription` | Active $30/yr subscribers | Full features on shared model, private instance management |
| `@require_admin` | Gduby only | `/admin/*` |

### 4.5 Master Wallet Deployment Service

The `DeploymentManager` service wraps the existing `scripts/akash_deploy.py` (672 lines) into an API-callable backend service.

**How it works:**
1. User pays via Stripe → webhook hits `/deploy/create`
2. Backend generates SDL YAML from template (model + GPU vars)
3. `DeploymentManager` calls Akash CLI from master wallet: `createDeployment()` → `waitForBids()` → `selectCheapestBid()` → `createLease()` → `sendManifest()`
4. Docker image: always `gdubx/trinity-inference:v{latest}` (you control the image)
5. Env vars per deployment: `MODEL_NAME`, `TIER_TYPE=paid`, all features enabled
6. Deployment tracked in DB: `{user_id, deployment_id, provider_uri, model, gpu, hourly_cost, balance_hours, status, created_at}`
7. Background job monitors deployment health + balance depletion
8. On balance exhaustion or user stop: close lease, credit unused time

**Master wallet management:**
- Single AKT wallet funded by you — key stored in env var (never in code)
- Stripe revenue → you periodically buy AKT on exchange → fund the wallet
- Wallet balance monitoring: alert if < $100 AKT remaining
- All deployment costs are your cost; Stripe revenue minus Akash cost = your margin

---

## Part 5: Revenue Model

### 5.1 Revenue Streams

| Stream | Type | Price | Margin |
|--------|------|-------|--------|
| Trinity Package subscription | Annual upfront | $30/year | ~100% (software, no per-user COGS) |
| Private instance markup | Per-hour, on-demand | Akash cost + 15% | 15% on every deployment hour |
| Free tier (dubya.ai) | Loss leader | $0 | -$91/mo |

**Key insight:** Subscriptions scale with zero marginal cost — all subscribers share your one GPU until load requires scaling. The $30/yr is pure profit. Private instances are incremental revenue whenever users want more power.

### 5.2 Financial Projections

**Assumptions:**
- Free tier: $91/mo fixed cost (shared GPU + ICP canister)
- Subscription: $30/yr = $2.50/mo per subscriber (100% margin)
- 30% of subscribers occasionally spin up private instances
- Average private instance usage: 10 hours/month at T4 tier ($0.12/hr Akash cost)
- Private instance margin per active user: $0.12 × 10 × 15% = $0.18/mo
- Marketing: $200/mo (content, social, crypto community)
- Churn: 5%/mo (annual billing reduces this — most churn at renewal)

| Month | Free Cost | Subscribers | Sub Revenue | Instance Revenue | Monthly Profit | Cumulative |
|-------|-----------|------------|-------------|-----------------|---------------|-----------|
| 1 | -$91 | 5 | $12.50 | $0.27 | -$278 | -$278 |
| 3 | -$91 | 20 | $50 | $1.08 | -$240 | -$758 |
| 6 | -$91 | 60 | $150 | $3.24 | -$138 | -$1,327 |
| 12 | -$91 | 200 | $500 | $10.80 | +$220 | -$467 |
| 18 | -$91 | 400 | $1,000 | $21.60 | +$731 | +$3,400 |
| 24 | -$91 | 700 | $1,750 | $37.80 | +$1,497 | +$15,200 |

**Break-even:** ~Month 13 (200 subscribers at $2.50/mo covers free tier + marketing)  
**24-month cumulative profit:** ~$15,200

**Note:** These projections are conservative — they assume most subscribers use only the shared model. If private instance adoption is higher (e.g. power users running 72B models at $1.43/hr), the instance revenue contribution grows significantly. A single user running an A100 for 40 hours generates $8.58 in margin.

### 5.3 Scaling Milestones

| Subscribers | Infrastructure Change | Cost Impact |
|-------------|----------------------|-------------|
| 1-100 | Single shared GPU (Qwen 7B on T4) | Base case ($86/mo) |
| 100-300 | Consider 2nd shared GPU for load | +$86/mo, but 2x capacity |
| 300-500 | Upgrade shared model to Qwen 14B for quality | +$94/mo, better conversion |
| 500+ | Multiple shared GPU replicas, referral program | Revenue covers all costs 10x+ |
| 1,000+ | Consider load balancer, premium shared tier | Revenue supports A100-level shared model |

---

## Part 6: Existing Codebase Assets

What's already built that accelerates development:

| Component | Location | Reusable For |
|-----------|----------|-------------|
| Multi-model config | `deploy/docker/startup.sh` env vars | Model switching backend |
| AKT price feed | `backend/services/akash.py` (CoinGecko) | Live pricing in model picker |
| Escrow balance query | `backend/services/akash.py` | Master wallet balance monitoring |
| TokenTracker | `backend/services/caching.py` | Usage metering for subscribers |
| Session payment flow | `backend/routes/session.py` | Private instance purchase skeleton |
| Ed25519 auth | `backend/icp_auth.py` | Base for new auth system (to be redesigned) |
| SSE streaming | `backend/routes/generate.py`, `trinity-icp/src/core/api.js` | Chat streaming on all platforms + deployment log streaming |
| Deployment automation | `scripts/akash_deploy.py` (672 lines) | Wrap into `DeploymentManager` backend service |
| Loading messages | `backend/services/loading_messages.py` | Whimsical download progress in app |
| Modal system | `trinity-icp/src/ui/modals.js` | Reference for upgrade modals, model picker UI |
| Zustand state | `trinity-icp/src/state/store.js` | Same state lib in React Native + Electron |
| Akash SDL templates | `deploy/akash/deploy-tier*.yaml` | Generate dynamic YAMLs per user's model/GPU selection |

**Estimated reuse: ~35% of the paid product has foundational code already built.**

---

## Part 7: Implementation Roadmap

### Phase -1: Auth System Redesign (Weeks 0-2) — BLOCKS EVERYTHING

> **This phase must be completed before any app development begins.**

The current Ed25519 self-custody auth was built by a lesser model and has critical security gaps. A dedicated Auth Plan will be created to:

1. Audit the current system (836 lines of hand-written auth code + 8,579-line bundled Dfinity lib)
2. Document all vulnerabilities (principal spoofing, browser fingerprint fragility, localStorage loss)
3. Evaluate options: improved self-custody, traditional accounts, passkeys/WebAuthn
4. Select approach that works seamlessly across: ICP web frontend, React Native (iOS/Android), Electron (macOS/Windows/Linux)
5. Implement the chosen auth system on dubya.ai first, then ensure it ports to all app platforms

| Task | Priority | Effort |
|------|----------|--------|
| Create Auth Plan document (options analysis) | P0 | 1 day |
| Fix principal-key binding vulnerability | P0 | 2 days |
| Select auth approach (self-custody vs traditional vs passkeys) | P0 | 1 day |
| Implement new auth on dubya.ai (web) | P0 | 1 week |
| Verify auth approach ports to React Native + Electron | P0 | 2 days |
| Remove/replace 8.5K-line Dfinity bundle | P1 | 2 days |

### Phase 0: Foundation (Weeks 2-4) — BEFORE USERS

| Task | Priority | Effort |
|------|----------|--------|
| Fix CF Worker IP stripping | P0 | 2 hours |
| Add `@require_admin` to admin routes | P0 | 2 hours |
| Encrypt user memory at rest | P0 | 1 hour |
| Disable code execution in prod | P0 | 30 min |
| Fix CI test path (`test/` → `tests/`) | P0 | 30 min |
| Remove `|| echo "skipping"` from CI | P0 | 30 min |
| Create `deploy/akash/deploy-free-tier.yaml` | P1 | 1 hour |
| Add branch protection (`develop` → `main` PRs) | P1 | 1 hour |
| Local Docker smoke test (`docker-compose.dev.yml`) | P1 | 3 hours |

### Phase 1: Free Funnel (Weeks 4-6)

| Task | Effort |
|------|--------|
| Guest rate limit middleware (15 per random 2-6hr window, countdown at 10) | 3 days |
| Example prompt cards UI | 2 days |
| Upgrade modal + CTAs | 1 day |
| Deploy free-tier YAML to Akash | 1 day |
| Feature gating (strip RAG/agent/memory for guests) | 2 days |

### Phase 2: Subscription & Payment System (Weeks 6-10)

| Task | Effort |
|------|--------|
| Stripe integration ($30/year checkout) | 3 days |
| `@require_subscription` decorator + route gating | 2 days |
| Account management routes (register, login, profile) | 1 week |
| Subscription status tracking (active/expired/renewal) | 2 days |
| Webhook handler for Stripe payment events | 2 days |

### Phase 3: Private Instance Backend (Weeks 10-14)

| Task | Effort |
|------|--------|
| `DeploymentManager` service (wrap `akash_deploy.py` as API) | 1 week |
| Master wallet setup + AKT funding flow | 2 days |
| `/deploy/create`, `/deploy/stop`, `/deploy/status` routes | 1 week |
| `/deploy/logs` SSE stream (container logs + model pull progress) | 3 days |
| `/models` endpoint (catalog with pricing) | 1 day |
| Balance tracking + credit system for unused time | 3 days |
| Stripe payment flow for private instances (per-hour billing) | 3 days |

### Phase 4: iOS App (Months 3-4)

| Task | Effort |
|------|--------|
| React Native project scaffolding (TypeScript, Zustand, navigation) | 3 days |
| Auth screens (login, register, subscribe) | 1 week |
| Chat screen (SSE streaming, markdown, KaTeX) | 2 weeks |
| Private Instance screen (model catalog, deploy, logs, progress) | 1 week |
| Stripe payment integration (Apple Pay) | 3 days |
| Settings screen (account, subscription status) | 2 days |
| iOS Keychain integration for credential storage | 2 days |
| Push notifications (deployment ready, low balance, subscription expiry) | 2 days |
| TestFlight beta → App Store submission | 1 week |

### Phase 5: Android App (Months 4-5)

| Task | Effort |
|------|--------|
| Android-specific adjustments (shared RN codebase) | 3 days |
| Google Pay integration | 2 days |
| Android Keystore integration | 1 day |
| Google Play beta → Play Store submission | 1 week |

### Phase 6: macOS App (Months 5-6)

| Task | Effort |
|------|--------|
| Electron project scaffolding (shared renderer with web-like frontend) | 3 days |
| `electron-updater` auto-update (GitHub Releases or S3 feed) | 2 days |
| System tray icon (deployment status indicator) | 2 days |
| Native file dialogs for attachments | 1 day |
| Apple notarization + code signing | 2 days |
| DMG packaging + dubya.ai download page | 2 days |

### Phase 7: Windows + Linux Apps (Months 6-8)

| Task | Effort |
|------|--------|
| Windows-specific adjustments (shared Electron codebase) | 2 days |
| Windows code signing (EV certificate) | 2 days |
| NSIS installer packaging | 1 day |
| Linux AppImage + Snap builds | 2 days |
| dubya.ai download page (OS detection, serve correct binary) | 1 day |

### Phase 8: Polish & Scale (Months 8+)

| Task | Effort |
|------|--------|
| Referral program | 1 week |
| Usage dashboard (hours consumed, cost breakdown) | 1 week |
| Multi-GPU load balancing for shared model | 3 days |
| Model fine-tuning pipeline (Trinity v2 custom model) | Ongoing |
| B2B API tier (from B2B pivot research) | Future |

---

## Part 8: Risk Analysis

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Low paid adoption | Medium | High | Free tier proves product; $30/yr is impulse-buy pricing |
| Auth system redesign delays app launch | Medium | High | Phase -1 is first; blocks all app work; time-boxed to 2 weeks |
| Akash provider goes offline (private instance) | Medium | High | `DeploymentManager` can redeploy to different provider automatically |
| Akash price volatility | Low | Low | 15% markup absorbs fluctuation; adjust monthly |
| App Store rejection | Low | High | No crypto trading in app; payment via Stripe (Apple-approved); no AKT wallet exposure |
| Model quality insufficient on shared tier | Medium | Medium | Wide model selection for private instances; upgrade shared model as revenue grows |
| Support burden | High | Medium | Self-serve docs, FAQ, community Discord; closed-source prevents user tinkering |
| $30/yr too cheap to sustain | Low | Medium | Private instance markup is the real revenue driver; subscription is acquisition |
| Master wallet compromised | Low | Critical | Hardware wallet for cold storage; hot wallet holds only operational AKT; key in env var, never in code |
| Stripe regulatory issues with crypto-adjacent product | Low | Medium | Product is "AI chat subscription" — crypto infrastructure is backend implementation detail |

---

## Key Decisions (Resolved)

| Decision | Resolution | Rationale |
|----------|-----------|-----------|
| App or website? | Both — website (free funnel) + apps (paid product) | Website attracts users, apps are the product |
| Platform priority? | iOS → Android → macOS → Windows → Linux | Mobile first (largest market, App Store distribution), desktop follows |
| Mobile framework? | React Native | Best LLM familiarity, JS ecosystem, Akash SDK compat, ~90% code shared iOS/Android |
| Desktop framework? | Electron | Mature auto-updater, same JS codebase, 100% shared across macOS/Windows/Linux |
| Shared or per-user GPU? | Shared (subscription) + optional per-user (on-demand) | Subscription scales at zero marginal cost; private instances are optional upgrade |
| Monthly or annual billing? | Annual only ($30/yr upfront) | Reduces churn, simpler billing, impulse-buy pricing |
| Auth system? | TBD — dedicated Auth Plan required | Current system has critical gaps; must work across web + all app platforms |
| Per-user or master wallet? | Master wallet (you deploy on their behalf) | Dramatically simpler UX; user pays USD, never touches crypto |
| Open or closed source? | Closed source, auto-updates pushed by Gduby | User downloads, logs in, it works. No tinkering, no forks, controlled experience |
| ICP canister strategy? | Shared (web-only) — no per-user canisters | Apps bundle their own frontend; web users share one canister (~$5/mo) |
| Free tier model? | Qwen 7B on T4 | Good enough to impress, cheap enough to sustain ($86/mo) |

---

## Competitive Positioning

### Price Comparison

| Product | Monthly Cost | What You Get |
|---------|-------------|-------------|
| ChatGPT Plus | $20/mo ($240/yr) | GPT-4o, no privacy, rate limits |
| Claude Pro | $20/mo ($240/yr) | Claude 4, no privacy, rate limits |
| **Trinity Package** | **$2.50/mo ($30/yr)** | **Unlimited shared model, full privacy, optional private GPU** |

Trinity is **8x cheaper** than ChatGPT Plus for the software. The shared model is included — no additional compute costs. Users who want more power can optionally spin up private instances.

### Why Users Switch

1. **"My data is my data"** — Nothing goes to OpenAI/Google. Encrypted storage, private by default.
2. **"It just works for $2.50/month"** — Download, login, unlimited AI chat. No complexity.
3. **"I can upgrade when I need to"** — Day-to-day on the shared model, spin up 72B for serious work.
4. **"Any model I want"** — Not locked to one provider's model. Choose from the catalog.
5. **"No rate limits"** — Unlimited on shared model; dedicated throughput on private instances.
6. **"It's 8x cheaper"** — $30/yr vs $240/yr. And the AI quality keeps improving.

---

## Appendix A: Akash GPU Pricing Reference (Feb 2026)

| GPU | VRAM | $/hr | $/mo (24/7) | Best For |
|-----|------|------|------------|---------|
| T4 | 16GB | $0.12 | $86 | 3B-14B models |
| RTX 3090 | 24GB | $0.14 | $101 | 14B-32B models |
| RTX 3090 Ti | 24GB | $0.11 | $79 | 14B-32B models |
| RTX 4090 | 24GB | $0.39 | $281 | 32B models |
| RTX 5090 | 32GB | $0.52 | $374 | 32B models |
| A100 80GB | 80GB | $1.24 | $893 | 70B-72B models |
| H100 80GB | 80GB | $1.35 | $972 | 70B-72B models |
| H200 141GB | 141GB | $2.95 | $2,124 | Largest models |

*Source: akash.network/pricing/gpus, live marketplace data.*

## Appendix B: Cost Analysis Deep-Dive

See [cost-analysis-research.md](cost-analysis-research.md) for full break-even analysis comparing Trinity self-hosted costs vs. OpenAI, Anthropic, Google, and DeepSeek API pricing across usage levels.

**Key finding:** Self-hosting beats APIs at >10,000 messages/month against premium models (Claude Sonnet, GPT-4o). For light usage, APIs are cheaper — which is why the free tier uses a shared backend, not per-user deployment.

---

*This document is the definitive Trinity product plan. It supersedes TRINITY-B2B-PIVOT.md and all prior monetization docs.*  
*Last updated: February 11, 2026 (v2 — two-tier model, master wallet, closed source, auth TBD)*
