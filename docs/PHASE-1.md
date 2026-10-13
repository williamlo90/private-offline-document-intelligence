# Phase 1 - Native application foundation

Validated 2026-10-09 on the local Windows development host.

The native harness supports text ingest, tenant/object-scoped source access,
manual source-backed checklist preparation, separate-actor approval, stale-source
handling and sanitized audit. React uses the same FastAPI domain service. Tokens
remain in tab memory; sign-out unmounts the workspace. Authenticated responses
disable browser caching. No model inference, database persistence or Odoo write
is claimed by this milestone.

## Run locally

1. Install the isolated Python environment from `requirements.lock`.
2. In `frontend`, run `npm ci` and `npm run build`.
3. Run `python scripts/create_lab_profile.py` once. It creates ignored local
   credentials and refuses to overwrite an existing profile.
4. Set `PRIVATE_LAB_CONFIG` to the absolute path of `local/lab-identities.json`.
5. Run `.venv/Scripts/python.exe -m uvicorn backend.main:load_app --factory --host 127.0.0.1 --port 8077 --no-access-log`.
6. Open `http://127.0.0.1:8077/ui/` and use the appropriate local account token.

Use distinct technician and service-manager accounts for preparation and approval.
The UI marks approved checklists as not yet saved to Odoo. Synthetic source seed
and all changes are in memory; restarting resets the session data.

For frontend development, `npm run dev` serves the UI and proxies API paths to
loopback port 8077. No external fonts, images or CDN assets are required.

## Evidence

- `python scripts/verify_phase0.py`: source and rubric fixture checks.
- `.venv/Scripts/python.exe -m pytest -q tests/test_foundation.py`: 9 passed,
  including tenant/object denial, self-approval, replay, source drift, sanitized
  errors and review-queue isolation.
- `npm run build`: TypeScript and production asset build passed.
- `npm run test:e2e` in `frontend`: actual Chromium against the native API;
  source selection, preparation, separate-account approval, sign-out clearing,
  cross-client isolation, text ingest and a 390px viewport passed.
- `.venv/Scripts/python.exe scripts/check_deployment_static.py`: PostgreSQL
  grammar and Compose YAML checks passed; it does not invoke Docker.

Machine evidence and desktop/mobile screenshots are in ignored `local/phase-1/`.
The UI was visually reviewed with no clipping or horizontal overflow observed.
The browser test observed no non-local requests. This is not proof of full-stack
offline operation; an isolated network-boundary test is still required.

## Remaining acceptance boundaries

PostgreSQL/pgvector migration execution, RLS, constraints and transaction behavior
are pending Phase 7. The prepared schema does not establish a working PostgreSQL
adapter. Image digests must be pinned before Phase 7 builds. No Docker command was
run. Cache/export/retrieval adapters are not introduced in Phase 1; all later
implementations must preserve domain authorization and revocation semantics.

Text ingest is a Phase 1 fixture surface. PDF parsing/OCR, page provenance,
immutable version history, effective dates and deterministic search are Phase 2.
The current test client emits a Starlette httpx deprecation warning; tests pass.
