# Synthetic MSP walkthrough

The [workspace screenshot](assets/fieldnote-review.png) captures the review queue after the Odoo read-back in the Phase 8 local lab. The Atlas and Birch clients are fictional.

1. **Find the evidence.** An Atlas technician uploads a PDF, searches the indexed source and asks the local assistant. The answer includes the exact source/page; a missing answer abstains and conflicting versions enter review.
2. **Keep clients separate.** A Birch identity cannot open the Atlas source. The browser test also observed zero non-loopback requests.
3. **Prepare the work.** The technician proposes a source-backed checklist. A different manager reviews that payload, and another authorized reviewer checks the Odoo destination.
4. **Verify the effect.** The worker records the operation and reads the Odoo activity back. The UI shows the verified receipt and removes the save action to avoid a blind repeat.
5. **Recover.** The same document and receipt survived a full service stop/start; app and Odoo database backups restored into disposable clones.

The Chromium UI and MCP stdio read path were exercised against the **same** fresh Phase 8 deployment. The new-volume first answer took 5.056 s; after restart it took 17.768 s. The app, PostgreSQL, Odoo and Ollama were on a Docker internal network. The host was not physically air-gapped, and Odoo filestore recovery was not tested. [Evidence and operator commands](PHASE-8-DELIVERY.md).
