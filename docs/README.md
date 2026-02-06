# 📚 Trinity Documentation

> Organized documentation for humans and AIs alike.

---

## Quick Navigation

| Category | Description | For Who |
|----------|-------------|---------|
| [🤖 ai-context/](ai-context/) | Project knowledge base for AI assistants | **AI/LLMs** |
| [🏗️ architecture/](architecture/) | System design & technical decisions | **Engineers** |
| [🔒 security/](security/) | Audits, testing, threat models | **Security/Auditors** |
| [🚀 getting-started/](getting-started/) | Setup guides & tutorials | **New Developers** |
| [📖 reference/](reference/) | CLI commands & API docs | **All Developers** |
| [📜 lore/](lore/) | Model battle reports & AI chronicles | **Blog/Marketing** |
| [🗄️ archive/](archive/) | Completed plans & historical docs | **Context** |

---

## 🤖 For AI Assistants

**Start here:** [ai-context/CLAUDE.md](ai-context/CLAUDE.md)

This is the authoritative reference document for understanding Trinity. It contains:
- Architecture overview
- State management patterns (Zustand)
- Authentication flow (Ed25519)
- Deployment workflows
- Common pitfalls

**Also useful:** [ai-context/FEATURE_CATALOG.md](ai-context/FEATURE_CATALOG.md) — Complete inventory of every feature.

---

## 🏗️ For Engineers

### Understanding the System
1. [architecture/trinity-storage-architecture.md](architecture/trinity-storage-architecture.md) — Data flow diagram
2. [architecture/decisions/](architecture/decisions/) — ADRs explaining key design choices

### Security Review
1. [security/SECURITY-AUDITOR-OVERVIEW.md](security/SECURITY-AUDITOR-OVERVIEW.md) — Start here for audits
2. [security/security-audit.md](security/security-audit.md) — Test coverage report

---

## 🚀 For New Developers

### Setup (in order)
1. [getting-started/quickstart.md](getting-started/quickstart.md) — 5-minute quick start
2. [getting-started/developer-setup.md](getting-started/developer-setup.md) — Full local setup
3. [getting-started/setup.md](getting-started/setup.md) — Production deployment setup

### Orientation
4. [getting-started/architecture-walkthrough.md](getting-started/architecture-walkthrough.md) — System tour
5. [getting-started/common-tasks.md](getting-started/common-tasks.md) — Day-to-day workflows

---

## 📖 Reference

| Document | Contents |
|----------|----------|
| [reference/AKASH_CLI_REFERENCE.md](reference/AKASH_CLI_REFERENCE.md) | Akash deployment commands |

---

## 📜 The Trinity Lore

Epic tales of AI battles and model comparisons:

| Chronicle | Summary |
|-----------|---------|
| [lore/README.md](lore/README.md) | **The Chronicle of Trinity** — Full saga |
| [lore/battle-of-qwen.md](lore/battle-of-qwen.md) | Qwen 14B vs 32B showdown |
| [lore/war-of-three-kings.md](lore/war-of-three-kings.md) | Qwen vs Llama vs Mixtral |

---

## 🗄️ Archive

Historical documents from completed work:

| Document | Status |
|----------|--------|
| [archive/trinity-production-upgrade-master-plan.md](archive/trinity-production-upgrade-master-plan.md) | ✅ Complete |
| [archive/PHASE-2B-COMPLETION-MEMO.md](archive/PHASE-2B-COMPLETION-MEMO.md) | ✅ Complete |
| [archive/PHASE-3-COMPLETION-MEMO.md](archive/PHASE-3-COMPLETION-MEMO.md) | ✅ Complete |
| [archive/PHASE-5.5A-CRITICAL-METRICS-MIGRATION.md](archive/PHASE-5.5A-CRITICAL-METRICS-MIGRATION.md) | ✅ Complete |

---

## Directory Structure

```
docs/
├── README.md                    ← You are here
├── ai-context/                  ← 🤖 For AI assistants
│   ├── CLAUDE.md               ← Primary AI reference
│   └── FEATURE_CATALOG.md      ← Feature inventory
├── architecture/                ← 🏗️ System design
│   ├── trinity-storage-architecture.md
│   └── decisions/              ← ADRs (Architecture Decision Records)
│       ├── 001-complexity-routing.md
│       ├── 002-tiered-test-coverage.md
│       ├── 003-prometheus-over-saas.md
│       ├── 004-hash-based-experiments.md
│       └── 005-in-memory-caching.md
├── security/                    ← 🔒 Security docs
│   ├── SECURITY-AUDITOR-OVERVIEW.md
│   └── security-audit.md
├── getting-started/             ← 🚀 Setup guides
│   ├── quickstart.md
│   ├── developer-setup.md
│   ├── setup.md
│   ├── architecture-walkthrough.md
│   └── common-tasks.md
├── reference/                   ← 📖 CLI & API docs
│   └── AKASH_CLI_REFERENCE.md
├── lore/                        ← 📜 Battle reports
│   ├── README.md
│   ├── battle-of-qwen.md
│   ├── war-of-three-kings.md
│   ├── BATTLE_REPORT_TIER2_qwen14b.md
│   └── BATTLE_REPORT_TIER3_qwen32b.md
└── archive/                     ← 🗄️ Historical docs
    ├── trinity-production-upgrade-master-plan.md
    ├── PHASE-2B-COMPLETION-MEMO.md
    ├── PHASE-3-COMPLETION-MEMO.md
    ├── PHASE-5.5A-CRITICAL-METRICS-MIGRATION.md
    └── gdubx-next-steps.md
```

---

*"Documentation is love letters to your future self."*
