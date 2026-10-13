"""Pure receiver rules and syntax only. No emulated Odoo ORM."""
import ast
import importlib.util
from pathlib import Path
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from backend.bridge_signing import sign_envelope
from backend.odoo_contract import fingerprint, CONTRACT_VERSION, UPSTREAM_REVISION

ROOT=Path(__file__).resolve().parents[1]/'odoo/addons/private_checklist_bridge'
spec=importlib.util.spec_from_file_location('receiver_rules',ROOT/'rules.py')
rules=importlib.util.module_from_spec(spec);spec.loader.exec_module(rules)
KEY=b'fixture-receiver-signing-key-at-least-32'


def envelope():
    step='Catat ID pekerjaan dan jangan ubah "status" <script>alert(1)</script>.'
    payload={'contract_version':CONTRACT_VERSION,'upstream_revision':UPSTREAM_REVISION,'tenant':'atlas',
        'target':{'company_id':1,'customer_id':2,'opportunity_id':3,'assignee_id':4},
        'proposal_id':str(uuid4()),'proposal_hash':'a'*64,'prepared_by':'tech','reviewed_by':'manager',
        'steps':[step],'source_versions':[['sop',1,'b'*64]],'step_sources':[['sop',1,1,0,len(step)]]}
    return {'operation_id':str(uuid4()),'payload':payload,'payload_hash':fingerprint(payload),
        'requested_by':'manager','approved_by':'reviewer','expires_at':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()}


def test_application_signature_accepted_and_note_is_escaped():
    data=envelope()
    assert rules.validate(data,sign_envelope(data,KEY),KEY,'atlas',1)==data
    note=rules.render_note(data['payload'])
    assert '<script>' not in note and '&lt;script&gt;' in note
    assert rules.note_matches(note,data['payload'])
    assert not rules.note_matches(note.replace('Catat','Altered'),data['payload'])
    assert not rules.note_matches('<script>x</script>'+note,data['payload'])


@pytest.mark.parametrize('mutation',['target','expiry','span','duplicate_source','unknown','self','version'])
def test_signed_but_invalid_content_rejected(mutation):
    data=envelope();p=data['payload']
    if mutation=='target':p['target']['company_id']=True
    if mutation=='expiry':data['expires_at']='2000-01-01T00:00:00+00:00'
    if mutation=='span':p['step_sources'][0][4]=2
    if mutation=='duplicate_source':p['source_versions'].append(p['source_versions'][0])
    if mutation=='unknown':p['execute_command']='shell'
    if mutation=='self':data['approved_by']=data['requested_by']
    if mutation=='version':p['contract_version']='1.0'
    data['payload_hash']=fingerprint(p)
    with pytest.raises(ValueError):rules.validate(data,sign_envelope(data,KEY),KEY,'atlas',1)


def test_wrong_signature_or_tenant_rejected():
    data=envelope()
    with pytest.raises(ValueError):rules.validate(data,'0'*64,KEY,'atlas',1)
    with pytest.raises(ValueError):rules.validate(data,sign_envelope(data,KEY),KEY,'birch',1)


def test_addon_python_syntax_and_pinned_dependency():
    for file in ROOT.glob('*.py'):ast.parse(file.read_text(encoding='utf-8'))
    manifest=ast.literal_eval((ROOT/'__manifest__.py').read_text())
    assert 'ops_bridge' in manifest['depends'] and manifest['version'].startswith('19.')
