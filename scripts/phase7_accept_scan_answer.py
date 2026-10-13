"""Verify the offline native model cites the newly OCRed page itself."""
from __future__ import annotations

import json
from pathlib import Path
import time

import httpx


def main() -> None:
    identities = json.loads(Path("/run/secrets/lab-identities.json").read_text())
    token = next(actor["token"] for actor in identities["actors"] if actor["id"] == "atlas-technician")
    with httpx.Client(base_url="http://127.0.0.1:8077", timeout=130, trust_env=False,
                      headers={"Authorization": "Bearer " + token}) as client:
        documents = client.get("/documents").json()
        scans = [row for row in documents if row["id"].startswith("atlas-scanned-")]
        assert len(scans) == 1, len(scans)
        document = scans[0]
        started = time.monotonic()
        response = client.post("/skills/answer_client_question", json={"question":
                               "Which rehearsal ticket and storage checksum must Atlas record before manager review?"})
        seconds = time.monotonic() - started
        assert response.status_code == 200, (response.status_code, response.text[:120])
        answer = response.json()
        assert answer["status"] == "sourced_excerpts", answer
        assert any(row["evidence"]["document_id"] == document["id"] and
                   "R-731" in row["value"] and "C-88" in row["value"]
                   for row in answer["excerpts"]), answer
        for row in answer["excerpts"]:
            ev = row["evidence"]
            source = client.get(f"/documents/{ev['document_id']}/versions/{ev['version']}").json()
            page = next(item for item in source["pages"] if item["number"] == ev["page"])
            assert page["text"][ev["start"]:ev["end"]] == row["value"]
    print(json.dumps({"status": "passed", "profile": "offline internal Docker network",
                      "ocr_document_id": document["id"], "native_model_cited_ocr_page": True,
                      "all_citations_exact": True, "answer_seconds": round(seconds, 3)}))


if __name__ == "__main__":
    main()
