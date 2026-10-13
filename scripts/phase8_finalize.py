"""Close only the revised Phase 8 local-lab delivery gate from real evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

from scripts.release_ops import verify


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local/phase-8"
PROJECT = "private-documents-phase8"
IMAGE_ID = "sha256:97308d0926258c7ada1ae3cd09c8023f2c8a8f2068604c876ce8bc8e1a2b4966"
EVIDENCE = ("cold-start-existing-stack.json", "cold-start-new-stack.json",
            "offline-api-acceptance.json", "browser-live.json", "mcp-live.json",
            "network-audit.json", "restore-acceptance.json", "restart-acceptance.json")


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def main() -> None:
    evidence = {name: json.loads((LOCAL / name).read_text()) for name in EVIDENCE}
    assert all(item["status"] == "passed" for item in evidence.values())
    cold = evidence["cold-start-new-stack.json"]
    assert cold["api_image_id"] == IMAGE_ID and cold["api_restart_count"] == 0
    assert cold["first_answer_without_manual_restart"]
    api = evidence["offline-api-acceptance.json"]
    assert all(api[key] for key in ("native_ocr_and_index", "first_model_answer_sourced",
                                    "exact_citations", "other_tenant_denied",
                                    "missing_abstained", "conflict_reviewed"))
    browser = evidence["browser-live.json"]
    assert browser["offline_tested"] and browser["page_errors"] == 0
    assert browser["nonlocal_browser_requests"] == 0 and browser["odoo_readback_visible"]
    mcp = evidence["mcp-live.json"]
    assert mcp["authorized_search"] and mcp["native_sourced_answer"]
    network = evidence["network-audit.json"]
    assert network["internal"] and network["external_tcp"] == "ENETUNREACH from API, Odoo, Ollama"
    assert network["services"]["api"]["image_id"] == IMAGE_ID
    restore = evidence["restore-acceptance.json"]
    assert set(restore["database_backups"]) == {"app", "odoo"}
    for row in restore["database_backups"].values():
        assert row["source_rows"] == row["restored_rows"] >= 1
    restart = evidence["restart-acceptance.json"]
    assert restart["phase8_services_stopped_before_restart"] == 0
    assert restart["persistent_document_read"] and restart["first_answer_after_restart_sourced"]
    assert restart["phase8_services_stopped_after_checks"] == 0
    resource_path = LOCAL / "resource-samples.jsonl"
    samples = [json.loads(line) for line in resource_path.read_text().splitlines()]
    assert {row["label"] for row in samples} >= {"steady", "restart_warmup"}
    assert all(len(row["docker"]) == 4 for row in samples)
    release = LOCAL / "releases/candidate"
    manifest, missing = verify(release)
    assert not missing and len(manifest.artifacts) >= 99
    for source, staged in ((ROOT / "deploy/compose.phase8-lab.yaml", release / "phase8/compose.phase8-lab.yaml"),
                           (ROOT / "deploy/compose.phase8-runtime.yaml", release / "phase8/compose.phase8-runtime.yaml"),
                           (ROOT / "scripts/phase8_provision.py", release / "phase8/phase8_provision.py")):
        assert digest(source) == digest(staged)
    image = subprocess.check_output(["docker", "image", "inspect", "private-documents-api:phase7",
                                     "--format", "{{.Id}}"], text=True).strip()
    assert image == IMAGE_ID
    running = subprocess.check_output(["docker", "ps", "--filter",
        f"label=com.docker.compose.project={PROJECT}", "--format", "{{.Names}}"], text=True).strip()
    assert not running
    plan = (ROOT / "PHASES.md").read_text(encoding="utf-8")
    phase8 = plan.split("## Phase 8 —", 1)[1].split("## Phase 9 —", 1)[0]
    assert phase8.count("[x]") == 3 and "[ ]" not in phase8
    files = [*(LOCAL / name for name in EVIDENCE), resource_path, release / "manifest.json",
             ROOT / "PHASES.md", ROOT / "README.md", ROOT / "docs/PHASE-8-DELIVERY.md"]
    record = {"status": "offline_delivered_local_lab", "scope": "synthetic single-host lab; not production support or physical air-gap",
              "api_image_id": IMAGE_ID, "model_digest": cold["model_digest"],
              "release_artifacts_verified": len(manifest.artifacts),
              "project_services_running": 0,
              "evidence_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): digest(path)
                                  for path in files},
              "limits": ["Pre-provisioned Docker base images required",
                         "Host was not air-gapped; browser blocked non-loopback requests",
                         "Odoo filestore restore, long soak, host reboot and model rollback not tested"]}
    output = LOCAL / "final-evidence-manifest.json"
    if output.exists():
        raise RuntimeError("Refusing to overwrite final Phase 8 manifest")
    output.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"status": record["status"], "release_artifacts_verified": len(manifest.artifacts),
                      "project_services_running": 0}))


if __name__ == "__main__":
    main()
