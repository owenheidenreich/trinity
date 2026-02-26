# Trinity Conventions

> Machine-readable rules for AI coding assistants. One rule per line, grep-friendly.
> **Last Updated:** February 25, 2026

## State Management
DO: Use Zustand setter methods — `State.setAuthenticated()`, `State.setChatHistory()`
DON'T: Direct-assign Zustand state — `State.x = val` fails silently, no error thrown

## Deployment
DO: Docker build with `--platform linux/amd64` (dev is Apple Silicon, prod is amd64)
DO: Deploy via `./scripts/trinity-deploy-production.sh production` (or `test` for smoke-testing)
DON'T: Put API keys in Akash YAML — use `.env` + runtime injection
DON'T: Panic on 20-30s first-request delay after deploy — model loading is normal

## Backend Patterns
DO: Use `@require_auth` decorator for protected endpoints
DO: Register new blueprints in `routes/__init__.py` ALL_BLUEPRINTS list
DO: Add new services to `services/__init__.py` exports
DON'T: Pass `think=False` to llama-server — that was Ollama-specific. `think_filter.py` strips `<think>` blocks from the stream instead.
PATTERN: New API route → blueprint in `routes/` → register in `routes/__init__.py`
PATTERN: New tool → define in `tools.py` TOOL_DEFINITIONS → dispatch in `code_executor.py`
PATTERN: New middleware → add to `middleware/__init__.py` exports
DON'T: Import from `database.py` — it's unused dead code (future feature)
DON'T: Delete regex fallback patterns — they are the permanent safety net for low-confidence classifier results. See [MICROGPT.md](MICROGPT.md)
PATTERN: Classification order → classifier first (tiny_classifier.py), regex fallback if confidence < threshold, safe default if neither matches
DON'T: Reference `ollama_provider.py` or `ollama.py` — these files are deleted. Use `llama_server_provider.py`.
PATTERN: Context loading → `context_loader.load_context()` (single function, not scattered paths)
PATTERN: Prompt building → `prompt_assembler.assemble()` (token-budgeted, auto-generated tool sections)
PATTERN: Streaming → `pipeline.StreamingPipeline` (not agent.py directly)
PATTERN: Memory retrieval → `knowledge_store.search()` (unified ANN/brute-force)
PATTERN: Background ingestion → `ingestion_worker.enqueue_ingestion()` (event-driven daemon)
PATTERN: Query classification → `tiny_classifier.classify_query()` (ByteTransformer, pure numpy)
PATTERN: Tool detection → `tiny_classifier.detect_tools()` (ByteTransformer, pure numpy)
PATTERN: Temperature routing → `query_classifier.classify_temperature()` (code→0.1, factual→0.3, conversational→0.7)
PATTERN: LLM provider → `provider_factory.get_provider()` → `LlamaServerProvider` (OpenAI-compatible API)

## Frontend Patterns (React 19 — `src-react/`)
DO: Use hooks (`useAuth`, `useChat`, `useAutosave`, `useConnection`) not raw store access
DO: Use CSS Modules for component styles, `tokens.css` for design tokens
PATTERN: New component → `src-react/components/<domain>/` → import in parent
PATTERN: New state → add to `store/types.ts` → implement in `store/index.ts`
DON'T: Add features to `src/` (legacy vanilla JS) — only `src-react/` gets new work

## Auth
DO: Signed message format: `{principal}:{timestamp}:{endpoint}:{nonce}`
DO: Require all 5 auth headers on protected routes (`ICP-Principal`, `ICP-Signature`, `ICP-Timestamp`, `ICP-PublicKey`, `ICP-Nonce`)
DO: Enforce principal/public-key binding (derived principal from key must match header principal)
DO: Use `AUTH_TIMESTAMP_WINDOW_MS` from `config.py` (default 60s)
DON'T: Support nonce-optional fallback paths

## Testing
DO: Run `cd backend && python -m pytest tests/ -x -q` before committing backend changes
DO: Use pytest markers: `@pytest.mark.unit`, `@pytest.mark.security`, `@pytest.mark.p0`
PATTERN: New test → `tests/unit/test_<module>.py` → use fixtures from `tests/fixtures/`

## Documentation
DO: Update `CODEBASE-MAP.md` after adding/removing routes, services, or tools
DO: Grep `docs/` for stale values after changing constants or architecture
DON'T: Duplicate facts across context files — define once, cross-reference elsewhere
