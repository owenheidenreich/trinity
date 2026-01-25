## Trinity is a fully decentralized AI chat application featuring self-custody authentication, AES-256-GCM encrypted autosave, and permanent archival to Filecoin via Pinata.

## Primary Docs

- **For AI & Maintainers:** [CLAUDE.md](docs/CLAUDE.md) — authoritative project reference (architecture, implementation status, deployment notes, known failures).
-- **For Humans / Quick Tasks:** [quickstart.md](docs/user/quickstart.md) — short commands, common workflows, and daily tasks.
- **Architecture Diagrams:** [diagrams/ARCHITECTURE.md](docs/diagrams/ARCHITECTURE.md) — system design overview and topology.
- **Roadmap:** [plans/next-phase-implementation-plan.md](plans/next-phase-implementation-plan.md).

---

## Quick Start (most-used commands)

```bash
./dev.sh          # Start local development (TinyLlama via Ollama)
./test-prod.sh    # Run production smoke tests
./deploy.sh       # Build & prepare deployment artifacts
```

### Important URLs
- **Frontend:** https://trinityai.cc
- **API (Cloudflare worker):** https://api.trinityai.cc

---

## What to Read

| Task | Primary doc |
|------|-------------|
| Full technical reference | [CLAUDE.md](docs/CLAUDE.md) |
| Start local / daily commands | [quickstart.md](docs/user/quickstart.md#daily-commands) |
| Deploy frontend to ICP | [quickstart.md](docs/user/quickstart.md#frontend-deployment-icp) |
| Deploy/update backend (Akash) | [quickstart.md](docs/user/quickstart.md#akash-backend-deployment) |
| Architecture diagrams | [docs/diagrams/ARCHITECTURE.md](docs/diagrams/ARCHITECTURE.md) |

---

*Last updated: January 23, 2026*

---

## Key Concepts (short)

- Two environments: **Local** (TinyLlama 1.1B via Ollama — free, for development) and **Akash** (production GPUs running Llama 3.1 70B).
- Local development uses `TinyLlama:1.1b`; production uses `Llama 3.1 70B` on Akash (costs are typically in the ~$50–$60/month range for a kept deployment; actual cost varies by provider and uptime).

---

## Notes & Differences (from older READMEs)

- The canonical, authoritative reference is `docs/CLAUDE.md`. Treat it as the single source of truth for architecture, deployment, and known failures.
- Several legacy docs were consolidated; use `docs/user/quickstart.md` for short operational commands and `docs/CLAUDE.md` for deep dives.
- Pinata (not web3.storage) is the configured Filecoin/IPFS gateway; follow `docs/CLAUDE.md` for Pinata setup steps.

---

## Getting Help / Diagnostics

Check these first:

```bash
# Backend health
curl https://api.trinityai.cc/health

# Local backend (if running)
curl http://localhost:8000/health

# Tail backend logs (local dev)
tail -f /tmp/trinity_backend.log
```

For deeper troubleshooting and the list of known failures, see: [docs/CLAUDE.md#known-failures--lessons-learned](docs/CLAUDE.md#known-failures--lessons-learned).

---

## Quick Links

- [docs/CLAUDE.md](docs/CLAUDE.md) — authoritative reference
- [docs/quickstart.md](docs/quickstart.md) — short operational guide
- [docs/diagrams/ARCHITECTURE.md](docs/diagrams/ARCHITECTURE.md) — architecture diagrams
