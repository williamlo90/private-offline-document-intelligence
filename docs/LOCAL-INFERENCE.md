# Local inference profile

Phase 3 uses a project-owned Ollama 0.40.3 Windows runtime and one pinned
`qwen3:4b-instruct-2507-q4_K_M` GGUF. The runtime and model assets stay under
ignored `local/`; [the lock](../config/ollama-runtime-lock.json) pins their
checksums, prompt, schema and rubric. The source release and model are linked
there. No hosted fallback or automatic model pull exists.

Run the native supervisor only when this project's GPU has at least 4.5 GiB
free and the host has at least 1.75 GiB free RAM:

```powershell
.venv/Scripts/python.exe -m scripts.run_phase3_lab probe
.venv/Scripts/python.exe -m scripts.run_phase3_lab api_smoke
.venv/Scripts/python.exe -m scripts.run_phase3_lab evaluate
```

The supervisor verifies all model blobs and checks the executable/prompt/schema
pins before launching its dedicated loopback daemon on port 11439. It sets
`OLLAMA_NO_CLOUD=1`, one loaded model, one parallel request and immediate unload.
The adapter disables proxies and redirects, validates the model digest before
and after each generation, and requires an empty loaded-model list before
dispatch. It permits one request per API process and has a 120-second deadline,
1 GiB host RAM runtime reserve and bounded input/output. Failure after dispatch
latches recovery because closing HTTP does not prove inference stopped.

The model selects clauses from server-filtered sources. The server verifies
exact page text and reconstructs offsets, rechecks permissions/version/status,
and returns sourced excerpts or abstention/review. Extraction splits pages into
source sentences before asking the model to classify each clause. It remains
read-only; checklist approval and platform writes are separate contracts.

[Phase 3 results](PHASE-3.md) report native development evidence and limits.
The dedicated native run is not a whole-stack offline egress test, production
resource cap or held-out generalization result. The default API without
`PRIVATE_OLLAMA_PROFILE` returns `native_model_unavailable`; operators must also
start this project's pinned daemon before enabling that profile.
