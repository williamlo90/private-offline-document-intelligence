"""Offline release staging and local-file recovery. No services are started here."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import zipfile

from backend.skills import BundleManifest, BUNDLE_COMPONENTS


def checksum(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):digest.update(chunk)
    return digest.hexdigest()


def safe_file(root, relative):
    path=Path(relative)
    lexical=root/path
    candidate=lexical.resolve()
    if path.is_absolute() or '..' in path.parts or ':' in relative or not candidate.is_relative_to(root.resolve()):
        raise ValueError('Unsafe release path')
    part=root
    for name in path.parts:
        part=part/name
        if part.is_symlink():raise ValueError('Unsafe release path')
    return candidate


def verify(bundle):
    bundle=Path(bundle).resolve()
    manifest_path=bundle/'manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size>100_000:
        raise ValueError('Missing or oversized release manifest')
    manifest=BundleManifest.model_validate_json(manifest_path.read_bytes())
    identifiers={item.id for item in manifest.artifacts}
    if len(identifiers)!=len(manifest.artifacts) or set(manifest.components)-set(BUNDLE_COMPONENTS):
        raise ValueError('Invalid release component references')
    for item in manifest.artifacts:
        source=safe_file(bundle,item.path)
        if not source.is_file() or checksum(source)!=item.sha256:
            raise ValueError('Release artifact checksum mismatch: '+item.id)
    missing=[name for name in BUNDLE_COMPONENTS if not manifest.components.get(name) or not set(manifest.components[name])<=identifiers]
    return manifest,missing


def stage(bundle, releases, name):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}',name):
        raise ValueError('Invalid release name')
    bundle=Path(bundle).resolve();releases=Path(releases).resolve()
    if releases.is_relative_to(bundle):raise ValueError('Release target must be outside bundle source')
    manifest,missing=verify(bundle)
    if missing:raise ValueError('Incomplete offline bundle: '+', '.join(missing))
    target=releases/name
    if target.exists():raise FileExistsError('Release already exists')
    releases.mkdir(parents=True,exist_ok=True)
    required=sum(safe_file(bundle,item.path).stat().st_size for item in manifest.artifacts)
    if shutil.disk_usage(releases.parent).free<required+1024**3:
        raise ValueError('Insufficient release staging disk reserve')
    target.mkdir(parents=True)
    try:
        for item in manifest.artifacts:
            destination=safe_file(target,item.path)
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(safe_file(bundle,item.path),destination)
            if checksum(destination)!=item.sha256:raise ValueError('Artifact changed during installation')
        shutil.copyfile(bundle/'manifest.json',target/'manifest.json')
        with zipfile.ZipFile(target/'application.zip') as archive:
            if len(archive.infolist())>1000 or sum(member.file_size for member in archive.infolist())>100*1024**2:
                raise ValueError('Application archive resource budget exceeded')
            for member in archive.infolist():
                destination=safe_file(target/'application',member.filename)
                if member.is_dir():continue
                if member.file_size>100*1024**2 or (member.external_attr>>16)&0o170000==0o120000:
                    raise ValueError('Unsafe application member')
                destination.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(member) as source,destination.open('xb') as output:shutil.copyfileobj(source,output)
        (target/'release.json').write_text(json.dumps({'name':name,'manifest_sha256':checksum(target/'manifest.json'),
                                                       'status':'staged; runtime smoke required before activation'},indent=2)+'\n')
    except BaseException:
        # target is a fixed child of the caller's explicit release directory.
        if target.resolve().parent==releases:shutil.rmtree(target)
        raise
    return target


def _pointer(path,value):
    temp=path.with_suffix('.tmp')
    with temp.open('w',encoding='utf-8') as output:
        json.dump({'release':value},output);output.flush();os.fsync(output.fileno())
    os.replace(temp,path)


def activate(releases,name):
    releases=Path(releases).resolve();target=releases/name
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}',name) or target.is_symlink() or not target.is_dir():
        raise ValueError('Unknown release')
    verify(target)
    # A staged bundle is never implicitly deployable. Phase 7 writes this
    # project-local record only after connected/runtime acceptance.
    acceptance=target/'acceptance.json'
    try:
        evidence=json.loads(acceptance.read_text(encoding='utf-8'))
        if evidence.get('status')!='accepted' or evidence.get('manifest_sha256')!=checksum(target/'manifest.json'):
            raise ValueError('Release acceptance does not match manifest')
    except (OSError,KeyError,json.JSONDecodeError) as error:
        raise ValueError('Release acceptance evidence missing') from error
    current=releases/'current.json';previous=releases/'previous.json'
    old=json.loads(current.read_text())['release'] if current.exists() else None
    if old and (not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}',old) or not (releases/old).is_dir()):
        raise ValueError('Invalid current release pointer')
    if old:_pointer(previous,old)
    _pointer(current,name)


def rollback(releases):
    releases=Path(releases).resolve();previous=releases/'previous.json'
    if not previous.is_file():raise ValueError('No previous release')
    name=json.loads(previous.read_text())['release']
    activate(releases,name)


def backup(state,archive):
    state=Path(state).resolve();archive=Path(archive).resolve()
    if not state.is_dir() or archive.exists() or archive.is_relative_to(state):raise ValueError('Invalid backup paths')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(state.rglob('*')):
            if path.is_symlink():raise ValueError('Symlinks are not backed up')
            if path.is_file():output.write(path,path.relative_to(state).as_posix())
    return checksum(archive)


def restore(archive,target):
    archive=Path(archive).resolve();target=Path(target).resolve()
    if target.exists() or not archive.is_file():raise ValueError('Restore requires a new target directory')
    target.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive) as source:
            if len(source.infolist())>1000 or sum(item.file_size for item in source.infolist())>5*1024**3:
                raise ValueError('Backup resource budget exceeded')
            for item in source.infolist():
                if item.is_dir() or item.file_size>1024**3:raise ValueError('Invalid backup member')
                destination=safe_file(target,item.filename)
                destination.parent.mkdir(parents=True,exist_ok=True)
                with source.open(item) as stream,destination.open('xb') as output:shutil.copyfileobj(stream,output)
    except BaseException:
        if target.resolve().parent==Path(target).parent.resolve():shutil.rmtree(target)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    for command,fields in {'verify':['bundle'],'stage':['bundle','releases','name'],
                           'activate':['releases','name'],'rollback':['releases'],
                           'backup':['state','archive'],'restore':['archive','target']}.items():
        part=sub.add_parser(command)
        for field in fields:part.add_argument(field)
    args=parser.parse_args()
    result=globals()[args.command](*(getattr(args,field) for field in vars(args) if field!='command'))
    print(json.dumps({'command':args.command,'result':str(result)}))
