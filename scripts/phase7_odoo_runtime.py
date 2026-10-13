"""Container entrypoint for the isolated two-company Odoo acceptance lab."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


mode = sys.argv[1]
if mode not in {"init", "seed", "serve", "upgrade"}:
    raise SystemExit("Invalid project-07 Odoo mode")
config = ("[options]\n"
          "db_host=database\ndb_port=5432\ndb_user=private_documents_odoo\n"
          f"db_password={os.environ['PRIVATE_DOCUMENTS_ODOO_DB_PASSWORD']}\n"
          f"admin_passwd={os.environ['PRIVATE_DOCUMENTS_ODOO_ADMIN_PASSWORD']}\n"
          "db_name=private_documents_odoo_lab\ndbfilter=^private_documents_odoo_lab$\n"
          "list_db=False\n"
          "addons_path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons\n"
          "data_dir=/var/lib/odoo\nmax_cron_threads=0\nworkers=0\n"
          "log_level=warn\nlog_handler=werkzeug:ERROR\n")
with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as file:
    file.write(config)
    filename = file.name
try:
    if mode == "seed":
        command = ["odoo", "shell", "-c", filename, "--no-http"]
        result = subprocess.run(command, input=Path("/opt/project07/seed.py").read_text(), text=True)
    elif mode in {"init", "upgrade"}:
        command = ["odoo", "-c", filename, "-i" if mode == "init" else "-u",
                   "private_checklist_bridge", "--without-demo", "--stop-after-init", "--no-http"]
        result = subprocess.run(command)
    else:
        result = subprocess.run(["odoo", "-c", filename])
    raise SystemExit(result.returncode)
finally:
    Path(filename).unlink(missing_ok=True)
