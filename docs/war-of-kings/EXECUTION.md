# Tournament Execution Guide

> **Follow this document step-by-step. Do not skip phases.**

---

## Phase 0: The Awakening

### Step 0.1 — Health Check All Kings

Execute these curl commands and wait for JSON responses (not 502):

```bash
# 👑 QWEN EMPEROR
curl -s --max-time 30 "https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org/health"

# 🦙 LLAMA LORD  
curl -s --max-time 30 "http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so/health"

# 🔮 MIXTRAL MAVEN
curl -s --max-time 30 "https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com/health"
```

**Expected Response:**
```json
{"status": "healthy", "model": "qwen2.5:72b", "provider_id": "king-qwen72b", ...}
```

**If 502:** Wait 5 minutes, retry. Models are still downloading (~40-80GB).

### Step 0.2 — Warmup Queries

Send ONE simple query to each king to load model into VRAM:

```bash
# 👑 QWEN EMPEROR
curl -s -X POST "https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org/generate" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Say hello", "max_length": 50}' | jq .

# 🦙 LLAMA LORD
curl -s -X POST "http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so/generate" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Say hello", "max_length": 50}' | jq .

# 🔮 MIXTRAL MAVEN
curl -s -X POST "https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com/generate" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Say hello", "max_length": 50}' | jq .
```

### Step 0.3 — Record Baseline Metrics

```bash
# Scrape metrics from each king
curl -s "https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org/metrics" > /tmp/qwen_baseline.txt
curl -s "http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so/metrics" > /tmp/llama_baseline.txt
curl -s "https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com/metrics" > /tmp/mixtral_baseline.txt
```

**✅ Phase 0 Complete when:** All 3 kings return healthy + respond to warmup

---

## Phase 1: Battle 1 — The IQ Test

### Execution Method

Run each question from `prompts/iq-test-questions.md` **sequentially** against each king.

**For each question:**

```bash
# Template - replace ENDPOINT and PROMPT
curl -s -X POST "ENDPOINT/generate" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "PROMPT", "max_length": 2000}' | jq '.response'
```

### Order of Operations

1. Run ALL 25 questions against 👑 Qwen Emperor
2. Record responses in `kings/qwen-emperor.md`
3. Run ALL 25 questions against 🦙 Llama Lord
4. Record responses in `kings/llama-lord.md`
5. Run ALL 25 questions against 🔮 Mixtral Maven
6. Record responses in `kings/mixtral-maven.md`
7. Grade all responses using rules in `battles/battle-1-iq-test.md`
8. Calculate GPA for each king
9. Record in `results/battle-1-results.md`

**✅ Phase 1 Complete when:** All kings graded, GPAs calculated

---

## Phase 2: Battle 2 — The Crowd Pleaser

### Execution Method

Send MANY simple requests **concurrently** and measure throughput.

### Ramp Schedule

| Ramp | Concurrent Users | Duration | Total Requests |
|------|------------------|----------|----------------|
| 1 | 10 | 60 sec | ~60 |
| 2 | 25 | 60 sec | ~150 |
| 3 | 50 | 60 sec | ~300 |
| 4 | 75 | 60 sec | ~450 |
| 5 | 100 | 60 sec | ~600 |
| 6 | 150 | 60 sec | ~900 |
| 7 | 200 | 60 sec | ~1200 |

**Stop ramp when:** Error rate > 10% OR p99 latency > 60 seconds

### For Each King

1. Start at Ramp 1 (10 concurrent)
2. Use prompts from `prompts/simple-prompts.md` (rotate through)
3. Record: success count, error count, latencies
4. If < 10% errors, proceed to next ramp
5. Continue until breaking point found
6. Record max sustainable concurrency
7. Scrape `/metrics` after each ramp

### Metrics to Capture

- Peak requests/second achieved
- Max concurrent users before breakdown
- p50, p95, p99 latency at each ramp
- Error types (503 capacity, timeout, other)

**✅ Phase 2 Complete when:** Breaking point found for all 3 kings

---

## Phase 3: Battle 3 — The Strongest Man

### Execution Method

Send COMPLEX requests at HIGH concurrency. Measure quality under pressure.

### Configuration

- **Concurrency:** 50 simultaneous requests
- **Total Requests:** 100 per king
- **Prompts:** From `prompts/complex-prompts.md` (rotate through)
- **Timeout:** 120 seconds per request

### For Each King

1. Fire 50 concurrent complex requests
2. Wait for all to complete (or timeout)
3. Fire next 50 concurrent complex requests
4. Record: completion count, timeout count, error count
5. Sample 10 random responses for accuracy grading
6. Compare accuracy to Battle 1 performance (degradation check)
7. Scrape `/metrics` after completion

### Metrics to Capture

- Completion rate (responses received / requests sent)
- Accuracy rate (correct / completed)
- Degradation % vs Battle 1 baseline
- Average latency under load
- Memory/CPU from metrics

**✅ Phase 3 Complete when:** All kings tested, accuracy sampled

---

## Phase 4: The Coronation

### Scoring Calculation

**Battle 1 Score (max 40):**
```
score = (correct_answers / 25) × 40
if zero_f_grades: score += 2
if any_timeout: score -= 1 per timeout
```

**Battle 2 Score (max 30):**
```
best_concurrency = max(qwen_max, llama_max, mixtral_max)
score = (king_max_concurrency / best_concurrency) × 25
score += (king_peak_rps / best_peak_rps) × 5
if error_rate < 1% at breaking point: score += 2
```

**Battle 3 Score (max 30):**
```
score = (completion_rate × 0.4 + accuracy_rate × 0.6) × 25
degradation = (battle1_accuracy - battle3_accuracy) / battle1_accuracy
score += (1 - degradation) × 5
```

### Final Ranking

```
TOTAL = Battle1 + Battle2 + Battle3
MAX POSSIBLE = 100 points
```

**Crown the king with highest total.**

**✅ Tournament Complete when:** `results/FINAL-RANKINGS.md` populated

---

## Quick Reference: Endpoints

```bash
# Save these as environment variables for convenience
export QWEN="https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org"
export LLAMA="http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so"
export MIXTRAL="https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com"

# Health check
curl -s "$QWEN/health" | jq .status
curl -s "$LLAMA/health" | jq .status  
curl -s "$MIXTRAL/health" | jq .status

# Generate
curl -s -X POST "$QWEN/generate" -H "Content-Type: application/json" -d '{"prompt": "test"}' | jq .
```

---

## Timeline

| Phase | Duration | Cumulative |
|-------|----------|------------|
| Phase 0: Awakening | ~30 min | 0:30 |
| Phase 1: IQ Test | ~2 hrs | 2:30 |
| Phase 2: Crowd Pleaser | ~3 hrs | 5:30 |
| Phase 3: Strongest Man | ~2.5 hrs | 8:00 |
| Phase 4: Coronation | ~2 hrs | 10:00 |

**Total Tournament Time: ~10 hours**
