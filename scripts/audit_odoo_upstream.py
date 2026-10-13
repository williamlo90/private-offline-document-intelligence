"""Read-only audit of the pinned Project 02 contract and local changes."""
import hashlib
import json
from pathlib import Path
import subprocess

from backend.odoo_contract import UPSTREAM_REVISION

root=Path(__file__).resolve().parents[1]
upstream=root.parent/'02 - Odoo Business Operations MCP Server'
selected=['backend/contracts.py','backend/odoo_adapter.py','odoo/addons/ops_bridge/models.py']

def git(*args):
    return subprocess.run(['git',*args],cwd=upstream,check=True,capture_output=True).stdout

head=git('rev-parse','HEAD').decode().strip()
status=git('status','--porcelain').decode().splitlines()
changed=[line[3:] for line in status]
hashes={name:hashlib.sha256(git('show',f'{UPSTREAM_REVISION}:{name}')).hexdigest()
        for name in selected}
report={'pinned_revision':UPSTREAM_REVISION,'observed_head':head,
        'working_tree_changes':changed,'selected_pinned_sha256':hashes,
        'selected_files_modified':any(name in changed for name in selected),
        'upstream_modified_by_this_project':False}
out=root/'local/phase-4/upstream-contract-audit.json'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'pinned_revision':UPSTREAM_REVISION,'head':head,
                  'changed_files':len(changed),'selected_files_modified':report['selected_files_modified']}))
