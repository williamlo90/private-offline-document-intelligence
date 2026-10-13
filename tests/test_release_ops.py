import json
import zipfile

import pytest

from scripts.build_offline_bundle import build, SOURCE_DIRS, SOURCE_FILES
from backend.skills import BUNDLE_COMPONENTS
from scripts.release_ops import verify,stage,backup,restore,activate,rollback,checksum


def fixture_bundle(root):
    for name in SOURCE_DIRS:(root/name).mkdir(parents=True,exist_ok=True)
    for name in SOURCE_FILES:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{}')
    (root/'backend/example.py').write_text('print(1)')
    (root/'local').mkdir(exist_ok=True)
    bundle=root/'local/bundle';build(bundle,root)
    return bundle


def test_incomplete_release_refuses_stage_and_activation(tmp_path):
    bundle=fixture_bundle(tmp_path)
    _,missing=verify(bundle)
    assert 'generative_model' in missing
    with pytest.raises(ValueError,match='Incomplete offline bundle'):
        stage(bundle,tmp_path/'releases','v1')
    with pytest.raises(ValueError,match='Unknown release'):
        activate(tmp_path/'releases','v1')


def test_backup_restore_new_target_and_zip_traversal(tmp_path):
    state=tmp_path/'state';state.mkdir();(state/'checkpoint.json').write_text('{"attempts":1}')
    archive=tmp_path/'backup.zip'
    assert len(backup(state,archive))==64
    target=tmp_path/'restored';restore(archive,target)
    assert (target/'checkpoint.json').read_text()=='{"attempts":1}'
    with pytest.raises(ValueError):restore(archive,target)
    bad=tmp_path/'bad.zip'
    with zipfile.ZipFile(bad,'w') as output:output.writestr('../outside','blocked')
    with pytest.raises(ValueError,match='Unsafe release path'):
        restore(bad,tmp_path/'unsafe')
    assert not (tmp_path/'outside').exists()


def test_staging_requires_explicit_acceptance_and_rollback_pointer(tmp_path):
    bundle=fixture_bundle(tmp_path)
    path=bundle/'manifest.json';manifest=json.loads(path.read_text())
    # Mechanical manifest fixture only: the real builder never invents assets.
    manifest['components']={name:['application'] for name in BUNDLE_COMPONENTS}
    path.write_text(json.dumps(manifest))
    releases=tmp_path/'releases'
    first=stage(bundle,releases,'v1')
    assert (first/'application/backend/example.py').is_file()
    with pytest.raises(ValueError,match='acceptance evidence missing'):activate(releases,'v1')
    (first/'acceptance.json').write_text(json.dumps({'status':'accepted','manifest_sha256':checksum(first/'manifest.json')}))
    activate(releases,'v1')
    second=stage(bundle,releases,'v2')
    (second/'acceptance.json').write_text(json.dumps({'status':'accepted','manifest_sha256':checksum(second/'manifest.json')}))
    activate(releases,'v2')
    rollback(releases)
    assert json.loads((releases/'current.json').read_text())['release']=='v1'
