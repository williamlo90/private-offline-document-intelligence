"""One real HTTP vertical slice using native Ollama and isolated DB/Odoo lab."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
from uuid import uuid4

import httpx


ROOT = Path(__file__).resolve().parents[1]
MODE = os.environ.get("PRIVATE_PHASE7_MODE", "connected")
if MODE not in {"connected", "offline"}:
    raise RuntimeError("Invalid Phase 7 acceptance mode")
OUT = (ROOT / "local/phase-7/lean-vertical-slice.json" if MODE == "connected"
       else Path("/tmp/phase7-offline-vertical-slice.json"))
BASE = "http://127.0.0.1:8077"


def main() -> None:
    if OUT.exists():
        raise RuntimeError("Refusing to overwrite vertical-slice evidence")
    if MODE == "offline":
        with socket.socket() as outside:
            outside.settimeout(2)
            try:
                outside.connect(("1.1.1.1", 443))
            except OSError as error:
                assert error.errno == 101, ("Unexpected egress result", error)
            else:
                raise AssertionError("External TCP unexpectedly reachable")
    identity_path = (Path("/run/secrets/lab-identities.json") if MODE == "offline"
                     else ROOT / "local/phase-7/lab-identities.json")
    identities = json.loads(identity_path.read_text())
    tokens = {row["id"]: row["token"] for row in identities["actors"]}
    identifier = "atlas-lean-" + uuid4().hex[:10]
    pdf = (ROOT / "evaluation/development/atlas-backup-v1.pdf").read_bytes()
    expected_pdf_hash = hashlib.sha256(pdf).hexdigest()
    assert expected_pdf_hash == "c07f2daa19c1e0e03dd51e3c2151869aeba39a6a13d2f052119a95431c004443"

    with httpx.Client(base_url=BASE, timeout=180, trust_env=False) as client:
        def call(actor: str, method: str, path: str, **kwargs):
            headers = {"Authorization": "Bearer " + tokens[actor], **kwargs.pop("headers", {})}
            result = client.request(method, path,
                                    headers=headers, **kwargs)
            if result.status_code >= 400:
                raise AssertionError((method, path, result.status_code, result.text[:150]))
            return result.json()

        health = client.get("/health").json()
        assert health["persistence"] == "postgres-lab"
        document = call("atlas-technician", "POST", "/pdf-documents",
                        params={"identifier": identifier, "title": "Lean slice backup SOP",
                                "language": "eng", "effective": "2026-01-01",
                                "expires": "2026-12-31"},
                        content=pdf, headers={"Content-Type": "application/pdf"})
        assert document["digest"] == expected_pdf_hash
        hits = call("atlas-technician", "GET", "/search", params={"q": "job ID completion time"})
        assert any(hit["document_id"] == identifier for hit in hits)
        denied = client.get(f"/documents/{identifier}",
                            headers={"Authorization": "Bearer " + tokens["birch-technician"]})
        assert denied.status_code in (403, 404)

        answer = call("atlas-technician", "POST", "/skills/answer_client_question",
                      json={"question": "What must be recorded during Atlas backup verification?"})
        assert answer["status"] == "sourced_excerpts", answer
        assert any("job ID and completion time" in row["value"] for row in answer["excerpts"])
        for row in answer["excerpts"]:
            ev = row["evidence"]
            source = call("atlas-technician", "GET",
                          f"/documents/{ev['document_id']}/versions/{ev['version']}")
            page = next(p for p in source["pages"] if p["number"] == ev["page"])
            assert page["text"][ev["start"]:ev["end"]] == row["value"]
        other_answer = call("birch-technician", "POST", "/skills/answer_client_question",
                            json={"question": "What must be recorded during Atlas backup verification?"})
        assert not any(row["evidence"]["document_id"].startswith("atlas-")
                       for row in other_answer["excerpts"])

        step = "Record the job ID and completion time."
        proposal = call("atlas-technician", "POST", "/skills/prepare_service_checklist",
                        json={"document_ids": [identifier], "steps": [step],
                              "expected_versions": {identifier: document["version"]}})
        approved = call("atlas-service_manager", "POST",
                        f"/checklists/{proposal['id']}/approve",
                        json={"payload_hash": proposal["payload_hash"]})
        preview = call("atlas-service_manager", "POST", "/save-operations/prepare",
                       json={"proposal_id": approved["id"]})
        call("atlas-reviewer", "POST", f"/save-operations/{preview['id']}/approve",
             json={"payload_hash": preview["payload_hash"]})
        saved = call("atlas-service_manager", "POST",
                     f"/save-operations/{preview['id']}/dispatch")
        assert saved["status"] == "verified" and saved["external_id"] > 0
        replay = call("atlas-service_manager", "POST",
                      f"/save-operations/{preview['id']}/dispatch")
        assert replay["external_id"] == saved["external_id"]
        assert any(event["action"] == "save_verified"
                   for event in call("atlas-auditor", "GET", "/audit"))

    evidence = {"status": "passed", "profile": ("internal Docker network with local Ollama, PostgreSQL and Odoo"
                                               if MODE == "offline" else
                                               "Windows-native Ollama/API plus isolated Docker PostgreSQL/Odoo"),
                "pdf_sha256": expected_pdf_hash, "uploaded_document_id": identifier,
                "pdf_parse_and_keyword_index": True, "native_model_sourced_answer": True,
                "exact_citations": True, "cross_tenant_source_denied": True,
                "separate_review_actors": True, "odoo_readback_verified": True,
                "replay_external_id_unchanged": True, "audit_verified": True,
                "document_version": document["version"], "operation_id": preview["id"],
                "external_id": saved["external_id"],
                "offline_tested": MODE == "offline", "external_tcp_blocked": MODE == "offline",
                "full_phase7_gate": False}
    OUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
