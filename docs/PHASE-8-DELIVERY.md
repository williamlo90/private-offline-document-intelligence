# Phase 8 — local offline lab handoff

**Scope:** a synthetic, single-host local lab. The app, PostgreSQL, Odoo and Ollama run on one Docker `internal` network; the host browser and MCP client use a temporary loopback-only `docker exec` bridge. The host itself was not air-gapped. Pinned PostgreSQL, Odoo and Python base images must be pre-provisioned in Docker's cache before disconnected installation. This is not a customer production or long-running support claim.

## Evidence

The fresh `private-documents-phase8` project used new database, Odoo, runtime and model volumes. A staged checksummed bundle supplied the application, OCR/embedding/model assets, Odoo addon snapshot and final API image tar. The pinned model completed a readiness inference before the API accepted traffic. Its first API answer was sourced in 5.056 s with no manual API restart. The same deployment passed scanned-PDF OCR/indexing, exact citations, missing-evidence abstention, conflict review, cross-client denial, Chromium review and Odoo read-back, and MCP stdio search/answer. API, Odoo and Ollama external TCP probes returned `ENETUNREACH`. App and Odoo PostgreSQL backups restored to disposable clones with matching document and receipt counts. After a full stop/start, the persisted document and Odoo receipt remained and the first answer succeeded in 17.768 s. Two point-in-time resource samples observed up to 2,791 MiB whole-host GPU use and 654.9 MiB Ollama container RAM; these are not continuous maxima. The Odoo filestore was not restored.

Evidence: `local/phase-8/cold-start-new-stack.json`, `offline-api-acceptance.json`, `browser-live.json`, `mcp-live.json`, `network-audit.json`, `restore-acceptance.json`, `restart-acceptance.json`, `resource-samples.jsonl` and `releases/candidate/manifest.json`. These synthetic tests validate only the declared lab. Phase 7's 154 tests and short load test remain tied to the same API image; they were not repeated as a production soak.

**No-port follow-up:** the current source Compose file removes all service port mappings. On 2026-10-13, its four services were recreated on the same Windows Docker host and existing synthetic volumes. Effective Compose config, running container `PortBindings`/`NetworkSettings.Ports`, former host listeners and external TCP probes passed the [sanitized recheck](evidence/phase8-no-port-recheck.json). A temporary loopback bridge then served read-only sourced/abstain/conflict and cross-tenant checks. This does not replace the original fresh-volume acceptance or prove behavior on every Docker host. The original private release bundle's embedded Compose copy predates this source change; regenerate and revalidate a new bundle before treating the revised profile as a fresh-install release.

## Operator quick start (PowerShell, project root)

Provision pinned Docker base images and the GPU runtime while online, then disconnect this lab from external networks. Check Docker Linux/GPU availability and free disk before loading the 2.5 GB model. The release bundle is `local/offline-bundles/phase8-candidate`; its manifest and the final API image ID are pinned. Do not reuse Phase 7 volumes.

```powershell
python -m scripts.release_ops verify local/offline-bundles/phase8-candidate
python -m scripts.release_ops stage local/offline-bundles/phase8-candidate local/phase-8/releases candidate
docker load -i local/phase-8/releases/candidate/api-image-phase7.tar
```

The runtime archive and model must be unpacked into fresh project-owned Docker volumes. `phase8_seed_model_volume.py` verifies each copied model blob and assigns the runtime UID. The runtime extraction uses the bundled `zstd` package inside an offline helper container. The printed runtime SHA-256 must equal `1c66ac15d93ba17f2abe47d93262a62290b2233fb3c9b745564b31fd94815bd7`. Rerunning `prepare` or staging onto an existing target deliberately fails to protect secrets and state.

```powershell
docker volume create private-documents-phase8_project07-phase8-runtime
docker run --rm --network none -v "${PWD}/local/phase-8/releases/candidate:/release:ro" -v 'private-documents-phase8_project07-phase8-runtime:/runtime' --entrypoint sh python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e -c 'set -eu; dpkg-deb -x /release/local/runtime/linux-debs/zstd_1.5.5+dfsg2-2build1.1_amd64.deb /tmp/zstd; /tmp/zstd/usr/bin/zstd -d -c /release/local/runtime/ollama-linux-amd64-v0.40.3.tar.zst | tar -xf - -C /runtime; sha256sum /runtime/bin/ollama'
docker volume create private-documents-phase8_project07-phase8-models
docker run --rm --network none -v "${PWD}/local/phase-8/releases/candidate:/release:ro" -v 'private-documents-phase8_project07-phase8-models:/models' --entrypoint python python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e /release/phase8/phase8_seed_model_volume.py
```

```powershell
python -m scripts.phase8_provision prepare
python -m scripts.phase8_provision migrate
python -m scripts.phase8_provision seed-odoo
$p07Compose = @('compose','-p','private-documents-phase8','--env-file','local/phase-8/compose.env','-f','deploy/compose.phase8-lab.yaml','-f','deploy/compose.phase8-runtime.yaml')
docker @p07Compose up -d --wait --no-build
python scripts/phase8_loopback_bridge.py
```

Run the bridge in a separate local terminal only while an operator is using the UI/MCP. Open `http://127.0.0.1:8078/ui/` and use a Phase 8 synthetic actor token from the ignored `local/phase-8/lab-identities.json`. The browser acceptance test aborts non-loopback requests; the MCP client is configured for that same loopback port. Do not publish these lab tokens or enable the bridge on a public interface.

```powershell
python -m scripts.phase8_accept_offline
node frontend/tests/phase8-offline.mjs
node mcp/tests/phase8-offline.mjs
python -m scripts.phase8_audit_network
python -m scripts.phase8_restore_probe
```

The current Phase 8 Compose profile declares **no published ports**. The temporary bridge is the only intended host listener, bound to `127.0.0.1:8078`; stop it with Ctrl+C when the operator session ends. Check effective Compose configuration and each service's Docker inspect `NetworkSettings.Ports` before use on another Docker host. Start the project again with `up -d --wait --no-build`, then start the bridge if needed. Readiness waits for the model before the API starts. A cold start can take minutes on this laptop because GPU/model initialization is serial. If Ollama remains unhealthy, inspect only this project's Ollama logs and confirm model/runtime checksums, GPU memory, and the internal network. A 504 after readiness is an incident requiring diagnosis; do not call it success. Backups are in the ignored `local/phase-8/backups/` directory. Recovery of Odoo attachments/filestore, host reboot, long soak and upgrade rollback need separate operational evidence.

## Short English demo

An MSP technician uploads a local PDF, searches the source and asks a question. The assistant returns an exact citation or asks for review when evidence conflicts; it abstains when the document does not contain the answer. A Birch identity cannot open the Atlas source. A manager prepares and approves a sourced checklist, a separate reviewer approves the Odoo destination, and the saved Odoo activity is read back and audited. The same deployment also exposes the authorized read path through MCP stdio. All data in this demonstration is synthetic.
