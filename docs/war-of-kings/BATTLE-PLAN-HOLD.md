# Battle Plan - ON HOLD

**Status:** ⏸️ PAUSED - Qwen disk space issue
**Created:** February 6, 2026 02:35

---

## Planned Execution Strategy

### No Code Changes Required
All curl commands pre-written, output capture configured.

### Battle 1: IQ Test (25 Questions)
- Sequential execution per king
- Full JSON response capture including `think` field
- Timing with `time` prefix
- Error capture with `2>&1`

### Battle 2: General Knowledge Spam
- Parallel execution: 5 → 10 → 25 → 50 concurrent
- `xargs -P` for parallelism
- Timestamped output files per concurrency level

### Battle 3: Complex Knowledge Spam  
- 50 parallel curls
- 120s timeout for complex reasoning
- Capture `eval_count`, `prompt_eval_count` tokens

### Output Structure
```
results/raw/
├── qwen/
│   ├── battle1-iq/
│   ├── battle2-general/
│   └── battle3-complex/
├── llama/
│   └── ...
└── mixtral/
    └── ...
```

### Claude Analysis
- Collect all JSON outputs
- Single prompt to Claude with comparative scoring
- Metrics: correctness, reasoning quality, speed, error handling

---

## BLOCKED BY

**CRITICAL: Qwen Emperor disk space exhausted**

```
[trinity]: 2. Network connection issues
[trinity]: 3. Insufficient disk space
[trinity]: 4. Model is too large for available space
```

### Resolution Options
1. Increase ephemeral storage in Akash YAML (currently 100Gi?)
2. Redeploy with larger disk allocation
3. Use different provider with more storage

---

## Resume When
- [ ] Qwen disk issue resolved
- [ ] All 3 kings return healthy status
- [ ] Warmup tests pass
