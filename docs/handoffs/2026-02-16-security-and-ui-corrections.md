# Security + UI Corrections (Feb 16, 2026)

This handoff captures the production-impacting corrections applied across backend security and frontend chat persistence behavior.

## 1) Security Corrections (Backend)

- Enforced strict ICP auth requirements:
  - `ICP-Nonce` is required on protected routes.
  - `ICP-Principal` must match the principal derived from `ICP-PublicKey`.
  - Timestamp validation uses `AUTH_TIMESTAMP_WINDOW_MS` from config (default 60s).
- Locked down MCP:
  - `POST /mcp` now requires authenticated requests.
  - Added rate limiting on MCP POST calls.
- Protected expensive tool endpoints:
  - `/tools/documents/query` and `/tools/transcript/clean` now require auth and rate limiting.
- Hardened command execution:
  - `run_command` moved away from shell interpretation (`shell=False`) with argument parsing.
  - This removes metacharacter chaining via shell semantics.
- Quota and usage consistency:
  - Quota identity resolution now prefers authenticated principal state.
  - Token quota enforcement/recording is applied consistently on generation paths.
- Passphrase unlock now rate-limited.
- Cleanup metadata path corrected to use decrypt/re-save through encrypted storage flow.

## 2) Minor Interface Bug Corrections (Frontend + Chat Routes)

The following user-facing issues were addressed:

- New accounts incorrectly showing a blank "Recovered Chat".
- Clicking "New Chat" and sending a message overwriting a single existing sidebar chat.
- Autosave persisting only the latest utterance instead of full conversation history.

Fixes applied:

- Backend chat listing now excludes non-chat artifacts (canary/metadata/master bundle) from fallback scan.
- Chat lookup/archive matching now uses strict parsed chat IDs instead of substring matching.
- Frontend send/autosave flows now read latest store state at execution time (avoids stale closure writes).
- New chat IDs are generated and propagated reliably when a chat starts.
- Continue-generation path updates the latest active history slice safely.

## 3) Validation and Test Notes

Security patch set validation (backend full suite):

- `python3 -m pytest tests/ --no-cov -q`
- Result: **867 passed, 9 skipped**

Chat/UI regression validation:

- `python3 -m pytest -q --no-cov backend/tests/unit/test_chat_lifecycle.py`
  - Result: **52 passed**
- `npm --prefix trinity-icp test -- src-react/__tests__/useChat.test.ts`
  - Result: **14 passed**
- `npm --prefix trinity-icp run typecheck`
  - Result: passed

## 4) Deploy Impact

- Clients must send valid nonce + principal/public-key bound auth headers on protected endpoints.
- `/mcp` POST now requires valid auth.
- `/tools/documents/query` and `/tools/transcript/clean` now require auth and are rate-limited.
- Frontend should be rebuilt/redeployed so autosave + new-chat flow fixes are active.
