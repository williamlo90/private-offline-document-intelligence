"""Refresh the not-yet-accepted Phase 8 lab plan before first deployment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from backend.skills import BundleManifest


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "local/offline-bundles/phase8-candidate"
STAGED = ROOT / "local/phase-8/releases/candidate"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    paths = (("phase8-provision", ROOT / "scripts/phase8_provision.py", "phase8/phase8_provision.py"),
             ("phase8-runtime-overlay", ROOT / "deploy/compose.phase8-runtime.yaml",
              "phase8/compose.phase8-runtime.yaml"),
             ("phase8-loopback-bridge", ROOT / "scripts/phase8_loopback_bridge.py",
              "phase8/phase8_loopback_bridge.py"),
             ("phase8-offline-acceptance", ROOT / "scripts/phase8_accept_offline.py",
              "phase8/phase8_accept_offline.py"),
             ("phase8-restore-probe", ROOT / "scripts/phase8_restore_probe.py",
              "phase8/phase8_restore_probe.py"),
             ("phase8-network-audit", ROOT / "scripts/phase8_audit_network.py",
              "phase8/phase8_audit_network.py"),
             ("phase8-model-seed", ROOT / "scripts/phase8_seed_model_volume.py",
              "phase8/phase8_seed_model_volume.py"),
             ("phase8-resource-sample", ROOT / "scripts/phase8_resource_sample.py",
              "phase8/phase8_resource_sample.py"),
             ("phase8-operator-guide", ROOT / "docs/PHASE-8-DELIVERY.md",
              "phase8/OPERATOR.md"),
             ("phase8-browser-test", ROOT / "frontend/tests/phase8-offline.mjs",
              "phase8/phase8-offline-browser.mjs"),
             ("phase8-mcp-test", ROOT / "mcp/tests/phase8-offline.mjs",
              "phase8/phase8-offline-mcp.mjs"),
             ("phase8-scan-fixture", ROOT / "local/phase-7/atlas-restore-scan.pdf",
              "phase8/atlas-restore-scan.pdf"),
             ("phase8-text-fixture", ROOT / "evaluation/development/atlas-backup-v1.pdf",
              "phase8/atlas-backup-v1.pdf"))
    for target in (BUNDLE, STAGED):
        document = json.loads((target / "manifest.json").read_text())
        artifacts = {row["id"]: row for row in document["artifacts"]}
        for identifier, source, relative in paths:
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            row = {"id": identifier, "path": relative, "sha256": sha(destination)}
            if identifier in artifacts:
                artifacts[identifier].update(row)
            else:
                document["artifacts"].append(row)
        BundleManifest.model_validate(document)
        (target / "manifest.json").write_text(json.dumps(document, indent=2) + "\n")
    if sha(BUNDLE / "manifest.json") != sha(STAGED / "manifest.json"):
        raise RuntimeError("Bundle and staged release manifests diverged")
    release = STAGED / "release.json"
    record = json.loads(release.read_text())
    if record.get("status") != "staged; runtime smoke required before activation":
        raise RuntimeError("Refusing to change activated release")
    record["manifest_sha256"] = sha(STAGED / "manifest.json")
    release.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"status": "staged_plan_refreshed", "artifacts": len(document["artifacts"]),
                      "manifest_sha256": record["manifest_sha256"]}))


if __name__ == "__main__":
    main()
