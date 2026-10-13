"""Append one bounded resource snapshot for the isolated Phase 8 stack."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "local/phase-8/resource-samples.jsonl"
PROJECT = "private-documents-phase8"


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"restart_warmup", "steady"}:
        raise SystemExit("usage: phase8_resource_sample.py restart_warmup|steady")
    names = [f"{PROJECT}-{service}-1" for service in ("api", "database", "odoo", "ollama")]
    rows = subprocess.check_output(["docker", "stats", "--no-stream", "--format", "{{json .}}",
                                    *names], text=True, timeout=30).splitlines()
    stats = [json.loads(row) for row in rows]
    gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used,memory.free",
                                   "--format=csv,noheader,nounits"], text=True, timeout=15).strip()
    record = {"utc": datetime.now(timezone.utc).isoformat(), "label": sys.argv[1],
              "docker": stats, "gpu_memory_used_free_mib": gpu,
              "scope": "point-in-time samples; not continuous maxima"}
    with OUT.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record) + "\n")
    print(json.dumps({"label": record["label"], "containers": len(stats), "gpu": gpu}))


if __name__ == "__main__":
    main()
