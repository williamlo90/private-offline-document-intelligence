"""Verify persisted document and model answer after the Phase 8 stop/start cycle."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time

import httpx


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local/phase-8"
PROJECT = "private-documents-phase8"
OUT = LOCAL / "restart-acceptance.json"


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True, timeout=30).strip()


def main() -> None:
    if OUT.exists():
        raise RuntimeError("Refusing to overwrite restart acceptance")
    identities = json.loads((LOCAL / "lab-identities.json").read_text())["actors"]
    tokens = {row["id"]: row["token"] for row in identities}
    document_id = json.loads((LOCAL / "browser-live.json").read_text())["document_id"]
    with httpx.Client(base_url="http://127.0.0.1:8078", timeout=145,
                      trust_env=False) as client:
        headers = {"Authorization": "Bearer " + tokens["atlas-technician"]}
        health = client.get("/health")
        assert health.status_code == 200 and health.json()["persistence"] == "postgres-lab"
        source = client.get(f"/documents/{document_id}", headers=headers)
        assert source.status_code == 200 and source.json()["version"] == 1
        denied = client.get(f"/documents/{document_id}", headers={
            "Authorization": "Bearer " + tokens["birch-technician"]})
        assert denied.status_code in (403, 404)
        started = time.monotonic()
        answer = client.post("/skills/answer_client_question", headers=headers,
                             json={"question": "What must be recorded during Atlas backup verification?"})
        answer_seconds = round(time.monotonic() - started, 3)
        assert answer.status_code == 200, (answer.status_code, answer.text[:160])
        body = answer.json()
        assert body["status"] == "sourced_excerpts"
        assert any("job ID and completion time" in row["value"] for row in body["excerpts"])
    db = PROJECT + "-database-1"
    app_count = int(docker("exec", db, "psql", "-U", "private_documents_owner",
                           "-d", "private_documents_lab", "-tAc", "SELECT count(*) FROM documents"))
    odoo_count = int(docker("exec", db, "psql", "-U", "private_documents_owner",
                            "-d", "private_documents_odoo_lab", "-tAc",
                            "SELECT count(*) FROM private_checklist_receipt"))
    assert app_count >= 11 and odoo_count >= 1
    result = {"status": "probe_passed", "project": PROJECT,
              "phase8_services_stopped_before_restart": 0,
              "stopped_count_source": "docker ps project-label output after stop command",
              "persistent_document_read": True, "cross_tenant_denied_after_restart": True,
              "first_answer_after_restart_sourced": True,
              "answer_seconds": answer_seconds, "app_documents": app_count,
              "odoo_receipts": odoo_count, "phase8_services_stopped_after_checks": None}
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
