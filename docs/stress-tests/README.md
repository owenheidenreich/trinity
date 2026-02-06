# War of Three Kings — Stress Test Suite

> **The LLM is the God of this land. The three kings fight to serve the God with the greatest output, to prove their worth.**

## Tournament Overview

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                         WAR OF THREE KINGS                                   ║
║                      The Ultimate LLM Tournament                             ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║   👑 QWEN EMPEROR          🦙 LLAMA LORD           🔮 MIXTRAL MAVEN          ║
║   qwen2.5:72b              llama3.3:70b            mixtral:8x22b             ║
║   A100-80GB                A100-80GB               A100-80GB                 ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║   BATTLE 1: THE IQ TEST          — Who is the wisest?         (40 pts)      ║
║   BATTLE 2: THE CROWD PLEASER    — Who serves the masses?     (30 pts)      ║
║   BATTLE 3: THE STRONGEST MAN    — Who lifts the heaviest?    (30 pts)      ║
║                                                                              ║
║                         TOTAL: 100 POINTS                                    ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## Execution Tree

```
docs/stress-tests/
├── README.md                    # This file - Tournament overview
├── EXECUTION.md                 # Step-by-step execution guide
│
├── kings/                       # Per-king endpoints and tracking
│   ├── qwen-emperor.md          # 👑 Qwen 72B endpoint + results
│   ├── llama-lord.md            # 🦙 Llama 70B endpoint + results
│   └── mixtral-maven.md         # 🔮 Mixtral 8x22B endpoint + results
│
├── battles/                     # Battle specifications
│   ├── battle-1-iq-test.md      # Intelligence test (sequential)
│   ├── battle-2-crowd-pleaser.md # Throughput test (simple flood)
│   └── battle-3-strongest-man.md # Strength test (complex flood)
│
├── prompts/                     # Prompt sets for each battle
│   ├── iq-test-questions.md     # 25 graded questions
│   ├── simple-prompts.md        # 10 trivial prompts for Battle 2
│   └── complex-prompts.md       # 10 hard prompts for Battle 3
│
└── results/                     # Results (populated during tournament)
    ├── battle-1-results.md
    ├── battle-2-results.md
    ├── battle-3-results.md
    └── FINAL-RANKINGS.md
```

---

## King Endpoints

| King | Model | Endpoint | Status |
|------|-------|----------|--------|
| 👑 Qwen Emperor | qwen2.5:72b | `https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org` | ⏳ Loading |
| 🦙 Llama Lord | llama3.3:70b | `http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so` | ⏳ Loading |
| 🔮 Mixtral Maven | mixtral:8x22b | `https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com` | ⏳ Loading |

---

## Quick Health Check

```bash
# Run this to check if kings are ready
curl -s "https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org/health" | jq .
curl -s "http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so/health" | jq .
curl -s "https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com/health" | jq .
```

---

## Scoring System

| Battle | Max Points | Scoring Method |
|--------|------------|----------------|
| IQ Test | 40 | `(Correct/25) × 40` + bonuses |
| Crowd Pleaser | 30 | Normalized by best performer |
| Strongest Man | 30 | `(Completion × 0.4 + Accuracy × 0.6) × 25 + (1-Degradation) × 5` |

**Champion = Highest Total Score (max 100)**

---

## Start Here

1. **Check king status**: `docs/stress-tests/EXECUTION.md` → Phase 0
2. **Run IQ Test**: `docs/stress-tests/battles/battle-1-iq-test.md`
3. **Run Crowd Pleaser**: `docs/stress-tests/battles/battle-2-crowd-pleaser.md`
4. **Run Strongest Man**: `docs/stress-tests/battles/battle-3-strongest-man.md`
5. **View Results**: `docs/stress-tests/results/FINAL-RANKINGS.md`

---

*Created: February 6, 2026*
*Tournament Status: AWAITING KINGS*
