# Battle 2: Simple Prompts

> **10 trivial prompts for throughput testing (The Crowd Pleaser)**

---

## Purpose

These prompts are intentionally SIMPLE. The goal is to test:
- Maximum requests per second
- Concurrent connection handling
- Response time under load
- NOT intelligence

---

## Prompts

```json
[
  {"id": 1, "prompt": "What is 2+2?", "expected": "4"},
  {"id": 2, "prompt": "What color is the sky?", "expected": "blue"},
  {"id": 3, "prompt": "Say the word 'hello'", "expected": "hello"},
  {"id": 4, "prompt": "Is water wet? Answer yes or no.", "expected": "yes"},
  {"id": 5, "prompt": "Name any fruit.", "expected": "any fruit name"},
  {"id": 6, "prompt": "What is 10 minus 3?", "expected": "7"},
  {"id": 7, "prompt": "How many legs does a dog have?", "expected": "4"},
  {"id": 8, "prompt": "What day comes after Monday?", "expected": "Tuesday"},
  {"id": 9, "prompt": "Is the sun hot? Answer yes or no.", "expected": "yes"},
  {"id": 10, "prompt": "Count from 1 to 5.", "expected": "1 2 3 4 5"}
]
```

---

## Curl Templates

```bash
# Prompt 1
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "What is 2+2?", "max_length": 50}'

# Prompt 2
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "What color is the sky?", "max_length": 50}'

# Prompt 3
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Say the word hello", "max_length": 50}'

# Prompt 4
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Is water wet? Answer yes or no.", "max_length": 50}'

# Prompt 5
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Name any fruit.", "max_length": 50}'

# Prompt 6
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "What is 10 minus 3?", "max_length": 50}'

# Prompt 7
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "How many legs does a dog have?", "max_length": 50}'

# Prompt 8
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "What day comes after Monday?", "max_length": 50}'

# Prompt 9
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Is the sun hot? Answer yes or no.", "max_length": 50}'

# Prompt 10
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Count from 1 to 5.", "max_length": 50}'
```

---

## Rotation Strategy

During load testing, rotate through prompts to avoid caching effects:

```
Request 1  → Prompt 1
Request 2  → Prompt 2
Request 3  → Prompt 3
...
Request 10 → Prompt 10
Request 11 → Prompt 1  (restart cycle)
...
```

---

## Success Criteria

A response is **successful** if:
1. HTTP status 200
2. Response contains `"response":` field
3. Latency < 60 seconds

A response is **failed** if:
1. HTTP status 503 (at capacity)
2. HTTP status 504 (timeout)
3. Connection refused/timeout
4. Malformed JSON response

---

## Metrics to Capture

For each ramp level:

| Metric | Description |
|--------|-------------|
| `total_requests` | Number of requests sent |
| `successful` | HTTP 200 with valid response |
| `failed` | Any error |
| `error_rate` | `failed / total_requests` |
| `p50_latency` | 50th percentile response time |
| `p95_latency` | 95th percentile response time |
| `p99_latency` | 99th percentile response time |
| `requests_per_second` | `successful / duration_seconds` |
