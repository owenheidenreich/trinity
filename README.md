<p align="center">
  <img src="https://img.shields.io/badge/status-live-brightgreen" alt="Status: Live">
  <img src="https://img.shields.io/badge/self--custody-Ed25519-ff6b6b" alt="Self-Custody">
  <img src="https://img.shields.io/badge/encryption-AES--256--GCM-ffd93d" alt="Encrypted">
  <img src="https://img.shields.io/badge/stack-fully%20decentralized-blueviolet" alt="Fully Decentralized">
</p>

<h1 align="center">Trinity</h1>

<h3 align="center"><em>Your Keys. Your Data. Your AI.</em></h3>

<p align="center">
The first AI chat application where you truly own everything.<br>
No accounts. No passwords. No company storing your conversations.<br>
Just cryptographic keys that belong to you.
</p>

<p align="center">
  <strong><a href="https://trinityai.cc">→ Start Chatting at trinityai.cc ←</a></strong>
</p>

---

## Why Trinity Exists

Every AI chat service today follows the same model: create an account, hand over your data, trust them not to read it, sell it, or lock you out. You don't own your conversations—they do.

**Trinity inverts this entirely.**

When you open Trinity, your browser generates a cryptographic keypair. That's your identity—not an email, not a username, just mathematics. Your private key never leaves your device. Every message you save is encrypted *before* it leaves your browser with keys derived from your identity. The backend literally cannot read your chats.

If you lose your key, your data is gone forever. That's not a bug—it's the whole point. **True ownership means no backdoors, no recovery, no "forgot password."** Your keys, your responsibility, your freedom.

---

## The Trinity: Three Blockchains, One Stack

| Blockchain | Role | Replaces |
|------------|------|----------|
| **ICP** (Internet Computer) | Frontend hosting + identity | AWS S3, Cloudflare, Auth0 |
| **Akash** (AKT) | GPU compute for AI inference | AWS EC2, Google Cloud, Azure |
| **IPFS/Filecoin** | Permanent encrypted storage | AWS S3, Google Drive, Dropbox |

No single company. No single point of failure. No kill switch.

Like Neo choosing to see the truth, Trinity represents awakening to a different reality—one where you control your digital existence instead of renting it from corporations.


Three becoming one. Distinct technologies unified into a seamless experience. An homage to faith and the belief that something greater can emerge from the union of parts.

---

## What Makes This Different

<table>
<tr>
<th width="50%">Traditional AI Chat</th>
<th width="50%">Trinity</th>
</tr>
<tr>
<td>

❌ Create account with email/password  
❌ Company stores all conversations  
❌ Company can read your data  
❌ Company can ban you  
❌ Company can shut down  
❌ Limited export options  
❌ Servers in corporate data centers  

</td>
<td>

✅ Generate keypair in browser (30 seconds)  
✅ You encrypt before saving  
✅ Backend cannot decrypt your chats  
✅ No accounts = no bans  
✅ Decentralized = unstoppable  
✅ Full data portability (export key)  
✅ Compute on decentralized networks  

</td>
</tr>
</table>

**The backend operators—including me—cannot read your messages.** The encryption happens in your browser with keys derived from your cryptographic identity. I store ciphertext. That's it.

---

## Features

### 🔐 Self-Custody Authentication

No passwords. No accounts. No "forgot password" emails.

Your browser generates an Ed25519 keypair—the same cryptography used by SSH, Signal, and modern blockchains. Your public key becomes your **principal ID** (your identity). Your private key is yours to export, backup, and protect.

**Import your key on any device** and your identity comes with you. No company can lock you out because no company controls your access.

### 🔒 Zero-Knowledge Encryption

Every saved chat is encrypted with **AES-256-GCM** before leaving your browser:

- **PBKDF2 key derivation** with 100,000 iterations
- **Random salt + nonce** per encryption operation
- **Your principal ID** as the encryption password

The backend stores only ciphertext. Even if the server is compromised, attackers get encrypted blobs they cannot decrypt without your private key.

### 🧠 Intelligent Reasoning (v3.7)

Trinity doesn't just respond—it *thinks*. A multi-pass agentic pipeline automatically routes questions by complexity:

| Complexity | Pipeline | Passes |
|------------|----------|--------|
| **Simple** | Direct answer | 1 |
| **Medium** | Understand → Execute → Critique | 3 |
| **Complex** | Understand → Plan → Execute → Critique → Refine | 5 |

For current information (prices, news, events), Trinity searches the web via Brave Search and synthesizes results into coherent answers.

### 💾 Smart Memory

- **6-message sliding window** for immediate context
- **Automatic summarization** every 15 messages (compress, don't lose)
- **User memory** that persists across all chats (facts, preferences, context)
- **Autosave** with 2-second debounce (never lose a message)

### 📊 LaTeX Mathematics

Full support for mathematical notation with **live rendering** as you chat:
- Inline: `$E = mc^2$` renders as $E = mc^2$
- Block equations with `$$...$$`
- Equations render progressively during response typing
- Powered by KaTeX for fast, beautiful rendering

---

## The Stack

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           TRINITY ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│    ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │
│    │       ICP        │  │      AKASH       │  │    FILECOIN      │    │
│    │  Internet        │  │   Decentralized  │  │   Permanent      │    │
│    │  Computer        │  │   Cloud          │  │   Storage        │    │
│    ├──────────────────┤  ├──────────────────┤  ├──────────────────┤    │
│    │ • Frontend       │  │ • GPU compute    │  │ • IPFS pinning   │    │
│    │ • Backend canister│  │ • LLM inference │  │ • Verified deals │    │
│    │ • Ed25519 auth   │  │ • Hot storage    │  │ • 540+ day proof │    │
│    │ • HTTPS outcalls │  │ • Flask API      │  │ • Multi-gateway  │    │
│    └──────────────────┘  └──────────────────┘  └──────────────────┘    │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│  ZERO DEPENDENCE ON: AWS, Google Cloud, Azure, Cloudflare, Auth0       │
│  CUSTOM DOMAIN: [no-domain-yet] → ICP boundary nodes (~200ms load)        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

Trinity is fully open source. Clone it, deploy it, own it.

```bash
# Clone the repository
git clone https://github.com/yourusername/Trinity.git
cd Trinity

# Copy environment template
cp .env.example .env
# Edit .env with your API keys:
# - LIGHTHOUSE_API_KEY (get from https://files.lighthouse.storage/)
# - BRAVE_SEARCH_API_KEY (get from https://brave.com/search/api/)

# Start local development (TinyLlama, no GPU needed)
./dev

# Or deploy to production (choose your tier)
./scripts/trinity-deploy-production.sh 1  # TinyLlama ~$25/mo
./scripts/trinity-deploy-production.sh 2  # Llama 8B ~$50/mo  
./scripts/trinity-deploy-production.sh 3  # Qwen 72B ~$200/mo
```

### Deployment Tiers

| Tier | Model | Intelligence | Cost | Use Case |
|------|-------|--------------|------|----------|
| **1** | TinyLlama 1.1B | Basic | ~$25/mo | Testing, light use |
| **2** | Llama 3.1 8B | Good | ~$50/mo | Daily driver |
| **3** | Qwen 2.5 32B+ | Excellent | ~$200/mo | Complex reasoning |

---

## Security Model

### What The Operators Cannot Do

- **Read your chats** → Encrypted client-side before transmission
- **Recover your account** → No accounts exist, only keypairs
- **Ban you** → No identity system to ban
- **Comply with data requests** → Cannot decrypt what we cannot read
- **Sell your data** → We don't have readable data

### What You Control

- **Your private key** → Export, backup, protect it
- **Your encrypted archives** → Stored on Filecoin with your CIDs
- **Your chat history** → Delete anytime from local storage
- **Your identity** → Same key works across devices

### The Trade-Off

**If you lose your private key, your data is gone forever.**

There is no "forgot password." There is no recovery email. There is no customer support that can help you. This is the price of true ownership—and it's a feature, not a bug.

Back up your key. Store it safely. You are your own bank.

---

## Technical Deep Dive

### Authentication Flow

```
Browser                           Backend
   │                                 │
   │  1. Generate Ed25519 keypair    │
   │  2. Derive principal ID         │
   │                                 │
   │  ──── Request + Signature ───►  │
   │       (timestamp, payload)      │
   │                                 │
   │                   3. Verify signature
   │                   4. Check timestamp (5-min window)
   │                   5. Process request
   │                                 │
   │  ◄──── Encrypted Response ────  │
```

### Encryption Layers

| Layer | Algorithm | Purpose |
|-------|-----------|---------|
| Transport | TLS 1.3 | Network security |
| Application | AES-256-GCM | Chat encryption |
| Key Derivation | PBKDF2 (100k iterations) | Password to key |
| Identity | Ed25519 | Signatures + principal |

### Storage Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                       STORAGE ARCHITECTURE                        │
├───────────────────────────────────────────────────────────────────┤
│  IPFS (Lighthouse) = Source of Truth                             │
│  • All encrypted chats stored permanently                         │
│  • Metadata synced for recovery after redeployment               │
│  • Content-addressed (CID) for integrity verification            │
├───────────────────────────────────────────────────────────────────┤
│  Browser (IndexedDB) = Session Cache                             │
│  • Immediate responsiveness                                       │
│  • Cleared on logout                                              │
└───────────────────────────────────────────────────────────────────┘
```

**Note:** Akash disk is only used for temporary metadata caching (chat list) to speed up requests. All actual chat data lives on IPFS and survives Akash redeployments.

---

## Project Structure

```
Trinity/
├── backend/                    # Python Flask backend
│   ├── inference_server.py     # Main API + encryption
│   ├── icp_auth.py             # Ed25519 verification
│   ├── config.py               # Environment configuration
│   └── services/
│       ├── agent.py            # Multi-pass reasoning
│       ├── complexity.py       # Question classifier
│       └── search.py           # Brave web search
│
├── trinity-icp/                # Frontend + ICP canisters
│   ├── src/
│   │   ├── app.js              # Main application
│   │   ├── auth/               # Keypair management
│   │   ├── state/              # Zustand + context memory
│   │   ├── storage/            # Autosave + Lighthouse
│   │   └── ui/                 # Modular components
│   └── src/backend_canister/   # Rust ICP canister
│
├── deploy/
│   ├── akash/                  # Tier 1/2/3 manifests
│   ├── docker/                 # Container builds
│   └── vercel-proxy/           # SSL termination
│
└── docs/
    └── CLAUDE.md               # Complete technical reference
```

---

## Support Trinity

Running decentralized infrastructure costs real money:

| Resource | Monthly Cost |
|----------|--------------|
| Akash GPU (current tier) | ~$50-200 |
| ICP Canister Cycles | ~$5-10 |
| Domain + DNS | ~$1 |

**Total: ~$60-220/month** depending on model tier.

If Trinity is valuable to you, consider:

- **Donating AKT/ICP/FIL** to help cover infrastructure
- **Running your own instance** to decentralize further
- **Contributing code** to improve the project
- **Spreading the word** to others who value data sovereignty

*Contact information and wallet addresses coming soon.*

---

## Roadmap

- [x] **Phase 1:** Self-custody authentication (Ed25519)
- [x] **Phase 2:** Encrypted autosave (AES-256-GCM)
- [x] **Phase 3:** Filecoin archive (Lighthouse SDK)
- [x] **Phase 4:** ICP backend canister (HTTPS Outcalls)
- [x] **Phase 5:** Custom domain (trinityai.cc)
- [x] **Phase 6:** Agentic reasoning pipeline (v3.6)
- [x] **Phase 7:** LaTeX mathematics (KaTeX)
- [ ] **Phase 8:** Lightweight RAG (local embeddings)
- [ ] **Phase 9:** Voice input/output
- [ ] **Phase 10:** Mobile PWA

---

## Contributing

Trinity is built for transparency. Every line of code is visible. Every decision is documented.

1. Fork the repository
2. Read `docs/CLAUDE.md` for technical context
3. Create a feature branch
4. Submit a pull request

---

## Links

- **Live App:** [trinityai.cc](https://trinityai.cc)
- **ICP Canister:** [zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io](https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io)
- **Documentation:** [docs/CLAUDE.md](docs/CLAUDE.md)
- **Docker Hub:** [gdubx/trinity-inference](https://hub.docker.com/r/gdubx/trinity-inference)

---

<p align="center">
<strong>Built without permission. Runs without servers. Owned by no one.</strong>
</p>

<p align="center">
<em>Because your conversations with AI should belong to you.</em>
</p>
