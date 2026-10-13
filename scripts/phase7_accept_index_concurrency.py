"""Real pgvector indexing/deletion and concurrent version-CAS acceptance."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg

from backend.domain import Actor, DomainError, Service
from backend.postgres_repository import PostgresRepository
from backend.vector_adapter import PgVectorSearch


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local/phase-7"


def config():
    data = json.loads((LOCAL / "db-config.json").read_text(encoding="utf-8"))
    return {key: data[key] for key in ("host", "port", "dbname", "user", "password")}


def actors():
    data = json.loads((LOCAL / "lab-identities.json").read_text(encoding="utf-8"))
    return [Actor(row["id"], row["tenant"], row["role"],
                  None if row.get("document_ids") is None else frozenset(row["document_ids"]))
            for row in data["actors"]]


def main():
    output = LOCAL / "index-concurrency-acceptance.json"
    if output.exists():
        raise RuntimeError("Refusing to overwrite index/concurrency evidence")
    profiles = actors()
    technician = next(actor for actor in profiles if actor.id == "atlas-technician")
    manager = next(actor for actor in profiles if actor.id == "atlas-service_manager")
    birch = next(actor for actor in profiles if actor.id == "birch-technician")
    identifier = "p7index-" + uuid4().hex[:12]
    service = Service(PostgresRepository(config(), profiles))
    source = "Verify Atlas endpoint inventory before maintenance."
    document = service.ingest(technician, identifier, "Index acceptance", source)
    embedding = [1.0] + [0.0] * 383
    with psycopg.connect(**config(), autocommit=True) as connection:
        index = PgVectorSearch(connection, "phase7-fixture-384")
        with service.repo.scoped(technician):
            result = index.replace_index(service, technician, identifier, 1,
                [{"page": 1, "start": 0, "end": len(source), "quote": source,
                  "embedding": embedding}])
            assert result["indexed_chunks"] == 1
            hits = index.search(service, technician, embedding)
            assert len(hits) == 1 and hits[0]["quote"] == source
        with service.repo.scoped(birch):
            assert index.search(service, birch, embedding) == []
        service.ingest(technician, identifier, "Index acceptance", source + " Record the result.")
        with service.repo.scoped(technician):
            assert index.search(service, technician, embedding) == []  # stale version is excluded
        with service.repo.scoped(manager):
            index.delete_index(service, manager, identifier)
        with service.repo.scoped(technician):
            assert index.search(service, technician, embedding) == []

    concurrent_id = "p7cas-" + uuid4().hex[:12]
    original = service.ingest(technician, concurrent_id, "Concurrency", "Original version.")
    gate = Barrier(2)

    def attempt(number):
        repo = PostgresRepository(config(), profiles)
        candidate = replace(original, version=2, text=f"Writer {number} update.",
                            digest=__import__("hashlib").sha256(f"Writer {number} update.".encode()).hexdigest())
        gate.wait(timeout=5)
        try:
            with repo.scoped(technician), repo.lock:
                repo.put_document(candidate)
            return "committed"
        except DomainError as error:
            assert error.code == "source_changed_or_expired"
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(attempt, (1, 2)))
    assert outcomes == ["committed", "conflict"], outcomes
    assert service.read_document(technician, concurrent_id).version == 2
    evidence = {"status": "passed", "backend": "PostgreSQL/pgvector",
                "index_document": identifier, "vector_dimension": 384,
                "source_span_verified": True, "stale_version_excluded": True,
                "index_deletion_verified": True, "concurrent_version_outcomes": outcomes,
                "lost_update": False}
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
