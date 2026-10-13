# Local AI and Provider Profiles

Diperbarui 2026-10-13. Status: profil Ollama lokal tervalidasi dalam [lab Phase 8](docs/PHASE-8-DELIVERY.md). Target dan opsi provider lain di bawah bukan klaim implementasi; [rencana fase](PHASES.md) mencatat batasnya.

## Profil produk V1

**Wajib:** satu model Ollama dengan local OCR, embeddings, tokenizer dan retrieval yang benar-benar lulus kebutuhan V1. Native inference untuk development; Linux deployment/operational proof dan Docker integration Phase 7. Seluruh pipeline privat tidak boleh fallback ke hosted provider.

**Opsional:** llama.cpp sebagai pembanding; vLLM jika hardware dan kebutuhan serving membenarkan. Tidak harus memasang tiga runtime untuk memenuhi JD yang menyebut alternatif.

**Benchmark extension:** adapter OpenAI/Claude/Grok hanya pada runner/profile terisolasi, data publik/sintetis yang diizinkan, tanpa akses corpus/secrets produk privat. Contract tests dan bounded live canaries menentukan klaim per provider. Extension belum dijalankan tidak memblokir offline-delivered; pengalaman multi-provider utama diperdalam pada #4.

## Acceptance

- [ ] Catat hardware, OS/WSL/VM, model/license/revision/quantization, context limit, runtime dan concurrency.
- [ ] Jalankan inference native nyata sebelum final Docker session; kecil/besar model dipilih berdasarkan kualitas serta resources.
- [ ] Pin checksum seluruh model/OCR/embedding/tokenizer assets; bedakan provisioning online dan operasi offline.
- [ ] Health, warm-up, limits, cancellation, timeout, OOM/unavailable runtime dan safe degradation.
- [ ] Cold start setelah provisioning dengan egress diblokir; cek DNS/HTTP/telemetry/download attempts pada boundary host maupun container. Jangan mengganggu jaringan proyek lain.
- [ ] Phase 7: service startup, reboot lab Linux/VM, restart, model/config rollback, restore dan peak resources. WSL process restart bukan bukti host boot recovery.
- [ ] Ukur kualitas, citations/abstention, end-to-end latency, throughput, RAM/VRAM dan asumsi biaya hardware. Harga API atau biaya listrik yang tidak diukur tidak disebut nol.

Satu runtime lulus lebih penting daripada tiga runtime sekadar terpasang. Native measurements, container results dan optional hosted benchmark dilaporkan terpisah. Model yang menolak semua tugas tidak disebut berkualitas hanya karena tidak melanggar izin.

Cloud opsional Phase 9 tidak mengubah produk utama menjadi dependent pada internet. n8n tidak dibutuhkan pada offline V1.
