# Battle 3: The Strongest Man

> **"Who can lift the heaviest?"**

---

## Overview

| Attribute | Value |
|-----------|-------|
| **Type** | Strength Under Pressure |
| **Execution** | Concurrent (50 at once) |
| **Prompts** | Complex (code, proofs, reasoning) |
| **Max Points** | 30 |
| **Goal** | Quality maintenance under load |

---

## Objective

Test if the king can maintain quality when overwhelmed with hard problems. We send 100 complex requests at high concurrency and measure:
- Completion rate (did it finish?)
- Accuracy (is the answer correct?)
- Degradation (how much worse vs Battle 1?)

---

## Configuration

| Parameter | Value |
|-----------|-------|
| Concurrency | 50 simultaneous |
| Total Requests | 100 per king |
| Timeout | 120 seconds |
| Prompts | 10 complex (rotated) |
| Retries | 0 (no retries) |

---

## Execution Steps

### For Each King

1. **Set endpoint:**
   ```bash
   export KING="ENDPOINT_HERE"
   ```

2. **Fire first batch of 50 concurrent:**
   ```bash
   # Fire 50 complex requests simultaneously
   for i in {1..50}; do
     PROMPT_IDX=$((($i - 1) % 10 + 1))
     curl -s -X POST "$KING/generate" \
       -H "Content-Type: application/json" \
       -d "{\"prompt\": \"$(cat /tmp/complex_$PROMPT_IDX.txt)\", \"max_length\": 2000}" \
       -w "\nRequest $i: %{http_code} %{time_total}s" \
       -o /tmp/battle3_response_$i.json &
   done
   wait
   ```

3. **Fire second batch of 50 concurrent:**
   ```bash
   for i in {51..100}; do
     PROMPT_IDX=$((($i - 1) % 10 + 1))
     curl -s -X POST "$KING/generate" \
       -H "Content-Type: application/json" \
       -d "{\"prompt\": \"$(cat /tmp/complex_$PROMPT_IDX.txt)\", \"max_length\": 2000}" \
       -w "\nRequest $i: %{http_code} %{time_total}s" \
       -o /tmp/battle3_response_$i.json &
   done
   wait
   ```

4. **Count results:**
   ```bash
   COMPLETED=0
   FAILED=0
   for i in {1..100}; do
     if grep -q '"response"' /tmp/battle3_response_$i.json 2>/dev/null; then
       ((COMPLETED++))
     else
       ((FAILED++))
     fi
   done
   echo "Completed: $COMPLETED / 100"
   echo "Failed: $FAILED / 100"
   ```

5. **Sample 10 for accuracy grading:**
   ```bash
   # Pick 10 random responses to grade
   shuf -i 1-100 -n 10 | while read i; do
     echo "=== Response $i ==="
     jq -r '.response' /tmp/battle3_response_$i.json | head -50
     echo ""
   done
   ```

6. **Grade samples against rubric (manual or LLM-judge)**

---

## Complex Prompts Setup

Create prompt files before running:

```bash
# Complex 1: Prime Check
cat > /tmp/complex_1.txt << 'EOF'
Write a Python function that checks if a number is prime. Include edge cases for 0, 1, 2, and negative numbers.
EOF

# Complex 2: Induction Proof
cat > /tmp/complex_2.txt << 'EOF'
Prove by mathematical induction that the sum of the first n odd numbers equals n squared. Show base case and inductive step.
EOF

# Complex 3: Consistency
cat > /tmp/complex_3.txt << 'EOF'
Explain the difference between strong consistency and eventual consistency in distributed systems. Give a real-world example of each.
EOF

# Complex 4: Fibonacci
cat > /tmp/complex_4.txt << 'EOF'
Implement a recursive Fibonacci function with memoization in Python. Explain the time complexity improvement.
EOF

# Complex 5: Quicksort
cat > /tmp/complex_5.txt << 'EOF'
What is the time complexity of quicksort in best, average, and worst cases? What causes the worst case and how can it be avoided?
EOF

# Complex 6: LRU Cache
cat > /tmp/complex_6.txt << 'EOF'
Write a Python class implementing an LRU cache with O(1) get and put operations. Use a doubly linked list and hash map.
EOF

# Complex 7: CAP Theorem
cat > /tmp/complex_7.txt << 'EOF'
Explain the CAP theorem in distributed systems. Why can a system not have all three properties? Give examples of CP and AP systems.
EOF

# Complex 8: Binary Search
cat > /tmp/complex_8.txt << 'EOF'
Implement binary search in Python that returns the index of the FIRST occurrence of the target in a sorted array with duplicates.
EOF

# Complex 9: Root 2 Proof
cat > /tmp/complex_9.txt << 'EOF'
Prove that the square root of 2 is irrational using proof by contradiction. Be rigorous.
EOF

# Complex 10: Floyd Cycle
cat > /tmp/complex_10.txt << 'EOF'
Write a Python function to detect a cycle in a linked list using Floyd tortoise and hare algorithm. Explain why it works.
EOF
```

---

## Grading Rubric

Grade each sampled response 1-10:

| Score | Criteria |
|-------|----------|
| 10 | Perfect, complete, correct |
| 8-9 | Excellent, minor issues |
| 6-7 | Good, core correct |
| 4-5 | Fair, partial credit |
| 2-3 | Poor, major errors |
| 0-1 | Failed, wrong/gibberish |

---

## Scoring

### Calculate Score

```
completion_rate = completed / 100
accuracy_rate = sum(sample_grades) / (10 × 10)  # Max 100 points from 10 samples

# Compare to Battle 1 baseline
battle1_accuracy = king_gpa / 4.0  # From Battle 1
degradation = max(0, (battle1_accuracy - accuracy_rate) / battle1_accuracy)

# Final score
battle3_score = (completion_rate × 0.4 + accuracy_rate × 0.6) × 25
              + (1 - degradation) × 5

Max Score: 30
```

### Example

If king has:
- Completed: 85/100 (85%)
- Accuracy: 7.2/10 average (72%)
- Battle 1 GPA: 3.2/4.0 (80%)
- Degradation: (80% - 72%) / 80% = 10%

Then:
```
score = (0.85 × 0.4 + 0.72 × 0.6) × 25 + (1 - 0.10) × 5
      = (0.34 + 0.432) × 25 + 0.90 × 5
      = 0.772 × 25 + 4.5
      = 19.3 + 4.5
      = 23.8 points
```

---

## Metrics to Record

| Metric | Value |
|--------|-------|
| Total Sent | 100 |
| Completed | |
| Timed Out | |
| Errors (503, etc.) | |
| Completion Rate | % |
| Sampled Accuracy | /10 |
| Accuracy Rate | % |
| Battle 1 Baseline | % |
| Degradation | % |
| **Score** | /30 |

---

## Results Template

| King | Completed | Accuracy | Degradation | Score |
|------|-----------|----------|-------------|-------|
| 👑 Qwen | /100 | /10 | % | /30 |
| 🦙 Llama | /100 | /10 | % | /30 |
| 🔮 Mixtral | /100 | /10 | % | /30 |

---

## Notes

- **Degradation Matters:** A king that scores A+ in Battle 1 but drops to C under load loses points.
- **Completion ≠ Quality:** Finishing fast with wrong answers is worse than taking time with correct ones.
- **Sample Size:** 10 samples provides ~95% confidence interval of ±15%. Good enough for comparison.
- **Timeout:** 120s is generous. If a complex request can't complete in 2 minutes under load, it's a failure.
