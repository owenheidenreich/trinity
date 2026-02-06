# Battle 1: The IQ Test

> **"Who is the wisest?"**

---

## Overview

| Attribute | Value |
|-----------|-------|
| **Type** | Intelligence Test |
| **Execution** | Sequential (one at a time) |
| **Questions** | 25 |
| **Max Points** | 40 |
| **Time Pressure** | None (unlimited timeout) |

---

## Objective

Test pure reasoning ability without time pressure. Each king gets the same 25 questions, answered one at a time with no concurrent load. This establishes the **baseline intelligence** for each model.

---

## Execution Steps

### For Each King

1. **Set endpoint variable:**
   ```bash
   # Choose one:
   export KING="https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org"  # Qwen
   export KING="http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so"  # Llama
   export KING="https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com"  # Mixtral
   ```

2. **Run each question from `prompts/iq-test-questions.md`:**
   ```bash
   # Template
   time curl -s -X POST "$KING/generate" \
     -H "Content-Type: application/json" \
     -d '{"prompt": "QUESTION_HERE", "max_length": 2000}' | jq -r '.response'
   ```

3. **Record response and latency in king's tracking file**

4. **Grade response using rules from prompts file**

5. **Calculate GPA after all 25 questions**

---

## Quick Reference: All 25 Questions

```bash
# Q1: √144
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "What is the square root of 144? Answer with just the number.", "max_length": 100}' | jq -r '.response'

# Q2: 15% of 80
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "What is 15% of 80? Answer with just the number.", "max_length": 100}' | jq -r '.response'

# Q3: 2^10
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "What is 2 to the power of 10? Answer with just the number.", "max_length": 100}' | jq -r '.response'

# Q4: Apples/Oranges
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "I have 3 apples. I give away 2 oranges. How many apples do I have?", "max_length": 200}' | jq -r '.response'

# Q5: Steel vs Feathers
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Which weighs more: a pound of steel or a pound of feathers?", "max_length": 200}' | jq -r '.response'

# Q6: Bat and Ball
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "A bat and a ball cost $1.10 together. The bat costs $1.00 more than the ball. How much does the ball cost? Show your work.", "max_length": 500}' | jq -r '.response'

# Q7: Sally Sisters
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Sally has 3 brothers. Each brother has 2 sisters. How many sisters does Sally have?", "max_length": 300}' | jq -r '.response'

# Q8: Strawberry Letters
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "How many times does the letter r appear in the word strawberry? Count carefully.", "max_length": 300}' | jq -r '.response'

# Q9: Sheep Trick
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "A farmer has 17 sheep. All but 9 run away. How many sheep does the farmer have left?", "max_length": 200}' | jq -r '.response'

# Q10: Train Problem
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Two trains are 100 miles apart, heading toward each other. Train A travels 40 mph, Train B travels 60 mph. How long until they meet? Answer in hours.", "max_length": 400}' | jq -r '.response'

# Q11: Three Liars
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "You meet three people: A, B, and C. A says I always lie. B says A is telling the truth. C says B always lies. Who is definitely a liar?", "max_length": 500}' | jq -r '.response'

# Q12: Truth-Teller Island
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "On an island, knights always tell truth, knaves always lie. You meet someone who says I am a knave. What are they?", "max_length": 400}' | jq -r '.response'

# Q13: Monty Hall
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "In the Monty Hall problem, you pick door 1. The host opens door 3 revealing a goat. Should you switch to door 2? Explain with probability.", "max_length": 800}' | jq -r '.response'

# Q14: Sum of Odd Numbers
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Prove that the sum of the first n odd numbers equals n squared. Use mathematical induction.", "max_length": 1500}' | jq -r '.response'

# Q15: Root 2 Irrational
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Prove that the square root of 2 is irrational using proof by contradiction.", "max_length": 1500}' | jq -r '.response'

# Q16: Pigeonhole
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Using the pigeonhole principle, prove that in any group of 13 people, at least 2 share a birthday month.", "max_length": 800}' | jq -r '.response'

# Q17: Carmichael
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Write a Python function that determines if a given number is a Carmichael number. Include the mathematical definition.", "max_length": 2000}' | jq -r '.response'

# Q18: Binary Search
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Write a Python function for binary search that returns the index of the FIRST occurrence of the target. Handle duplicates.", "max_length": 1500}' | jq -r '.response'

# Q19: LRU Cache
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Write a Python class implementing an LRU cache with O(1) get and put operations. Use OrderedDict or your own implementation.", "max_length": 2000}' | jq -r '.response'

# Q20: Quicksort Complexity
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "What is the time complexity of quicksort in best, average, and worst cases? Explain why the worst case occurs.", "max_length": 1000}' | jq -r '.response'

# Q21: Godel
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Explain Godels First Incompleteness Theorem in simple terms. What does it mean for mathematics?", "max_length": 1000}' | jq -r '.response'

# Q22: P vs NP
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Explain the P vs NP problem. Give an example of an NP-complete problem.", "max_length": 1000}' | jq -r '.response'

# Q23: Halting Problem
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Explain why the halting problem is undecidable. Sketch the proof.", "max_length": 1200}' | jq -r '.response'

# Q24: CAP Theorem
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Explain the CAP theorem. Give an example of a CP system and an AP system.", "max_length": 1000}' | jq -r '.response'

# Q25: Consistency Types
curl -s -X POST "$KING/generate" -H "Content-Type: application/json" \
  -d '{"prompt": "Explain the difference between strong consistency and eventual consistency. When would you choose each?", "max_length": 1000}' | jq -r '.response'
```

---

## Scoring

### Grade Assignment

| Grade | Points | Auto-Grade Criteria |
|-------|--------|---------------------|
| A+ | 4.0 | All rules pass, excellent explanation |
| A | 4.0 | All rules pass |
| A- | 3.7 | Minor formatting issue |
| B+ | 3.3 | Most rules pass |
| B | 3.0 | Core concept correct |
| B- | 2.7 | Partial understanding |
| C | 2.0 | Minimally acceptable |
| D | 1.0 | Major errors |
| F | 0.0 | Wrong or no answer |

### Final Score Calculation

```
GPA = Sum(all grades) / 25
Battle1_Score = GPA × 10

Bonuses:
  +2 points if zero F grades
  
Penalties:
  -1 point per timeout/error
  
Max Score: 40 + 2 = 42 (capped at 40)
```

---

## Results Template

Record results in the king's tracking file (`kings/[king-name].md`).

| King | GPA | A/A+ Count | F Count | Score |
|------|-----|------------|---------|-------|
| 👑 Qwen | /4.0 | /25 | /25 | /40 |
| 🦙 Llama | /4.0 | /25 | /25 | /40 |
| 🔮 Mixtral | /4.0 | /25 | /25 | /40 |
