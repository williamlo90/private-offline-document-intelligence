"""Stage only the CPU Ollama files from the already verified local Linux runtime."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/home/william/project07-lab-runtime/ollama")
DESTINATION = ROOT / "local/phase-7/ollama-cpu"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def main():
    if sys.platform != "linux" or not SOURCE.is_dir() or DESTINATION.exists():
        raise RuntimeError("Expected one-time staging from provisioned Linux runtime")
    selected = []
    for file in sorted(SOURCE.rglob("*")):
        if not file.is_file() or any(part in {"cuda_v12", "cuda_v13", "vulkan"} for part in file.relative_to(SOURCE).parts):
            continue
        selected.append(file)
    total = sum(file.stat().st_size for file in selected)
    if not selected or total > 300 * 1024**2 or shutil.disk_usage(DESTINATION.parent).free < total + 512 * 1024**2:
        raise RuntimeError("CPU runtime staging exceeds resource budget")
    DESTINATION.mkdir(parents=True)
    manifest = {}
    for source in selected:
        relative = source.relative_to(SOURCE)
        target = DESTINATION / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=True)
        manifest[relative.as_posix()] = {"sha256": digest(target), "bytes": target.stat().st_size}
    result = {"version": "0.40.3", "source": str(SOURCE),
              "excluded_accelerators": ["cuda_v12", "cuda_v13", "vulkan"],
              "files": manifest, "total_bytes": total}
    (DESTINATION / "cpu-runtime-manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "staged", "files": len(selected), "bytes": total}))


if __name__ == "__main__":
    main()
