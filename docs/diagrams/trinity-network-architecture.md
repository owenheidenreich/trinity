# Trinity Network Architecture

> Last Updated: January 2026
> Status: Production

---

```
                            ╔══════════════════════════════════════════════════════════════╗
                            ║                     TRINITY ARCHITECTURE                      ║
                            ║              Decentralized AI Chat Application                ║
                            ╚══════════════════════════════════════════════════════════════╝


    ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
    │                                         USERS                                               │
    │                                                                                             │
    │     🌐 Browser                    🌐 Browser                      🌐 Browser                │
    │   trinityai.cc               www.trinityai.cc            zc67k-...icp0.io (direct)          │
    └─────────────┬─────────────────────┬─────────────────────────────┬───────────────────────────┘
                  │                     │                             │
                  │ HTTPS               │ HTTPS                       │ HTTPS
                  ▼                     ▼                             │
    ┌─────────────────────────────────────────────────────────┐       │
    │                                                         │       │
    │           ☁️  CLOUDFLARE (Edge Network)                 │       │
    │                                                         │       │
    │   ┌─────────────────────────────────────────────────┐   │       │
    │   │              DNS RECORDS (Proxied)              │   │       │
    │   │  ┌────────────────────────────────────────────┐ │   │       │
    │   │  │ @    CNAME → icp0.io    (Orange Cloud)     │ │   │       │
    │   │  │ www  CNAME → icp0.io    (Orange Cloud)     │ │   │       │
    │   │  │ api  CNAME → ...        (Orange Cloud)     │ │   │       │
    │   │  └────────────────────────────────────────────┘ │   │       │
    │   └─────────────────────────────────────────────────┘   │       │
    │                          │                              │       │
    │   ┌─────────────────────────────────────────────────┐   │       │
    │   │              CLOUDFLARE WORKERS                 │   │       │
    │   │                                                 │   │       │
    │   │  ┌───────────────────────────────────────────┐  │   │       │
    │   │  │      trinity-frontend-proxy               │  │   │       │
    │   │  │      Route: trinityai.cc/*                │  │   │       │
    │   │  │      Route: www.trinityai.cc/*            │  │   │       │
    │   │  │                  │                        │  │   │       │
    │   │  │                  ▼                        │  │   │       │
    │   │  │      Forwards to ICP Canister ────────────┼──┼───┼───┐   │
    │   │  └───────────────────────────────────────────┘  │   │   │   │
    │   │                                                 │   │   │   │
    │   │  ┌───────────────────────────────────────────┐  │   │   │   │
    │   │  │      trinity-api-proxy                    │  │   │   │   │
    │   │  │      Route: api.trinityai.cc/*            │  │   │   │   │
    │   │  │                  │                        │  │   │   │   │
    │   │  │                  ▼                        │  │   │   │   │
    │   │  │      Forwards to Akash Backend ───────────┼──┼───┼───┼───┐
    │   │  │      + CORS Headers                       │  │   │   │   │
    │   │  │      + Endpoint Whitelist                 │  │   │   │   │
    │   │  └───────────────────────────────────────────┘  │   │   │   │
    │   └─────────────────────────────────────────────────┘   │   │   │
    │                                                         │   │   │
    │   Nameservers: blakely.ns.cloudflare.com                │   │   │
    │                noah.ns.cloudflare.com                   │   │   │
    │                                                         │   │   │
    └─────────────────────────────────────────────────────────┘   │   │
                                                                  │   │
                  ┌───────────────────────────────────────────────┘   │
                  │                                                   │
                  ▼                                                   ▼
    ┌─────────────────────────────────────────────┐     ┌─────────────────────────────────────────────┐
    │                                             │     │                                             │
    │  🔗 INTERNET COMPUTER PROTOCOL (ICP)        │     │  🖥️  AKASH NETWORK (Decentralized Cloud)    │
    │                                             │     │                                             │
    │  ┌───────────────────────────────────────┐  │     │  ┌───────────────────────────────────────┐  │
    │  │  Canister ID:                         │  │     │  │  Provider: trinity-qwen72b            │  │
    │  │  zc67k-kiaaa-aaaal-qtmiq-cai          │  │     │  │  GPU: NVIDIA A100                     │  │
    │  │                                       │  │     │  │  Model: qwen2.5:72b                   │  │
    │  │  Type: Assets Canister                │  │     │  │                                       │  │
    │  │  Content: Trinity Frontend (HTML/JS)  │  │     │  │  Ingress URL:                         │  │
    │  │                                       │  │     │  │  cls1e8des1db50r65f6dpc8c7g           │  │
    │  │  Direct URL:                          │  │     │  │  .ingress.a100.dsm.val.akash.pub      │  │
    │  │  zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io  │  │     │  │                                       │  │
    │  └───────────────────────────────────────┘  │     │  │  Endpoints:                           │  │
    │                                             │     │  │  ├─ /health                           │  │
    │  Serves:                                    │     │  │  ├─ /generate                         │  │
    │  ├─ index.html (HTML structure)             │     │  │  └─ /stats                            │  │
    │  ├─ app.js (JavaScript app)                 │     │  │                                       │  │
    │  ├─ styles.css (CSS styling)                │     │  │  (No persistence layer)               │  │
    │  ├─ .well-known/ic-domains                  │     │  │                                       │  │
    │  └─ .ic-assets.json5 (Config)               │     │  │                                       │  │
    │                                             │     │  │                                       │  │
    └─────────────────────────────────────────────┘     │  └───────────────────────────────────────┘  │
                                                        │                                             │
                                                        │  Backend: Python Flask + Ollama            │
                                                        │  Protocol: HTTP (Cloudflare adds HTTPS)    │
                                                        │                                             │
                                                        └─────────────────────────────────────────────┘
```

---

## Data Flow Diagrams

### Page Load Flow

```
    ┌──────────┐      HTTPS       ┌────────────┐    HTTPS     ┌─────────────┐
    │  User    │ ───────────────► │ Cloudflare │ ───────────► │ ICP Canister│
    │ Browser  │ trinityai.cc     │  Worker    │  icp0.io     │  (Frontend) │
    └──────────┘                  └────────────┘              └─────────────┘
         │                              │                            │
         │◄─────────────────────────────┼────────────────────────────┘
         │         HTML/JS/CSS Response │
         ▼                              │
    ┌──────────────────────────────────────────────────────────────────────────┐
    │                         FRONTEND LOADED IN BROWSER                        │
    └──────────────────────────────────────────────────────────────────────────┘
```

### LLM Query Flow

```
    ┌──────────┐      HTTPS        ┌────────────┐     HTTP      ┌─────────────┐
    │ Frontend │ ────────────────► │ Cloudflare │ ────────────► │   Akash     │
    │ (Browser)│ api.trinityai.cc  │  Worker    │  akash.pub    │  Backend    │
    └──────────┘   /generate       └────────────┘               └─────────────┘
         │                               │                            │
         │                               │         ┌──────────────────┘
         │                               │         │ LLM Response
         │                               │         ▼
         │                         ┌─────────────────────┐
         │                         │ + CORS Headers      │
         │                         │ + Origin Validation │
         │                         └─────────────────────┘
         │                               │
         │◄──────────────────────────────┘
         │         JSON Response
         ▼
    ┌──────────────────────────────────────────────────────────────────────────┐
    │                         AI RESPONSE DISPLAYED                             │
    └──────────────────────────────────────────────────────────────────────────┘
```

---

## Component Reference

| Component | Identifier | Purpose |
|-----------|------------|---------|
| **Domain** | `trinityai.cc` | Primary user-facing URL |
| **ICP Canister** | `zc67k-kiaaa-aaaal-qtmiq-cai` | Hosts frontend assets |
| **Frontend Worker** | `trinity-frontend-proxy` | Routes domain → ICP |
| **API Worker** | `trinity-api-proxy` | Routes API → Akash |
| **Akash Ingress** | `cls1e8des1db50r65f6dpc8c7g.ingress.a100.dsm.val.akash.pub` | LLM backend |
| **LLM Model** | `qwen2.5:72b` | 72B parameter AI model |

---

## Cloudflare Configuration

### DNS Records

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| CNAME | @ | zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io | Proxied (Orange) |
| CNAME | www | zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io | Proxied (Orange) |
| CNAME | api | *(any valid target)* | Proxied (Orange) |

### Worker Routes

| Route | Worker |
|-------|--------|
| `trinityai.cc/*` | `trinity-frontend-proxy` |
| `www.trinityai.cc/*` | `trinity-frontend-proxy` |
| `api.trinityai.cc/*` | `trinity-api-proxy` |

### Nameservers

```
blakely.ns.cloudflare.com
noah.ns.cloudflare.com
```

---

## File Locations

| File | Path | Purpose |
|------|------|---------|
| Frontend HTML | `trinity-icp/src/trinity_frontend/assets/index.html` | HTML structure |
| Frontend JS | `trinity-icp/src/trinity_frontend/assets/app.js` | JavaScript application |
| Frontend CSS | `trinity-icp/src/trinity_frontend/assets/styles.css` | CSS styling |
| API Worker | `cloudflare/workers/trinity-ai-proxy.js` | Cloudflare Worker for API |
| Frontend Worker | `cloudflare/workers/trinity-frontend-proxy.js` | Cloudflare Worker for frontend |
| ICP Config | `trinity-icp/src/trinity_frontend/assets/.ic-assets.json5` | Asset headers/CSP |
| Domain Config | `trinity-icp/src/trinity_frontend/assets/.well-known/ic-domains` | Custom domain list |

---

## Updating Components

### When Akash Deployment Changes

1. Update `AKASH_BACKEND` in `cloudflare/workers/trinity-ai-proxy.js`
2. Update fallback URL in `app.js` → `CONFIG.API_URL` getter (lines 20-28)
3. Redeploy Cloudflare Worker via dashboard
4. Run verification commands below

### When ICP Canister Changes

1. Update `ICP_CANISTER_URL` in `cloudflare/workers/trinity-frontend-proxy.js`
2. Update `.well-known/ic-domains` if domain changes
3. Deploy: `cd trinity-icp && dfx deploy --ic`
4. Redeploy Cloudflare Worker

### When Adding New API Endpoints

1. Add endpoint to `allowedPaths` array in `trinity-ai-proxy.js`
2. Redeploy Cloudflare Worker

---

## Verification Commands

```bash
# Test frontend via custom domain
curl -s "https://trinityai.cc/" | head -5

# Test frontend via ICP direct
curl -s "https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io/" | head -5

# Test API health
curl -s "https://api.trinityai.cc/health" | jq .

# Test LLM generation
curl -s -X POST "https://api.trinityai.cc/generate" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello", "max_length": 10}'

# Test domain registration file
curl -s "https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io/.well-known/ic-domains"
```

---

## Security Notes

- **HTTPS Everywhere**: Cloudflare provides SSL termination for all user-facing endpoints
- **CORS Protection**: API worker validates `Origin` header against whitelist
- **Endpoint Whitelist**: Only specific API paths are allowed through the proxy
- **No Direct Akash Access**: Users cannot bypass Cloudflare to reach Akash directly (HTTP blocked by browsers from HTTPS pages)

---

## Cost Structure

| Service | Tier | Notes |
|---------|------|-------|
| Cloudflare | Free | Workers, DNS, SSL included |
| ICP | Pay-per-use | Cycles for compute/storage |
| Akash | Pay-per-use | GPU compute time |
| Domain | Annual | trinityai.cc registration |
