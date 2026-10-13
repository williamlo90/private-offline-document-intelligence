# Security and publication

This is a local synthetic MSP lab, not an internet-facing production service. Do not expose the development API, Odoo bridge or temporary loopback UI bridge to a public interface.

The backend binds actors to server-owned tokens and checks tenant/document scope before source access. Source versions and approval payloads are checked before writes. Odoo saves use an operation ledger and read-back; uncertain outcomes require observation before retry. MCP arguments and model output do not grant authority. A conflicting, missing or stale source requires review or abstention.

Keep `.env`, `local/`, access tokens, signing keys, database volumes/backups, customer documents and private model output out of Git. The public PDFs and screenshot are synthetic. The CI checks forbidden paths and scans Git history for secrets. A clean scan is useful evidence, not a guarantee against arbitrary private content.

The Phase 8 application network was internal-only and active external TCP probes returned `ENETUNREACH` from API, Odoo and Ollama. This does not establish a physically air-gapped host or prove that no packets were attempted. A production deployment needs its own network, backup and operational review.

Report a vulnerability through GitHub's private vulnerability reporting if enabled. Include the revision and a synthetic reproduction; never put secrets or customer data in a public issue.
