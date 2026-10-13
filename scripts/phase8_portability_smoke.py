"""Read-only user journey on the revised no-port profile; keeps prior evidence intact."""
from __future__ import annotations

import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8078"


def main() -> None:
    identities = json.loads((ROOT / "local/phase-8/lab-identities.json").read_text())
    tokens = {row["id"]: row["token"] for row in identities["actors"]}
    with httpx.Client(base_url=BASE, timeout=150, trust_env=False) as client:
        assert client.get("/health").json()["persistence"] == "postgres-lab"
        def ask(question: str) -> dict:
            response = client.post("/skills/answer_client_question", json={"question": question},
                headers={"Authorization": "Bearer " + tokens["atlas-technician"]})
            response.raise_for_status()
            return response.json()
        answer = ask("What must be recorded during Atlas backup verification?")
        assert answer["status"] == "sourced_excerpts"
        assert any(item["evidence"]["page"] >= 1 for item in answer["excerpts"])
        missing = ask("What is the monthly service fee?")
        assert missing["status"] == "abstain"
        conflict = ask("What is the backup retention period?")
        assert conflict["status"] == "review"
        denied = client.get("/documents/atlas-backup-v1", headers={
            "Authorization": "Bearer " + tokens["birch-technician"]})
        assert denied.status_code in (403, 404)
    result = {"status": "passed", "scope": "read-only native model/API smoke on reused Phase 8 volumes",
              "profile": "revised no-published-port Compose and temporary loopback bridge",
              "sourced_answer": True, "citation_page_present": True,
              "missing_abstained": True, "conflict_reviewed": True, "cross_tenant_denied": True,
              "limitations": ["Not a new clean install", "No new Odoo write or backup/restore probe"]}
    (ROOT / "local/phase-8/port-hardening-smoke.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
