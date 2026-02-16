# Trinity No-Duct-Tape Plan (Phase A -> E)

Date: 2026-02-16
Owner: Codex
Status: Completed

## Scope
Implement the requested no-duct-tape architecture phases:
- one canonical frontend path
- one canonical generation path
- strict async memory ingestion
- graph memory substrate (`identity.kuzu`)
- durability-first IPFS checkpointing
- explicit SLO tracking and eval gates

## Phase A - Simplify first

Completed:
- Canonical frontend path declared in config (`CANONICAL_FRONTEND_PATH=src-react`) and reflected by existing default build path.
- Canonical generation route declared (`CANONICAL_GENERATE_ROUTE=/generate/agent`).
- Local-first autosave retained (no blocking Lighthouse upload on autosave hot path).
- Blocking restore removed from generation paths; hydration now background async via `hydrate_user_data_async()`.
- Assistant-origin auto extraction remains disabled by default (`AUTO_EXTRACT_ASSISTANT_MEMORY=false`).

## Phase B - Conversational quality architecture

Completed:
- Intent-based memory mention policy in `backend/services/agent.py`.
- Prompt policy updated to remove global persona pressure in `backend/services/agent_prompts.py`.
- Model strategy added:
  - `CONVERSATION_MODEL_NAME`
  - `CODER_MODEL_NAME`
  - heuristic router (`backend/services/model_router.py`)
  - routed provider selection in `backend/services/provider_factory.py`.

## Phase C - Memory engine upgrade

Completed:
- Added Kuzu-backed per-user graph service (`backend/services/graph_memory.py`) using `identity.kuzu` path per user.
- Added triple extractor (`backend/services/graph_extractor.py`).
- Added strict async ingestion worker (`backend/services/memory_ingestion.py`) for facts + graph triples.
- Retrieval merge path now includes:
  - recent context
  - relevant profile facts
  - relevant semantic snippets
  - relevant graph triples

## Phase D - IPFS durability redesign

Completed:
- Checkpoint scheduler:
  - existing chat checkpoint debounce + max-wait enforcement
  - event flush on archive action
- Content-hash dedupe before upload in `_upload_with_retry()`.
- Versioned manifest metadata:
  - `manifestVersion`
  - `currentManifestCid`
  - `manifestHistory` (rolling history)
  - rollback support (`rollback_manifest`) + admin endpoint.
- Background hydration on generation path; restore does not block first token path.
- Graph durability added:
  - graph artifact sync/restore
  - graph manifest section (`graphIndex`).

## Phase E - Quality and reliability gates

Completed:
- Eval helper for memory relevance precision/recall (`backend/services/memory_eval.py`).
- Runtime SLO metrics service (`backend/services/slo_metrics.py`) with:
  - first token latency
  - memory precision/recall (eval-backed)
  - unsolicited personal reference rate
  - IPFS writes per active user/hour
- Admin visibility:
  - `GET /admin/slo/status`
  - `POST /admin/storage/rollback/<principal_id>`

## Validation

Executed:

```bash
python3 -m pytest --no-cov -q backend/tests/unit/test_model_routing.py backend/tests/unit/test_graph_memory.py backend/tests/unit/test_memory_ingestion.py backend/tests/unit/test_slo_metrics.py backend/tests/unit/test_memory_phase3.py backend/tests/unit/test_providers.py backend/tests/unit/test_chat_lifecycle.py backend/tests/unit/test_memory_foundation.py
python3 -m pytest --no-cov -q backend/tests/unit/test_full_pipeline.py backend/tests/unit/test_phase2_stability.py backend/tests/unit/test_lighthouse.py
python3 -m pytest --no-cov -q backend/tests/unit/test_phase4_quality.py::TestImportPatterns::test_generate_only_allowed_lazy_imports
python3 -m pytest --no-cov -q backend/tests/unit
```

Results:
- `158 passed`
- `74 passed`
- `1 passed`
- `897 passed`
