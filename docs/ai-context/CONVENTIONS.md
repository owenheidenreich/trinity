# Trinity Conventions

> Machine-readable rules for AI coding assistants. One rule per line, grep-friendly.
> **Last Updated:** February 13, 2026

## State Management
DO: Use Zustand setter methods — `State.setAuthenticated()`, `State.setChatHistory()`
DON'T: Direct-assign Zustand state — `State.x = val` fails silently, no error thrown

## Deployment
DO: Docker build with `--platform linux/amd64` (dev is Apple Silicon, prod is amd64)
DO: Deploy via `./scripts/trinity-deploy-production.sh [tier]`
DON'T: Put API keys in Akash YAML — use `.env` + runtime injection
DON'T: Panic on 20-30s first-request delay after deploy — model loading is normal

## Backend Patterns
DO: Use `@require_auth` decorator for protected endpoints
DO: Register new blueprints in `routes/__init__.py` ALL_BLUEPRINTS list
DO: Add new services to `services/__init__.py` exports
PATTERN: New API route → blueprint in `routes/` → register in `routes/__init__.py`
PATTERN: New tool → define in `tools.py` TOOL_DEFINITIONS → dispatch in `code_executor.py`
PATTERN: New middleware → add to `middleware/__init__.py` exports
DON'T: Import from `database.py` — it's unused dead code (future feature)

## Frontend Patterns (React 19 — `src-react/`)
DO: Use hooks (`useAuth`, `useChat`, `useAutosave`, `useConnection`) not raw store access
DO: Use CSS Modules for component styles, `tokens.css` for design tokens
PATTERN: New component → `src-react/components/<domain>/` → import in parent
PATTERN: New state → add to `store/types.ts` → implement in `store/index.ts`
DON'T: Add features to `src/` (legacy vanilla JS) — only `src-react/` gets new work

## Auth
DO: Signed message format: `{principal}:{timestamp}:{endpoint}:{nonce}`
DO: Check 60s timestamp window (hardcoded in `icp_auth.py`, NOT the 5min in config.py)
DON'T: Trust `AUTH_TIMESTAMP_WINDOW_MS` from config.py — it's unused

## Testing
DO: Run `cd backend && python -m pytest tests/ -x -q` before committing backend changes
DO: Use pytest markers: `@pytest.mark.unit`, `@pytest.mark.security`, `@pytest.mark.p0`
PATTERN: New test → `tests/unit/test_<module>.py` → use fixtures from `tests/fixtures/`

## Documentation
DO: Update `CODEBASE-MAP.md` after adding/removing routes, services, or tools
DO: Grep `docs/` for stale values after changing constants or architecture
DON'T: Duplicate facts across context files — define once, cross-reference elsewhere
