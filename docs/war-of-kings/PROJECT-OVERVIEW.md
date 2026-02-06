# ⚔️ WAR OF THREE KINGS ⚔️
## Engineering-Grade AI Benchmark Tournament

**Version:** 2.0 (Reengineered)  
**Created:** February 6, 2026  
**Status:** 🟡 AWAITING KINGS

---

## 🎯 Mission

Determine which open-source 70B+ LLM provides the best balance of **accuracy**, **speed**, and **reliability** for Trinity's decentralized AI platform.

---

## 👑 THE COMBATANTS

| Crown | Name | Model | Size | Status |
|-------|------|-------|------|--------|
| 👑 | **Qwen Emperor** | qwen2.5:72b | 47GB | 🔴 Pull Failed |
| 🦙 | **Llama Lord** | llama3.3:70b | 40GB | 🟡 Loading |
| 🔮 | **Mixtral Maven** | mixtral:8x22b | 80GB | 🟡 Loading |

### Endpoints
```bash
QWEN="https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org"
LLAMA="http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so"
MIXTRAL="https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com"
```

---

## 📋 TEST OPTIONS

### Option A: Quick Battle (RECOMMENDED)
**Duration:** ~30 minutes  
**Cost:** ~$5-10  
**Data Points:** ~150 per king  

```bash
cd docs/war-of-kings/execute
./quick-battle.sh
```

| Phase | Duration | What It Tests |
|-------|----------|---------------|
| 1. Health Check | 2 min | Verify kings are online, warm up |
| 2. IQ Battle | 10 min | 25 scored questions (math, logic, coding) |
| 3. Speed Trial | 8 min | Throughput: requests/second |
| 4. Reasoning Gauntlet | 10 min | 10 hard problems (code, math, reasoning) |

### Option B: Overnight Endurance
**Duration:** 5 hours  
**Cost:** ~$75-150  
**Data Points:** ~1,100 per king  

```bash
cd docs/war-of-kings/execute
nohup ./overnight-stress.sh > overnight.log 2>&1 &
```

---

## 📊 WHAT WE MEASURE

| Metric | Phase | Why It Matters |
|--------|-------|----------------|
| **IQ Score** | IQ Battle | Raw intelligence - can it answer correctly? |
| **Avg Latency** | Speed Trial | User experience - how fast? |
| **Throughput** | Speed Trial | Scalability - requests per second? |
| **Gauntlet Completion** | Reasoning | Reliability - does it finish hard problems? |
| **Token Efficiency** | All phases | Cost - tokens per response? |

---

## 📁 OUTPUT STRUCTURE

```
results/battles/battle_YYYYMMDD_HHMMSS/
├── BATTLE_REPORT.md          # Final summary (human readable)
├── health/                   # Warm-up results
│   └── {king}_warmup.json
├── iq/                       # IQ test results
│   ├── {king}/q{0-24}.json   # Individual question results
│   └── {king}_summary.json   # Score summary
├── speed/                    # Throughput results
│   ├── {king}/req{1-20}.json # Individual requests
│   └── {king}_summary.json   # Latency stats
├── gauntlet/                 # Hard problems
│   ├── {king}/problem{0-9}.json
│   └── {king}_summary.json
└── summary/                  # Aggregated data
```

---

## ✅ EXECUTION CHECKLIST

### Before Running
- [ ] At least 1 king responds to health check
- [ ] Run `curl -s "$URL/api/tags"` - should return JSON, not 502
- [ ] Sufficient Akash credits (~$10 for quick battle)

### Quick Health Check
```bash
# Test each king
curl -s --max-time 30 "https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com/api/tags"
```

### Launch
```bash
cd /Users/gduby/Documents/Trinity/Trinity/docs/war-of-kings/execute
./quick-battle.sh
```

### After Running
- [ ] Check `BATTLE_REPORT.md` for summary
- [ ] Review gauntlet responses for quality
- [ ] Compare IQ scores across kings

---

## 🧮 SCORING FORMULA

### IQ Battle (25 questions)
- Each correct answer: +1 point
- Categories: Math (5), Logic (5), Knowledge (5), Coding (5), Reasoning (5)
- **Score:** X/25

### Speed Trial
- 20 rapid requests, minimal prompts
- **Metrics:** avg/min/max latency, requests/second

### Reasoning Gauntlet
- 10 complex problems (2 min timeout each)
- **Metrics:** completion rate, token usage, response quality

---

## 🔧 SCRIPTS

| Script | Purpose | Duration |
|--------|---------|----------|
| `quick-battle.sh` | Full 4-phase benchmark | ~30 min |
| `overnight-stress.sh` | Endurance test | ~5 hours |
| `run-war.sh` | Legacy commander | varies |

---

## 📈 ANALYSIS

### Quick Stats (after battle)
```bash
# View report
cat results/battles/battle_*/BATTLE_REPORT.md

# IQ Scores
cat results/battles/battle_*/iq/*_summary.json | jq

# Speed comparison
cat results/battles/battle_*/speed/*_summary.json | jq
```

### Feed to Claude for Analysis
```
1. Zip the results folder
2. Upload to Claude with prompts/claude-judge-prompt.md
3. Get detailed analysis and winner determination
```

---

## 🎯 DECISION FRAMEWORK

After benchmark, choose based on priority:

| If You Need | Choose |
|-------------|--------|
| Highest accuracy | Highest IQ score |
| Fastest responses | Lowest latency |
| Most throughput | Highest req/s |
| Best overall | Weighted score across all |

---

## 📝 NOTES

- Kings may be offline when Akash lease expires (~24hr default)
- First request after cold start is slow (model loading into GPU)
- 502 errors during test = king crashed, may need redeployment
- All results saved even on failure for debugging
