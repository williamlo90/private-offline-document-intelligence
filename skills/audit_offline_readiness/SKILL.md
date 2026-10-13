# Audit offline readiness — contract 1.0

Owner: local administrator. Use to inspect provisioned bundle assets before an
offline drill. Do not use its result as proof of network isolation or runtime
health. Asset verification alone never sets `offline_validated` to true.

Binding: `backend.skills.BusinessSkills.audit_offline_readiness`.
Transport: `POST /skills/audit_offline_readiness` with an empty object.
Input/output: `schema.json`. Administrator role is checked before filesystem
access. The bundle root is server-owned (`local/offline-bundle` in the lab API).
No caller paths, network claims, commands or credentials are accepted.

Read `manifest.json` with schema_version `1.0` and artifacts containing unique
id, relative path and SHA-256. Reject extra fields, traversal, paths outside the
bundle and alternate streams. Stream checksums and return identifiers/statuses,
never file contents or absolute paths. Missing/invalid manifests and missing or
changed assets remain explicit failures. No network access or downloads occur.

An optional `components` map declares artifact IDs for application, runtimes,
packages, OCR assets, embeddings, generative model and licenses. Missing or
unverified categories appear in `pending`. Asset checks do not prove component
semantics or completeness; old manifests without this map report all categories
pending while retaining artifact-check compatibility.

Limits: manifest 100 KB, 100 assets, 2 GiB cumulative reads and a five-second
cooperative budget checked between 1 MiB reads. Cancellation is checked between
artifacts and reads. A blocking filesystem call cannot be preempted by this
budget; use a supervised worker for unresponsive storage. No automatic retries.
The bundle must be operator-owned and immutable during inspection; this is not
a hostile-filesystem sandbox. A sanitized audit event records inspected status.

Validation: native temporary-file checksum/tamper/path/cancellation and HTTP
role tests in `tests/test_skills.py`. Cold start, network boundary, runtime health,
full bundle completeness and worker/MCP integration remain pending. Compatibility:
1.0 adds asset checks only; no claim of a complete offline installation.
