"""Real scanned-PDF OCR/index acceptance inside the offline project network."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

import httpx


def main() -> None:
    source = Path("/app/fixtures/atlas-restore-scan.pdf")
    data = source.read_bytes()
    assert hashlib.sha256(data).hexdigest() == "89559e883f195d5b143a77d929d1aea6ebd5217302a8cbe302ec796ee24b337d"
    actors = json.loads(Path("/run/secrets/lab-identities.json").read_text())["actors"]
    token = {actor["id"]: actor["token"] for actor in actors}
    identifier = "atlas-scanned-" + uuid4().hex[:10]
    with httpx.Client(base_url="http://127.0.0.1:8077", timeout=40, trust_env=False) as client:
        started = time.monotonic()
        result = client.post("/pdf-documents", params={"identifier": identifier,
                    "title": "Atlas restore rehearsal scan", "language": "eng",
                    "effective": "2026-01-01", "expires": "2027-01-01"},
                    headers={"Authorization": "Bearer " + token["atlas-technician"],
                             "Content-Type": "application/pdf"}, content=data)
        seconds = time.monotonic() - started
        assert result.status_code == 201, (result.status_code, result.text[:150])
        document = result.json()
        assert document["digest"] == hashlib.sha256(data).hexdigest()
        assert len(document["pages"]) == 1
        page = document["pages"][0]
        assert page["method"] == "tesseract" and page["quality"] == "usable", page
        assert "R-731" in page["text"] and "C-88" in page["text"], page["text"]
        hits = client.get("/search", params={"q": "rehearsal ticket R-731 storage checksum"},
                          headers={"Authorization": "Bearer " + token["atlas-technician"]})
        assert hits.status_code == 200 and any(row["document_id"] == identifier for row in hits.json())
        denied = client.get(f"/documents/{identifier}",
                            headers={"Authorization": "Bearer " + token["birch-technician"]})
        assert denied.status_code in (403, 404)
    print(json.dumps({"status": "passed", "profile": "offline internal Docker network",
                      "document_id": identifier, "scan_sha256": hashlib.sha256(data).hexdigest(),
                      "native_ocr": True, "quality": "usable", "keyword_index": True,
                      "cross_tenant_read_denied": True, "ocr_seconds": round(seconds, 3),
                      "source_text_contains": ["R-731", "C-88"]}))


if __name__ == "__main__":
    main()
