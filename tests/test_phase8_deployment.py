"""The offline profile must not publish a service port on any Docker host."""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_phase8_compose_declares_no_published_ports():
    profile = yaml.safe_load((ROOT / "deploy/compose.phase8-lab.yaml").read_text())
    overlay = yaml.safe_load((ROOT / "deploy/compose.phase8-runtime.yaml").read_text())
    assert profile["networks"]["offline"]["internal"] is True
    assert set(profile["services"]) == {"api", "database", "odoo", "ollama"}
    for service in profile["services"].values():
        assert service["networks"] == ["offline"]
        assert "ports" not in service and "network_mode" not in service
    for service in overlay["services"].values():
        assert "ports" not in service and "network_mode" not in service
