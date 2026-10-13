# Phase 5 — native offline gate passed

The local document worker watches an explicit source manifest, records checkpoints
atomically, retries transient parser failures at most three times, and sends
missing/poor-quality sources to review. When `PRIVATE_WORKER_CONFIG` is set on
the native API, it shares that process's repository; current keyword search and
the authorized review queue reflect its ingested versions. Native vector search
rebuilds stale versions lazily on the next search. The API also lists future,
expired, conflicting and poor-OCR sources for operator review.
The UI also exposes the local assistant's exact cited excerpts, abstentions and
source-review reasons, with navigation to the cited version and page.

The project-owned `local/offline-bundles/native-assets-v5` bundle inventories the application, OCR language data,
tokenizer, embedding model, pinned Windows and Linux Ollama archives, generative
model, Ubuntu 24.04 Python/OCR packages, Linux Node runtime, Python wheelhouse,
Node packages and pointers to license metadata. Artifact hashes verify. The
release script staged a copy in a separate local install lab; activation requires
matching runtime acceptance evidence and was not performed. Package metadata
inventory is not a legal clearance review.

In a Linux user/network namespace with only loopback, external DNS and TCP were
unreachable. A fresh venv installed all pinned Python packages from local wheels
without an index. English/Indonesian OCR, embedding inference, API cold start,
MCP stdio and one source-cited assistant task passed there using pinned Ollama
0.40.3 and Qwen3 4B Q4. The assistant smoke verified an exact 60-minute source
span, tenant separation and no unauthorized write. A `strace` sample of the
assistant process tree captured 289 `connect`/`sendto` calls; all parsed IP
destinations were loopback, with no observed external destination. The namespace
also had no external interface, DNS or TCP route. This is native lab evidence,
not container/database/Odoo acceptance or a claim about untraced runs.

Linux systemd templates rendered and passed static syntax verification. Actual
service install/reboot, durable PostgreSQL state, backup/restore of the database,
and full-stack offline acceptance remain Phase 7 work.
