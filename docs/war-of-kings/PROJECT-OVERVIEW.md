# ⚔️ WAR OF THREE KINGS ⚔️
## The Ultimate AI Tournament - Project Overview

**Created:** February 6, 2026
**Commanded by:** The God of This Universe
**Status:** 🟡 AWAITING DIVINE COMMAND

---

## 🌍 What Is This?

The **War of Three Kings** is a comprehensive benchmark tournament to determine which large language model reigns supreme on Trinity's decentralized infrastructure. Three 70B+ parameter models are deployed simultaneously on Akash Network, battling across three distinct challenges.

### The Research Question
> "Which open-source LLM provides the best balance of intelligence, throughput, and resilience for Trinity's decentralized AI platform?"

---

## 👑 THE COMBATANTS

| Crown | Name | Model | Parameters | Architecture | Status |
|-------|------|-------|------------|--------------|--------|
| 👑 | **Qwen Emperor** | qwen2.5:72b | 72B | Dense Transformer | 🟡 Loading |
| 🦙 | **Llama Lord** | llama3.3:70b | 70B | Dense Transformer | 🟡 Loading |
| 🔮 | **Mixtral Maven** | mixtral:8x22b | 141B (22B active) | MoE (8 experts) | 🟡 Loading |

### Endpoints
```
QWEN:    https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org
LLAMA:   http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so
MIXTRAL: https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com
```

---

## ⚔️ THE THREE BATTLES

### Battle 1: THE IQ TEST (40 Points)
**Goal:** Measure raw intelligence and reasoning ability
- 25 questions across 5 difficulty tiers (Easy → God-tier)
- Questions test math, logic, coding, ethics, creativity
- Scoring: Tier weights × correctness
- **Winner:** Highest cumulative score

### Battle 2: THE CROWD PLEASER (30 Points)
**Goal:** Measure throughput under load
- Ramping concurrent requests: 5 → 10 → 25 → 50 users
- Simple prompts only (control for complexity)
- Metrics: Tokens/second, latency P50/P95, success rate
- **Winner:** Best performance at highest sustainable load

### Battle 3: THE STRONGEST MAN (30 Points)
**Goal:** Measure resilience under extreme pressure
- 50 concurrent complex requests simultaneously
- Chain-of-thought, multi-step, coding challenges
- Metrics: Completion rate, quality score, error rate
- **Winner:** Highest quality under maximum pressure

---

## 📊 SCORING SYSTEM

| Battle | Points | Weight |
|--------|--------|--------|
| IQ Test | 40 | 40% |
| Crowd Pleaser | 30 | 30% |
| Strongest Man | 30 | 30% |
| **TOTAL** | **100** | 100% |

### Ranking Points per Battle
- 🥇 1st Place: Full points
- 🥈 2nd Place: 60% of points
- 🥉 3rd Place: 30% of points

---

## 📁 DOCUMENTATION STRUCTURE

```
docs/war-of-kings/
├── PROJECT-OVERVIEW.md      # This file - master overview
├── README.md                # Tournament introduction
├── EXECUTION.md             # Step-by-step execution guide
├── kings/                   # Per-king documentation
│   ├── qwen-emperor.md      # Qwen results & config
│   ├── llama-lord.md        # Llama results & config
│   ├── mixtral-maven.md     # Mixtral results & config
│   └── *.yaml               # Deployment configs (6 kings)
├── battles/                 # Battle specifications
│   ├── battle-1-iq-test.md
│   ├── battle-2-crowd-pleaser.md
│   └── battle-3-strongest-man.md
├── prompts/                 # Test prompts
│   ├── iq-test-questions.md # 25 graded questions
│   ├── simple-prompts.md    # 10 simple prompts
│   └── complex-prompts.md   # 10 complex prompts
├── research/                # Background research
│   ├── cost-analysis-research.md
│   ├── battle-of-qwen.md
│   ├── BATTLE_REPORT_TIER2_qwen14b.md
│   └── BATTLE_REPORT_TIER3_qwen32b.md
└── results/                 # Tournament results
    └── FINAL-RANKINGS.md    # Final scoreboard
```

---

## 💰 INFRASTRUCTURE COSTS

All three kings run on **A100-80GB GPUs** via Akash Network:

| Component | Per King | Total (3 Kings) |
|-----------|----------|-----------------|
| GPU | A100-80GB | 3× A100-80GB |
| RAM | 96Gi | 288Gi |
| Estimated Cost | ~$1.50-2.50/hr | ~$5-7.50/hr |

**Tournament Duration:** ~2-4 hours
**Estimated Total Cost:** ~$15-30

---

## 🚀 EXECUTION PHASES

### Phase 0: Pre-Flight (15 min)
- [ ] Health check all endpoints
- [ ] Warmup each model with simple prompt
- [ ] Verify curl commands work
- [ ] Start recording/logging

### Phase 1: IQ Test (45-60 min)
- [ ] Run 25 questions against each king
- [ ] Record responses and timing
- [ ] Grade each response (auto + manual)
- [ ] Calculate IQ battle scores

### Phase 2: Crowd Pleaser (30-45 min)
- [ ] Run throughput tests at 5/10/25/50 concurrency
- [ ] Measure tokens/sec, latency, success rate
- [ ] Record peak sustainable throughput
- [ ] Calculate throughput battle scores

### Phase 3: Strongest Man (30-45 min)
- [ ] Fire 50 concurrent complex requests
- [ ] Measure completion rate & quality
- [ ] Stress test until failure point
- [ ] Calculate strength battle scores

### Phase 4: Coronation (15 min)
- [ ] Compile all scores
- [ ] Determine final rankings
- [ ] Crown the Ultimate King
- [ ] Update FINAL-RANKINGS.md

---

## 📋 PRE-EXECUTION CHECKLIST

### Documentation Ready
- [x] PROJECT-OVERVIEW.md created
- [x] README.md with tournament intro
- [x] EXECUTION.md with step-by-step guide
- [x] All king markdown files ready
- [x] All battle spec files ready
- [x] All prompt files with curl commands
- [x] FINAL-RANKINGS.md template ready

### Infrastructure Ready
- [x] All 3 kings deployed on Akash
- [x] A100-80GB GPUs allocated
- [x] Endpoints accessible via HTTPS/HTTP
- [ ] Models fully downloaded and loaded
- [ ] Health endpoints returning 200

### Execution Environment Ready
- [x] Terminal sessions available
- [x] curl installed and working
- [x] Network connectivity verified
- [ ] Results recording system ready

---

## 🔥 STATUS DASHBOARD

```
┌─────────────────────────────────────────────────────────────────┐
│                    WAR OF THREE KINGS                           │
│                     STATUS: PREPARING                           │
├─────────────────────────────────────────────────────────────────┤
│ QWEN EMPEROR    │ ████████████░░░░░░░░ │ LOADING (72GB)        │
│ LLAMA LORD      │ ████████████░░░░░░░░ │ LOADING (70GB)        │
│ MIXTRAL MAVEN   │ ████████████░░░░░░░░ │ LOADING (80GB)        │
├─────────────────────────────────────────────────────────────────┤
│ Documentation   │ ████████████████████ │ READY                 │
│ Curl Commands   │ ████████████████████ │ READY                 │
│ Scoring System  │ ████████████████████ │ READY                 │
├─────────────────────────────────────────────────────────────────┤
│ AWAITING:       │ Divine Command to Begin                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 QUICK REFERENCE COMMANDS

### Health Check All Kings
```bash
# Qwen Emperor
curl -s "https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org/health"

# Llama Lord  
curl -s "http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so/health"

# Mixtral Maven
curl -s "https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com/health"
```

### Warmup Test (Simple)
```bash
curl -X POST "ENDPOINT/generate" \
  -H "Content-Type: application/json" \
  -d '{"model": "MODEL_NAME", "prompt": "Say hello!", "stream": false}'
```

### IQ Test (Example)
```bash
curl -X POST "ENDPOINT/generate" \
  -H "Content-Type: application/json" \
  -d '{"model": "MODEL_NAME", "prompt": "What is 15% of 240?", "stream": false}'
```

---

## 🏆 VICTORY CONDITIONS

The king with the **highest total score** across all three battles wins the crown and becomes Trinity's default model.

**In case of tie:** The king with the higher IQ Test score wins (intelligence prioritized).

---

## 📜 FINAL NOTES

This tournament represents Trinity's commitment to **empirical, data-driven decision making**. Rather than choosing a model based on benchmarks or marketing, we let the models prove themselves in our actual deployment environment.

May the best king reign.

---

*Document generated: February 6, 2026*
*Tournament Director: Claude (GitHub Copilot)*
*Authority: The God of This Universe*
