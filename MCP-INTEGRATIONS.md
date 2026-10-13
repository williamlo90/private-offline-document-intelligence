# Custom MCP Server APIs and Database

Diperbarui 2026-10-13. Protokol/kontrak MCP diuji pada harness dan jalur baca MCP stdio diuji pada lab Phase 8; lihat [rencana fase](PHASES.md) dan [bukti Phase 8](docs/PHASE-8-DELIVERY.md).

Client → TypeScript MCP → Python domain API → PostgreSQL/pgvector dan Odoo lokal. MCP tidak menulis tabel secara langsung atau menerima arbitrary SQL dari model.

Sepuluh tool berjalan melalui stdio SDK nyata ke API memory harness; reference
client lulus pemeriksaan schema, tenant, role, source version, approval terpisah,
unknown outcome, read-back dan replay. Lihat [bukti Phase 4](docs/PHASE-4.md).

| Tool | Jenis | Kontrak |
| --- | --- | --- |
| `private.document_search` | read | query → authorized evidence, pages, versions |
| `private.extract_service_terms` | read | document/version → sourced service fields |
| `private.answer_client_question` | read | scoped question → answer/abstention/conflict |
| `private.prepare_checklist` | prepare | SOP/context → versioned checklist proposal |
| `private.prepare_odoo_save` | prepare | approved proposal → destination-bound preview |
| `private.inspect_save` | read | operation ID → scoped preview/status |
| `private.approve_odoo_target` | approval | second manager + exact payload hash |
| `private.save_approved_checklist` | write | approved operation → one dispatch or unknown |
| `private.verify_save` | read-back | operation ID → verified receipt or unknown |
| `private.runtime_health` | read | admin-scoped sanitized health |

- [x] Pin SDK/protocol; uji real stdio client tanpa Docker Phase 4. Remote HTTP hanya jika hosting extension dipilih dan diotorisasi.
- [x] Strict schemas, descriptions, limits, source refs dan stable error codes.
- [x] Server memverifikasi identity, tenant/object scope, source/proposal version, approval dan idempotency; model input bukan otorisasi.
- [x] Uji schema errors, cancellation, timeout, injection, wrong tenant, stale approval, replay dan unknown outcomes.
- [x] Reuse Odoo #2 melalui pinned API/package contract, tanpa copy codebase. Phase 4 memakai contract tests; Phase 7 wajib Odoo nyata dengan data test terisolasi.

Model data: tenant, client, document_version, extraction, chunk/index, answer, checklist_proposal, approval, operation, model_manifest, runtime/hardware_profile, offline_test_run, audit_event.

FK/unique constraints, transaction behavior, migrations, RLS, cache isolation dan concurrent writes diverifikasi pada PostgreSQL nyata Phase 7. Menyimpan checklist bukan bukti eksekusi atau penyelesaian kasus IT.
