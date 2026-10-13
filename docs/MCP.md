# Local MCP transport

The TypeScript server in `mcp/src/server.ts` runs over stdio. SDK 1.32.1,
Zod, TypeScript and transitive dependencies are pinned in `mcp/package-lock.json`.
This uses the SDK's maintained v1 protocol line; no custom JSON-RPC implementation.

Build with `npm --prefix mcp ci` and `npm --prefix mcp run build`, then run
`node mcp/dist/server.js`. The launcher must supply `PRIVATE_API_PORT` and
`PRIVATE_API_TOKEN` for one local identity. Tokens never enter tool arguments or
stdout. Each client identity uses its own process; there is no tenant switch tool.
The API host is fixed to loopback and redirects are rejected.

Ten tools call existing Python endpoints: document search, source-term
extraction, source-bound question answering, versioned checklist preparation,
administrator-only readiness inspection, destination-bound save preview,
operation inspection, separate-actor destination approval, one-time dispatch
and read-back verification. Tools reject unknown input fields.
Model absence propagates as an error; no fallback generation is performed.
Tool metadata is advisory; the Python API enforces actual roles and grants.
Source excerpts are untrusted document content, never tool instructions.

HTTP requests have a 125-second deadline, propagate MCP cancellation and bound
response reads to 1 MB. Errors are sanitized and no requests retry automatically.
Cancellation/timeout after draft creation can leave an unknown outcome: inspect
the UI review queue before retrying. Transport failures on preparation report
`operation_outcome_unknown`. Cancellation does not prove a remote worker has
stopped. The server-owned `PRIVATE_API_TIMEOUT_MS` can shorten the deadline
(50 through 125,000 ms) for controlled tests.

`mcp/tests/boundaries.mjs` verifies real stdio cancellation closes the HTTP
request, read deadlines, draft/save unknown outcomes without retry, redirect rejection,
oversized/malformed response rejection and sanitized errors. It uses a faulty
HTTP test double; this is transport evidence, not downstream platform acceptance.

`npm --prefix mcp test` runs the SDK reference client against real stdio server
processes and disposable native FastAPI memory harnesses. It verifies protocol
handshake, list/call, strict input, tenant separation, admin restrictions,
model-unavailable reporting, version-bound drafts and stale-version rejection.
The save suite additionally verifies destination binding, separate service-manager
approval, lost-response/unknown outcome, independent read-back, replay,
source drift, injection and cross-tenant operation denial. Evidence is in
`local/phase-4/mcp-stdio.json` and `mcp-save-stdio.json`.

Save tools fail closed with `save_coordinator_unavailable` in the normal API
unless a coordinator is explicitly injected. The `backend.phase4_lab` fixture
uses only a synthetic bridge and memory ledger, which is lost on restart. The
real signed Odoo transport refuses this ledger; live dispatch requires durable
coordination and isolated Phase 7 acceptance. The current save flow never
claims that creating an Odoo activity completes the underlying IT work.

Reference: [official SDK v1 documentation](https://github.com/modelcontextprotocol/typescript-sdk/tree/v1.x).
