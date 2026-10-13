"""Provision a new project-07-only Odoo database; never inspect project-02 data."""
from __future__ import annotations

import json
from pathlib import Path
import secrets

import psycopg
from psycopg import sql

from scripts.phase7_bootstrap_db import LOCAL, owner_password


ROLE = "private_documents_odoo"
DATABASE = "private_documents_odoo_lab"
KEYS = ("PRIVATE_DOCUMENTS_ODOO_DB_PASSWORD", "PRIVATE_DOCUMENTS_ODOO_ADMIN_PASSWORD",
        "PRIVATE_CHECKLIST_SIGNING_KEY")


def main():
    env_file = LOCAL / "compose.env"
    values = dict(line.split("=", 1) for line in env_file.read_text(encoding="utf-8").splitlines()
                  if line and not line.startswith("#"))
    changed = False
    for key in KEYS:
        if key not in values:
            values[key] = secrets.token_urlsafe(40)
            changed = True
    if changed:
        env_file.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    (LOCAL / "odoo-config").mkdir(parents=True, exist_ok=True)
    with psycopg.connect(host="127.0.0.1", port=5477, dbname="postgres",
                         user="private_documents_owner", password=owner_password(), autocommit=True) as conn:
        role = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,)).fetchone()
        if not role:
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {}").format(
                sql.Identifier(ROLE), sql.Literal(values[KEYS[0]])))
        else:
            conn.execute(sql.SQL("ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {}").format(
                sql.Identifier(ROLE), sql.Literal(values[KEYS[0]])))
        existing = conn.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s", (DATABASE,)).fetchone()
        if existing and existing[0] != ROLE:
            raise RuntimeError("Refusing to touch an Odoo database owned by another role")
        if not existing:
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8'").format(
                sql.Identifier(DATABASE), sql.Identifier(ROLE)))
    with psycopg.connect(host="127.0.0.1", port=5477, dbname=DATABASE,
                         user=ROLE, password=values[KEYS[0]]) as conn:
        assert conn.execute("SELECT current_database()").fetchone()[0] == DATABASE
    print(json.dumps({"status": "passed", "database": DATABASE, "role": ROLE,
                      "isolated_company_count_target": 2, "secrets_printed": False}))


if __name__ == "__main__":
    main()
