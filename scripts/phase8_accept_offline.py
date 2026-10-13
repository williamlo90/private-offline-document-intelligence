"""Small same-deployment offline acceptance for scanned source and uncertainty."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

import httpx


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local/phase-8"
OUT = LOCAL / "offline-api-acceptance.json"
BASE = "http://127.0.0.1:8078"


def main() -> None:
    if OUT.exists():
        raise RuntimeError("Refusing to overwrite Phase 8 acceptance")
    identities = json.loads((LOCAL / "lab-identities.json").read_text())
    tokens = {row["id"]: row["token"] for row in identities["actors"]}
    scan = (LOCAL / "releases/candidate/phase8/atlas-restore-scan.pdf").read_bytes()
    scan_sha = hashlib.sha256(scan).hexdigest()
    assert scan_sha == "89559e883f195d5b143a77d929d1aea6ebd5217302a8cbe302ec796ee24b337d"
    identifier = "atlas-phase8-scan-" + uuid4().hex[:10]
    with httpx.Client(base_url=BASE, timeout=150, trust_env=False) as client:
        def call(actor: str, method: str, path: str, **kwargs):
            headers = {"Authorization": "Bearer " + tokens[actor], **kwargs.pop("headers", {})}
            response = client.request(method, path, headers=headers, **kwargs)
            assert response.status_code < 400, (method, path, response.status_code, response.text[:150])
            return response.json()

        health = client.get("/health").json()
        assert health["persistence"] == "postgres-lab"
        start = time.monotonic()
        document = call("atlas-technician", "POST", "/pdf-documents",
                        params={"identifier": identifier, "title": "Phase 8 restore scan",
                                "language": "eng", "effective": "2026-01-01",
                                "expires": "2027-01-01"},
                        content=scan, headers={"Content-Type": "application/pdf"})
        ocr_seconds = round(time.monotonic() - start, 3)
        assert document["digest"] == scan_sha
        assert document["pages"][0]["method"] == "tesseract"
        assert "R-731" in document["pages"][0]["text"]
        hits = call("atlas-technician", "GET", "/search",
                    params={"q": "rehearsal ticket R-731 storage checksum"})
        assert any(row["document_id"] == identifier for row in hits)
        denied = client.get(f"/documents/{identifier}", headers={
            "Authorization": "Bearer " + tokens["birch-technician"]})
        assert denied.status_code in (403, 404)
        start = time.monotonic()
        answer = call("atlas-technician", "POST", "/skills/answer_client_question",
                      json={"question": "What must be recorded during Atlas backup verification?"})
        answer_seconds = round(time.monotonic() - start, 3)
        assert answer["status"] == "sourced_excerpts"
        assert any("job ID and completion time" in row["value"] for row in answer["excerpts"])
        for row in answer["excerpts"]:
            source = call("atlas-technician", "GET",
                          f"/documents/{row['evidence']['document_id']}/versions/{row['evidence']['version']}")
            page = next(p for p in source["pages"] if p["number"] == row["evidence"]["page"])
            assert page["text"][row["evidence"]["start"]:row["evidence"]["end"]] == row["value"]
        missing = call("atlas-technician", "POST", "/skills/answer_client_question",
                       json={"question": "What is the monthly service fee?"})
        assert missing["status"] == "abstain"
        conflict = call("atlas-technician", "POST", "/skills/answer_client_question",
                        json={"question": "What is the backup retention period?"})
        assert conflict["status"] == "review"
    result = {"status": "passed", "project": "private-documents-phase8",
              "same_api_origin": BASE, "scanned_pdf_sha256": scan_sha,
              "ocr_seconds": ocr_seconds, "native_ocr_and_index": True,
              "first_model_answer_seconds": answer_seconds, "first_model_answer_sourced": True,
              "exact_citations": True, "other_tenant_denied": True,
              "missing_abstained": True, "conflict_reviewed": True}
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
