# Synthetic MSP walkthrough

Atlas and Birch are fictional clients. The [review/Odoo screenshot](assets/fieldnote-review.png) captures the real Phase 8 lab browser after Odoo read-back. The three AI-state screenshots below replay synthetic response fixtures through the same React build and FastAPI memory harness; their banner explicitly marks them as illustrative, not new live-model evidence. The [capture script](../frontend/tests/portfolio-capture.mjs) and [hash record](evidence/ui-replay.json) make the visual states repeatable without distributing model assets.

| Question | Visible outcome | Evidence shown |
| --- | --- | --- |
| “What must be recorded during Atlas backup verification?” | [Cited excerpt](assets/fieldnote-cited.png) | “Record the job ID and completion time”, `atlas-backup-v1`, page 1, version 1; source text visible beside it. |
| “What is the monthly service fee?” | [Abstain](assets/fieldnote-missing.png) | No authorized current source supports an answer. |
| “What is the backup retention period?” | [Review](assets/fieldnote-conflict.png) | Two conflicting retention documents appear in the queue. |

1. **Find the evidence.** An Atlas technician uploads a PDF, searches the indexed source and asks the local assistant. The answer includes the exact source/page; a missing answer abstains and conflicting versions enter review.
2. **Keep clients separate.** A Birch identity cannot open the Atlas source. The browser test also observed zero non-loopback requests.
3. **Prepare the work.** The technician proposes a source-backed checklist. A different manager reviews that payload, and another authorized reviewer checks the Odoo destination.
4. **Verify the effect.** The worker records the operation and reads the Odoo activity back. The UI shows the verified receipt and removes the save action to avoid a blind repeat.
5. **Recover.** The same document and receipt survived a full service stop/start; app and Odoo database backups restored into disposable clones.

The original Chromium UI and MCP stdio read path were exercised against the **same** fresh Phase 8 deployment. The new-volume first answer took 5.056 s; after restart it took 17.768 s. A later [no-port profile check](evidence/phase8-no-port-recheck.json) reused its synthetic volumes and verified four running services with no published host ports, blocked egress probes, and read-only cited/abstain/review behavior. The host was not physically air-gapped, and Odoo filestore recovery was not tested. [Evidence and operator commands](PHASE-8-DELIVERY.md).
