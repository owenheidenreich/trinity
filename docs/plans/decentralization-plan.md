# Decentralized LLM Inference — Proof of Concept

## Context

Trinity currently runs as a centralized Flask server that delegates inference to a local `llama-server` process. The goal is to pivot toward a **truly decentralized LLM** where model weights are split across multiple "host" nodes, any amount of compute works, and more hosts = better performance.

This plan covers the **PoC milestone**: 2-3 nodes splitting a 7B model on localhost, demonstrating end-to-end distributed inference. Trinity's existing features (memory, tools, chat, ReAct) stay as a client/orchestrator layer — only the inference backend changes. Incentive mechanisms are out of scope.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Trinity Backend (existing)                              │
│  StreamingPipeline → DistributedProvider (new LLMProvider)│
│                          │                               │
│                    ┌─────▼──────┐                        │
│                    │ Coordinator │                        │
│                    └─────┬──────┘                        │
│                          │ gRPC                          │
└──────────────────────────┼───────────────────────────────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │  Node 0    │→ │  Node 1    │→ │  Node 2    │
    │ embed +    │  │ layers     │  │ layers +   │
    │ layers 0-9 │  │ 10-19      │  │ 20-27+head │
    └────────────┘  └────────────┘  └────────────┘
         chain-forward (gRPC)
```

**Chain-forward pattern**: Coordinator sends to Node 0, which calls Node 1, which calls Node 2. Token bubbles back through gRPC responses. Each activation tensor traverses the network once (no coordinator bottleneck).

---

## File Structure

```
Trinity/
  distributed/                          # NEW — entire package
    __init__.py
    config.py                           # Distributed-specific config
    cli.py                              # CLI: partition, node, registry, generate
    proto/
      inference.proto                   # gRPC: Forward, GenerateStream, Health
      registry.proto                    # Node registration messages
      tensor_utils.py                   # Tensor ↔ protobuf serialization
    partitioner/
      __init__.py
      model_partitioner.py              # Split model into N layer groups
      layer_group.py                    # LayerGroup dataclass + safetensors I/O
    node/
      __init__.py
      node_server.py                    # gRPC server holding assigned layers
      layer_executor.py                 # Forward pass + KV cache + sampling
      kv_cache.py                       # Per-sequence KV cache management
    coordinator/
      __init__.py
      coordinator.py                    # Orchestrates generation across pipeline
      sequence_manager.py               # Track active sequences
    registry/
      __init__.py
      registry_server.py                # Simple Flask registry (REST)
      registry_client.py                # Registry client
    auth/
      __init__.py
      node_auth.py                      # Ed25519 node identity (reuses icp_auth patterns)
  backend/services/
    distributed_provider.py             # NEW — DistributedProvider(LLMProvider)
    provider_factory.py                 # MODIFIED — add "distributed" backend
  backend/config.py                     # MODIFIED — add distributed config vars
  distributed/requirements.txt          # NEW — torch, transformers, grpcio, etc.
  scripts/start_poc.sh                  # NEW — launch 3 nodes + registry on localhost
  tests/distributed/                    # NEW — unit + integration tests
```

---

## Implementation Steps (bottom-up)

### Step 1: Proto definitions + tensor utils
- Write `distributed/proto/inference.proto` — messages: `Tensor`, `ForwardRequest`, `ForwardResponse`, `GenerateTokenResponse`, `HealthRequest/Response`, `ClearSequenceRequest/Response`; service: `InferenceNode` with `Forward`, `GenerateStream`, `Health`, `ClearSequence` RPCs
- Write `distributed/proto/registry.proto` — messages: `NodeInfo`, `PipelineConfig`
- Write `distributed/proto/tensor_utils.py` — `tensor_to_proto()` / `proto_to_tensor()` for numpy↔protobuf roundtrip
- Generate Python stubs with `grpc_tools.protoc`

### Step 2: KV cache
- Write `distributed/node/kv_cache.py` — `NodeKVCache` class: per-sequence cache dict, create/append/clear/get_position methods
- Shapes: `[num_heads, seq_len, head_dim]` per layer, keyed by `(sequence_id, layer_idx)`

### Step 3: Model partitioner
- Write `distributed/partitioner/layer_group.py` — `LayerGroup` dataclass with `save()`/`load()` via safetensors
- Write `distributed/partitioner/model_partitioner.py` — `ModelPartitioner.partition(num_groups, output_dir)`:
  - Load model config via `AutoConfig.from_pretrained()`
  - Divide layers evenly (first/last groups slightly smaller to compensate for embed/head overhead)
  - Memory-efficient weight extraction via `safetensors.torch.load_file()` (memory-mapped)
  - Handle model-specific weight naming (Qwen2: `model.layers.{i}.*`, LLaMA: same pattern)
  - Group 0 gets `embed_tokens`; last group gets `norm` + `lm_head`

### Step 4: Layer executor
- Write `distributed/node/layer_executor.py` — `LayerExecutor` class:
  - `load(weights_path)` — instantiate empty decoder layers from model config, load state dict, set eval mode
  - `forward(activations, token_ids, sequence_id, position, is_prefill)` — run through layers with KV cache
  - `sample(logits, temperature, top_p)` — sample next token (last node only)
  - `tokenize(text)` — tokenize input (first node only)
  - Support Qwen2 and LLaMA architectures via decoder layer class registry
- **This is the hardest file** — requires importing model-specific `DecoderLayer` classes from transformers

### Step 5: Correctness validation (single-process)
- Run all 3 layer groups sequentially in one Python process
- Compare output to HuggingFace `model.generate()` with greedy decoding (temperature=0)
- Must produce identical tokens — this validates the partitioner + executor before adding networking

### Step 6: Node gRPC server
- Write `distributed/node/node_server.py` — `InferenceNodeServicer`:
  - `Forward()` — deserialize activations, run executor, chain-forward to next node via gRPC stub, return response
  - `GenerateStream()` — autoregressive loop: forward → chain → sample → yield token, repeat until EOS
  - `Health()` — return node status
  - `ClearSequence()` — free KV cache
  - `start_node_server()` function: load weights, create stubs, register with registry, start heartbeat thread

### Step 7: Registry
- Write `distributed/registry/registry_server.py` — Flask app with `NodeRegistry` class:
  - `POST /nodes` — register node
  - `DELETE /nodes/<id>` — deregister
  - `POST /nodes/<id>/heartbeat` — update heartbeat
  - `GET /pipeline/<model>` — get ordered pipeline config (validates contiguous layers, completeness)
  - `GET /health` — registry health
- Write `distributed/registry/registry_client.py` — REST client + heartbeat background thread

### Step 8: Coordinator
- Write `distributed/coordinator/sequence_manager.py` — `SequenceManager`: create/get/append/complete/cleanup sequences
- Write `distributed/coordinator/coordinator.py` — `DistributedCoordinator`:
  - `connect(model_name)` — query registry, establish gRPC channels, verify health
  - `generate_stream(prompt, max_tokens, temperature)` — send to first node's `GenerateStream`, yield tokens
  - `generate()` — non-streaming wrapper
  - `check_pipeline_health()` — health check all nodes

### Step 9: Trinity integration
- Write `backend/services/distributed_provider.py` — `DistributedProvider(LLMProvider)`:
  - Wraps `DistributedCoordinator`
  - `chat_stream()` applies chat template locally (loads tokenizer once), then calls `generate_stream()`
  - Conforms to yield contract: `str` tokens + `{"__done_reason": "stop"}` terminator
- Modify `backend/services/provider_factory.py` — add `MODEL_BACKEND == "distributed"` path
- Modify `backend/config.py` — add `DISTRIBUTED_REGISTRY_URL`, `DISTRIBUTED_MODEL_NAME`

### Step 10: CLI + demo script
- Write `distributed/cli.py` — argparse commands: `partition`, `node`, `registry`, `generate`
- Write `scripts/start_poc.sh` — start registry + 3 nodes on localhost, run test generation

---

## Key Technical Details

- **Model**: Qwen2.5-7B (28 layers, hidden_dim=3584) or LLaMA 3.1 8B (32 layers, hidden_dim=4096)
- **Activation tensor**: `[1, seq_len, hidden_dim]` in fp16 — ~7KB per token (4096 * 2 bytes) for LLaMA
- **gRPC max message**: Set to 64MB (prefill with long prompts can exceed default 4MB)
- **KV cache**: Maintained locally per node, per sequence. Lost if node dies (acceptable for PoC)
- **Quantization**: fp16 first for correctness. Q4 quantized models work with same partitioner (just smaller tensors)
- **Memory**: 7B fp16 ≈ 14GB total, ~5GB per node across 3. Q4 ≈ 4GB total, ~1.5GB per node

## Dependencies (distributed/requirements.txt)
```
torch>=2.1.0
transformers>=4.36.0
safetensors>=0.4.0
grpcio>=1.60.0
grpcio-tools>=1.60.0
protobuf>=4.25.0
flask>=3.0.0
```

## Files Modified in Existing Codebase
- [provider_factory.py](backend/services/provider_factory.py) — add `"distributed"` backend branch (~5 lines)
- [config.py](backend/config.py) — add 2 env vars (~3 lines)

## Verification Plan
1. **Unit tests**: tensor roundtrip, KV cache ops, partitioner with small model (GPT-2 124M), registry CRUD
2. **Correctness test**: 3 layer groups in single process → compare greedy output to HuggingFace reference
3. **Integration test**: 3 gRPC nodes on localhost → end-to-end streaming generation
4. **Trinity integration test**: `DistributedProvider` plugged into `StreamingPipeline` → verify SSE streaming works
5. **Demo**: `scripts/start_poc.sh` — partition model, start 3 nodes, generate response, verify output
