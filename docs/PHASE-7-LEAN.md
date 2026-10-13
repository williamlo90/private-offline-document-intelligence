# Phase 7: lean connected slice

This records the earlier connected milestone. For the current revised Phase 7 result and its offline backend limits, see [portfolio validation](PHASE-7-PORTFOLIO.md).

The current lab uses native Windows Ollama 0.40.3 and FastAPI with the pinned Qwen3 4B model, plus isolated Docker PostgreSQL/pgvector and Odoo 19 test services. No Ollama Docker image is required for this profile.

One real HTTP run parsed a synthetic PDF, indexed it, produced an exact cited native-model answer, blocked cross-tenant source access, required separate checklist and destination reviewers, saved to Odoo, verified read-back, and returned the same external ID on replay. A real MCP stdio client also searched and answered through this API. A real Chromium browser then uploaded a PDF, searched and opened its source, showed a native-model cited answer, prepared a checklist, completed both human reviews, saved it to Odoo with visible read-back, and confirmed the second client could not see the source. The 153-test backend suite and React build passed. After API process restart, the durable operation remained verified and replay did not create another Odoo receipt. Evidence is in `local/phase-7/lean-vertical-slice.json`, `mcp-live.json`, `browser-live.json`, and `lean-restart-recovery.json`.

This is a connected hybrid lab result. It is not full Phase 7 acceptance: blocked-egress cold start of the complete stack, Linux service/reboot recovery, final-stack quality and load measurements, and fault drills remain pending. An isolated Docker network blocked container egress but also made published database/Odoo ports unreachable from the native host; that trial was reverted, and the connected profile was restored. The API continues to report `offline_validated: false`.
