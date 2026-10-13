# Private answers and service checklists from client documents

**Status:** Phase 8 local offline lab handoff passed on synthetic data. Real PostgreSQL/pgvector, Odoo, OCR, Ollama, Chromium UI and MCP stdio ran on one isolated lab deployment. See the [overview](../README.md), [Phase 8 evidence](PHASE-8-DELIVERY.md) and [scope](../PHASES.md).

## The business problem

An MSP technician needs to know what a client contract covers, which exclusions apply and which procedure to follow. Those facts can be spread across contract versions, scanned PDFs and SOPs. Sending the corpus to an external model or returning another client's information is outside the intended private workflow.

## Intended workflow

Local documents are parsed or OCR-processed, indexed with client permissions and retrieved for a specific question. The assistant cites the relevant page and document version, surfaces conflicting or missing evidence and prepares a sourced service checklist. An operator reviews the checklist before it is saved as an Odoo activity/task and read back.

Saving a checklist does not execute an IT change or prove an incident resolved. The system does not make automatic legal or service-entitlement decisions.

## Engineering approach

Python/FastAPI and a TypeScript/React workspace share domain controls with a custom MCP server. PostgreSQL/pgvector stores the production-profile data and retrieval index; native harness results do not establish its transaction or isolation behavior. OCR, embeddings and the selected Ollama model run locally. The existing Odoo connector is reused through a pinned contract with a separate test database.

One local model that meets the task and hardware requirements is sufficient. Additional runtimes and isolated hosted-provider benchmarks are optional extensions. The private product has no hosted fallback and no required n8n dependency.

## Validated lab outcomes

- The first sourced answer on the fresh deployment succeeded without manually restarting the API; model readiness controls startup.
- The same deployment demonstrated scanned-PDF OCR, exact citations, missing/conflicting-evidence handling, tenant isolation, UI review, approved Odoo read-back and MCP stdio access.
- A full stop/start retained documents and the Odoo receipt. App and Odoo database backups restored into separate disposable clones.

The Phase 7 short workload and synthetic quality regression provide bounded performance and correctness evidence for the same API image. No customer time saving or production uptime has been established.

## Delivery

Phase 8 establishes `offline-delivered (local lab)` with pre-provisioned pinned Docker base images. The host was not physically air-gapped; browser requests were restricted to loopback and the application containers had an internal-only Docker network. Odoo filestore restore, customer support, long-running production reliability and model rollback remain outside this claim. Optional private-cloud hosting in Phase 9 needs its own evidence and is not automatically air-gapped.
