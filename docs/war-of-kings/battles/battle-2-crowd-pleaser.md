# Battle 2: The Crowd Pleaser

> **"Who can serve the masses?"**

---

## Overview

| Attribute | Value |
|-----------|-------|
| **Type** | Throughput Test |
| **Execution** | Concurrent (many at once) |
| **Prompts** | Simple (trivial questions) |
| **Max Points** | 30 |
| **Goal** | Maximum requests per second |

---

## Objective

Test raw throughput capacity. Flood each king with simple requests and measure:
- Maximum sustainable concurrent connections
- Peak requests per second
- Breaking point (where errors exceed 10%)

---

## Execution Steps

### Ramp Schedule

| Ramp | Concurrent | Duration | Expected Requests |
|------|------------|----------|-------------------|
| 1 | 10 | 60 sec | ~60-100 |
| 2 | 25 | 60 sec | ~150-250 |
| 3 | 50 | 60 sec | ~300-500 |
| 4 | 75 | 60 sec | ~450-750 |
| 5 | 100 | 60 sec | ~600-1000 |
| 6 | 150 | 60 sec | ~900-1500 |
| 7 | 200 | 60 sec | ~1200-2000 |

**Stop Criteria:** Error rate > 10% OR p99 latency > 60 seconds

---

## Simple Load Test (Manual Method)

For each king, you can run parallel curls using `xargs` or background jobs:

### Method 1: Sequential Baseline (1 user)

```bash
export KING="ENDPOINT_HERE"

# Run 10 sequential requests, measure total time
time for i in {1..10}; do
  curl -s -X POST "$KING/generate" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "What is 2+2?", "max_length": 50}' > /dev/null
done
```

### Method 2: Parallel with Background Jobs

```bash
export KING="ENDPOINT_HERE"

# Fire 10 requests in parallel
for i in {1..10}; do
  curl -s -X POST "$KING/generate" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "What is 2+2?", "max_length": 50}' > /tmp/result_$i.txt &
done
wait  # Wait for all to complete

# Check results
for i in {1..10}; do
  if grep -q "response" /tmp/result_$i.txt; then
    echo "Request $i: SUCCESS"
  else
    echo "Request $i: FAILED"
  fi
done
```

### Method 3: xargs Parallel

```bash
export KING="ENDPOINT_HERE"

# Create prompt file
echo '{"prompt": "What is 2+2?", "max_length": 50}' > /tmp/prompt.json

# Fire N parallel requests (adjust -P for concurrency)
seq 1 50 | xargs -P 10 -I {} \
  curl -s -X POST "$KING/generate" \
    -H "Content-Type: application/json" \
    -d @/tmp/prompt.json \
    -w "Request {}: %{http_code} in %{time_total}s\n" \
    -o /dev/null
```

---

## Prompts to Rotate

Use these 10 simple prompts (from `prompts/simple-prompts.md`):

```bash
PROMPTS=(
  "What is 2+2?"
  "What color is the sky?"
  "Say the word hello"
  "Is water wet? Answer yes or no."
  "Name any fruit."
  "What is 10 minus 3?"
  "How many legs does a dog have?"
  "What day comes after Monday?"
  "Is the sun hot? Answer yes or no."
  "Count from 1 to 5."
)
```

---

## Metrics to Record

After each ramp, record in king's tracking file:

| Metric | How to Measure |
|--------|----------------|
| Total Sent | Count of requests fired |
| Successful | HTTP 200 count |
| Failed | Non-200 count |
| Error Rate | Failed / Total Sent |
| p50 Latency | Sort latencies, take middle |
| p95 Latency | Sort latencies, take 95th percentile |
| p99 Latency | Sort latencies, take 99th percentile |
| Requests/sec | Successful / Duration |

---

## Scrape Server Metrics

After each ramp, capture server-side metrics:

```bash
curl -s "$KING/metrics" | grep -E "trinity_(http_requests|inference|tokens)"
```

Key metrics to watch:
- `trinity_http_requests_in_progress` — Current queue depth
- `trinity_inference_duration_seconds` — Server-side latency
- `trinity_system_memory_percent` — Memory usage

---

## Scoring

### Calculate Score

```
best_max_concurrency = max(qwen_max, llama_max, mixtral_max)
best_peak_rps = max(qwen_rps, llama_rps, mixtral_rps)

king_score = (king_max_concurrency / best_max_concurrency) × 25
           + (king_peak_rps / best_peak_rps) × 5

# Bonus
if king_error_rate_at_breaking_point < 1%:
    king_score += 2

Max Score: 30 + 2 = 32 (capped at 30)
```

### Example

If results are:
- Qwen: max 150 concurrent, 12 req/sec
- Llama: max 100 concurrent, 10 req/sec
- Mixtral: max 75 concurrent, 8 req/sec

Then:
```
Qwen Score = (150/150) × 25 + (12/12) × 5 = 30
Llama Score = (100/150) × 25 + (10/12) × 5 = 16.67 + 4.17 = 20.84
Mixtral Score = (75/150) × 25 + (8/12) × 5 = 12.5 + 3.33 = 15.83
```

---

## Results Template

| King | Max Concurrent | Peak RPS | Breaking Point | Error% at Break | Score |
|------|----------------|----------|----------------|-----------------|-------|
| 👑 Qwen | | | | | /30 |
| 🦙 Llama | | | | | /30 |
| 🔮 Mixtral | | | | | /30 |

---

## Notes

- **Rate Limiting:** Kings may have 30 req/min per IP. If hit, this is part of the test — real deployments have limits.
- **503 At Capacity:** The server returns 503 when queue is full. This counts as a failure.
- **Timeouts:** Any request taking >60s counts as failed for this battle.
- **Warm Cache:** Run a few warmup requests before starting ramps to ensure model is loaded.
