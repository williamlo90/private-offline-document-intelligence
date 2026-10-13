"""Add the frozen API image and Phase 8 lab installer to a complete offline bundle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from backend.skills import BundleManifest


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "local/offline-bundles/phase8-candidate"
UPSTREAM = ROOT.parent / "02 - Odoo Business Operations MCP Server/odoo/addons/ops_bridge"
IMAGE_ID = "sha256:97308d0926258c7ada1ae3cd09c8023f2c8a8f2068604c876ce8bc8e1a2b4966"


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            sha.update(block)
    return sha.hexdigest()


def main() -> None:
    manifest_path = BUNDLE / "manifest.json"
    document = json.loads(manifest_path.read_text())
    if any(item["id"].startswith("phase8-") for item in document["artifacts"]):
        raise RuntimeError("Phase 8 bundle extension already recorded")
    actual_id = subprocess.check_output(["docker", "image", "inspect", "private-documents-api:phase7",
                                         "--format", "{{.Id}}"], text=True).strip()
    if actual_id != IMAGE_ID:
        raise RuntimeError("API image does not match accepted Phase 7 candidate")
    assets = [("phase8-api-image", BUNDLE / "api-image-phase7.tar", "api-image-phase7.tar"),
              ("phase8-compose", ROOT / "deploy/compose.phase8-lab.yaml", "phase8/compose.phase8-lab.yaml"),
              ("phase8-provision", ROOT / "scripts/phase8_provision.py", "phase8/phase8_provision.py")]
    for source in sorted(UPSTREAM.rglob("*")):
        if source.is_file() and "__pycache__" not in source.parts and source.suffix != ".pyc":
            relative = source.relative_to(UPSTREAM).as_posix()
            assets.append(("phase8-ops-" + relative.replace("/", "-").replace(".", "-"),
                           source, "upstream/ops_bridge/" + relative))
    if len(assets) != 7:
        raise RuntimeError("Unexpected Odoo upstream addon file count")
    for identifier, source, relative in assets:
        if source.is_symlink() or not source.is_file():
            raise RuntimeError("Missing release asset: " + identifier)
        target = BUNDLE / relative
        if source != target:
            if target.exists():
                raise RuntimeError("Refusing to overwrite release asset: " + relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        document["artifacts"].append({"id": identifier, "path": relative,
                                       "sha256": digest(target)})
    BundleManifest.model_validate(document)
    manifest_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "phase8_release_frozen", "artifacts": len(document["artifacts"]),
                      "api_image_id": IMAGE_ID, "upstream_addon_files": 4}))


if __name__ == "__main__":
    main()
