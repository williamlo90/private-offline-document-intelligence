"""Connected, disposable PostgreSQL/pgvector RLS probe for project 07."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import psycopg
from psycopg.errors import InsufficientPrivilege

from scripts.phase7_bootstrap_db import DATABASE, LOCAL, ROLE, owner_password


def connect(*, owner: bool = False):
    password = owner_password() if owner else json.loads((LOCAL / "app-db-secret.json").read_text())["password"]
    return psycopg.connect(host="127.0.0.1", port=5477, dbname=DATABASE,
                           user="private_documents_owner" if owner else ROLE, password=password,
                           autocommit=not owner)


def identity(conn, tenant: str, actor: str) -> None:
    conn.execute("SELECT set_config('app.tenant_id', %s, true), set_config('app.actor_id', %s, true)",
                 (tenant, actor))


def main() -> None:
    documents = (("atlas", "phase7-rls-atlas", "atlas-technician"),
                 ("birch", "phase7-rls-birch", "birch-technician"))
    with connect(owner=True) as conn:
        for tenant, identifier, actor in documents:
            body = f"Synthetic Phase 7 {tenant} source."
            digest = hashlib.sha256(body.encode()).hexdigest()
            conn.execute("INSERT INTO documents(tenant_id,id,title,current_version) VALUES (%s,%s,%s,1) "
                         "ON CONFLICT (tenant_id,id) DO NOTHING", (tenant, identifier, identifier))
            conn.execute("INSERT INTO document_versions(tenant_id,document_id,version,content_hash,body) "
                         "VALUES (%s,%s,1,%s,%s) ON CONFLICT DO NOTHING", (tenant, identifier, digest, body))
            conn.execute("INSERT INTO document_grants(tenant_id,document_id,actor_id) VALUES (%s,%s,%s) "
                         "ON CONFLICT DO NOTHING", (tenant, identifier, actor))
    with connect() as conn:
        # No session identity means default deny on every tenant-scoped table.
        assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
        with conn.transaction():
            identity(conn, "atlas", "atlas-technician")
            assert conn.execute("SELECT id FROM documents WHERE id LIKE 'phase7-rls-%'").fetchall() == [("phase7-rls-atlas",)]
            assert conn.execute("SELECT document_id FROM document_versions WHERE document_id LIKE 'phase7-rls-%'").fetchall() == [("phase7-rls-atlas",)]
            assert conn.execute("SELECT document_id FROM document_grants WHERE document_id LIKE 'phase7-rls-%'").fetchall() == [("phase7-rls-atlas",)]
        with conn.transaction():
            identity(conn, "atlas", "atlas-service_manager")
            assert conn.execute("SELECT id FROM documents WHERE id LIKE 'phase7-rls-%'").fetchall() == []
        with conn.transaction():
            identity(conn, "birch", "birch-technician")
            assert conn.execute("SELECT id FROM documents WHERE id LIKE 'phase7-rls-%'").fetchall() == [("phase7-rls-birch",)]
        try:
            with conn.transaction():
                identity(conn, "atlas", "atlas-technician")
                conn.execute("INSERT INTO document_grants(tenant_id,document_id,actor_id) "
                             "VALUES ('birch','phase7-rls-birch','atlas-technician')")
        except InsufficientPrivilege:
            pass
        else:
            raise AssertionError("Cross-tenant grant unexpectedly succeeded")
    evidence = {"status": "passed", "database": DATABASE, "engine": "real PostgreSQL/pgvector",
                "app_role": ROLE, "default_deny": True, "tenant_isolation": True,
                "object_grant_isolation": True, "cross_tenant_write_denied": True,
                "fixtures": 2}
    output = LOCAL / "database-rls-probe.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
