"""Run inside an offline helper container with /release:ro and /models volume."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil


SOURCE = Path("/release/local/models/ollama")
TARGET = Path("/models")


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def main() -> None:
    if not SOURCE.is_dir() or any(TARGET.iterdir()):
        raise RuntimeError("Model source missing or target volume not fresh")
    for source in sorted(SOURCE.rglob("*")):
        if source.is_symlink():
            raise RuntimeError("Unexpected model symlink")
        target = TARGET / source.relative_to(SOURCE)
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if digest(target) != digest(source):
                raise RuntimeError("Model copy checksum mismatch")
            if target.name.startswith("sha256-") and digest(target) != target.name[7:]:
                raise RuntimeError("Model blob digest mismatch")
    paths = [TARGET, *TARGET.rglob("*")]
    for path in paths:
        os.chown(path, 10001, 10001)
    manifest = next((TARGET / "manifests").rglob("4b-instruct-2507-q4_K_M"))
    print(json.dumps({"status": "model_volume_seeded", "files": sum(p.is_file() for p in paths),
                      "manifest_sha256": digest(manifest), "uid": 10001}))


if __name__ == "__main__":
    main()
