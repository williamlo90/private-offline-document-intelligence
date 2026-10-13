# Phase 4 — MCP dan kontrak Odoo

**Gate kontrak lokal lulus (2026-10-12).** Sepuluh tool TypeScript MCP memakai
SDK stdio nyata dan endpoint FastAPI bersama: search, extract, answer, prepare
checklist, runtime health, preview tujuan Odoo, inspect operation, approval
tujuan, dispatch sekali, dan verify/read-back. Identity berasal dari proses MCP
dan token server; argumen tool tidak dapat memilih tenant atau target Odoo.

Reference client menjalankan SDK stdio terhadap FastAPI native dengan dua tenant
dan bridge sintetis. Kasus yang lulus mencakup schema/field tambahan, scope,
instruksi berbahaya dalam dokumen, timeout/cancellation, approval oleh aktor
berbeda, perubahan sumber setelah preview, respons dispatch hilang, read-back,
replay tanpa dispatch kedua, dan penolakan akses lintas tenant. Tes transport
memastikan redirect, respons terlalu besar dan error internal tidak diteruskan.
Regresi backend: 139 tes lulus; build TypeScript dan tiga suite MCP lulus.

Kontrak Odoo memakai revision Proyek 02
`6a55b9dc61acd87e61b3aacb4da97d61af84b0fa` untuk Odoo Community 19.0.
Ekstensi milik proyek ini memetakan company ke `res.company`, customer ke
`res.partner`, opportunity ke `crm.lead`, assignee ke `res.users`, dan checklist
lengkap beserta versi/sumber/operator ke note `mail.activity`, dengan receipt
terpisah. Preview mengikat tujuan dan hash; dua approval berbeda diperlukan.
Operation ledger mencatat dispatch sebelum call, memperlakukan hasil transport
yang hilang sebagai unknown, lalu hanya melakukan status/read-back untuk
rekonsiliasi. Kembalinya external ID saja tidak cukup untuk success.

Evidence lokal: `local/phase-4/mcp-stdio.json`, `mcp-save-stdio.json`,
`mcp-boundaries.json`, `backend-tests.xml`, dan `upstream-contract-audit.json`.
Mereka membuktikan protokol dan kontrak pada harness, **bukan koneksi Odoo**.
Ledger harness hilang setelah restart; adapter HTTP bertanda tangan menolak
ledger tersebut. Wiring persistence PostgreSQL, penerimaan addon Odoo, dua
company nyata, dan recovery lintas restart adalah acceptance Phase 7 sebelum
live dispatch diaktifkan. Membuat activity tidak berarti pekerjaan IT selesai.
