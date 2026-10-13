"""Live two-company Odoo JSON-2 acceptance with durable one-shot dispatch."""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg

from backend.main import load_app


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local/phase-7"


def counts():
    env = dict(line.split("=", 1) for line in (LOCAL / "compose.env").read_text(encoding="utf-8").splitlines()
               if line and not line.startswith("#"))
    with psycopg.connect(host="127.0.0.1", port=5477, dbname="private_documents_odoo_lab",
                         user="private_documents_odoo", password=env["PRIVATE_DOCUMENTS_ODOO_DB_PASSWORD"]) as conn:
        return dict(conn.execute("SELECT tenant,count(*) FROM private_checklist_receipt GROUP BY tenant").fetchall())


def main():
    output = LOCAL / "odoo-connected-acceptance.json"
    if output.exists():
        raise RuntimeError("Refusing to overwrite connected Odoo evidence")
    os.environ["PRIVATE_LAB_CONFIG"] = str(LOCAL / "lab-identities.json")
    os.environ["PRIVATE_DB_CONFIG"] = str(LOCAL / "db-config.json")
    os.environ["PRIVATE_ODOO_CONFIG"] = str(LOCAL / "odoo-bridge-config.json")
    identities = json.loads((LOCAL / "lab-identities.json").read_text(encoding="utf-8"))
    tokens = {actor["id"]: actor["token"] for actor in identities["actors"]}

    def call(client, actor, method, path, **kwargs):
        return client.request(method, path, headers={"Authorization": "Bearer " + tokens[actor]}, **kwargs)

    def expect(response, status):
        assert response.status_code == status, (response.status_code, response.json().get("error"))
        return response.json()

    def create_and_approve(client, tenant):
        technician, manager, reviewer = (f"{tenant}-technician", f"{tenant}-service_manager", f"{tenant}-reviewer")
        identifier = "p7odoo-" + uuid4().hex[:12]
        step = f"Record the {tenant} synthetic maintenance approval before work."
        expect(call(client, technician, "POST", "/documents",
                    json={"id": identifier, "title": "Connected Odoo acceptance", "text": step}), 201)
        proposal = expect(call(client, technician, "POST", "/checklists",
                               json={"document_ids": [identifier], "steps": [step]}), 201)
        expect(call(client, manager, "POST", f"/checklists/{proposal['id']}/approve",
                    json={"payload_hash": proposal["payload_hash"]}), 200)
        preview = expect(call(client, manager, "POST", "/save-operations/prepare",
                              json={"proposal_id": proposal["id"]}), 201)
        assert preview["status"] == "review" and preview["approved_by"] is None
        assert call(client, manager, "POST", f"/save-operations/{preview['id']}/approve",
                    json={"payload_hash": preview["payload_hash"]}).status_code == 403
        approved = expect(call(client, reviewer, "POST", f"/save-operations/{preview['id']}/approve",
                               json={"payload_hash": preview["payload_hash"]}), 200)
        assert approved["status"] == "approved" and approved["approved_by"] == reviewer
        return identifier, preview

    before = counts()
    ops = {}
    with TestClient(load_app()) as client:
        for tenant in ("atlas", "birch"):
            document_id, preview = create_and_approve(client, tenant)
            manager = f"{tenant}-service_manager"
            saved = expect(call(client, manager, "POST", f"/save-operations/{preview['id']}/dispatch"), 200)
            assert saved["status"] == "verified" and type(saved["external_id"]) is int
            assert saved["external_id"] > 0
            assert saved["payload"]["tenant"] == tenant
            assert saved["payload"]["step_sources"][0][0] == document_id
            assert call(client, "birch-service_manager" if tenant == "atlas" else "atlas-service_manager",
                        "GET", f"/save-operations/{preview['id']}").status_code == 404
            ops[tenant] = (preview["id"], saved["external_id"])
    after = counts()
    assert all(after.get(tenant, 0) == before.get(tenant, 0) + 1 for tenant in ("atlas", "birch"))

    with TestClient(load_app()) as client:
        for tenant, (operation_id, external_id) in ops.items():
            manager = f"{tenant}-service_manager"
            assert expect(call(client, manager, "GET", f"/save-operations/{operation_id}"), 200)["status"] == "verified"
            replay = expect(call(client, manager, "POST", f"/save-operations/{operation_id}/dispatch"), 200)
            assert replay["external_id"] == external_id
        assert counts() == after

        class LostResponse:
            requires_durable_ledger = True
            def __init__(self, live): self.live = live
            def info(self): return self.live.info()
            def execute(self, envelope):
                self.live.execute(envelope)  # Odoo commits, then caller loses its response.
                raise TimeoutError("synthetic transport response loss after live commit")
            def status(self, tenant, company_id, operation_id):
                return self.live.status(tenant, company_id, operation_id)

        coordinator = client.app.state.save_ops
        coordinator.bridges["atlas"] = LostResponse(coordinator.bridges["atlas"])
        _, preview = create_and_approve(client, "atlas")
        unknown = expect(call(client, "atlas-service_manager", "POST",
                              f"/save-operations/{preview['id']}/dispatch"), 200)
        assert unknown["status"] == "unknown" and unknown["external_id"] is None
        lost_id = preview["id"]
    after_loss = counts()
    assert after_loss.get("atlas", 0) == after.get("atlas", 0) + 1
    with TestClient(load_app()) as client:
        recovered = expect(call(client, "atlas-service_manager", "POST",
                                f"/save-operations/{lost_id}/verify"), 200)
        assert recovered["status"] == "verified" and recovered["external_id"] > 0
        replay = expect(call(client, "atlas-service_manager", "POST",
                             f"/save-operations/{lost_id}/dispatch"), 200)
        assert replay["external_id"] == recovered["external_id"]
        assert counts() == after_loss
    evidence = {"status": "passed", "backend": "real Odoo 19 JSON-2 and PostgreSQL durable ledger",
                "database": "private_documents_odoo_lab", "companies": ["atlas", "birch"],
                "verified_saves": 3, "separate_actors": True,
                "cross_tenant_read_denied": True, "readback_verified": True,
                "restart_persistence": True, "replay_created_new_effect": False,
                "lost_response_after_real_commit": True,
                "lost_response_reconciled_without_redispatch": True,
                "receipts_before": before, "receipts_after": after_loss}
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
