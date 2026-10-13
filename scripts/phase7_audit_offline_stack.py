"""Audit the isolated Phase 7 Docker network without altering host networking."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local/phase-7"
PROJECT = "private-documents-phase7"
NETWORK = PROJECT + "_phase7_offline"
SERVICES = ("api", "database", "odoo", "ollama")


def docker(*args: str):
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          timeout=30, check=True).stdout


def main():
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] not in
                              {"offline-network-audit.json", "final-network-audit.json"}):
        raise SystemExit("usage: phase7_audit_offline_stack.py [final-network-audit.json]")
    out = LOCAL / (sys.argv[1] if len(sys.argv) == 2 else "offline-network-audit.json")
    if out.exists():
        raise RuntimeError("Refusing to overwrite offline network evidence")
    network = json.loads(docker("network", "inspect", NETWORK))[0]
    assert network["Internal"] is True
    containers = {}
    for service in SERVICES:
        name = f"{PROJECT}-{service}-1"
        entry = json.loads(docker("inspect", name))[0]
        assert entry["State"]["Running"] is True
        assert set(entry["NetworkSettings"]["Networks"]) == {NETWORK}
        assert not any(entry["NetworkSettings"]["Ports"].values())
        containers[service] = {"image_id": entry["Image"],
                               "started_at": entry["State"]["StartedAt"],
                               "networks": list(entry["NetworkSettings"]["Networks"]),
                               "host_ports_published": False}
    probe = ("import socket; s=socket.socket(); s.settimeout(2); "
             "\ntry: s.connect(('1.1.1.1',443)); raise SystemExit('egress_reachable')"
             "\nexcept OSError as e: assert e.errno==101, e; print('ENETUNREACH')")
    for service, interpreter in (("api", "python"), ("odoo", "python3"), ("ollama", "python")):
        assert docker("exec", f"{PROJECT}-{service}-1", interpreter, "-c", probe).strip() == "ENETUNREACH"
    logged = subprocess.run(["docker", "logs", f"{PROJECT}-ollama-1"],
                            capture_output=True, text=True, timeout=30, check=True)
    log = logged.stdout + logged.stderr
    assert "Ollama cloud disabled: true" in log
    assert "library=CUDA" in log
    runtime = (LOCAL / "ollama-full/bin/ollama").read_bytes()
    executable_hash = hashlib.sha256(runtime).hexdigest()
    assert executable_hash == "1c66ac15d93ba17f2abe47d93262a62290b2233fb3c9b745564b31fd94815bd7"
    result = {"status": "passed", "network": NETWORK, "internal": True,
              "services": containers, "external_tcp": "ENETUNREACH from API, Odoo, Ollama",
              "host_ports_published": False, "ollama_cloud_disabled": True,
              "ollama_accelerator": "CUDA (daemon log)",
              "staged_runtime_sha256": executable_hash,
              "host_network_modified": False,
              "observation_limit": "Network topology and active TCP probes; no packet capture of attempted telemetry"}
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "internal": True,
                      "services": list(containers), "external_tcp": result["external_tcp"]}))


if __name__ == "__main__":
    main()
