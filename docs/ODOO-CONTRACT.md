# Checklist save contract

Project 02 remains pinned to revision
`6a55b9dc61acd87e61b3aacb4da97d61af84b0fa`, contract 1.0. Its activity API targets
`crm.lead` and supports only a summary up to 120 characters. It cannot store or
read back the complete sourced checklist. The working upstream repository has
advanced; this project has not changed its pin or modified that repository.
The target edition is Odoo Community 19.0 with Contacts, CRM, Sales and the
upstream `ops_bridge` addon. The project-owned extension maps tenant to the
server-owned connection/company binding, customer to `res.partner`, opportunity
to `crm.lead`, assignee to `res.users`, and the full sourced checklist to a
`mail.activity` note on that opportunity. It records a separate receipt for
read-back. `project.task` is not used by this V1 contract.

`backend/odoo_contract.py` defines the project-owned `private-checklist-1.0`
extension contract. It requires explicit full-checklist read-back and atomic
receipt capabilities. The upstream activity-only contract fails closed.

The save preview preserves every approved step, page/offset reference, source
version/hash, preparer and reviewer. Its hash also binds the server-owned target:
company, customer, opportunity and assignee. Destination review is required;
the existing source-checklist approval cannot authorize a subsequently changed
Odoo destination. Preview generation creates no external effect.

Read-back requires matching operation ID, payload hash, positive external ID and
the exact payload including company and complete content. An external record ID
alone is not success. Eight contract tests cover long checklist preservation,
destination drift, stale/cross-tenant access and mismatched receipts.

`backend/save_operations.py` now provides destination approval and an operation
state machine on an explicitly in-memory ledger. A different service manager
approves the target-bound payload; self-approval, expiry, source drift, changed
target and revoked reviewer access block dispatch. One operation is allocated
per tenant/proposal. Repeated or concurrent calls do not redispatch an operation.

Dispatch is recorded before the bridge call. Success requires an independent
status/read-back, not the execute response. Lost responses and missing receipts
remain unknown; retries only reconcile. Read-back mismatch requires review and
cannot be reapproved for another dispatch. Authorized reconciliation can continue
after approval expiry because it performs no new write.

Eighteen combined save/receipt tests pass with a bridge double, including lost
responses, duplicate concurrent calls, changed scope and missing receipts.
The harness holds its in-process locks across dispatch/read-back. It does not
prove database concurrency, bridge deduplication or restart recovery. Its ledger
is lost at restart and must never be used for live Odoo writes.

Prepared persistence: `migrations/003_save_operations.sql` defines tenant-scoped
operations, destination approver, unique proposal, attempts/revision and RLS for
managers with current source grants. `backend/save_repository.py` supplies a
parameterized compare-and-swap dispatch claim which returns only after commit.
It also prepares unique preview insertion, scoped reads, revision-bound approval
and read-back transitions. It is not connected to a persistent domain coordinator.
Tests cover repository-call/commit-failure contracts,
SQL syntax and signed-envelope validation; no PostgreSQL execution is claimed.

`backend/bridge_signing.py` signs canonical envelopes with HMAC-SHA256 and checks
signature, pinned contract, payload hash, tenant/company, separated actors and
expiry. Signing does not itself stop replay; atomic deduplication must be enforced
by the bridge ledger using operation ID. The bridge receiver must additionally
validate all content and current Odoo record relationships before writes.

`backend/bridge_adapter.py` provides a bounded, signed JSON-2 HTTP adapter for the
fixed `private.checklist.bridge` extension. It accepts only loopback port and
server-owned database/company/tenant/key configuration. Methods are restricted
to info, execute and status; proxies/redirects and retries are disabled. Responses
are capped at 1 MB and the total deadline defaults to 12 seconds. Execute failures
remain uncertain, while raw server bodies and keys are never forwarded as errors.
The memory save coordinator explicitly rejects this real HTTP adapter.

Transport-double tests verify signature, scope, timeouts, response limits,
malformed output, redirect rejection and absence of retries. The complete backend
suite passes 139 tests; these remain contract/native harness results.

The project-owned Odoo addon now exists at `odoo/addons/private_checklist_bridge`.
It prepares signed input validation, current customer/opportunity/assignee mapping
checks, atomic activity/receipt creation, operation/proposal uniqueness and actual
activity-note read-back. Ten standalone receiver-rule/syntax tests pass; none of
the Odoo ORM, SQL locks or commit behavior has been executed. See its README for
the isolated acceptance checklist and pinned dependency requirements.

The normal API and MCP expose save/verify operations but return
`save_coordinator_unavailable` unless a coordinator is explicitly configured.
`backend.phase4_lab` wires only the synthetic memory bridge. Its real SDK stdio
test covers preview, two-manager approval, unknown outcome, verification,
replay, source drift and tenant isolation. This is contract evidence, not a
connected Odoo result. Persistent domain/ledger coordinator wiring and native
addon acceptance remain Phase 7 prerequisites for enabling the signed adapter.
Only an isolated Phase 7 Odoo instance may provide connected acceptance.
