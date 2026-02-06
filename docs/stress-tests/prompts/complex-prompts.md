# Battle 3: Complex Prompts

> **10 hard prompts for strength testing (The Strongest Man)**

---

## Purpose

These prompts require:
- Extended reasoning
- Code generation
- Mathematical proofs
- Multi-step logic

The goal is to test quality under pressure — can the model maintain accuracy when handling many complex requests simultaneously?

---

## Prompts

```json
[
  {
    "id": 1,
    "prompt": "Write a Python function that checks if a number is prime. Include edge cases for 0, 1, 2, and negative numbers.",
    "grading": "Must have def, handle edge cases, correct logic"
  },
  {
    "id": 2,
    "prompt": "Prove by mathematical induction that the sum of the first n odd numbers equals n². Show base case and inductive step.",
    "grading": "Must show base case n=1, assume k, prove k+1"
  },
  {
    "id": 3,
    "prompt": "Explain the difference between strong consistency and eventual consistency in distributed systems. Give a real-world example of each.",
    "grading": "Must define both, give valid examples"
  },
  {
    "id": 4,
    "prompt": "Implement a recursive Fibonacci function with memoization in Python. Explain the time complexity improvement.",
    "grading": "Must have recursion, memoization, O(n) mention"
  },
  {
    "id": 5,
    "prompt": "What is the time complexity of quicksort in best, average, and worst cases? What causes the worst case and how can it be avoided?",
    "grading": "Must state O(n log n) and O(n²), explain pivot issue"
  },
  {
    "id": 6,
    "prompt": "Write a Python class implementing an LRU cache with O(1) get and put operations. Use a doubly linked list and hash map.",
    "grading": "Must have class, get/put methods, O(1) data structures"
  },
  {
    "id": 7,
    "prompt": "Explain the CAP theorem in distributed systems. Why can't a system have all three properties? Give examples of CP and AP systems.",
    "grading": "Must define C, A, P, explain tradeoff, give examples"
  },
  {
    "id": 8,
    "prompt": "Implement binary search in Python that returns the index of the FIRST occurrence of the target in a sorted array with duplicates.",
    "grading": "Must handle duplicates, return leftmost, correct bounds"
  },
  {
    "id": 9,
    "prompt": "Prove that the square root of 2 is irrational using proof by contradiction. Be rigorous.",
    "grading": "Must assume rational, derive both even, reach contradiction"
  },
  {
    "id": 10,
    "prompt": "Write a Python function to detect a cycle in a linked list using Floyd's tortoise and hare algorithm. Explain why it works.",
    "grading": "Must have slow/fast pointers, explain meeting condition"
  }
]
```

---

## Curl Templates

```bash
# Complex 1: Prime Check
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Write a Python function that checks if a number is prime. Include edge cases for 0, 1, 2, and negative numbers.", "max_length": 2000}'

# Complex 2: Induction Proof
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Prove by mathematical induction that the sum of the first n odd numbers equals n². Show base case and inductive step.", "max_length": 2000}'

# Complex 3: Consistency Types
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Explain the difference between strong consistency and eventual consistency in distributed systems. Give a real-world example of each.", "max_length": 2000}'

# Complex 4: Fibonacci Memo
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Implement a recursive Fibonacci function with memoization in Python. Explain the time complexity improvement.", "max_length": 2000}'

# Complex 5: Quicksort Complexity
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "What is the time complexity of quicksort in best, average, and worst cases? What causes the worst case and how can it be avoided?", "max_length": 2000}'

# Complex 6: LRU Cache
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Write a Python class implementing an LRU cache with O(1) get and put operations. Use a doubly linked list and hash map.", "max_length": 2000}'

# Complex 7: CAP Theorem
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Explain the CAP theorem in distributed systems. Why cannot a system have all three properties? Give examples of CP and AP systems.", "max_length": 2000}'

# Complex 8: Binary Search First Occurrence
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Implement binary search in Python that returns the index of the FIRST occurrence of the target in a sorted array with duplicates.", "max_length": 2000}'

# Complex 9: Root 2 Irrational
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Prove that the square root of 2 is irrational using proof by contradiction. Be rigorous.", "max_length": 2000}'

# Complex 10: Floyd Cycle Detection
curl -s -X POST "ENDPOINT/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Write a Python function to detect a cycle in a linked list using Floyd tortoise and hare algorithm. Explain why it works.", "max_length": 2000}'
```

---

## Grading Rubric

Each response is graded on a 10-point scale:

| Score | Criteria |
|-------|----------|
| 10 | Perfect. Complete, correct, well-explained |
| 8-9 | Excellent. Minor issues only |
| 6-7 | Good. Core concept correct, some gaps |
| 4-5 | Fair. Partially correct |
| 2-3 | Poor. Major errors or incomplete |
| 0-1 | Failed. Wrong or no meaningful response |

---

## Comparison Criteria

After Battle 3, compare accuracy to Battle 1:

**Degradation Formula:**
```
degradation = (battle1_accuracy - battle3_accuracy) / battle1_accuracy × 100%
```

**Interpretation:**
- 0-10% degradation: Excellent (handles pressure well)
- 10-25% degradation: Good (some quality loss under load)
- 25-50% degradation: Fair (significant quality loss)
- >50% degradation: Poor (breaks under pressure)

---

## Execution Parameters

| Parameter | Value |
|-----------|-------|
| Concurrent requests | 50 |
| Total requests per king | 100 |
| Timeout per request | 120 seconds |
| Max retries | 0 (no retries) |
| Prompt rotation | Cycle through 10 prompts |

---

## Metrics to Capture

| Metric | Description |
|--------|-------------|
| `total_sent` | Requests sent (should be 100) |
| `completed` | Responses received within timeout |
| `timed_out` | No response within 120s |
| `errors` | HTTP errors (503, 500, etc.) |
| `completion_rate` | `completed / total_sent` |
| `avg_latency` | Mean response time of completed |
| `accuracy_score` | Average grade of sampled responses |
| `degradation` | Compare to Battle 1 baseline |
