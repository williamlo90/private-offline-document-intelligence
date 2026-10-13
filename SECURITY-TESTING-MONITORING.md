# Access Control, Testing, Monitoring & Documentation

## Urutan eksekusi terbaru

Ikuti [rencana fase](PHASES.md), [bukti lab](docs/PHASE-8-DELIVERY.md) dan [batas keamanan](SECURITY.md). Checklist umum di bawah adalah target operasional, bukan klaim produksi; test double tidak menggantikan connected acceptance.

Proyek 07: **Private / Offline Document Intelligence System**

Tanggal rencana: 2026-10-08. Status: **rencana implementasi; belum ada implementasi baru dalam folder ini**. Checklist hanya dicentang setelah artefak dan verifikasinya tersedia.

## Access control sejak awal

| Role | Izin minimum |
| --- | --- |
| Operator | Membaca scope sendiri, menjalankan assistant, membuat proposal |
| Approver | Menyetujui tindakan dalam batas kewenangan; approval terikat payload/version |
| Administrator | Mengelola koneksi, policy, roles, model/runtime; tidak otomatis memperoleh hak approval bisnis |
| Auditor | Membaca audit/evidence yang disanitasi; tidak mengeksekusi action |
| Worker/service account | Hanya skill/tools dan tenant yang ditugaskan |

Pisahkan tenant dan object-level authorization pada API, MCP, workers, retrieval, cache, export, dan logs. Untuk tindakan penting terapkan pemisahan pengusul/approver sesuai policy. Test environment tidak mengakses data produksi dan destructive tests hanya ke database disposable.

## Kasus wajib spesifik proyek

- [ ] Cold start tanpa internet setelah instalasi
- [ ] Runtime mencoba mengunduh tokenizer/model tambahan
- [ ] Provider hosted di-set sebagai fallback tanpa izin
- [ ] GPU OOM atau CPU-only degradation
- [ ] Dokumen malicious/injection dan file rusak
- [ ] User tanpa akses mencoba mengambil evidence
- [ ] Restore backup dan rollback model tanpa kehilangan provenance

## Lapisan testing

- [ ] Unit: aturan bisnis, schemas, matching/parsing, transitions, permissions, evaluator semantics.
- [ ] Contract: provider, custom MCP protocol, platform API, migrations, skill versions.
- [ ] Integration: PostgreSQL nyata terisolasi, queue/worker, approval/execute/verify, sandbox platform.
- [ ] End-to-end: operator menjalankan UI/client sampai outcome tujuan; negative tests memanggil API langsung.
- [ ] AI quality: frozen labels, held-out cases, wrong/missing evidence, prompt injection, unsupported claims, abstention, regressions.
- [ ] Reliability: duplicate events, lost response, concurrent writes, worker interruption, resource exhaustion, restore dan rollback.

## KPI dan alat ukur

service-term field/document correctness; citation correctness; supported-claim rate; retrieval relevance; appropriate abstention/conflict handling; ACL leakage count; unexpected egress count; cold-start success; p95 latency; throughput; peak RAM/VRAM; local cost assumptions; quality delta per model/runtime.

Setiap report menyertakan code revision dan dirty diff fingerprint bila ada, dataset/version/hash, model/provider/runtime, environment/hardware, workload, durations, sample counts, excluded records beserta alasan, serta expected/observed results. Jangan menggabungkan benchmark berbeda menjadi satu persentase.

Tetapkan workload normal, peak, soak, batas error, resource budget, dan stop conditions sebelum run. p50/p90/p95/p99 dilaporkan per operasi dengan N dan distribusi status; satu upload bukan bukti distribusi tail latency. Ukur achieved rate/dropped work, queue wait, processing completion, dan correctness. Concurrency test harus membuktikan jumlah final effects yang tepat, bukan sekadar semua respons 200/409.

## Monitoring dan troubleshooting

- [ ] Correlation ID dari request sampai outcome; structured logs dengan redaction; metrics untuk errors, queue age, stale sync, model/schema failure, latency, resource usage, dan cost.
- [ ] Business metrics untuk verified completion, review/escalation, false closure/false hold jika relevan, dan perubahan kualitas per versi.
- [ ] Alert test: trigger incident terkontrol, buktikan notification diterima, dan dokumentasikan tindakan operator.
- [ ] Runbook untuk provider outage, expired platform token, failed sync, stuck job, unknown write, database restore, model rollback, dan duplicate incident.
- [ ] Retention dan akses logs/evidence/feedback jelas; raw sensitif disimpan terbatas, public evidence disanitasi.

## Release gate

- Nol bypass izin, cross-tenant leakage, duplicate side effect, dan false-success pada critical scenario suite yang ditetapkan. Nol pada suite terbatas tidak berarti jaminan nol di seluruh produksi.
- Quality thresholds ditentukan per risiko sebelum final evaluation; laporkan coverage serta kasus yang gagal.
- Container/connected evidence lulus pada Phase 7; delivery dan support lokal dimulai Phase 8. Cloud-runtime evidence hanya bila varian Phase 9 dipilih.
- Test yang gagal diselesaikan atau scope dikoreksi dan diverifikasi; tidak menurunkan gate diam-diam setelah melihat hasil.

## Acceptance automation yang dipilih

Release utama diuji tanpa n8n. Uji worker/scheduler/API yang benar-benar dipakai; n8n hanya memiliki acceptance tambahan jika extension secara eksplisit dipilih. Lihat [N8N-AUTOMATION.md](N8N-AUTOMATION.md).

## Kasus MSP dan final offline boundary

- [ ] Jawaban cakupan/pengecualian/SLA merujuk halaman dan versi yang benar; missing/expired/conflicting evidence tidak dijadikan jawaban pasti.
- [ ] Checklist hanya memuat langkah yang didukung SOP dan tenant context; penyimpanan checklist tidak dilaporkan sebagai incident resolution.
- [ ] Doc deletion/access revocation menghapus akses hasil retrieval/cache/export; dua klien dengan istilah serupa tidak tertukar.
- [ ] Native-model tests lebih awal; full-stack Docker/Odoo dan Linux recovery Phase 7. Ulangi kualitas pada retrieval/database nyata.
- [ ] Egress isolation mencakup OCR, tokenizer, embeddings, LLM native host, API, MCP, Odoo dan logs/notifications, bukan hanya satu container.
- [ ] Blokir/observasi jaringan pada lab terisolasi; jangan memutus internet seluruh workstation atau reboot host yang digunakan proyek lain.
