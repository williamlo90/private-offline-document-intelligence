"""Join only project-07 synthetic Odoo targets with the local signing key."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.phase7_bootstrap_db import LOCAL


def main():
    source = json.loads((LOCAL / "odoo-config/connections.json").read_text(encoding="utf-8"))
    if set(source) != {"atlas", "birch"}:
        raise RuntimeError("Expected two project-07 synthetic Odoo bindings")
    env = dict(line.split("=", 1) for line in (LOCAL / "compose.env").read_text(encoding="utf-8").splitlines()
               if line and not line.startswith("#"))
    bridges = {}
    for tenant, row in source.items():
        if row["tenant"] != tenant or row["database"] != "private_documents_odoo_lab":
            raise RuntimeError("Odoo connection escaped the isolated lab")
        bridges[tenant] = {"bridge": {"host": "127.0.0.1", "port": row["port"],
                                      "database": row["database"], "tenant": tenant,
                                      "company_id": row["company_id"], "api_key": row["api_key"],
                                      "signing_key": env["PRIVATE_CHECKLIST_SIGNING_KEY"]},
                           "target": {"company_id": row["company_id"],
                                      "customer_id": row["customer_id"],
                                      "opportunity_id": row["opportunity_id"],
                                      "assignee_id": row["assignee_id"]}}
    output = LOCAL / "odoo-bridge-config.json"
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing != {"profile": "project07-connected-odoo-lab", "bridges": bridges}:
            raise RuntimeError("Refusing to replace previously bound Odoo targets")
    else:
        output.write_text(json.dumps({"profile": "project07-connected-odoo-lab",
                                      "bridges": bridges}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "tenants": sorted(bridges),
                      "database": "private_documents_odoo_lab", "secrets_printed": False}))


if __name__ == "__main__":
    main()
