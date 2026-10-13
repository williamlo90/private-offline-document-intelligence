# Offline bundle preparation

`python -m scripts.build_offline_bundle --output local/<new-bundle-name> --include-local-models` creates
a new, non-overwriting bundle from explicit application directories and lockfiles.
The ZIP uses stable paths, permissions and timestamps for reproducible hashes.
It includes the synthetic seed manifest needed by the current native harness.
Local identity profiles, environment files and virtual environments are excluded.
English/Indonesian OCR language files, pinned Windows/Linux Ollama archives,
model manifest/blobs, embedding model/tokenizer, Ubuntu 24.04 Python/OCR runtime
packages, Linux Node, a Python wheelhouse and the project MCP node packages are
staged as separate artifacts. Node packages are placed in a deterministic ZIP;
the source `node_modules` tree itself is not included in `application.zip`.
Model blob sizes and hashes are checked before staging. No download occurs while
building. Omit `--include-local-models` for a small application-only snapshot.

`manifest.json` lists each artifact's relative path and SHA-256 plus declared
component membership. `inventory.json` records staged and missing components.
The admin readiness skill validates checksums and reports missing components in
`pending`. `assets_verified` only means listed artifacts match their checksums;
it never means the bundle is complete, installable or offline validated.
Component membership is operator-supplied inventory, not semantic validation of
each runtime/model. The manifest itself must be preserved in a trusted release
record; an attacker who changes both an artifact and its checksum is not detected.

The current inventory contains all declared component categories. `licenses` is
a pointer inventory to metadata and text inside bundled wheels, archives, Debian
packages and model layers; it is not legal clearance. Python/OCR Debian packages
target Ubuntu 24.04 amd64 and still rely on that distribution's base libraries.
Verification has an 8 GiB/120 second bound. Checksum success does not establish
installability or no egress; those are separate native and Phase 7 tests.

`python -m scripts.release_ops verify <bundle>` reports manifest completeness.
`stage` refuses partial bundles. `activate` requires a matching `acceptance.json`
from later runtime acceptance; no release is activated by staging. `backup` and
`restore` handle explicit local state directories, restoring into a new empty
target. Database backup/restore and service restart are Phase 7 work.

Tests verify deterministic archives, excluded secrets, refusal to overwrite,
output containment, incomplete-component reporting, artifact tampering and invalid
component references. Build into a fresh local directory after code changes;
existing bundles are immutable snapshots and are not automatically refreshed.
