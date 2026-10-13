"""Verify portable DB backups by restoring disposable clones in the Phase 8 lab."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local/phase-8"
CONTAINER = "private-documents-phase8-database-1"
PROJECT = "private-documents-phase8"
SOURCES = {"app": ("private_documents_lab", "private_documents_phase8_app_restore", "documents"),
           "odoo": ("private_documents_odoo_lab", "private_documents_phase8_odoo_restore",
                    "private_checklist_receipt")}


def run(*args: str) -> str:
    return subprocess.run(["docker", *args], check=True, capture_output=True,
                          text=True, timeout=180).stdout.strip()


def main() -> None:
    label = run("inspect", "--format", '{{index .Config.Labels "com.docker.compose.project"}}',
                CONTAINER)
    if label != PROJECT:
        raise RuntimeError("Refusing to restore outside the Phase 8 lab")
    backup_dir = LOCAL / "backups"
    backup_dir.mkdir(exist_ok=True)
    evidence = {}
    for key, (source, target, table) in SOURCES.items():
        destination = backup_dir / f"{key}.dump"
        if destination.exists():
            raise RuntimeError("Refusing to overwrite backup")
        remote = f"/tmp/phase8-{key}.dump"
        run("exec", CONTAINER, "pg_dump", "-Fc", "-U", "private_documents_owner",
            "-d", source, "-f", remote)
        run("cp", f"{CONTAINER}:{remote}", str(destination))
        checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
        run("exec", CONTAINER, "createdb", "-U", "private_documents_owner", target)
        try:
            run("cp", str(destination), f"{CONTAINER}:{remote}")
            run("exec", CONTAINER, "pg_restore", "-U", "private_documents_owner",
                "--no-owner", "-d", target, remote)
            query = f"SELECT count(*) FROM {table};"
            original = int(run("exec", CONTAINER, "psql", "-U", "private_documents_owner",
                               "-d", source, "-tAc", query))
            restored = int(run("exec", CONTAINER, "psql", "-U", "private_documents_owner",
                               "-d", target, "-tAc", query))
            if restored != original or restored < 1:
                raise AssertionError((key, original, restored))
            evidence[key] = {"source_database": source, "backup_sha256": checksum,
                             "backup_bytes": destination.stat().st_size,
                             "source_rows": original, "restored_rows": restored,
                             "clone_removed_after_probe": True}
        finally:
            run("exec", CONTAINER, "dropdb", "-U", "private_documents_owner", target)
    result = {"status": "passed", "project": PROJECT, "database_backups": evidence,
              "scope": "PostgreSQL app and Odoo data restored to disposable clones; Odoo filestore restore not tested"}
    (LOCAL / "restore-acceptance.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
