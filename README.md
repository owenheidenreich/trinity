<p align="center">
  <img src="https://img.shields.io/badge/status-live-brightgreen" alt="Status: Live">
  <img src="https://img.shields.io/badge/stack-fully%20decentralized-blueviolet" alt="Fully Decentralized">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License: MIT">
</p>

# Trinity

**A fully decentralized AI chat application.** No accounts. No passwords. No centralized servers. Just you and your AI, secured by cryptography.

<p align="center">
  <a href="https://trinityai.eth.limo">trinityai.eth.limo</a> · 
  <a href="https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io">ICP Canister</a>
</p>

---

## What Makes Trinity Different

| Traditional AI Chat | Trinity |
|---------------------|---------|
| Create account with email/password | Generate cryptographic keypair in browser |
| Company stores your conversations | You own your data, encrypted with keys only you hold |
| Servers in data centers | Compute on Akash (decentralized cloud) |
| Data on company databases | Archives on Filecoin (permanent, verifiable storage) |
| Access via company domain | Access via ENS (trinityai.eth) or ICP canister |

**Zero trust architecture.** We can't read your chats. We can't lock you out. We can't shut down.

---

## The Stack

```
┌─────────────────────────────────────────────────────────────────┐
│                         TRINITY STACK                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│   │     ICP     │    │    AKASH    │    │  FILECOIN   │        │
│   │  Identity   │    │   Compute   │    │   Storage   │        │
│   └─────────────┘    └─────────────┘    └─────────────┘        │
│                                                                 │
│   • Frontend hosting  • GPU inference   • Permanent archives   │
│   • Ed25519 auth      • LLM serving     • Verified deals       │
│   • HTTPS outcalls    • Hot storage     • IPFS pinning         │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│   DNS: trinityai.eth (ENS) → eth.limo gateway → IPFS mirror    │
└─────────────────────────────────────────────────────────────────┘
```

**No Cloudflare. No AWS. No Google. No single point of failure.**

---

## Features

### Self-Custody Authentication
Generate an Ed25519 keypair in your browser. Your public key becomes your identity. Your private key is your password. Export it, back it up, own it forever.

### End-to-End Encryption
Every saved chat is encrypted with AES-256-GCM before leaving your browser. The key is derived from your principal ID. Not even the backend can read your messages.

### Permanent Archives
Click archive and your chat is uploaded to IPFS, then automatically sealed into a Filecoin deal. Verifiable, permanent, censorship-resistant storage.

### Context Memory
Trinity remembers. A 6-message sliding window plus periodic summarization means coherent long conversations without exploding token counts.

### Decentralized DNS
Access via `trinityai.eth` in Brave/Opera, or `trinityai.eth.limo` in any browser. No ICANN, no registrars, no takedowns.

---

## Quick Start

### Use Trinity (No Installation)
Just visit **[trinityai.eth.limo](https://trinityai.eth.limo)** and start chatting.

### Run Locally (Development)
```bash
# Clone the repo
git clone https://github.com/yourusername/Trinity.git
cd Trinity

# Start local backend with TinyLlama
./dev

# Opens browser to frontend
# Backend runs at localhost:8000
```

### Deploy to Production
```bash
# Build Docker image for Akash
cd deploy/docker && ./build.sh

# Deploy via Akash Console (manual)
# Use deploy/akash/deploy-tinyllama-prod.yaml

# Deploy frontend to ICP
cd trinity-icp && dfx deploy --ic trinity_frontend
```

---

## Architecture

### Data Flow
```
User Input
    ↓
Browser (Ed25519 signature)
    ↓
ICP Frontend Canister
    ↓
ICP Backend Canister (HTTPS outcalls)
    ↓
Vercel Proxy (SSL termination)
    ↓
Akash Backend (Flask + Ollama)
    ↓
LLM Response
    ↓
Autosave (encrypted) → Akash disk
    ↓
Archive (optional) → Lighthouse → IPFS + Filecoin
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Frontend | `trinity-icp/src/` | Modular vanilla JS with Zustand state |
| Backend | `backend/` | Flask API with Ed25519 auth |
| Deployment | `deploy/` | Docker, Akash YAML, Vercel proxy |
| Scripts | `scripts/` | Dev, deploy, provider switching |

---

## Project Structure

```
Trinity/
├── backend/                 # Python Flask backend
│   ├── inference_server.py  # Main API server
│   └── icp_auth.py          # Ed25519 signature verification
├── trinity-icp/             # Frontend + ICP canisters
│   ├── src/
│   │   ├── app.js           # Main application
│   │   ├── auth/            # Ed25519 keypair management
│   │   ├── state/           # Zustand store + context memory
│   │   ├── storage/         # Autosave + Lighthouse SDK
│   │   └── ui/              # Modular UI components
│   └── src/backend_canister/ # Rust ICP canister
├── deploy/
│   ├── akash/               # GPU deployment manifests
│   ├── docker/              # Container build scripts
│   └── vercel-proxy/        # SSL termination proxy
├── docs/
│   └── CLAUDE.md            # Comprehensive technical reference
└── scripts/                 # Automation scripts
```

---

## Technology

| Layer | Technology | Why |
|-------|------------|-----|
| **Frontend** | Vanilla JS + Vite | No framework lock-in, fast builds |
| **State** | Zustand 5.0 | Minimal, immutable, predictable |
| **Auth** | Ed25519 (TweetNaCl) | Industry standard, self-custody |
| **Encryption** | AES-256-GCM | Military-grade, browser-native |
| **Backend** | Flask + Ollama | Simple, battle-tested |
| **Compute** | Akash Network | Decentralized, cost-effective GPUs |
| **Hosting** | ICP Canisters | Unstoppable, no servers |
| **Storage** | Lighthouse SDK | IPFS + verified Filecoin deals |
| **DNS** | ENS (trinityai.eth) | Decentralized, censorship-resistant |
| **Proxy** | Vercel Edge | SSL termination for Akash |

---

## Security Model

### What We Can't Do
- Read your chats (encrypted client-side)
- Lock you out (you own your keys)
- Shut down your access (decentralized hosting)
- Sell your data (we don't have it)

### What You Control
- Your private key (export and back up!)
- Your encrypted archives (stored on Filecoin)
- Your chat history (delete anytime)

### Trust Assumptions
- Browser cryptography is sound (Web Crypto API)
- ICP canisters execute as written
- Akash providers run unmodified containers
- Filecoin deals are honored

---

## Cost

Running Trinity costs real crypto:

| Resource | Token | Approximate Cost |
|----------|-------|------------------|
| Akash GPU (Tier 1) | AKT | ~$25-50/month |
| ICP Canister Cycles | ICP | ~$5-10/month |
| Filecoin Storage | FIL | ~$0.01/GB/year |
| ENS Domain | ETH | ~$5/year |

**Total:** ~$30-60/month for a fully decentralized AI chat with permanent storage.

---

## Roadmap

- [x] Phase 1: Self-custody authentication (Ed25519)
- [x] Phase 2: Encrypted autosave
- [x] Phase 3: Filecoin archive via Lighthouse
- [x] Phase 4: ICP backend canister (no Cloudflare)
- [x] Phase 5: ENS domain (trinityai.eth)
- [ ] Phase 6: Dynamic LLM tier routing
- [ ] Phase 7: Donation/payment system
- [ ] Phase 8: Open source release

---

## Contributing

Trinity is built for transparency. The code does exactly what it says.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

See `docs/CLAUDE.md` for comprehensive technical documentation.

---

## License

MIT License. Use it, fork it, improve it.

---

## Links

- **Live App:** [trinityai.eth.limo](https://trinityai.eth.limo)
- **ICP Canister:** [zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io](https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io)
- **IPFS Mirror:** `ipfs://bafybeigylq4xs26nj23hzfrsmdw2iqutsrlgpakddebdrpqssdcboddsau`
- **Documentation:** [docs/CLAUDE.md](docs/CLAUDE.md)

---

<p align="center">
  <i>Built without permission. Runs without servers. Owned by no one.</i>
</p>
