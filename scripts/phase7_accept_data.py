"""Connected API durability/ACL/approval acceptance on the disposable Phase 7 DB."""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.main import load_app


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local/phase-7"


def main() -> None:
    output = LOCAL / "database-domain-acceptance.json"
    if output.exists():
        raise RuntimeError("Refusing to overwrite connected acceptance evidence")
    os.environ["PRIVATE_LAB_CONFIG"] = str(LOCAL / "lab-identities.json")
    os.environ["PRIVATE_DB_CONFIG"] = str(LOCAL / "db-config.json")
    identities = json.loads((LOCAL / "lab-identities.json").read_text(encoding="utf-8"))
    tokens = {actor["id"]: actor["token"] for actor in identities["actors"]}

    def call(client, actor, method, path, **kwargs):
        return client.request(method, path, headers={"Authorization": "Bearer " + tokens[actor]}, **kwargs)

    identifier = "p7accept-" + uuid4().hex[:12]
    source = "Check the Atlas backup status before maintenance."
    with TestClient(load_app()) as client:
        assert client.get("/health").json()["persistence"] == "postgres-lab"
        response = call(client, "atlas-technician", "POST", "/documents",
                        json={"id": identifier, "title": "Phase 7 source", "text": source})
        assert response.status_code == 201, response.text
        assert response.json()["version"] == 1
        assert call(client, "birch-technician", "GET", f"/documents/{identifier}").status_code == 404
        assert call(client, "birch-technician", "GET", "/search?q=Atlas+backup+status").json() == []
        proposal = call(client, "atlas-technician", "POST", "/checklists",
                        json={"document_ids": [identifier], "steps": [source]}).json()
        assert proposal["status"] == "review" and proposal["step_sources"][0][0] == identifier
        approved = call(client, "atlas-service_manager", "POST", f"/checklists/{proposal['id']}/approve",
                        json={"payload_hash": proposal["payload_hash"]})
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"

    with TestClient(load_app()) as client:
        assert call(client, "atlas-technician", "GET", f"/documents/{identifier}").json()["version"] == 1
        assert call(client, "atlas-service_manager", "GET", f"/checklists/{proposal['id']}").json()["status"] == "approved"
        revoked = call(client, "atlas-administrator", "POST", f"/documents/{identifier}/access",
                       json={"actor_id": "atlas-technician", "revoked": True})
        assert revoked.status_code == 204, revoked.text
        assert call(client, "atlas-technician", "GET", f"/documents/{identifier}").status_code == 404
        assert call(client, "atlas-technician", "GET", f"/documents/{identifier}/versions/1").status_code == 404
        assert not any(item["document_id"] == identifier for item in
                       call(client, "atlas-technician", "GET", "/search?q=maintenance").json())
        assert call(client, "atlas-service_manager", "GET", f"/checklists/{proposal['id']}").json()["status"] == "stale"
        restored = call(client, "atlas-administrator", "POST", f"/documents/{identifier}/access",
                        json={"actor_id": "atlas-technician", "revoked": False})
        assert restored.status_code == 204
        assert call(client, "atlas-technician", "GET", f"/documents/{identifier}").status_code == 200
        assert call(client, "atlas-service_manager", "GET", f"/checklists/{proposal['id']}").json()["status"] == "stale"
        updated = call(client, "atlas-technician", "POST", "/documents",
                       json={"id": identifier, "title": "Phase 7 source", "text": source + " Record the outcome."})
        assert updated.status_code == 201 and updated.json()["version"] == 2, updated.text
        assert call(client, "atlas-technician", "GET", f"/documents/{identifier}/versions/1").json()["text"] == source
        assert call(client, "atlas-service_manager", "DELETE", f"/documents/{identifier}").status_code == 204
        assert call(client, "atlas-technician", "GET", f"/documents/{identifier}/versions/1").status_code == 404
        audit = call(client, "atlas-administrator", "GET", "/audit")
        assert audit.status_code == 200
        assert {"document_ingested", "checklist_prepared", "checklist_approved", "access_revoked",
                "access_restored", "document_deleted"} <= {row["action"] for row in audit.json()}
    evidence = {"status": "passed", "backend": "real PostgreSQL/pgvector via non-owner role",
                "document_id": identifier, "api_round_trips": 21,
                "restart_durability": True, "version_history": True,
                "two_tenant_isolation": True, "approval_separation": True,
                "revocation_blocks_current_history_search": True,
                "revocation_stales_approval": True, "delete_hides_history": True,
                "audit_persistent": True}
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
