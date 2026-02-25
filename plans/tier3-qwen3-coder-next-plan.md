# Trinity Tier 3 Implementation Plan: Qwen3-Coder-Next-GGUF

> **Created:** February 20, 2026  
> **Status:** Planning  
> **Model:** [Qwen/Qwen3-Coder-Next-GGUF](https://huggingface.co/Qwen/Qwen3-Coder-Next-GGUF)

---

## Context

Trinity currently runs Qwen3-32B (Q4_K_M GGUF, ~18-20GB) as its chat model on llama-server. Qwen3-Coder-Next is Qwen's next-generation coding agent model — 80B total parameters with only 3B activated per token (high-sparsity Mixture-of-Experts). It matches models with 10-20x more active parameters on coding and agentic benchmarks, and ships with an official GGUF and documented llama.cpp support, making it a direct drop-in for Trinity's existing llama-server backend.

Rather than replacing the proven Tier 2 production deployment, we add a new **Tier 3** deployment tier that targets 80GB GPUs (A100-80GB, H100-80GB). The existing Tier 1 (test) and Tier 2 (production) are untouched.

### Why Qwen3-Coder-Next-GGUF over Qwen3-Next-80B-A3B-Instruct

Both models share the same `qwen3_next` architecture (80B total, 3B activated, 512 experts, hybrid Gated DeltaNet + Gated Attention). The deciding factor is deployment compatibility:

| Factor | Qwen3-Coder-Next-GGUF | Qwen3-Next-80B-A3B-Instruct |
|--------|------------------------|------------------------------|
| Format | Official GGUF (Qwen-published) | Safetensors (BF16) only |
| llama.cpp/llama-server | Explicitly documented, tested | Not documented; needs community GGUF or backend swap |
| Backend change required | None — same llama-server OpenAI API | Would require migrating to vLLM or SGLang (4-GPU tensor parallel) |
| Focus | Coding agents, tool calling, IDE integration | General instruct |
| `<think>` blocks | None (non-thinking only) | None (non-thinking only) |

Choosing the Coder-Next GGUF means **zero backend code changes** to the inference layer. The model serves the same `/v1/chat/completions` endpoint via llama-server.

---

## Model Specs

| Property | Qwen3-Coder-Next (Tier 3 chat) | Qwen3-8B (ingest, unchanged) |
|----------|-------------------------------|-------------------------------|
| Architecture | `qwen3_next` — hybrid MoE | `qwen3` — dense |
| Total params | 80B | 8B |
| Activated params | 3B per token | 8B (all) |
| MoE config | 512 experts, 10 active + 1 shared | N/A (dense) |
| Attention | Hybrid: Gated DeltaNet + Gated Attention | Standard attention |
| Native context | 262,144 tokens | 128K tokens |
| Quantization | Q4_K_M | Q4_K_M |
| GGUF size | **48.4 GB** (4 split shards) | ~5 GB (single file) |
| GGUF files | `Qwen3-Coder-Next-Q4_K_M-00001-of-00004.gguf` through `-00004` | `Qwen3-8B-Q4_K_M.gguf` |
| HuggingFace repo | `Qwen/Qwen3-Coder-Next-GGUF` | `Qwen/Qwen3-8B-GGUF` |

### VRAM Budget (A100-80GB / H100-80GB)

| Component | VRAM |
|-----------|------|
| Qwen3-Coder-Next Q4_K_M weights | ~48.4 GB |
| Chat KV cache (q8_0, 65K context) | ~8-12 GB |
| Qwen3-8B Q4_K_M weights (ingest) | ~5 GB |
| Ingest KV cache (8K context) | ~0.5 GB |
| CUDA overhead | ~1-2 GB |
| **Total** | **~63-70 GB** |
| **Remaining on 80GB GPU** | **~10-17 GB headroom** |

The dual-instance architecture (chat + ingest on a single GPU) is preserved — 80GB GPUs have ample room for both models plus KV caches.

### GPU Compatibility

| GPU | VRAM | Tier 3 compatible? | Notes |
|-----|------|---------------------|-------|
| A100-80GB | 80 GB | **Yes** | Primary target |
| H100-80GB | 80 GB | **Yes** | Primary target |
| A100-40GB | 40 GB | No | 48.4GB weights exceed VRAM |
| A6000 | 48 GB | No | No room for KV cache |
| L40S | 48 GB | No | No room for KV cache |
| A40 | 48 GB | No | No room for KV cache |
| RTX 4090 | 24 GB | No | Impossible |

---

## Deployment Tiers (after implementation)

| Tier | YAML | Chat model | GPU | Cost estimate |
|------|------|-----------|-----|---------------|
| **Tier 1 (test)** | `deploy-test.yaml` | Qwen3-8B Q4_K_M | Any NVIDIA | ~$40-100/mo |
| **Tier 2 (production)** | `deploy-production.yaml` | Qwen3-32B Q4_K_M | a100/a6000/h100/l40s/a40/rtx4090 | ~$600-1000/mo |
| **Tier 3 (high-perf)** | `deploy-tier3.yaml` | Qwen3-Coder-Next Q4_K_M | a100-80gb/h100-80gb only | ~$1200-2500/mo |

---

## Implementation Steps

### Step 1: Update `resolve_model()` in startup.sh

**File:** [deploy/docker/startup.sh](deploy/docker/startup.sh)

Add a new case to the `resolve_model()` function for the `qwen3-coder-next` model identifier.

```bash
"qwen3-coder-next"|"qwen3-coder-next:80b")
    HF_REPO="Qwen/Qwen3-Coder-Next-GGUF"
    HF_SUBDIR="Qwen3-Coder-Next-Q4_K_M"
    MODEL_FILENAME="Qwen3-Coder-Next-Q4_K_M-00001-of-00004.gguf"
    IS_SPLIT_GGUF=true
    SPLIT_SHARD_COUNT=4
    ;;
```

Key difference from existing models: this is a **split GGUF** (4 shards). llama-server handles split GGUFs natively — you pass `--model .../00001-of-00004.gguf` and it auto-discovers the remaining shards from the same directory. But the download logic must fetch all 4 files.

### Step 2: Add split GGUF download support to startup.sh

**File:** [deploy/docker/startup.sh](deploy/docker/startup.sh)

The current download logic uses `hf_hub_download(filename=...)` for a single file. For split GGUFs, we need to download all shards. Two approaches:

**Option A (preferred): Use `snapshot_download` with `allow_patterns`**
```python
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="Qwen/Qwen3-Coder-Next-GGUF",
    allow_patterns="Qwen3-Coder-Next-Q4_K_M/*",
    local_dir="/home/trinity/.models"
)
```

**Option B: Loop `hf_hub_download` over each shard**
```python
for i in range(1, SPLIT_SHARD_COUNT + 1):
    shard = f"Qwen3-Coder-Next-Q4_K_M-{i:05d}-of-{SPLIT_SHARD_COUNT:05d}.gguf"
    hf_hub_download(repo_id=HF_REPO, filename=f"{HF_SUBDIR}/{shard}", ...)
```

Option A is simpler and lets HuggingFace handle the shard enumeration. The model path passed to llama-server becomes:
```
/home/trinity/.models/Qwen3-Coder-Next-Q4_K_M/Qwen3-Coder-Next-Q4_K_M-00001-of-00004.gguf
```

### Step 3: Update llama-server launch flags

**File:** [deploy/docker/startup.sh](deploy/docker/startup.sh)

For the chat instance when running Qwen3-Coder-Next, add flags per the official llama.cpp docs:

```bash
llama-server \
    --host 0.0.0.0 \
    --port 8081 \
    --model /home/trinity/.models/Qwen3-Coder-Next-Q4_K_M/Qwen3-Coder-Next-Q4_K_M-00001-of-00004.gguf \
    --ctx-size ${LLAMA_SERVER_CHAT_CTX:-65536} \
    --n-gpu-layers -1 \
    --cache-type-k q8_0 \
    --cache-type-v q8_0 \
    --cont-batching \
    --jinja \         # NEW: enables Jinja2 chat template processing (required for this model)
    -fa               # NEW: flash attention (recommended for qwen3_next architecture)
```

The `--jinja` flag enables server-side chat template rendering, which Qwen3-Coder-Next requires for proper tool-calling format. The `-fa` flag enables flash attention for better throughput with the hybrid attention architecture.

The ingest instance (port 8082) is **unchanged** — it continues running Qwen3-8B.

### Step 4: Bump health check timeouts

**File:** [deploy/docker/startup.sh](deploy/docker/startup.sh), [deploy/docker/Dockerfile](deploy/docker/Dockerfile)

The 80B MoE model loads more data into VRAM than the 32B dense model (48GB vs 20GB). Even on fast NVLink GPUs, initial load time increases.

| Setting | Current | Tier 3 |
|---------|---------|--------|
| Chat health timeout (startup.sh) | 600s | **900s** |
| Docker HEALTHCHECK start-period | 1200s | **1800s** (covers download + load on first boot) |

These are safe to increase globally since they're upper bounds, not delays. Tier 1/2 models will pass health checks at the same speed as before.

### Step 5: Create Tier 3 Akash YAML

**New file:** [deploy/akash/deploy-tier3.yaml](deploy/akash/deploy-tier3.yaml)

Based on `deploy-production.yaml` with these changes:

| Setting | Tier 2 (production) | Tier 3 |
|---------|---------------------|--------|
| GPU allowlist | a100, a6000, h100, l40s, a40, rtx4090 | **a100, h100** (80GB only) |
| Memory | 48 GiB | **64 GiB** |
| Persistent storage | 80 GiB | **120 GiB** |
| `OLLAMA_CHAT_MODEL` | `qwen3:32b` | **`qwen3-coder-next`** |
| `OLLAMA_INGEST_MODEL` | `qwen3:8b` | `qwen3:8b` (unchanged) |
| `LLAMA_SERVER_CHAT_CTX` | 65536 | 65536 (can increase to 131072 later) |

All other settings (ports, timeouts, auth, read_timeout=60000) remain identical.

### Step 6: Sampling parameter adjustments

**File:** [backend/config.py](backend/config.py)

Qwen3-Coder-Next recommends different sampling parameters than Qwen3-32B:

| Parameter | Current (Qwen3-32B) | Qwen3-Coder-Next recommended |
|-----------|---------------------|------------------------------|
| temperature | 0.7 (conversational) | 1.0 |
| top_p | 0.8 | 0.95 |
| top_k | 20 | 40 |

Rather than changing defaults globally (which would affect Tiers 1 and 2), make these configurable via environment variables so the Tier 3 YAML can override them:

```python
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))
TEMPERATURE_CODE = float(os.getenv("TEMPERATURE_CODE", "0.1"))
TEMPERATURE_FACTUAL = float(os.getenv("TEMPERATURE_FACTUAL", "0.3"))
TEMPERATURE_CONVERSATIONAL = float(os.getenv("TEMPERATURE_CONVERSATIONAL", "0.7"))
DEFAULT_TOP_P = float(os.getenv("DEFAULT_TOP_P", "0.8"))
DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "20"))
```

Tier 3 YAML then sets:
```yaml
env:
  - TEMPERATURE_CONVERSATIONAL=1.0
  - TEMPERATURE_CODE=0.3
  - DEFAULT_TOP_P=0.95
  - DEFAULT_TOP_K=40
```

**Prerequisite check:** Verify that `top_p` and `top_k` are actually passed through to llama-server in the provider. If they're not, wire them through `llama_server_provider.py` → `chat_stream()` alongside temperature. This may be the one backend code change needed.

### Step 7: Verify llama.cpp `qwen3next` architecture support

**File:** [deploy/docker/Dockerfile](deploy/docker/Dockerfile)

The `qwen3next` architecture (Gated DeltaNet + hybrid MoE with 512 experts) is a recent addition to llama.cpp. The Dockerfile pulls from:

```dockerfile
FROM ghcr.io/ggml-org/llama.cpp:server-cuda AS llama
```

This must be a version that includes `qwen3next` support. Steps:

1. Check the [llama.cpp releases](https://github.com/ggerganov/llama.cpp/releases) for the first version supporting `qwen3next`
2. Pin the Dockerfile to that tag or later: `ghcr.io/ggml-org/llama.cpp:server-cuda-b4567` (example)
3. If the current `:server-cuda` (latest) already includes it, confirm by running `llama-server --list-models` or checking the build's `gguf.cpp` for the architecture string

**Risk:** If `qwen3next` is not yet in the llama.cpp `server-cuda` image, this is a blocker. Fallback: build llama.cpp from source in the Dockerfile (adds ~5min build time).

### Step 8: Create/update deployment script

**File:** [scripts/trinity-deploy-production.sh](scripts/trinity-deploy-production.sh) (or new file)

Add support for a `tier3` argument:

```bash
./scripts/trinity-deploy-production.sh tier3
```

This should select `deploy/akash/deploy-tier3.yaml` and follow the same build → push → deploy flow as existing tiers.

### Step 9: Update documentation

**Files to update:**

| File | Change |
|------|--------|
| [docs/ai-context/CLAUDE.md](docs/ai-context/CLAUDE.md) | Add Tier 3 to stack description, `qwen3-coder-next` to model references, add a100-80gb/h100-80gb to GPU notes |
| [docs/ai-context/CODEBASE-MAP.md](docs/ai-context/CODEBASE-MAP.md) | Add `deploy-tier3.yaml` to file listings, add Tier 3 model constants |
| [docs/ai-context/MICROGPT.md](docs/ai-context/MICROGPT.md) | Add Tier 3 to the LLM Backend dual-instance table |
| `.github/copilot-instructions.md` | Add Tier 3 to deployment section, GPU allowlist note |

---

## Verification Checklist

### Local testing (before deploy)

- [ ] Download Qwen3-Coder-Next Q4_K_M locally (all 4 shards)
- [ ] Start llama-server with `--model .../00001-of-00004.gguf --jinja -ngl -1 -fa --ctx-size 8192` (small ctx for local testing)
- [ ] Verify `/health` returns `ok`
- [ ] Verify `/v1/chat/completions` returns valid responses
- [ ] Verify tool calling works via the OpenAI-compatible API
- [ ] Confirm `--cache-type-k q8_0 --cache-type-v q8_0` is compatible (no errors on start)
- [ ] Run `cd backend && python -m pytest tests/ -x -q` — all 1028+ tests pass

### Docker testing

- [ ] `docker build --platform linux/amd64 -t trinity-tier3 -f deploy/docker/Dockerfile .`
- [ ] Container starts, `startup.sh` resolves `qwen3-coder-next` correctly
- [ ] Both llama-server instances start (8081 + 8082)
- [ ] Flask health endpoint responds

### Akash deployment

- [ ] Deploy `deploy-tier3.yaml` to Akash
- [ ] Bid accepted on A100-80GB or H100-80GB provider
- [ ] Model downloads successfully (first boot, ~48GB download)
- [ ] Both llama-server instances pass health checks
- [ ] Chat responses stream within 60s (Akash read_timeout)
- [ ] Tool calling works end-to-end
- [ ] Memory extraction (ingest instance) works — verify via `/api/memory` endpoint
- [ ] Subsequent restarts use cached model (persistent volume)

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| llama.cpp doesn't support `qwen3next` architecture yet | Medium | Blocker | Check before starting. Fallback: build from source or wait for release |
| Split GGUF download fails on Akash (network timeout, disk space) | Low | Recoverable | 120GB persistent storage provides headroom. Download retries in startup.sh |
| 48GB model + KV cache exceeds 80GB on A100 | Low | Blocker | Q4_K_M (48.4GB) + q8_0 KV at 65K ctx (~10GB) + 8B ingest (~5GB) = ~63GB. Safe margin. Reduce ctx-size if needed |
| Akash A100-80GB/H100-80GB availability is limited | Medium | Deploy delay | These are premium GPUs with fewer providers. May need to bid higher or wait for availability |
| Qwen3-Coder-Next tool calling format differs from Qwen3-32B | Low | Functional | Both use OpenAI-compatible format. Test tool calling in isolation before deploy |
| First-byte latency exceeds 60s Akash timeout | Low | User-visible | MoE with 3B activated params should be *faster* than 32B dense for inference. The 60s timeout is for first SSE chunk, not full response |
| Cost increase (~2x production) | Expected | Budget | Tier 3 is opt-in. Tier 2 remains the default production deployment |

---

## Future Considerations

- **Q5_K_M quantization** (56.7GB): Higher quality, still fits 80GB with reduced KV cache context or without quantized KV. Could be offered as an env var toggle.
- **Context window increase**: With ~10-17GB VRAM headroom, could test `--ctx-size 131072` (128K) for even longer conversations.
- **Multi-Token Prediction (MTP)**: Qwen3-Coder-Next supports MTP for speculative decoding, but this requires framework support (SGLang/vLLM, not llama-server). Future consideration if migrating inference backends.
- **Separate ingest deployment**: If Tier 3 needs maximum VRAM for the chat model, ingest could move to its own Tier 1-class deployment (~$40-100/mo additional).
- **LoRA fine-tuning**: llama-server already supports `--lora` flag. Qwen3-Coder-Next could be fine-tuned on Trinity-specific tool patterns.
