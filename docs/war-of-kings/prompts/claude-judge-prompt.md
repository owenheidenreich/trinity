# Claude Analysis Prompt Template

## Instructions for Claude

You are the impartial judge of the **War of Three Kings** - a benchmark tournament between three state-of-the-art open source LLMs:

| King | Model | Parameters |
|------|-------|------------|
| 👑 Qwen Emperor | qwen2.5:72b | 72B dense |
| 🦙 Llama Lord | llama3.3:70b | 70B dense |
| 🔮 Mixtral Maven | mixtral:8x22b | 141B MoE (22B active) |

Your task is to analyze the battle results and determine the winner.

---

## Battle 1: IQ Test Analysis

For each of the 25 IQ test questions, score each king's response on:

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Correctness | 50% | Is the answer factually correct? |
| Reasoning | 30% | Does it show clear logical steps? |
| Completeness | 15% | Does it fully address the question? |
| Conciseness | 5% | Is it appropriately brief? |

**Scoring Scale:** 0-10 per question

### Output Format for Battle 1:
```json
{
  "battle": "IQ Test",
  "scores": {
    "qwen": { "Q01": 9, "Q02": 8, ... "total": 215, "avg": 8.6 },
    "llama": { "Q01": 8, "Q02": 9, ... "total": 208, "avg": 8.3 },
    "mixtral": { "Q01": 7, "Q02": 8, ... "total": 195, "avg": 7.8 }
  },
  "analysis": "Qwen excelled at mathematical proofs while Llama showed stronger coding abilities...",
  "winner": "qwen",
  "ranking": ["qwen", "llama", "mixtral"]
}
```

---

## Battle 2: General Knowledge Spam Analysis

For the throughput tests, evaluate based on:

| Metric | Weight | Description |
|--------|--------|-------------|
| Success Rate | 40% | % of requests completed without error |
| Throughput | 30% | Requests per second sustained |
| Latency P95 | 20% | 95th percentile response time |
| Stability | 10% | Consistency across concurrency levels |

### Output Format for Battle 2:
```json
{
  "battle": "General Knowledge Spam",
  "metrics": {
    "qwen": { "success_rate": 98.5, "rps": 2.3, "p95": 4.2, "stability": "high" },
    "llama": { "success_rate": 99.1, "rps": 2.8, "p95": 3.1, "stability": "very high" },
    "mixtral": { "success_rate": 95.2, "rps": 1.9, "p95": 5.8, "stability": "medium" }
  },
  "analysis": "Llama demonstrated superior throughput at all concurrency levels...",
  "winner": "llama",
  "ranking": ["llama", "qwen", "mixtral"]
}
```

---

## Battle 3: Complex Knowledge Spam Analysis

For the stress test with complex reasoning, evaluate:

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Completion Rate | 30% | % of complex requests that finished |
| Response Quality | 40% | Quality of reasoning under pressure |
| Error Handling | 15% | Graceful degradation vs crashes |
| Token Efficiency | 15% | Tokens/second under load |

**Quality Assessment:** Read 5-10 sample responses per king and rate:
- Reasoning coherence (1-10)
- Code correctness if applicable (1-10)
- Factual accuracy (1-10)

### Output Format for Battle 3:
```json
{
  "battle": "Complex Knowledge Spam",
  "metrics": {
    "qwen": { "completion": 92, "quality_avg": 8.1, "errors": 4, "tps": 45 },
    "llama": { "completion": 88, "quality_avg": 7.8, "errors": 6, "tps": 52 },
    "mixtral": { "completion": 78, "quality_avg": 7.2, "errors": 11, "tps": 38 }
  },
  "analysis": "Qwen maintained reasoning quality even under 50 concurrent requests...",
  "winner": "qwen",
  "ranking": ["qwen", "llama", "mixtral"]
}
```

---

## Final Championship Scoring

| Battle | Points | Winner Gets | 2nd Gets | 3rd Gets |
|--------|--------|-------------|----------|----------|
| IQ Test | 40 | 40 pts | 24 pts | 12 pts |
| General Spam | 30 | 30 pts | 18 pts | 9 pts |
| Complex Spam | 30 | 30 pts | 18 pts | 9 pts |
| **Total** | **100** |

### Final Output Format:
```json
{
  "tournament": "War of Three Kings",
  "date": "2026-02-06",
  "final_scores": {
    "qwen": { "b1": 40, "b2": 18, "b3": 30, "total": 88 },
    "llama": { "b1": 24, "b2": 30, "b3": 18, "total": 72 },
    "mixtral": { "b1": 12, "b2": 9, "b3": 9, "total": 30 }
  },
  "champion": "qwen",
  "final_ranking": [
    { "rank": 1, "king": "Qwen Emperor", "score": 88, "title": "👑 SUPREME CHAMPION" },
    { "rank": 2, "king": "Llama Lord", "score": 72, "title": "🥈 Worthy Challenger" },
    { "rank": 3, "king": "Mixtral Maven", "score": 30, "title": "🥉 Honorable Mention" }
  ],
  "recommendation": "Deploy Qwen 2.5 72B as Trinity's primary model. Consider Llama 3.3 as fallback for throughput-sensitive operations.",
  "detailed_analysis": "..."
}
```

---

## Special Considerations

1. **Ties:** If two kings tie in a battle, split the points (e.g., 34/34/12 for tied 1st)
2. **Errors:** Timeouts and 5xx errors count as 0 points for that question
3. **Partial Credit:** For IQ questions, give partial credit for correct reasoning with wrong final answer
4. **MoE Advantage:** Note that Mixtral uses only 22B active parameters despite 141B total - context matters

---

## Data Input Section

**[PASTE BATTLE RESULTS BELOW THIS LINE]**

```
=== BATTLE 1: IQ TEST RESULTS ===
[Results will be pasted here]

=== BATTLE 2: GENERAL SPAM RESULTS ===
[Results will be pasted here]

=== BATTLE 3: COMPLEX SPAM RESULTS ===
[Results will be pasted here]
```
