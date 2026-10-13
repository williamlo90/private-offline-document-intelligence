# Reusable Business Skills

Diperbarui 2026-10-12. Status implementasi Phase 3 tervalidasi pada harness lokal; checklist umum di bawah adalah kontrak lanjutan, bukan klaim acceptance seluruh stack. Urutan dan gate mengikuti [PHASES.md](PHASES.md) serta [aturan eksekusi lokal](../LOCAL-FIRST-EXECUTION.md).

Skills adalah kemampuan aplikasi executable, bukan kumpulan prompt. Setiap paket mempunyai `skills/<name>/SKILL.md`, JSON Schema, binding implementasi dan tests.

Keempat skill mempunyai binding Python, JSON Schema, endpoint HTTP dan tests.
Answer/extraction menggunakan Ollama native saat profil proyek diaktifkan;
default tanpa profil tetap mengembalikan 503 untuk generation. Hasil development
native serta batasnya tercatat pada [Phase 3](docs/PHASE-3.md). UI checklist
versi-terikat memakai binding bersama. Audit hanya memverifikasi aset manifest
lokal; cold start/network/runtime keseluruhan belum lulus. Konsumsi MCP/worker
dan evaluasi held-out adalah pekerjaan fase berikutnya.

| Skill | Input | Output | Batas |
| --- | --- | --- | --- |
| `extract_service_terms` | authorized document/version | cakupan, pengecualian, SLA/kewajiban + kutipan | read-only, tidak menafsirkan hukum |
| `answer_client_question` | question + authorized corpus | jawaban bersumber atau abstention/conflict | local inference dan retrieval |
| `prepare_service_checklist` | SOP + scoped context | draft checklist + sumber/versi | tidak menjalankan pekerjaan IT |
| `audit_offline_readiness` | runtime manifest | dependency/network/health evidence | admin only; tidak membuka egress |

## Isi paket

- [ ] Masalah bisnis, owner, kapan dipakai/tidak dipakai, preconditions, langkah dan exceptions.
- [ ] Versioned schema dan Python implementation binding; business rules tidak diduplikasi pada prompt.
- [ ] Minimum tools/permissions, timeout, cancellation, retry limits dan source provenance.
- [ ] Fixtures normal/ambiguous/failure, reference outcomes independen dari generation.
- [ ] Compatibility/changelog serta correctness, latency dan resource metrics.

UI/MCP dan worker harus memanggil implementasi yang sama. Tenant kedua memakai config/permissions berbeda, bukan copy logic. Approved-save/read-back ke Odoo adalah domain/MCP operation yang memakai checklist hasil skill; agent tidak dapat memberi approval sendiri. Hosted benchmark extension tidak mengubah permissions atau masuk profil privat.
