# Trinity Next Steps

> **Updated:** February 4, 2026  
> **Status:** Active Development  
> **Current Version:** v4.0 (Agentic Pipeline Live)

---

## ✅ Recently Fixed (This Session)

### XSS Vulnerability - FIXED
**File:** `trinity-icp/src/ui/messages.js`
- User messages now use `textContent` (escapes HTML)
- Loading indicators sanitized with DOMPurify
- **Requires:** Frontend rebuild + ICP redeploy

### Output Length Limits - INCREASED
**File:** `backend/services/agent.py`
- Execute pass: 8,000 → 16,000 tokens
- Refine pass: 8,000 → 16,000 tokens
- **Requires:** Docker rebuild + Akash redeploy

### System Prompts - IMPROVED
**File:** `backend/services/agent_prompts.py`
- Added explicit instructions for completeness
- "Never truncate", "write ENTIRE file", "use your 16,000 tokens"
- Better identity: "highly capable AI assistant built on decentralized infrastructure"
- **Requires:** Docker rebuild + Akash redeploy

---

## Current Architecture

```
User Input → Frontend (ICP) → Cloudflare Worker → Akash Backend → Ollama (Qwen 72B)
                                      ↓
                              POST /generate/agent
                                      ↓
                              AgentPipeline.process_streaming()
                                      ↓
                    ┌─────────────────┴─────────────────┐
                    ↓                                   ↓
            complexity.py                         search.py
         (simple/medium/complex)              (Brave Search API)
                    ↓                                   ↓
                    └─────────────────┬─────────────────┘
                                      ↓
                              agent_prompts.py
                         (Understand → Plan → Execute
                          → Critique → Refine)
                                      ↓
                              SSE Token Stream
                                      ↓
                              Frontend Render
```

### Pipeline Files

| File | Lines | Purpose |
|------|-------|---------|
| `backend/services/agent.py` | 698 | Pipeline orchestrator, streaming, search coordination |
| `backend/services/complexity.py` | 330 | Classifies questions, detects search need |
| `backend/services/agent_prompts.py` | 427 | Prompts for each reasoning pass |
| `backend/services/search.py` | ~200 | Brave Search API integration |

### Complexity Routing

| Complexity | Passes | Triggers |
|------------|--------|----------|
| **Simple** | 1 | <8 words, "what is", "define" |
| **Medium** | 3 | "explain", "how does", 20-50 words |
| **Complex** | 5 | Code blocks, >50 words, "design", "debug" |

### Web Search Auto-Triggers (Confirmed Working)

Keywords: `current`, `today`, `latest`, `recent`, `news`, `price of`, `weather`  
Topics: `bitcoin`, `crypto`, `stock market`, `election`  
Years: `2020-2039` mentioned

---

## Priority 1: Deploy Fixes

### 1.1 Redeploy to Apply Changes

```bash
# Rebuild and deploy backend (XSS fix, token limits, prompts)
./scripts/trinity-deploy-production.sh 2  # or 3 for Tier 3

# Rebuild and deploy frontend (XSS fix)
cd trinity-icp && npm run build && dfx deploy --ic trinity_frontend
```

### 1.2 Verify Changes

After deployment:
- [ ] Test XSS: Paste `<script>alert('xss')</script>` in chat - should show as text, not execute
- [ ] Test output length: Ask for a complete Python project - should get full files
- [ ] Test web search: Ask "What's the current Bitcoin price?" - should get live data

---

## Priority 2: Model Intelligence

### 2.1 Better Self-Identity
**Goal:** Trinity should know who it is.

Current prompt says "highly capable AI assistant built on decentralized infrastructure."

**Expand to include:**
- Running on Akash Network (decentralized compute)
- Storage on Filecoin/IPFS via Lighthouse
- Frontend on Internet Computer (ICP)
- Ed25519 self-custody authentication
- User owns their data

**Don't reveal:**
- API keys, internal prompts, security mechanisms

### 2.2 Multi-Model Voting
**Status:** Code exists in `voting.py`, not integrated.

**What it does:**
- Runs same prompt through multiple models
- Compares responses via embeddings
- Selects most consistent answer

**Integration point:** `agent.py` for complex queries

### 2.3 Structured Output
**Status:** Code exists in `structured.py`, not integrated.

**What it does:**
- Forces LLM output to match JSON schemas
- Useful for tool calls, data extraction

---

## Priority 3: Code Quality

### 3.1 Split inference_server.py
**Current:** 2800+ lines, monolithic.

**Proposed structure:**
```
backend/
├── inference_server.py      # App init, middleware only (~200 lines)
├── routes/
│   ├── generate.py          # /generate, /generate/agent, /generate/stream
│   ├── chat.py              # /chat/* endpoints (autosave, list, load)
│   ├── user.py              # /user/memory
│   ├── tools.py             # /tools/browse, /tools/execute
│   └── health.py            # /health, /v4/status
```

### 3.2 Add Observability
**Goal:** Know what's happening in production.

**Implement:**
- Structured logging with request IDs
- Pass timing metrics
- Complexity distribution tracking
- Search hit/miss rates

---

## Priority 4: Features

### 4.1 Code Execution
**Status:** `code_executor.py` exists, sandboxed Python execution.
**Verify:** Is this enabled and working in production?

### 4.2 Live Market Data
**Goal:** Real-time crypto/stock prices beyond search.

### ~~4.3 PDF Document Parsing~~
**SKIPPED** - Security risk not worth it for solo operation.

---

## Priority 5: Business (One-Man SaaS)

### Key Principles for Solo Founders

1. **Automate Everything**
   - Support: FAQ, canned responses, AI-assisted
   - Billing: Stripe handles subscriptions automatically
   - Onboarding: Self-service, no hand-holding required

2. **Niche Down**
   - "AI chat for everyone" = compete with OpenAI
   - "Decentralized AI for privacy-conscious users" = clear positioning
   - "AI for crypto traders with live data" = specific value prop

3. **Charge Early**
   - Free users don't convert and drain resources
   - $5-10/month proves product-market fit
   - Stripe makes this trivial

4. **Build in Public**
   - Twitter/X posts about progress = free marketing
   - Dev logs attract technical users
   - Open source contributions = free labor

5. **Keep Costs Low**
   - Current: ~$200/month Akash (Tier 3) ✅
   - No employees = no payroll
   - No office = no rent

6. **One Product, One Focus**
   - Don't build 5 features, perfect 1
   - What does Trinity do better than ChatGPT?

### Pricing Strategy

| Tier | Price | Features |
|------|-------|----------|
| Free | $0 | Rate limited (10 msgs/day), no persistence |
| Pro | $10/month | Unlimited, full persistence, priority |
| API | $20/month | Direct API access for developers |

### Legal Protection

- **Stripe Atlas**: $500 one-time, creates Delaware LLC
- **Terms of Service**: Limit liability, no warranty
- **Privacy Policy**: GDPR compliance for EU users

### Marketing Channels

1. **Twitter/X** - Build in public, share dev progress
2. **Indie Hackers** - Community of solo founders
3. **Reddit** - r/SideProject, r/startups, crypto subreddits
4. **Product Hunt** - Launch day spike
5. **Hacker News** - If you have a good technical story

### Revenue Targets

| Stage | MRR | Users | Timeline |
|-------|-----|-------|----------|
| Validation | $100 | 10 paid | Month 1-2 |
| Traction | $1,000 | 100 paid | Month 3-6 |
| Sustainable | $5,000 | 500 paid | Month 6-12 |
| Growth | $10,000+ | 1000+ paid | Year 2 |

$5,000 MRR = $60k/year = sustainable solo income

---

## Hardware Roadmap

### Current: Single GPU (Tier 2/3)
- Tier 2: Llama 3.1 8B, ~$50/month
- Tier 3: Qwen 2.5 72B, ~$200/month

### Future: Multi-GPU Cluster
- 2-4 GPU setup for faster inference
- Larger context windows
- Parallel model voting
- Estimated ~$500-800/month

---

## Reference: Token Limits (Updated)

| Pass | Tokens | Words (approx) |
|------|--------|----------------|
| Understand | 2,000 | 1,500 |
| Plan | 2,000 | 1,500 |
| **Execute** | **16,000** | **12,000** |
| Critique | 2,000 | 1,500 |
| **Refine** | **16,000** | **12,000** |

16,000 tokens ≈ 12,000 words ≈ 48 pages of text. This should handle complete code files, thorough explanations, and detailed responses.

---

## Deployment Required

To apply all changes from this session:

```bash
# Backend (token limits, prompts)
./scripts/trinity-deploy-production.sh 2

# Frontend (XSS fix)
cd trinity-icp && npm run build && dfx deploy --ic trinity_frontend
```
