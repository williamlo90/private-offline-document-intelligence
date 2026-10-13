"""Audit only the fresh Phase 8 project network and final image pins."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local/phase-8"
PROJECT = "private-documents-phase8"
NETWORK = PROJECT + "_offline"
SERVICES = ("api", "database", "odoo", "ollama")
IMAGE_ID = "sha256:97308d0926258c7ada1ae3cd09c8023f2c8a8f2068604c876ce8bc8e1a2b4966"


def run(*args: str) -> str:
    return subprocess.run(["docker", *args], check=True, capture_output=True,
                          text=True, timeout=40).stdout.strip()


def main() -> None:
    network = json.loads(run("network", "inspect", NETWORK))[0]
    assert network["Internal"] is True
    containers = {}
    for service in SERVICES:
        name = f"{PROJECT}-{service}-1"
        item = json.loads(run("inspect", name))[0]
        assert item["State"]["Running"]
        assert item["Config"]["Labels"]["com.docker.compose.project"] == PROJECT
        assert set(item["NetworkSettings"]["Networks"]) == {NETWORK}
        assert not any(item["NetworkSettings"]["Ports"].values())
        containers[service] = {"image_id": item["Image"],
                               "started_at": item["State"]["StartedAt"],
                               "host_ports_published": False}
    assert containers["api"]["image_id"] == IMAGE_ID
    probe = ("import socket;s=socket.socket();s.settimeout(2);"
             "\ntry:s.connect(('1.1.1.1',443));raise SystemExit('egress_reachable')"
             "\nexcept OSError as e:assert e.errno==101,e;print('ENETUNREACH')")
    for service, interpreter in (("api", "python"), ("odoo", "python3"), ("ollama", "python")):
        assert run("exec", f"{PROJECT}-{service}-1", interpreter, "-c", probe) == "ENETUNREACH"
    runtime_sha = run("exec", f"{PROJECT}-ollama-1", "sha256sum", "/opt/ollama/bin/ollama").split()[0]
    assert runtime_sha == "1c66ac15d93ba17f2abe47d93262a62290b2233fb3c9b745564b31fd94815bd7"
    log = subprocess.run(["docker", "logs", f"{PROJECT}-ollama-1"],
                         capture_output=True, text=True, check=True, timeout=40)
    assert "Ollama cloud disabled: true" in log.stdout + log.stderr
    bundle = LOCAL / "releases/candidate/manifest.json"
    result = {"status": "passed", "network": NETWORK, "internal": True,
              "services": containers, "external_tcp": "ENETUNREACH from API, Odoo, Ollama",
              "ollama_cloud_disabled": True, "runtime_sha256": runtime_sha,
              "release_manifest_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
              "observation_limit": "Network topology and active TCP probes, not packet capture; "
                                   "temporary host loopback bridge only during browser/MCP acceptance"}
    (LOCAL / "network-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": "passed", "internal": True,
                      "egress": result["external_tcp"]}))


if __name__ == "__main__":
    main()
