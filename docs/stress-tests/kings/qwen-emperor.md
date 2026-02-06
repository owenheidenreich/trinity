# 👑 Qwen Emperor

## Endpoint Configuration

| Field | Value |
|-------|-------|
| **Model** | qwen2.5:72b |
| **Provider ID** | king-qwen72b |
| **GPU** | A100-80GB |
| **Memory** | 96Gi |
| **Base URL** | `https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org` |
| **Health** | `/health` |
| **Generate** | `/generate` |
| **Metrics** | `/metrics` |

---

## API Reference

### Health Check
```bash
curl -s "https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org/health" | jq .
```

### Generate Request
```bash
curl -s -X POST "https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org/generate" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "YOUR PROMPT HERE", "max_length": 2000}' | jq .
```

### Metrics
```bash
curl -s "https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org/metrics"
```

---

## Battle 1: IQ Test Results

| # | Question | Answer | Grade | Latency |
|---|----------|--------|-------|---------|
| 1 | √144 | | | |
| 2 | Apples/Oranges | | | |
| 3 | Steel vs Feathers | | | |
| 4 | Bat & Ball | | | |
| 5 | Train Problem | | | |
| 6 | Three Liars | | | |
| 7 | Strawberry Letters | | | |
| 8 | Sally's Sisters | | | |
| 9 | Sheep Trick | | | |
| 10 | Gödel's Incompleteness | | | |
| 11 | Sum of Odd Numbers | | | |
| 12 | ∫e^(x²) | | | |
| 13 | N-Door Guards | | | |
| 14 | P vs NP | | | |
| 15 | Carmichael Code | | | |
| 16 | CAP Theorem | | | |
| 17 | Strong vs Eventual | | | |
| 18 | Monty Hall | | | |
| 19 | √2 Irrational | | | |
| 20 | Binary Search | | | |
| 21 | LRU Cache | | | |
| 22 | Quicksort Complexity | | | |
| 23 | Halting Problem | | | |
| 24 | Pigeonhole Proof | | | |
| 25 | 2^10 | | | |

**GPA:** _____/4.0
**Score:** _____/40 points

---

## Battle 2: Crowd Pleaser Results

| Ramp | Concurrent | Success | Errors | Error% | p50 (ms) | p95 (ms) | p99 (ms) |
|------|------------|---------|--------|--------|----------|----------|----------|
| 1 | 10 | | | | | | |
| 2 | 25 | | | | | | |
| 3 | 50 | | | | | | |
| 4 | 75 | | | | | | |
| 5 | 100 | | | | | | |
| 6 | 150 | | | | | | |
| 7 | 200 | | | | | | |

**Max Sustainable Concurrency:** _____
**Peak Requests/Second:** _____
**Breaking Point:** _____
**Score:** _____/30 points

---

## Battle 3: Strongest Man Results

| Metric | Value |
|--------|-------|
| Total Requests | 100 |
| Completed | |
| Timed Out | |
| Errors | |
| Completion Rate | % |
| Accuracy (sampled 10) | /10 |
| Accuracy Rate | % |
| Degradation vs B1 | % |
| Avg Latency | ms |

**Score:** _____/30 points

---

## Final Score

| Battle | Score | Max |
|--------|-------|-----|
| IQ Test | | 40 |
| Crowd Pleaser | | 30 |
| Strongest Man | | 30 |
| **TOTAL** | | **100** |

---

## Raw Response Log

*Paste raw responses here during tournament for audit*

### Battle 1 Responses

```
Q1: 
Q2:
...
```

### Battle 3 Sample Responses

```
Complex Q1:
Complex Q2:
...
```
