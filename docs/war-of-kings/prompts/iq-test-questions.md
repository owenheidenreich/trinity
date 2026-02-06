# Battle 1: IQ Test Questions

> **25 graded questions to test pure intelligence**

---

## Grading Rules

| Rule | Syntax | Example |
|------|--------|---------|
| Contains | `contains:X` | Response must contain X |
| Not Contains | `not_contains:X` | Response must NOT contain X |
| Contains Any | `contains_any:X,Y,Z` | Response must contain at least one |
| Exact | `exact:X` | Response must be exactly X (trimmed) |

---

## Questions

### Category: Arithmetic (3 questions)

**Q1: Square Root**
```
Prompt: "What is the square root of 144? Answer with just the number."
Grade: contains:12
Expected: 12
```

**Q2: Percentage**
```
Prompt: "What is 15% of 80? Answer with just the number."
Grade: contains:12
Expected: 12
```

**Q3: Power**
```
Prompt: "What is 2 to the power of 10? Answer with just the number."
Grade: contains:1024
Expected: 1024
```

---

### Category: Word Problem Traps (3 questions)

**Q4: Apples and Oranges**
```
Prompt: "I have 3 apples. I give away 2 oranges. How many apples do I have?"
Grade: contains:3, not_contains:1
Expected: 3 (oranges are a distractor)
```

**Q5: Steel vs Feathers**
```
Prompt: "Which weighs more: a pound of steel or a pound of feathers?"
Grade: contains_any:same,equal,weigh the same,both weigh
Expected: They weigh the same (both are a pound)
```

**Q6: Bat and Ball**
```
Prompt: "A bat and a ball cost $1.10 together. The bat costs $1.00 more than the ball. How much does the ball cost? Show your work."
Grade: contains_any:$0.05,0.05,5 cents,five cents
Expected: $0.05 (NOT $0.10)
```

---

### Category: Logic Traps (4 questions)

**Q7: Sally's Sisters**
```
Prompt: "Sally has 3 brothers. Each brother has 2 sisters. How many sisters does Sally have?"
Grade: contains:1, not_contains:2 sister
Expected: 1 (Sally + 1 sister = 2 sisters total, but Sally has 1)
```

**Q8: Strawberry Letters**
```
Prompt: "How many times does the letter 'r' appear in the word 'strawberry'? Count carefully."
Grade: contains:3
Expected: 3 (st-r-awbe-r-r-y)
```

**Q9: Sheep Trick**
```
Prompt: "A farmer has 17 sheep. All but 9 run away. How many sheep does the farmer have left?"
Grade: contains:9
Expected: 9 (all but 9 = 9 remain)
```

**Q10: Train Problem**
```
Prompt: "Two trains are 100 miles apart, heading toward each other. Train A travels 40 mph, Train B travels 60 mph. How long until they meet? Answer in hours."
Grade: contains:1
Expected: 1 hour (combined speed 100 mph, 100 miles apart)
```

---

### Category: Formal Logic (3 questions)

**Q11: Three Liars**
```
Prompt: "You meet three people: A, B, and C. A says 'I always lie.' B says 'A is telling the truth.' C says 'B always lies.' Who is definitely a liar?"
Grade: contains:A
Expected: A (if A always lies, saying 'I always lie' is a paradox - A must be lying)
```

**Q12: Truth-Teller Island**
```
Prompt: "On an island, knights always tell truth, knaves always lie. You meet someone who says 'I am a knave.' What are they?"
Grade: contains_any:impossible,neither,paradox,cannot exist
Expected: Impossible/paradox (knight can't say it, knave can't say it truthfully)
```

**Q13: Monty Hall**
```
Prompt: "In the Monty Hall problem, you pick door 1. The host opens door 3 revealing a goat. Should you switch to door 2? Explain with probability."
Grade: contains_any:switch,2/3,66%,67%
Expected: Yes, switch (2/3 probability vs 1/3)
```

---

### Category: Mathematical Proofs (3 questions)

**Q14: Sum of Odd Numbers**
```
Prompt: "Prove that the sum of the first n odd numbers equals n². Use mathematical induction."
Grade: contains_any:induction,base case,n=1,k+1
Expected: Valid induction proof
```

**Q15: √2 Irrational**
```
Prompt: "Prove that the square root of 2 is irrational using proof by contradiction."
Grade: contains_any:contradiction,a/b,both even,gcd
Expected: Contradiction proof with both a and b even
```

**Q16: Pigeonhole**
```
Prompt: "Using the pigeonhole principle, prove that in any group of 13 people, at least 2 share a birthday month."
Grade: contains_any:pigeonhole,12 months,13 > 12
Expected: 13 people, 12 months, must share
```

---

### Category: Code (4 questions)

**Q17: Carmichael Numbers**
```
Prompt: "Write a Python function that determines if a given number is a Carmichael number. Include the mathematical definition."
Grade: contains_any:def ,Korselt,a^n ≡ a
Expected: Working function with Korselt's criterion
```

**Q18: Binary Search**
```
Prompt: "Write a Python function for binary search that returns the index of the FIRST occurrence of the target. Handle duplicates."
Grade: contains_any:def ,while,mid,left,right
Expected: Binary search with leftmost handling
```

**Q19: LRU Cache**
```
Prompt: "Write a Python class implementing an LRU cache with O(1) get and put operations. Use OrderedDict or your own implementation."
Grade: contains_any:class ,def get,def put,OrderedDict
Expected: LRU with O(1) operations
```

**Q20: Quicksort Complexity**
```
Prompt: "What is the time complexity of quicksort in best, average, and worst cases? Explain why the worst case occurs."
Grade: contains_any:O(n log n),O(n²),sorted,pivot
Expected: Best/avg O(n log n), worst O(n²), sorted input
```

---

### Category: Theory (3 questions)

**Q21: Gödel's Incompleteness**
```
Prompt: "Explain Gödel's First Incompleteness Theorem in simple terms. What does it mean for mathematics?"
Grade: contains_any:unprovable,consistent,complete,true statements
Expected: Consistent systems have true but unprovable statements
```

**Q22: P vs NP**
```
Prompt: "Explain the P vs NP problem. Give an example of an NP-complete problem."
Grade: contains_any:polynomial,verify,SAT,traveling salesman,NP-complete
Expected: P=easy solve, NP=easy verify, example NP-complete problem
```

**Q23: Halting Problem**
```
Prompt: "Explain why the halting problem is undecidable. Sketch the proof."
Grade: contains_any:undecidable,contradiction,diagonal,Turing
Expected: Contradiction via self-reference
```

---

### Category: Systems (2 questions)

**Q24: CAP Theorem**
```
Prompt: "Explain the CAP theorem. Give an example of a CP system and an AP system."
Grade: contains_any:Consistency,Availability,Partition,CP,AP
Expected: CAP tradeoffs with examples
```

**Q25: Strong vs Eventual Consistency**
```
Prompt: "Explain the difference between strong consistency and eventual consistency. When would you choose each?"
Grade: contains_any:strong consistency,eventual,read-after-write,stale
Expected: Definitions and use cases
```

---

## Grading Scale

| Grade | Points | Criteria |
|-------|--------|----------|
| A+ | 4.0 | Perfect answer, excellent explanation |
| A | 4.0 | Correct answer with good explanation |
| A- | 3.7 | Correct answer, minor issues |
| B+ | 3.3 | Mostly correct, some gaps |
| B | 3.0 | Core concept correct |
| B- | 2.7 | Partial understanding |
| C+ | 2.3 | Significant gaps |
| C | 2.0 | Minimally acceptable |
| D | 1.0 | Major errors |
| F | 0.0 | Wrong or no answer |

**GPA = Sum of Points / 25**
**Battle 1 Score = GPA × 10 (max 40)**
