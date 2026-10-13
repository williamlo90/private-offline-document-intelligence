# Document watcher/worker — local harness

`backend/document_worker.py` polls an explicit operator-owned source manifest,
hashes bounded PDF inputs and invokes the existing isolated parser and authorized
domain ingestion. Each source has an ID, relative path, title, OCR language and
optional effective/expiry dates and family. Up to 100 configured sources are
supported, with at most ten pending jobs per poll and one parser at a time.

The worker checks current identity grants before reading a source, rejects paths
outside the configured root and rechecks the file hash before and after parsing.
Current source bytes and metadata changes create new document versions. Keyword
search follows the current domain documents; persistent vector indexing is pending.

Checkpoint JSON contains job metadata only. An OS file lock prevents overlapping
polls using the same checkpoint. Attempt count is fsynced before parsing and the
checkpoint is atomically replaced after processing. Transient parser busy/timeout
and source-change failures retry with bounded backoff, at most three attempts per
input/configuration revision. Permanent errors and poor OCR go to review.
Missing files do not automatically delete documents. Distinct checkpoint files
are not a distributed queue or global parser-concurrency mechanism.

Run `python -m scripts.run_document_worker --config <local-watch-config.json>`
for one poll, or add `--watch` for polling. `PRIVATE_LAB_CONFIG` supplies the
existing server-owned identity profile. The watch config supplies `actor_id`,
`root`, `checkpoint`, `sources` and optional `poll_seconds` (5-60).
Keep source roots/checkpoints writable only by the operator; this is not a
hostile-filesystem sandbox. No worker is automatically started by this change.

Set `PRIVATE_WORKER_CONFIG` on the native API process to attach the same watcher
to its repository at startup. It polls in one background thread, so ingested
versions immediately appear in that API's keyword search and source review
queue. Review entries for missing files remain visible without pretending the
source document exists. The standalone CLI still uses its own memory harness;
it does not populate a separate running API process. A saved done checkpoint
is reprocessed if the current domain repository has lost that document. Source
identity must match the checkpoint. No proposal/approval/Odoo operation is created.

Tests cover actual native text PDFs, version updates, repository reset,
retry limits, checkpoint identity, scope denial, unsafe paths, queue bound, OS
lock, changes during parsing and in-process API/review integration. Persistent
repository, eager vector worker and OS reboot/disk-full recovery remain Phase 7
acceptance work. Native vector search rebuilds stale versions on its next search.
