## Updated Trinity Pivot Plan (Aligned To Post-Cleanup Codebase)

### Summary
Trinity should pivot to a **private, developer-first AI workspace** with three parallel tracks:
1. **Product track:** private instances + BYO provider + controlled repo access.
2. **ML depth track:** continuous learning for small components (classifiers/tool routing/evals), not base-model training.
3. **Feature track:** chart rendering + audio transcription first, then optional image generation.

This plan is updated for your current baseline after dead-code removal (`414bff3`): 7 blueprints / 31 routes, canonical `state.db` runtime, and removed `admin/session/mcp/graph/vector/user_data_store` modules.

---

### Locked Decisions
1. Keep **hybrid architecture** now; don’t force full on-chain inference.
2. Keep **local llama-server** as default provider; add BYO as explicit opt-in.
3. Use **owned/consented-only** data for learning pipelines.
4. Prioritize **power users/devs** over consumer UX.
5. Use leased GPU budget for **eval/distillation windows**, not base-model pretraining.

---

### Phase 0 (Week 1): Post-Cleanup Foundation Hardening
1. Reconcile stale references and route/docs drift:
- [backend/routes/tools.py](/Users/gduby/Documents/Trinity/Trinity/backend/routes/tools.py)
- [backend/services/provider_factory.py](/Users/gduby/Documents/Trinity/Trinity/backend/services/provider_factory.py)
- [docs/ai-context/CLAUDE.md](/Users/gduby/Documents/Trinity/Trinity/docs/ai-context/CLAUDE.md)
2. Remove or replace residual references to deleted modules (example: optional `.model_router` import fallback path in provider factory).
3. Add an explicit architecture note: runtime truth is canonical `state.db`, IPFS is checkpoint/archive only:
- [backend/services/state_checkpoint.py](/Users/gduby/Documents/Trinity/Trinity/backend/services/state_checkpoint.py)
- [backend/services/state_store/_base.py](/Users/gduby/Documents/Trinity/Trinity/backend/services/state_store/_base.py)

Acceptance criteria:
- No imports reference deleted services/routes.
- Route and feature docs exactly match runtime.
- Test collection runs without route/module drift errors.

---

### Phase 1 (Weeks 2-3): BYO Provider (Core Product Pivot)
1. Add provider registry service and storage:
- New: `backend/services/provider_registry.py`
- New encrypted table in state store: `provider_configs`
2. Add provider endpoints:
- `POST /user/providers`
- `GET /user/providers`
- `PATCH /user/providers/<provider_id>`
- `DELETE /user/providers/<provider_id>`
3. Extend generation request contract:
- [backend/routes/generate.py](/Users/gduby/Documents/Trinity/Trinity/backend/routes/generate.py) accepts `provider_id`.
- [trinity-icp/src-react/types/api.ts](/Users/gduby/Documents/Trinity/Trinity/trinity-icp/src-react/types/api.ts) updates `GenerateRequest`.
4. Implement provider adapter:
- New: `backend/services/openai_compatible_provider.py` (generic OpenAI-compatible backend).
- Keep existing [backend/services/llama_server_provider.py](/Users/gduby/Documents/Trinity/Trinity/backend/services/llama_server_provider.py) as default.
5. Update provider resolution:
- [backend/services/provider_factory.py](/Users/gduby/Documents/Trinity/Trinity/backend/services/provider_factory.py) resolves by `(principal_id, provider_id)` with secure fallback to local.

Security rules:
- API keys encrypted at rest, never returned in plaintext.
- Masked key preview only in `GET /user/providers`.
- Per-principal ownership enforced server-side.

Acceptance criteria:
- User can switch providers per chat/request.
- Local provider still works unchanged when `provider_id` absent.
- No plaintext secrets in logs or API responses.

---

### Phase 2 (Weeks 4-5): Controlled Repo Access Sessions
1. Add workspace session model:
- New state table: `workspace_sessions` with `session_id`, encrypted `root_path`, `scopes`, `expires_at`.
2. Add workspace session endpoints:
- `POST /workspace/sessions`
- `GET /workspace/sessions/<session_id>`
- `DELETE /workspace/sessions/<session_id>`
3. Add scoped execution enforcement:
- [backend/services/code_executor.py](/Users/gduby/Documents/Trinity/Trinity/backend/services/code_executor.py) must accept context root override and scope checks.
- Scopes: `read`, `write`, `exec`.
4. Extend `/generate/agent` to accept `workspace_session_id`.
5. Pass workspace context through pipeline/react/tool execution chain:
- [backend/services/pipeline.py](/Users/gduby/Documents/Trinity/Trinity/backend/services/pipeline.py)
- [backend/services/react_loop.py](/Users/gduby/Documents/Trinity/Trinity/backend/services/react_loop.py)

Safety defaults:
- Deny by default without session.
- TTL default 1 hour.
- Path must be inside env allowlist `WORKSPACE_ALLOWED_ROOTS`.
- `exec` scope required for `run_command`.

Acceptance criteria:
- Agent can inspect/code against approved repo roots only.
- Path traversal blocked under all tools.
- Expired sessions cannot execute tools.

---

### Phase 3 (Weeks 6-7): Continuous Learning Loop (Small Components)
1. Add learning event capture:
- New table `learning_events` in state store.
- Store: classifier label/confidence, tool decision, tool success/failure, latency, user outcome signal.
2. Add explicit feedback endpoint:
- `POST /learning/feedback` from frontend actions (retry/edit/thumbs).
3. Add consent controls:
- New per-user field: `learning_opt_in`.
- Dataset builder includes only opted-in principals.
4. Add offline pipeline scripts:
- New: `scripts/build_learning_dataset.py`
- Reuse: [scripts/train_classifiers.py](/Users/gduby/Documents/Trinity/Trinity/scripts/train_classifiers.py)
- New: `scripts/eval_classifiers.py` with fixed benchmark set.
5. Add deploy gate:
- Candidate model promoted only if F1 improves and false-positive ceiling stays within threshold.

Acceptance criteria:
- Nightly retrain job produces versioned artifacts.
- Automatic rollback to previous `.npz` on failed eval gate.
- Dataset audit report lists exact event counts and opt-in coverage.

---

### Phase 4 (Weeks 8-9): Leased GPU Utilization Policy
1. Add job scheduler lanes:
- `P0`: interactive chat
- `P1`: ingestion
- `P2`: eval/retrain/distillation
2. Add throttling rules:
- Pause `P2` when queue depth or latency threshold exceeds limits.
3. Add job control endpoints (admin-auth):
- `GET /ops/jobs`
- `POST /ops/jobs/retrain`
- `POST /ops/jobs/cancel/<job_id>`
4. Add observability:
- Queue depth, GPU utilization windows, retrain duration, promotion decisions.

Acceptance criteria:
- P95 interactive latency unchanged under background load.
- Retrain jobs auto-yield under contention.
- All job runs produce structured reports.

---

### Phase 5 (Weeks 10-11): Feature Expansion For Dev Users
1. Charts/graphs:
- Add chart-spec renderer in frontend message pipeline.
- Detect fenced `chart-json` blocks and render with a chart component.
- Files:
  - [trinity-icp/src-react/components/chat/MarkdownRenderer.tsx](/Users/gduby/Documents/Trinity/Trinity/trinity-icp/src-react/components/chat/MarkdownRenderer.tsx)
  - [trinity-icp/src-react/components/chat/Message.tsx](/Users/gduby/Documents/Trinity/Trinity/trinity-icp/src-react/components/chat/Message.tsx)
2. Audio transcription:
- Add `POST /tools/audio/transcribe`.
- Add post-clean endpoint `POST /tools/transcript/clean`.
- Reuse existing tools blueprint pattern in [backend/routes/tools.py](/Users/gduby/Documents/Trinity/Trinity/backend/routes/tools.py).
3. Image generation (optional flag):
- Add provider-capability check.
- Add `POST /tools/image/generate` only for providers that advertise image support.

Acceptance criteria:
- Chart blocks render deterministically from JSON schema.
- Audio file -> transcript -> cleaned transcript roundtrip works.
- Image generation remains disabled unless provider capability is configured.

---

### Public API / Interface Changes
1. Update `POST /generate/agent` request:
- `provider_id?: string`
- `workspace_session_id?: string`
2. Add new route groups:
- `/user/providers/*`
- `/workspace/sessions/*`
- `/learning/feedback`
- `/ops/jobs/*`
- `/tools/audio/transcribe`
- `/tools/transcript/clean`
- Optional: `/tools/image/generate`
3. Frontend types/state updates:
- `GenerateRequest` in [trinity-icp/src-react/types/api.ts](/Users/gduby/Documents/Trinity/Trinity/trinity-icp/src-react/types/api.ts)
- Chat sending in [trinity-icp/src-react/hooks/useChat.ts](/Users/gduby/Documents/Trinity/Trinity/trinity-icp/src-react/hooks/useChat.ts)

---

### Test Plan
1. Security tests:
- Secret storage encryption, no plaintext leak.
- Workspace path traversal and scope enforcement.
- Expired session denial.
2. Integration tests:
- Provider CRUD + request routing.
- Generate flow with provider override.
- Repo tools gated by workspace session.
- Audio transcription endpoints.
3. ML pipeline tests:
- Dataset builder consent filtering.
- Reproducible classifier training outputs.
- Eval gate pass/fail + rollback behavior.
4. Regression tests:
- Existing 31-route behavior remains stable.
- Chat/memory/state checkpoint behavior unchanged.

---

### Assumptions And Defaults
1. Keep current deployment topology (`dubya.ai` + `api.dubya.ai`) unchanged during this roadmap.
2. No base-model training-from-scratch.
3. No automatic training on non-consented data.
4. BYO provider support starts with OpenAI-compatible APIs, then expands.
5. Decentralization work focuses on verifiable control/data plane first, not inference path replacement.
