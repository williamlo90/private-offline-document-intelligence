# Phase Plan — Private Client Knowledge and Document Assistant for MSPs

Proyek 07, di folder Private - Offline Document Intelligence System. Diperbarui 2026-10-13. Checklist yang dicentang merujuk pada bukti; target operasional di luar lab tetap belum diuji.

Urutan portofolio: **0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8**. Phase 8 adalah serah-terima offline lokal dalam batas lab yang telah dipilih dan diuji; Phase 9 cloud opsional dan selalu terakhir. Ikuti [aturan eksekusi lokal](../LOCAL-FIRST-EXECUTION.md): tidak wajib Docker pada Phase 0–6; testing ringan dan security sejak awal; acceptance database/platform/container dicatat terpisah dari tes native. Gate awal tidak menyatakan integrasi fake sudah live-validated.

## Phase 0 — Scope bisnis dan hardware

- [x] Tetapkan pengguna: teknisi MSP, service manager dan administrator lokal; dua organisasi sintetis dengan dokumen/izin terpisah.
- [x] Tiga tugas V1: mencari cakupan/pengecualian layanan; menjawab prosedur dari SOP; menyiapkan checklist pekerjaan bersumber untuk review dan penyimpanan di Odoo lokal.
- [x] Dokumen V1: SOP, kontrak/SLA dan service runbook PDF teks/scan. Tetapkan bahasa, ukuran, scan quality dan versi yang didukung. Tidak membuat keputusan entitlement atau penafsiran hukum otomatis.
- [x] Inventaris CPU/GPU/RAM/VRAM/disk, license, quantization dan dependency bundle. Tetapkan workload, resource budget dan rubric kualitas sebelum model dipilih.
- [x] Audit reuse parser/review dari AI Document, retrieval/permissions dari Case Resolution bila cocok, serta kontrak Odoo #2. Tidak wajib menunggu #5/#6; import modul terpilih dengan revision jelas, bukan seluruh repo.
- [x] Buat source corpus, expected answers/evidence locations dan kasus missing/conflicting/expired. Catat integrasi nyata yang baru dijalankan Phase 7.

**Gate:** scope, hardware budget, rubric dan dependency map tersedia; Docker belum diperlukan.


Evidence Phase 0: config/scope-v1.json, config/dependency-map.json, evaluation/rubric-v1.json, evaluation/development/manifest.json dan expected.json; verifikasi lokal melalui scripts/verify_phase0.py. Corpus awal: 9 PDF teks, 11 halaman, 13 kasus development. Scan fixtures dan held-out independen disiapkan pada fase berikutnya. Model belum dipilih.

## Phase 1 — Fondasi aplikasi tanpa Docker

- [x] Bangun FastAPI, UI TypeScript/React, PostgreSQL/pgvector migrations dan config/health; jalankan Python/Node sebagai proses lokal.
- [x] Implementasikan identity, roles, tenant/object permissions, audit dan redaction pada API, retrieval, cache serta export sejak awal.
- [x] Buat repository interfaces/test doubles. Native PostgreSQL terisolasi opsional bila sudah tersedia; RLS/transaksi/migrations nyata tetap diuji Phase 7.
- [x] Siapkan Dockerfile/Compose/resource profiles secara statis tanpa build/start.
- [x] Uji schemas, state transitions, API authorization dan UI review dengan fixtures. Secrets tidak masuk Git.

**Gate:** ingest → daftar dokumen berizin → review berjalan pada local harness; jenis persistence dan batas tes dinyatakan.


Evidence Phase 1: docs/PHASE-1.md; 9 backend tests, React build, browser workflow dan static SQL/YAML checks passed. Memory harness only; real database/Odoo/container acceptance pending Phase 7. Retrieval/cache/export belum diimplementasikan dan wajib memakai izin domain saat diperkenalkan.

## Phase 2 — Dokumen, versi dan baseline pencarian

- [x] Bangun parser/OCR lokal dengan page/section provenance, document hash, effective date dan error states.
- [x] Jalankan OCR/embeddings native dengan aset terpasang; batasi file size dan antrekan pekerjaan. Tidak memakai hosted OCR pada profil privat.
- [x] Implementasikan chunking, indexing, deletion/invalidation dan tenant filters; siapkan pgvector adapter dan keyword-search baseline. Database vector nyata diuji Phase 7 bila belum tersedia native.
- [x] Definisikan schema cakupan, pengecualian, prosedur, kewajiban dan SLA; setiap angka/tanggal harus bersumber. Konflik versi ditampilkan, tidak ditebak.
- [x] Implementasikan checklist draft dan approval/version contract; rules tidak bergantung pada model.

**Gate:** parser, provenance, versioning dan deterministic workflow cocok dengan reference outcomes; baseline tanpa generasi AI tersedia.

## Phase 3 — Assistant lokal dan reusable skills

- [x] Pilih satu model Ollama yang memenuhi kualitas dan hardware. Bila gagal, perbaiki model/retrieval/config dan evaluasi ulang; bisa berjalan saja tidak cukup.
- [x] Jawaban memiliki kutipan halaman/bagian; abstain saat bukti kurang; tampilkan dokumen bertentangan/kedaluwarsa.
- [x] Implementasikan skills `extract_service_terms`, `answer_client_question`, `prepare_service_checklist`, `audit_offline_readiness` sesuai REUSABLE-SKILLS.md.
- [x] Jalankan inference native nyata; uji malformed output, unsupported claims, injection, timeout dan resource exhaustion. Permissions tidak ditegakkan lewat prompt.
- [x] Pin model/prompt/schema/artifact checksums; tidak ada hosted fallback. Adapter OpenAI/Claude/Grok hanya benchmark extension terisolasi pada data publik/sintetis, bukan dependency produk offline.

**Gate:** satu tugas AI utuh berjalan native dengan sumber benar; kasus meragukan masuk review. Inference yang belum dijalankan tetap pending, bukan mock-success.

Evidence Phase 3: [hasil dan batas bukti](docs/PHASE-3.md),
`config/ollama-runtime-lock.json`, `local/phase-3/native-development-evaluation.json`,
`local/phase-3/evaluate-supervisor.json`, `local/phase-3/api-smoke.json` dan
`local/phase-3/backend-tests.xml`. Gate development native lulus; held-out,
egress offline serta acceptance stack nyata tetap pada fase berikutnya.

## Phase 4 — MCP dan kontrak Odoo

- [x] Implementasikan custom MCP TypeScript: search/extract, answer, prepare checklist, approved save, verify dan role-scoped runtime health.
- [x] Jalankan reference client melalui protocol stdio nyata tanpa Docker; uji schema, scope, injection, timeout, stale approval dan replay dengan adapter doubles.
- [x] Gunakan konektor #2 melalui API/package contract dipin. Tentukan mapping customer dan activity/task yang tersedia pada edition Odoo lokal terpilih.
- [x] Menyimpan checklist bukan eksekusi pekerjaan IT atau bukti masalah teknis selesai. Source references, dokumen versi dan operator tetap tercatat.
- [x] Implementasikan operation ledger/read-back/unknown-outcome recovery serta company mapping. Acceptance Odoo nyata menunggu Phase 7.

**Gate:** protocol/domain contracts lulus dan adapter siap connected acceptance; fake tidak disebut bukti live integration.

Evidence Phase 4: [hasil dan batas kontrak lokal](docs/PHASE-4.md),
`local/phase-4/mcp-save-stdio.json`, `mcp-boundaries.json`, `backend-tests.xml`
dan `upstream-contract-audit.json`. Real Odoo/PostgreSQL tetap acceptance Phase 7.

## Phase 5 — Offline packaging dan alur operator

- [x] Buat Python watcher/worker untuk dokumen berubah, reindex, checkpoint, bounded retry dan review queue; n8n tidak menjadi dependency.
- [x] Buat manifest aplikasi/OCR/tokenizer/embeddings/model; pisahkan provisioning online dari operasi offline.
- [x] Uji cold start native setelah internet diblokir pada boundary lab terisolasi; cek telemetry/download attempts dan hosted fallback. Jangan memutus jaringan seluruh host atau proyek lain.
- [x] UI menyediakan source viewer, citations, version status, review checklist dan audit; notifikasi lokal tidak membutuhkan SaaS.
- [x] Siapkan installer, Linux service config, backup/restore dan rollback scripts. Container acceptance ada pada Phase 7; reboot lab/VM masuk backlog hardening operasional.

**Gate:** native workflow dan bundle siap evaluasi; bukti offline native dipisah dari acceptance seluruh stack Docker/Odoo.

Evidence Phase 5: [hasil dan batas bukti](docs/PHASE-5.md),
`local/offline-bundles/native-assets-v5/manifest.json`,
`local/phase-5/final-bundle-audit.json`, `offline-ai-api-smoke.json`,
`offline-connect-sendto-audit.json`, `offline-ocr.json`,
`offline-embedding-fresh-venv.json`, `offline-mcp-stdio.json`,
`backend-tests.xml` dan `systemd-static.json`. Worker berbagi repository
native API; keyword current dan vector lazy reindex. Full-stack persistent,
connected Odoo serta restore tetap Phase 7; reboot lab masuk hardening operasional.

## Phase 6 — Evaluasi kualitas sebelum Docker

- [x] Bekukan development/regression dan held-out berdasarkan keluarga dokumen/klien; salinan template tidak dibagi untuk menghasilkan holdout semu.
- [x] Uji scope/exclusions, prosedur/SLA, missing/conflicting/expired evidence, scan buruk, cross-client dan injection; labels berasal dari source documents.
- [x] Ukur field/document correctness, supported claims, citation correctness, retrieval relevance, abstention dan unauthorized disclosures; denominator per kategori jelas.
- [x] Bandingkan dengan keyword/source search. Benchmark manual vs assisted boleh single-operator, dengan correctness setara, active work/wait time terpisah. Tidak perlu demo tester atau klaim customer ROI.
- [x] Tetapkan SLO dan resource budget Phase 7. Native p95/resource observations tidak disebut hasil container/produksi.
- [x] Freeze candidate dan acceptance tertunda; perubahan scope/model untuk memperbaiki kualitas harus dicatat serta diuji ulang.

**Gate:** native AI memenuhi rubric scope; report reproducible. Kualitas retrieval end-to-end tetap diulang pada backend nyata Phase 7.

Evidence Phase 6: [hasil native dan batasnya](docs/PHASE-6.md),
`local/phase-6/quality-summary.json`, `local/phase-6/candidate-freeze.json`.
Semua tujuh split lulus rubric; backend persisten dan acceptance Odoo nyata tetap Phase 7.

## Phase 7 — Validasi prototipe portofolio (revisi 2026-10-13)

**Tujuan:** buktikan alur bisnis, privasi dan kualitas pada lingkungan lokal yang dinyatakan dengan jelas. Hasil fase ini adalah **portfolio-validated prototype**, bukan produk `offline-delivered` atau jaminan ketahanan operasi. Tidak perlu image Ollama resmi bila runtime lokal terpin terbukti.

**Sudah terbukti:**

- [x] PostgreSQL/pgvector nyata: migration, RLS dua klien, indexing/concurrency dan backup/restore lab.
- [x] Odoo 19 nyata: dua company, approval terpisah, save/read-back, replay dan lost-response recovery.
- [x] Demo UI Chromium dan MCP stdio pada profil **terhubung**: PDF → sumber/jawaban → review → Odoo → audit.
- [x] Empat layanan Docker Linux pada jaringan internal: OCR scan, Ollama CUDA lokal, jawaban bersitasi, review/Odoo dan probe egress TCP terblokir. Ini bukti **backend offline**, bukan uji browser/MCP offline atau packet capture telemetry. Inference pertama pada cold start kandidat final timeout; smoke setelah restart API berhasil, sehingga reliabilitas first-request belum terbukti.
- [x] Set sintetis beku pada stack persisten: 7/7 tugas terjawab, 6/6 abstain/review, 14/14 field dan 14/14 sitasi tepat/relevan; ACL lintas klien ditolak. Setelah dipakai memperbaiki relevansi, set ini adalah **regression**, bukan held-out independen untuk kode final.
- [x] Reviewer menerima alert konflik dan OCR buruk melalui queue lokal. Layanan lab proyek dihentikan saat pekerjaan dijeda.

**Penutupan Phase 7 revisi:**

1. [x] Bekukan satu kandidat final. Regresi 154 tes, build dari aset terpin, dan smoke alur offline pada image final lulus setelah recovery startup yang tercatat.
2. [x] Beban singkat kandidat final: satu pengguna normal dan dua pengguna puncak, 20 pencarian, 7 jawaban, antrean terbatas; p95 pencarian 0,030 s, p95 jawaban 30,180 s, queue wait maksimum 18,001 s, nol HTTP error. Sampel RAM/VRAM berada di bawah budget. Soak panjang tidak diwajibkan.
3. [x] Evidence manifest dan ringkasan portofolio membedakan profil UI/MCP terhubung dari backend Docker offline, dataset sintetis dan batas observasi jaringan. Hanya layanan test proyek ini dihentikan dan diverifikasi.

**Gate revisi: lulus sebagai prototipe portofolio** berdasarkan [ringkasan evidence](docs/PHASE-7-PORTFOLIO.md). Pada suite yang dideklarasikan tidak terlihat kebocoran lintas klien, false success atau efek Odoo ganda. Bukti dari profil berbeda tidak digabung menjadi klaim satu demo UI end-to-end offline. First-request cold-start tetap keterbatasan material.

**Di luar gate portofolio:** cold start tanpa intervensi, instalasi bersih dari artefak dan UI/MCP offline penuh menjadi prioritas Phase 8 bila mengejar `offline-delivered` di lab. Reboot VM, simulasi disk-full/OOM seluruh stack, rollback model/config langsung, soak panjang, packet capture telemetry dan support incident adalah hardening lanjutan sesuai kebutuhan operasi; tidak boleh diklaim lulus dari Phase 7 revisi.

## Phase 8 — Serah-terima offline lokal yang ringkas (opsional)

**Tujuan:** buktikan bahwa kandidat Phase 7 dapat dinyalakan dan dipakai ulang secara offline oleh operator lokal, bukan hanya dari developer state. Tiga pekerjaan berikut adalah seluruh gate; gunakan artefak/model terpin dan data sintetis yang sudah ada.

1. [x] **Cold start tanpa restart API manual** pada image final: readiness Ollama memuat model terpin sebelum API menerima trafik. Pada project/volume baru, jawaban pertama bersitasi berhasil dalam 5,056 s; setelah full stop/start berhasil lagi dalam 17,768 s. Dua snapshot resource dicatat; bukan peak kontinu.
2. [x] **Release terpin pada project/volume lab baru:** database/Odoo kosong dimigrasi dan di-seed; runtime/model disalin dari bundle; image API di-load dari tar dengan ID identik. Pada satu deployment internal yang sama, API scan/OCR, sitasi, konflik/abstain dan penolakan lintas klien, Chromium review/Odoo read-back serta MCP stdio lulus. Browser hanya mengakses loopback; layanan aplikasi berada pada jaringan internal dengan probe egress `ENETUNREACH`.
3. [x] **Operator handoff:** quick start, prasyarat aset/citra terpin, checksum, start/stop, troubleshooting, lisensi, batas klaim dan demo English ringkas tersedia. Backup PostgreSQL aplikasi dan Odoo dipulihkan pada clone disposable dengan hitungan dokumen/receipt cocok; start/stop lab diuji. Manifest final mengikat bukti dan status.

**Gate: lulus `offline-delivered (local lab)`** menurut [handoff dan evidence Phase 8](docs/PHASE-8-DELIVERY.md). Ini adalah lab sintetis satu host dengan citra dasar Docker yang telah disiapkan; host tidak di-air-gap. Bukti egress berupa topologi internal dan probe TCP aktif, bukan packet capture menyeluruh. Restore filestore Odoo, produksi/customer support dan reliabilitas jangka panjang belum dibuktikan.

**Tidak wajib untuk gate:** reboot host/VM, soak panjang, simulasi OOM/disk-full seluruh stack, packet capture menyeluruh, upgrade/rollback model, support incident berulang, cloud, runtime tambahan, n8n dan hosted benchmarks. Kerjakan hanya bila ada kebutuhan deployment nyata; jangan mengklaim kemampuan yang belum diuji.

## Phase 9 — Private-cloud opsional dan paling akhir

- [ ] Bila kebutuhan hosting terpisah dipilih, siapkan biaya/resource/privacy, network boundary, secrets dan deployment plan sebelum provisioning.
- [ ] Setelah Phase 0–8 lulus, deploy Azure/private network bila dipilih; ulangi connected acceptance, quality, authorization, alerts, restore dan rollback pada runtime tersebut.
- [ ] Private-network hosted bukan otomatis offline/air-gapped. Klaim zero-egress lokal tidak dipindah ke cloud tanpa pengujian baru.
- [ ] Catat biaya, owner, teardown/maintenance. Bila tidak dipilih: **not selected**; status portofolio atau delivery lokal mengikuti gate-nya sendiri, bukan cloud-pending.

**Gate extension:** cloud-validated hanya setelah bukti runtime tersedia. Produk utama tidak wajib cloud.
