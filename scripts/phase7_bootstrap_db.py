"""Create only project-07 lab identities and a non-owner PostgreSQL app role."""
from __future__ import annotations

import json
from pathlib import Path
import secrets

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local/phase-7"
DATABASE = "private_documents_lab"
ROLE = "private_documents_app"


def owner_password() -> str:
    entries = dict(line.split("=", 1) for line in
                   (LOCAL / "compose.env").read_text(encoding="utf-8").splitlines()
                   if line and not line.startswith("#"))
    return entries["PRIVATE_DOCUMENTS_DB_PASSWORD"]


def main() -> None:
    LOCAL.mkdir(parents=True, exist_ok=True)
    secret_file = LOCAL / "app-db-secret.json"
    if secret_file.exists():
        app_password = json.loads(secret_file.read_text(encoding="utf-8"))["password"]
    else:
        app_password = secrets.token_urlsafe(40)
        secret_file.write_text(json.dumps({"host": "127.0.0.1", "port": 5477,
                                           "database": DATABASE, "user": ROLE,
                                           "password": app_password}) + "\n", encoding="utf-8")
    actors = json.loads((ROOT / "local/lab-identities.json").read_text(encoding="utf-8"))
    if actors["profile"] != "native-memory-harness" or {a["tenant"] for a in actors["actors"]} != {"atlas", "birch"}:
        raise RuntimeError("Expected isolated two-tenant synthetic identities")
    identity_file = LOCAL / "lab-identities.json"
    if identity_file.exists():
        persistent_identities = json.loads(identity_file.read_text(encoding="utf-8"))
    else:
        persistent_identities = {**actors, "profile": "persistent-postgres-lab",
            "actors": [*actors["actors"], *({"id": f"{tenant}-reviewer", "tenant": tenant,
                 "role": "service_manager", "document_ids": None,
                 "token": secrets.token_urlsafe(36)} for tenant in ("atlas", "birch"))]}
        identity_file.write_text(json.dumps(persistent_identities, indent=2) + "\n", encoding="utf-8")
    existing_ids = {actor["id"] for actor in persistent_identities["actors"]}
    for tenant in ("atlas", "birch"):
        if f"{tenant}-reviewer" not in existing_ids:
            persistent_identities["actors"].append({"id": f"{tenant}-reviewer", "tenant": tenant,
                "role": "service_manager", "document_ids": None, "token": secrets.token_urlsafe(36)})
    identity_file.write_text(json.dumps(persistent_identities, indent=2) + "\n", encoding="utf-8")
    if (persistent_identities.get("profile") != "persistent-postgres-lab" or
        {a["tenant"] for a in persistent_identities["actors"]} != {"atlas", "birch"}):
        raise RuntimeError("Persistent identity profile is invalid")
    (LOCAL / "db-config.json").write_text(json.dumps({"profile": "persistent-postgres-lab",
        "host": "127.0.0.1", "port": 5477, "dbname": DATABASE,
        "user": ROLE, "password": app_password}, indent=2) + "\n", encoding="utf-8")
    with psycopg.connect(host="127.0.0.1", port=5477, dbname=DATABASE,
                         user="private_documents_owner", password=owner_password()) as conn:
        with conn.cursor() as cur:
            assert cur.execute("SELECT current_database()").fetchone()[0] == DATABASE
            exists = cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,)).fetchone()
            if not exists:
                cur.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {}").format(
                    sql.Identifier(ROLE), sql.Literal(app_password)))
            else:
                cur.execute(sql.SQL("ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {}").format(
                    sql.Identifier(ROLE), sql.Literal(app_password)))
            cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(DATABASE), sql.Identifier(ROLE)))
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL("REVOKE INSERT,UPDATE,DELETE ON document_grants FROM {}").format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(sql.Identifier(ROLE)))
            for tenant in ("atlas", "birch"):
                cur.execute("INSERT INTO tenants(id) VALUES (%s) ON CONFLICT DO NOTHING", (tenant,))
            for actor in persistent_identities["actors"]:
                newly_created = cur.execute("SELECT 1 FROM actors WHERE tenant_id=%s AND id=%s",
                                            (actor["tenant"], actor["id"])).fetchone() is None
                cur.execute("INSERT INTO actors(tenant_id,id,role,document_ids) VALUES (%s,%s,%s,%s) "
                            "ON CONFLICT (tenant_id,id) DO UPDATE SET role=EXCLUDED.role,document_ids=EXCLUDED.document_ids",
                            (actor["tenant"], actor["id"], actor["role"], actor.get("document_ids")))
                if newly_created and actor["role"] in {"technician", "service_manager", "administrator"}:
                    cur.execute("INSERT INTO document_grants(tenant_id,document_id,actor_id) "
                                "SELECT d.tenant_id,d.id,%s FROM documents d WHERE d.tenant_id=%s "
                                "AND (%s::text[] IS NULL OR d.id=ANY(%s::text[])) ON CONFLICT DO NOTHING",
                                (actor["id"], actor["tenant"], actor.get("document_ids"), actor.get("document_ids")))
    with psycopg.connect(host="127.0.0.1", port=5477, dbname=DATABASE,
                         user=ROLE, password=app_password) as conn:
        with conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true), set_config('app.actor_id', %s, true)",
                         ("atlas", "atlas-technician"))
            assert conn.execute("SELECT count(*) FROM actors").fetchone()[0] == 5
    print(json.dumps({"status": "passed", "database": DATABASE, "role": ROLE,
                      "role_is_non_owner": True, "synthetic_actors": len(persistent_identities["actors"])}))


if __name__ == "__main__":
    main()
