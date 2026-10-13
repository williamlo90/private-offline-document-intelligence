# Private checklist bridge — prepared, not runtime validated

This project-owned Odoo 19 addon extends the `ops_bridge` addon from Project 02
at revision `6a55b9dc61acd87e61b3aacb4da97d61af84b0fa`. It calls the upstream
private binding/model/record helpers; no upstream repository was modified.
Install only with that audited dependency on an isolated Phase 7 database.
The reported revision identifies the expected dependency, not a runtime Git check.

Expose only `info`, `execute` and `status` from `private.checklist.bridge` through
the application adapter. The existing connector user/group and company binding
are reused. Configure a separate `PRIVATE_CHECKLIST_SIGNING_KEY` of at least
32 bytes on both ends; do not reuse customer tokens or put the key in source.

Receiver validation checks signed tenant/company, target IDs, separate actors,
expiry, complete payload schema, source digests and step offsets. It verifies the
current company/customer/opportunity/assignee relationship before creation.
Documents themselves remain in the document system; the receiver trusts signed
domain approval and cannot independently prove source-text correctness.

The implementation uses a fresh READ COMMITTED transaction and conservative
table locks to serialize binding/mapping changes and receipt allocation. An
activity with escaped full checklist JSON and its receipt commit together.
Operation ID is unique; tenant/proposal is also unique to reject a replay using
a different operation ID. Matching retries read the existing receipt. Read-back
checks the actual activity note, assignee, opportunity and customer mapping.
No direct user ACL is granted to the receipt model.

Tests execute the standalone validation/rendering rules and parse addon Python
syntax. They do not import an Odoo ORM stub or claim database correctness.
Pending isolated acceptance: install/upgrade, access rights, JSON-2 authentication,
company isolation, HTML sanitization, concurrent duplicate submissions, rollback
between activity/receipt creation, response loss, actual read-back and recovery.
Odoo's HTML sanitizer may require a rendering adjustment after native testing;
the current read-back fails closed on unexpected markup changes.

The application still refuses to connect this adapter to the memory ledger.
Persistent source/approval/operation coordination must be complete before live use.
