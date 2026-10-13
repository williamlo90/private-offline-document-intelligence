"""Dump and restore only the disposable project-07 database into a second lab DB."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import psycopg

from scripts.phase7_bootstrap_db import LOCAL, owner_password


CONTAINER = "private-documents-phase7-database-1"
SOURCE = "private_documents_lab"
RESTORE = "private_documents_restore"


def docker(*args):
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True)


def main():
    output = LOCAL / "database-restore-acceptance.json"
    if output.exists():
        raise RuntimeError("Refusing to overwrite restore evidence")
    names = docker("inspect", "--format", "{{index .Config.Labels \"com.docker.compose.project\"}}", CONTAINER).stdout.strip()
    if names != "private-documents-phase7":
        raise RuntimeError("Container does not belong to isolated project-07 session")
    backup_inside = "/tmp/project07-phase7-backup.dump"
    backup = LOCAL / "database-backup.dump"
    if backup.exists():
        raise RuntimeError("Refusing to overwrite prior backup")
    docker("exec", CONTAINER, "pg_dump", "-Fc", "-U", "private_documents_owner",
           "-d", SOURCE, "-f", backup_inside)
    docker("cp", f"{CONTAINER}:{backup_inside}", str(backup))
    backup_sha = hashlib.sha256(backup.read_bytes()).hexdigest()
    docker("exec", CONTAINER, "createdb", "-U", "private_documents_owner", RESTORE)
    try:
        docker("exec", CONTAINER, "pg_restore", "-U", "private_documents_owner",
               "-d", RESTORE, backup_inside)
        with psycopg.connect(host="127.0.0.1", port=5477, dbname=RESTORE,
                             user="private_documents_owner", password=owner_password()) as conn:
            owner_count = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
            version_count = conn.execute("SELECT count(*) FROM document_versions").fetchone()[0]
            proposal_count = conn.execute("SELECT count(*) FROM checklist_proposals").fetchone()[0]
            audit_count = conn.execute("SELECT count(*) FROM audit_events").fetchone()[0]
            extension = conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
            assert owner_count >= 10 and version_count >= owner_count
            assert proposal_count >= 1 and audit_count >= 1 and extension
        app = json.loads((LOCAL / "app-db-secret.json").read_text(encoding="utf-8"))
        with psycopg.connect(host="127.0.0.1", port=5477, dbname=RESTORE,
                             user=app["user"], password=app["password"], autocommit=True) as conn:
            assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
            with conn.transaction():
                conn.execute("SELECT set_config('app.tenant_id', %s, true), set_config('app.actor_id', %s, true)",
                             ("atlas", "atlas-technician"))
                atlas_count = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
                assert 1 <= atlas_count < owner_count
            with conn.transaction():
                conn.execute("SELECT set_config('app.tenant_id', %s, true), set_config('app.actor_id', %s, true)",
                             ("birch", "birch-technician"))
                birch_count = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
                assert 1 <= birch_count < owner_count
        evidence = {"status": "passed", "source_db": SOURCE, "restore_db": RESTORE,
                    "backup_sha256": backup_sha, "backup_bytes": backup.stat().st_size,
                    "documents": owner_count, "versions": version_count,
                    "proposals": proposal_count, "audit_events": audit_count,
                    "restored_vector_extension": extension[0],
                    "restored_default_deny": True, "restored_tenant_rls": True,
                    "atlas_visible": atlas_count, "birch_visible": birch_count,
                    "restore_database_removed_after_probe": True}
    finally:
        docker("exec", CONTAINER, "dropdb", "-U", "private_documents_owner", RESTORE)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
