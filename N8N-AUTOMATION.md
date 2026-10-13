# Automation Decision — 07 - Private - Offline Document Intelligence System

## Urutan eksekusi terbaru

Ikuti [rencana fase](PHASES.md) dan [panduan delivery](PROJECT-DELIVERY.md). Produk utama memakai worker lokal tanpa n8n. Contoh extension di bawah bukan dependency release yang telah divalidasi.

Status: **rencana; belum menjadi hasil benchmark atau implementasi baru**.

**Keputusan:** Tanpa n8n pada produk offline utama.

**Peran:** Python worker/scheduler lokal, local inference/OCR/embeddings, PostgreSQL dan Odoo lokal. n8n lokal hanya extension jika operator perlu mengubah workflow secara visual.

**Alasan:** Tidak menambah engine hanya untuk timer atau pemanggilan API lokal. Jika extension dipilih, seluruh dependency/notification tetap lokal dan isolation diuji ulang.

Dokumen ini mencatat keputusan proyek 07: n8n tetap extension opsional, bukan bagian dari runtime yang tervalidasi.

## Contoh extension, bukan pekerjaan wajib V1

1. **Workflow utama:** n8n self-hosted pada jaringan lokal menjadwalkan panggilan ke intake API lokal → backend menemukan dokumen lokal baru → OCR, extraction, embeddings, inference dan review berjalan lokal → hasil yang disetujui ditulis ke Odoo lokal.
2. **Monitoring dan tindak lanjut:** Jadwal lokal → backend memeriksa job gagal, kapasitas disk, dan status runtime → n8n membuat notifikasi pada dashboard atau kanal lokal. Uji cold start dan seluruh workflow dengan internet terputus; tanpa node SaaS, hosted inference, atau callback eksternal.

## Ownership dan acceptance

- Pilih pemilik orchestration, retries, approval records dan business state secara eksplisit. Satu operasi bisnis punya satu sumber status otoritatif.
- n8n boleh menjalankan agent, tool calls, branching, wait/approval dan reusable sub-workflows bila cocok. Pembagian Python/n8n adalah keputusan proyek, bukan batas kemampuan n8n.
- Approval dari UI aplikasi maupun workflow harus terikat actor, tenant, payload/version dan kewenangan; penerimaan callback atau teks approved tidak cukup.
- Side effects membutuhkan deduplication/idempotency dan verifikasi hasil. Unknown outcomes direkonsiliasi sebelum retry; state berhasil di engine tidak otomatis berarti masalah bisnis selesai.
- Scope authorization berlaku pada semua jalur: assistant, MCP, worker, automation engine dan direct API.

## Acceptance produk utama

- [ ] Instalasi, workflow utama, protocol/API tests, monitoring, delivery dan deployment lulus tanpa n8n terpasang.
- [ ] Dokumentasikan engine/scheduler yang benar-benar dipilih serta source of truth, retries dan recovery.
- [ ] Tidak ada checklist export workflow atau deployment n8n wajib pada release utama.
- [ ] Jika extension automation dipilih kemudian, catat kebutuhan operator, manfaat, ownership, biaya operasi dan acceptance terpisah sebelum menjadikannya dependency.

Contoh extension di atas tidak boleh mengubah status release utama menjadi belum selesai. n8n yang tidak dipilih dilaporkan not selected, bukan implementation failure.
