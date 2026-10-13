"""Create immutable-looking local lab profiles for container DNS, not public config."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.phase7_bootstrap_db import LOCAL, ROOT


def write_once(path, data):
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != data:
            raise RuntimeError("Refusing to replace a bound container profile: " + path.name)
    else:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main():
    db = json.loads((LOCAL / "db-config.json").read_text(encoding="utf-8"))
    bridge = json.loads((LOCAL / "odoo-bridge-config.json").read_text(encoding="utf-8"))
    model = json.loads((ROOT / "config/ollama-profile.json").read_text(encoding="utf-8"))
    assert db["profile"] == "persistent-postgres-lab"
    assert bridge["profile"] == "project07-connected-odoo-lab"
    db = {**db, "host": "database", "port": 5432}
    bridge = {**bridge, "bridges": {tenant: {**row, "bridge": {**row["bridge"],
              "host": "odoo", "port": 8069}} for tenant, row in bridge["bridges"].items()}}
    model = {**model, "host": "ollama"}
    write_once(LOCAL / "db-config-container.json", db)
    write_once(LOCAL / "odoo-bridge-container.json", bridge)
    write_once(LOCAL / "ollama-container-profile.json", model)
    print(json.dumps({"status": "passed", "container_hosts": ["database", "odoo", "ollama"],
                      "secrets_printed": False}))


if __name__ == "__main__":
    main()
