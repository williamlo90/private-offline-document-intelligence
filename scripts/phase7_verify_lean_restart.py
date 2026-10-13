"""Verify a real Phase 7 save survives API restart without another Odoo effect."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import psycopg

from scripts.phase7_accept_odoo import counts


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local/phase-7"


def main() -> None:
    output = LOCAL / "lean-restart-recovery.json"
    if output.exists():
        raise RuntimeError("Refusing to overwrite restart evidence")
    config = json.loads((LOCAL / "db-config.json").read_text())
    with psycopg.connect(**{key: config[key] for key in ("host", "port", "dbname", "user", "password")},
                         autocommit=True) as conn:
        with conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id','atlas',true), "
                         "set_config('app.actor_id','atlas-service_manager',true)")
            row = conn.execute("SELECT id::text, external_id FROM save_operations "
                               "WHERE tenant_id='atlas' AND status='verified' "
                               "ORDER BY created_at DESC LIMIT 1").fetchone()
            assert row is not None
    operation_id, external_id = row
    identities = json.loads((LOCAL / "lab-identities.json").read_text())
    token = next(actor["token"] for actor in identities["actors"]
                 if actor["id"] == "atlas-service_manager")
    before = counts()
    with httpx.Client(base_url="http://127.0.0.1:8077", timeout=30, trust_env=False,
                      headers={"Authorization": "Bearer " + token}) as client:
        assert client.get("/health").json()["persistence"] == "postgres-lab"
        read = client.get(f"/save-operations/{operation_id}")
        assert read.status_code == 200
        assert read.json()["status"] == "verified" and read.json()["external_id"] == external_id
        replay = client.post(f"/save-operations/{operation_id}/dispatch")
        assert replay.status_code == 200
        assert replay.json()["status"] == "verified" and replay.json()["external_id"] == external_id
    assert counts() == before
    evidence = {"status": "passed", "api_process_restarted": True,
                "persistent_ledger_readable": True, "operation_id": operation_id,
                "external_id": external_id, "replay_same_external_id": True,
                "odoo_receipt_count_unchanged": True, "scope": "API process restart only; not VM reboot"}
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
