# Odoo lokal untuk checklist pekerjaan MSP

Diperbarui 2026-10-13. Kontrak Phase 4 dan Odoo lab Phase 7–8 telah diuji; lihat [rencana fase](PHASES.md) dan [bukti Phase 8](docs/PHASE-8-DELIVERY.md). Ini bukan klaim Odoo produksi.

**Platform:** Odoo lokal pada jaringan privat yang sama. Profil offline tidak memakai Odoo SaaS atau Microsoft 365.

**Alur:** pertanyaan/SOP klien → evidence → checklist proposal → review → approved save ke customer activity/task → read-back dan audit. Q&A tetap bisa digunakan tanpa write; delivery V1 tetap mencakup satu connected Odoo workflow.

- [x] Pilih entity/edition/API pada kontrak Odoo Community 19.0 terpin (customer + CRM opportunity + activity); cek runtime nyata Phase 7.
- [x] Reuse kontrak konektor #2; catat IDs, company mapping, source-of-truth, timestamps dan version rules.
- [x] Payload menyimpan checklist/source references yang disetujui, bukan credentials atau isi semua dokumen tanpa kebutuhan.
- [x] Approval terikat actor, tenant, payload dan versi sumber. Perubahan SOP setelah approval membutuhkan review baru.
- [x] Idempotency, ledger dan read-back menentukan success pada harness; timeout dapat berarti unknown; rekonsiliasi sebelum retry.
- [x] Phase 4 menyiapkan adapter/contract fixtures tanpa Docker. Phase 7 memakai Odoo lokal nyata pada database test khusus, termasuk dua company, duplicate/replay, source drift dan interrupted write.
- [ ] Buktikan offline workflow, local notifications serta failure/recovery tanpa external callbacks.

Simpan sanitized external ID, approval ID, source versions, expected/observed state dan effect counts. Tidak mengubah instance/data kerja #2. Tidak perlu customer sungguhan atau orang lain mencoba demo.
