# AI Assistant untuk dokumen klien MSP

Diperbarui 2026-10-13. Status: Phase 8 lulus dalam batas lab sintetis lokal; [rencana fase](PHASES.md) dan [hasil delivery](PROJECT-DELIVERY.md) membedakan bukti aktual dari target lanjutan. Phase 9 cloud opsional.

## Tugas

- Jawab cakupan, pengecualian, prosedur dan kewajiban layanan dari dokumen yang diizinkan, dengan kutipan halaman/bagian dan versi.
- Tunjukkan konflik, expired sources dan informasi yang tidak tersedia. Jangan mengarang syarat layanan atau menyembunyikan ketidakpastian.
- Siapkan checklist kerja dari SOP dan konteks klien untuk operator review; simpan approved checklist ke Odoo lokal melalui kontrol domain.
- Tidak mengeksekusi tindakan IT, memperluas akses, membuat approval sendiri atau menyatakan incident resolved karena checklist tersimpan.

## Kontrak

Input membawa authenticated actor, tenant dan document references; scope diturunkan dari server, bukan prompt. Output berisi status, source-linked facts, missing/conflicting evidence dan proposed checklist. Confidence bukan izin bertindak.

Python menegakkan auth, arithmetic, state, approval/version dan idempotency. Dokumen adalah input tak tepercaya; prompt injection tidak dapat membuka tools/tenant lain. Agent memakai allowlisted tools, step/time limits dan terminal states yang jelas.

## Artefak

- [ ] UI/source viewer untuk jawaban, kutipan, versi, checklist dan audit.
- [ ] Typed assistant contracts, prompt/model/schema versions, timeout/cancellation dan safe errors.
- [ ] Skills executable dipakai UI/MCP dan worker dengan core logic sama.
- [ ] Scenario tests: normal, no answer, conflicting version, malicious PDF, wrong tenant, Odoo failure.
- [ ] Trace menghubungkan task, document/model versions, approval dan observed outcome tanpa raw secrets.

Python worker/scheduler merupakan engine utama. Ollama native dipakai lebih awal; final offline boundary termasuk inference host, database, OCR, embeddings dan Odoo diuji Phase 7. Tidak ada hosted fallback/n8n dependency.
