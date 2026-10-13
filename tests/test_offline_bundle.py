import json
import hashlib
import zipfile
import pytest
from backend.domain import Actor,Service,MemoryRepository
from backend.skills import BusinessSkills,AuditReadiness
from scripts.build_offline_bundle import build,SOURCE_DIRS,SOURCE_FILES


def source_tree(root):
    for directory in SOURCE_DIRS:(root/directory).mkdir(parents=True,exist_ok=True)
    for file in SOURCE_FILES:
        path=root/file;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{}')
    (root/'backend/example.py').write_text('print("fixture")')
    (root/'backend/.env').write_text('SECRET=do-not-package')
    (root/'local').mkdir(exist_ok=True)
    (root/'local/lab-identities.json').write_text('SECRET-token')


def test_reproducible_snapshot_excludes_identity_and_env(tmp_path):
    source_tree(tmp_path)
    first=build(tmp_path/'local/bundle1',tmp_path)
    second=build(tmp_path/'local/bundle2',tmp_path)
    assert first['artifacts']==second['artifacts']
    with zipfile.ZipFile(tmp_path/'local/bundle1/application.zip') as archive:
        assert 'backend/example.py' in archive.namelist()
        assert not any('local/' in name or '.env' in name for name in archive.namelist())
    assert 'generative_model' in first['components_missing'] and first['offline_validated'] is False
    with pytest.raises(FileExistsError):build(tmp_path/'local/bundle1',tmp_path)
    with pytest.raises(ValueError):build(tmp_path/'outside',tmp_path)


def test_partial_bundle_audit_and_tampering(tmp_path):
    source_tree(tmp_path);bundle=tmp_path/'local/bundle'
    build(bundle,tmp_path)
    skills=BusinessSkills(Service(MemoryRepository()),bundle)
    admin=Actor('admin','atlas','administrator')
    result=skills.audit_offline_readiness(admin,AuditReadiness())
    assert result.status=='assets_verified' and not result.offline_validated
    assert 'component:generative_model' in result.pending
    assert 'component:application' not in result.pending
    (bundle/'application.zip').write_bytes(b'tampered')
    result=skills.audit_offline_readiness(admin,AuditReadiness())
    assert result.status=='assets_incomplete' and 'component:application' in result.pending


def test_component_cannot_reference_unlisted_artifact(tmp_path):
    source_tree(tmp_path);bundle=tmp_path/'local/bundle';build(bundle,tmp_path)
    path=bundle/'manifest.json';manifest=json.loads(path.read_text())
    manifest['components']['generative_model']=['invented']
    path.write_text(json.dumps(manifest))
    skills=BusinessSkills(Service(MemoryRepository()),bundle)
    assert skills.audit_offline_readiness(Actor('a','atlas','administrator'),AuditReadiness()).status=='manifest_invalid'


def test_pinned_model_and_tokenizer_staging(tmp_path):
    source_tree(tmp_path)
    sha=lambda data:hashlib.sha256(data).hexdigest()
    blob=b'fixture-gguf';digest=sha(blob)
    blob_path=tmp_path/'local/models/ollama/blobs'/('sha256-'+digest)
    blob_path.parent.mkdir(parents=True);blob_path.write_bytes(blob)
    manifest_path=tmp_path/'local/models/ollama/manifests/registry.ollama.ai/library/qwen3/4b-instruct-2507-q4_K_M'
    manifest_path.parent.mkdir(parents=True)
    manifest=json.dumps({'config':{'digest':'sha256:'+digest,'size':len(blob)},
                         'layers':[{'digest':'sha256:'+digest,'size':len(blob),'mediaType':'application/vnd.ollama.image.license'}]}).encode()
    manifest_path.write_bytes(manifest)
    runtime=b'fixture-runtime'
    runtime_path=tmp_path/'local/runtime/ollama-windows-amd64-v0.40.3.zip'
    runtime_path.parent.mkdir(parents=True);runtime_path.write_bytes(runtime)
    lock_path=tmp_path/'config/ollama-runtime-lock.json';lock_path.parent.mkdir(parents=True,exist_ok=True)
    lock_path.write_text(json.dumps({'runtime':{'archive_sha256':sha(runtime)},
                                    'model':{'manifest_sha256':sha(manifest),'gguf_sha256':digest}}))
    tokenizer=tmp_path/'local/models/multilingual-minilm/tokenizer.json'
    tokenizer.parent.mkdir(parents=True);tokenizer.write_text('{}')
    result=build(tmp_path/'local/full',tmp_path,include_local_models=True)
    assert {'tokenizer','embeddings','generative_model','ollama_runtime'}<=set(result['components_staged'])
    audit=BusinessSkills(Service(MemoryRepository()),tmp_path/'local/full').audit_offline_readiness(
        Actor('a','atlas','administrator'),AuditReadiness())
    assert audit.status=='assets_verified'
    blob_path.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='Pinned model blob mismatch'):
        build(tmp_path/'local/tampered',tmp_path,include_local_models=True)
