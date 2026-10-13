"""Provision only the fresh, synthetic Phase 8 Compose lab."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local/phase-8"
RELEASE = LOCAL / "releases/candidate"
PROJECT = "private-documents-phase8"
DB = "private_documents_lab"
ODOO_DB = "private_documents_odoo_lab"
APP_ROLE = "private_documents_app"
ODOO_ROLE = "private_documents_odoo"


def settings() -> dict[str, str]:
    return dict(line.split("=", 1) for line in (LOCAL / "compose.env").read_text().splitlines()
                if line and not line.startswith("#"))


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", "-p", PROJECT, "--env-file", str(LOCAL / "compose.env"),
                    "-f", str(ROOT / "deploy/compose.phase8-lab.yaml"),
                    "-f", str(ROOT / "deploy/compose.phase8-runtime.yaml"), *args], check=True)


def prepare() -> None:
    if not (RELEASE / "application/migrations/001_foundation.sql").is_file():
        raise RuntimeError("Stage the verified Phase 8 release first")
    if not (RELEASE / "upstream/ops_bridge/__manifest__.py").is_file():
        raise RuntimeError("Pinned Odoo upstream snapshot is missing")
    LOCAL.mkdir(parents=True, exist_ok=True)
    env = LOCAL / "compose.env"
    if env.exists():
        raise RuntimeError("Refusing to regenerate Phase 8 secrets")
    passwords = {key: secrets.token_urlsafe(40) for key in (
        "PRIVATE_DOCUMENTS_DB_PASSWORD", "PRIVATE_DOCUMENTS_ODOO_DB_PASSWORD",
        "PRIVATE_DOCUMENTS_ODOO_ADMIN_PASSWORD", "PRIVATE_CHECKLIST_SIGNING_KEY")}
    env.write_text("".join(f"{key}={value}\n" for key, value in passwords.items()), encoding="utf-8")
    actors = [{"id": f"{tenant}-{role}", "tenant": tenant, "role": role,
               "document_ids": None, "token": secrets.token_urlsafe(36)}
              for tenant in ("atlas", "birch")
              for role in ("technician", "service_manager", "administrator", "auditor", "reviewer")]
    for actor in actors:
        if actor["role"] == "reviewer":
            actor["role"] = "service_manager"
    (LOCAL / "lab-identities.json").write_text(json.dumps({"profile": "persistent-postgres-lab",
                                                 "actors": actors}, indent=2) + "\n")
    profile = json.loads((RELEASE / "application/config/ollama-profile.json").read_text())
    profile["host"] = "ollama"
    (LOCAL / "ollama-profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    (LOCAL / "odoo-config").mkdir(exist_ok=True)
    print(json.dumps({"status": "prepared", "project": PROJECT,
                      "actors": len(actors), "secrets_printed": False}))


def owner(dbname: str = DB):
    import psycopg

    return psycopg.connect(host="database" if os.environ.get("PRIVATE_PHASE8_INSIDE") else "127.0.0.1",
                           port=5432 if os.environ.get("PRIVATE_PHASE8_INSIDE") else 5478, dbname=dbname,
                           user="private_documents_owner",
                           password=settings()["PRIVATE_DOCUMENTS_DB_PASSWORD"], autocommit=True)


def migrate() -> None:
    if not os.environ.get("PRIVATE_PHASE8_INSIDE"):
        compose("up", "-d", "database")
        subprocess.run(["docker", "run", "--rm", "--network", PROJECT + "_offline",
                        "-v", f"{LOCAL}:/app/local/phase-8",
                        "-v", f"{ROOT / 'scripts/phase8_provision.py'}:/app/scripts/phase8_provision.py:ro",
                        "-e", "PRIVATE_PHASE8_INSIDE=1", "--entrypoint", "python",
                        "private-documents-api:phase7", "/app/scripts/phase8_provision.py", "migrate"],
                       check=True)
        return
    import psycopg
    from psycopg import sql
    for attempt in range(60):
        try:
            connection = owner()
            break
        except psycopg.OperationalError:
            if attempt == 59:
                raise
            time.sleep(1)
    with connection as conn:
        if conn.execute("SELECT to_regclass('public.tenants')").fetchone()[0] is not None:
            raise RuntimeError("Phase 8 database is not fresh")
        migrations = sorted((RELEASE / "application/migrations").glob("*.sql"))
        if len(migrations) != 6:
            raise RuntimeError("Unexpected migration count")
        for migration in migrations:
            conn.execute(migration.read_text(encoding="utf-8"))
        password = secrets.token_urlsafe(40)
        conn.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {}").format(
            sql.Identifier(APP_ROLE), sql.Literal(password)))
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(DB), sql.Identifier(APP_ROLE)))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(APP_ROLE)))
        conn.execute(sql.SQL("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(APP_ROLE)))
        conn.execute(sql.SQL("REVOKE INSERT,UPDATE,DELETE ON document_grants FROM {}").format(sql.Identifier(APP_ROLE)))
        conn.execute(sql.SQL("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(sql.Identifier(APP_ROLE)))
        actors = json.loads((LOCAL / "lab-identities.json").read_text())["actors"]
        for tenant in ("atlas", "birch"):
            conn.execute("INSERT INTO tenants(id) VALUES (%s)", (tenant,))
        for actor in actors:
            conn.execute("INSERT INTO actors(tenant_id,id,role,document_ids) VALUES (%s,%s,%s,%s)",
                         (actor["tenant"], actor["id"], actor["role"], actor.get("document_ids")))
    (LOCAL / "db-config-container.json").write_text(json.dumps({"profile": "persistent-postgres-lab",
        "host": "database", "port": 5432, "dbname": DB,
        "user": APP_ROLE, "password": password}, indent=2) + "\n")
    with owner("postgres") as conn:
        conn.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {}").format(
            sql.Identifier(ODOO_ROLE), sql.Literal(settings()["PRIVATE_DOCUMENTS_ODOO_DB_PASSWORD"])))
        conn.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8'").format(
            sql.Identifier(ODOO_DB), sql.Identifier(ODOO_ROLE)))
    print(json.dumps({"status": "migrated", "migrations": len(migrations),
                      "actors": len(actors), "fresh_database": True}))


def seed_odoo() -> None:
    compose("run", "--rm", "--no-deps", "odoo", "init")
    compose("run", "--rm", "--no-deps", "odoo", "seed")
    source = json.loads((LOCAL / "odoo-config/connections.json").read_text())
    if set(source) != {"atlas", "birch"}:
        raise RuntimeError("Expected two synthetic Odoo companies")
    bridges = {}
    for tenant, row in source.items():
        if row["database"] != ODOO_DB or row["tenant"] != tenant:
            raise RuntimeError("Odoo binding escaped the Phase 8 lab")
        bridges[tenant] = {"bridge": {"host": "odoo", "port": 8069,
            "database": ODOO_DB, "tenant": tenant, "company_id": row["company_id"],
            "api_key": row["api_key"],
            "signing_key": settings()["PRIVATE_CHECKLIST_SIGNING_KEY"]},
            "target": {key: row[key] for key in ("company_id", "customer_id",
                                                  "opportunity_id", "assignee_id")}}
    (LOCAL / "odoo-bridge-container.json").write_text(json.dumps({
        "profile": "project07-connected-odoo-lab", "bridges": bridges}, indent=2) + "\n")
    print(json.dumps({"status": "odoo_seeded", "companies": len(source),
                      "secrets_printed": False}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=("prepare", "migrate", "seed-odoo"))
    step = parser.parse_args().step
    {"prepare": prepare, "migrate": migrate, "seed-odoo": seed_odoo}[step]()
