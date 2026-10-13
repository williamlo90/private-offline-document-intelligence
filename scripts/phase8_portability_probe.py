"""Probe the revised no-published-port Compose profile on the current host."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import psutil

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "private-documents-phase8"
SERVICES = ("api", "database", "odoo", "ollama")
NETWORK = PROJECT + "_offline"
OLD_PORTS = {5478, 8178, 8078}


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True, timeout=45).strip()


def main() -> None:
    compose = json.loads(docker("compose", "-p", PROJECT, "--env-file",
        str(ROOT / "local/phase-8/compose.env"), "-f", str(ROOT / "deploy/compose.phase8-lab.yaml"),
        "-f", str(ROOT / "deploy/compose.phase8-runtime.yaml"), "config", "--format", "json"))
    assert all(not service.get("ports") for service in compose["services"].values())
    assert compose["networks"]["offline"]["internal"] is True
    containers = {}
    for service in SERVICES:
        item = json.loads(docker("inspect", f"{PROJECT}-{service}-1"))[0]
        assert item["State"]["Running"]
        assert item["Config"]["Labels"]["com.docker.compose.project"] == PROJECT
        assert not item["HostConfig"]["PortBindings"]
        assert not any(item["NetworkSettings"]["Ports"].values())
        assert set(item["NetworkSettings"]["Networks"]) == {NETWORK}
        containers[service] = {"running": True, "host_port_bindings": 0,
                               "published_ports": 0}
    listeners = [dict(ip=conn.laddr.ip, port=conn.laddr.port)
                 for conn in psutil.net_connections(kind="tcp")
                 if conn.status == "LISTEN" and conn.laddr.port in OLD_PORTS]
    assert not listeners, f"Unexpected listener on former Phase 8 port: {listeners}"
    probe = ("import socket;s=socket.socket();s.settimeout(2);"
             "\ntry:s.connect(('1.1.1.1',443));raise SystemExit('egress_reachable')"
             "\nexcept OSError as e:assert e.errno==101,e;print('ENETUNREACH')")
    for service, interpreter in (("api", "python"), ("odoo", "python3"), ("ollama", "python")):
        assert docker("exec", f"{PROJECT}-{service}-1", interpreter, "-c", probe) == "ENETUNREACH"
    result = {"status": "passed", "scope": "reused synthetic Phase 8 volumes on Windows Docker Desktop",
              "profile": "revised no-published-port Compose source", "effective_compose_ports": 0,
              "internal_network": True, "services": containers, "former_host_port_listeners": listeners,
              "egress_probes": "ENETUNREACH from API, Odoo and Ollama",
              "limitations": ["Reused volumes; not a new clean install", "Host itself was not air-gapped",
                              "Port observations are from this Docker host, not a cross-platform guarantee"]}
    target = ROOT / "local/phase-8/port-hardening.json"
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
