"""Stage a partial offline bundle from explicit local allowlists; no downloads."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE_DIRS=('backend','scripts','migrations','skills','deploy/systemd','odoo/addons/private_checklist_bridge',
             'frontend/dist','mcp/dist')
SOURCE_FILES=('requirements.in','requirements.lock','deploy/Dockerfile','deploy/compose.yaml',
              'deploy/compose.offline.yaml','deploy/compose.phase8.yaml','deploy/compose.phase8-lab.yaml',
              'frontend/package.json','frontend/package-lock.json',
              'mcp/package.json','mcp/package-lock.json','config/scope-v1.json','config/dependency-map.json','config/embedding-profile.json',
              'config/ollama-profile.json','config/ollama-runtime-lock.json',
              'config/ollama-linux-runtime-lock.json','config/ocr-linux-packages-lock.json',
              'config/node-linux-runtime-lock.json','config/phase7-resource-budget.json',
              'config/python-linux-runtime-lock.json',
              'docs/OFFLINE-BUNDLE.md','docs/WORKER.md','docs/PHASE-5.md','docs/PHASE-6.md',
              'evaluation/development/manifest.json')


def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):result.update(chunk)
    return result.hexdigest()


def _stage_asset(root, output, relative, artifact_id, artifacts):
    source=root/relative
    if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(root):
        raise ValueError('Missing or unsafe bundle asset: '+relative)
    target=output/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    checksum=digest(target)
    if checksum!=digest(source):raise ValueError('Asset changed during staging: '+relative)
    artifacts.append({'id':artifact_id,'path':relative,'sha256':checksum})
    return checksum


def _model_sources(root):
    lock=json.loads((root/'config/ollama-runtime-lock.json').read_text(encoding='utf-8'))
    manifest='local/models/ollama/manifests/registry.ollama.ai/library/qwen3/4b-instruct-2507-q4_K_M'
    if digest(root/manifest)!=lock['model']['manifest_sha256']:
        raise ValueError('Pinned model manifest checksum mismatch')
    document=json.loads((root/manifest).read_text(encoding='utf-8'))
    blobs=[]
    for item in [document['config'],*document['layers']]:
        match=re.fullmatch(r'sha256:([0-9a-f]{64})',item['digest'])
        if not match:raise ValueError('Unsafe model blob digest')
        relative='local/models/ollama/blobs/sha256-'+match.group(1)
        source=root/relative
        if source.is_symlink() or not source.is_file() or source.stat().st_size!=item['size'] or digest(source)!=match.group(1):
            raise ValueError('Pinned model blob mismatch: '+match.group(1))
        blobs.append(relative)
    if lock['model']['gguf_sha256'] not in {item['digest'].split(':')[1] for item in document['layers']}:
        raise ValueError('Selected model is absent from pinned manifest')
    return lock,manifest,blobs


def build(output, root=ROOT, *, include_local_models=False):
    from backend.skills import BundleManifest, BUNDLE_COMPONENTS
    root=root.resolve();output=Path(output).resolve()
    if not output.is_relative_to(root/'local'):
        raise ValueError('Bundle output must stay inside project local directory')
    if output.exists():raise FileExistsError('Refusing to overwrite an existing bundle')
    sources=[]
    for name in SOURCE_DIRS:
        directory=root/name
        if not directory.is_dir():raise ValueError('Required application directory missing: '+name)
        for source in sorted(directory.rglob('*')):
            if '__pycache__' in source.parts or source.suffix=='.pyc':continue
            if source.is_symlink() or not source.resolve().is_relative_to(directory.resolve()):raise ValueError('Unsafe source link')
            if source.name.startswith('.') or source.suffix not in {'.py','.json','.md','.sql','.js','.css','.html','.template'}:continue
            if source.is_file():sources.append(source)
    for name in SOURCE_FILES:
        source=root/name
        if source.is_symlink() or not source.is_file():raise ValueError('Required lockfile missing')
        sources.append(source)
    total=sum(source.stat().st_size for source in sources)
    if total>100*1024**2 or shutil.disk_usage(root).free<total+100*1024**2:raise ValueError('Bundle resource budget exceeded')
    output.mkdir(parents=True)
    artifacts=[]
    archive=output/'application.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
        for source in sorted(sources):
            relative=source.relative_to(root).as_posix()
            info=zipfile.ZipInfo(relative,date_time=(2020,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
            bundle.writestr(info,source.read_bytes())
    artifacts.append({'id':'application','path':archive.name,'sha256':digest(archive)})
    components={'application':['application']}
    for language in ('eng','ind'):
        source=root/'local/ocr/tessdata'/f'{language}.traineddata'
        if source.is_file() and not source.is_symlink():
            target=output/source.name;shutil.copyfile(source,target)
            artifacts.append({'id':'ocr-'+language,'path':target.name,'sha256':digest(target)})
    if {'ocr-eng','ocr-ind'}<={a['id'] for a in artifacts}:components['ocr_languages']=['ocr-eng','ocr-ind']
    if include_local_models:
        lock,model_manifest,blobs=_model_sources(root)
        embedding_root=root/'local/models/multilingual-minilm'
        embedding_files=sorted(path for path in embedding_root.rglob('*') if path.is_file())
        if not embedding_files or any(path.is_symlink() or not path.resolve().is_relative_to(embedding_root) for path in embedding_files):
            raise ValueError('Embedding assets absent or unsafe')
        runtime='local/runtime/ollama-windows-amd64-v0.40.3.zip'
        asset_paths=[runtime,model_manifest,*blobs,*[p.relative_to(root).as_posix() for p in embedding_files]]
        asset_size=sum((root/path).stat().st_size for path in asset_paths)
        if asset_size>6*1024**3 or shutil.disk_usage(root).free<asset_size+1024**3:
            raise ValueError('Local model staging budget exceeded')
        if digest(root/runtime)!=lock['runtime']['archive_sha256']:
            raise ValueError('Pinned Ollama archive checksum mismatch')
        _stage_asset(root,output,runtime,'ollama-runtime',artifacts)
        components['ollama_runtime']=['ollama-runtime']
        linux_lock=json.loads((root/'config/ollama-linux-runtime-lock.json').read_text(encoding='utf-8'))
        linux_runtime='local/runtime/ollama-linux-amd64-v0.40.3.tar.zst'
        if (root/linux_runtime).is_file():
            if (root/linux_runtime).stat().st_size!=linux_lock['bytes'] or digest(root/linux_runtime)!=linux_lock['sha256']:
                raise ValueError('Pinned Linux Ollama archive checksum mismatch')
            _stage_asset(root,output,linux_runtime,'ollama-linux-runtime',artifacts)
            components['ollama_runtime'].append('ollama-linux-runtime')
            extractor='local/runtime/linux-debs/'+linux_lock['extractor_package']
            if digest(root/extractor)!=linux_lock['extractor_sha256']:
                raise ValueError('Pinned Linux extractor checksum mismatch')
            _stage_asset(root,output,extractor,'ollama-linux-extractor',artifacts)
            components['ollama_runtime'].append('ollama-linux-extractor')
        ocr_lock=json.loads((root/'config/ocr-linux-packages-lock.json').read_text(encoding='utf-8'))
        if ocr_lock.get('packages'):
            package_ids=[]
            for index,(filename,expected) in enumerate(sorted(ocr_lock['packages'].items())):
                relative='local/runtime/linux-debs/'+filename
                if digest(root/relative)!=expected:raise ValueError('Pinned OCR package checksum mismatch')
                artifact_id=f'ocr-runtime-{index}'
                _stage_asset(root,output,relative,artifact_id,artifacts)
                package_ids.append(artifact_id)
            components['ocr_runtime']=package_ids
        python_lock=json.loads((root/'config/python-linux-runtime-lock.json').read_text(encoding='utf-8'))
        if python_lock.get('packages'):
            package_ids=[]
            for index,(filename,expected) in enumerate(sorted(python_lock['packages'].items())):
                relative='local/runtime/linux-debs/'+filename
                if digest(root/relative)!=expected:raise ValueError('Pinned Python package checksum mismatch')
                artifact_id=f'python-runtime-{index}'
                _stage_asset(root,output,relative,artifact_id,artifacts)
                package_ids.append(artifact_id)
            components['python_runtime']=package_ids
        wheelhouse=root/'local/runtime/python-wheels-linux'
        wheels=sorted(wheelhouse.glob('*.whl')) if wheelhouse.is_dir() else []
        requirement_count=sum('==' in line and not line.lstrip().startswith('#') for line in (root/'requirements.lock').read_text().splitlines())
        if len(wheels)==requirement_count:
            wheel_ids=[]
            for index,source in enumerate(wheels):
                artifact_id=f'python-wheel-{index}'
                _stage_asset(root,output,source.relative_to(root).as_posix(),artifact_id,artifacts)
                wheel_ids.append(artifact_id)
            components['python_packages']=wheel_ids
        node_lock=json.loads((root/'config/node-linux-runtime-lock.json').read_text(encoding='utf-8'))
        node_runtime='local/runtime/node-v22.19.0-linux-x64.tar.xz'
        if (root/node_runtime).is_file():
            if digest(root/node_runtime)!=node_lock['sha256']:raise ValueError('Pinned Node archive checksum mismatch')
            _stage_asset(root,output,node_runtime,'node-runtime',artifacts)
            components['node_runtime']=['node-runtime']
        modules=root/'mcp/node_modules'
        if modules.is_dir():
            module_files=sorted(path for path in modules.rglob('*') if path.is_file())
            if not module_files or any(path.is_symlink() for path in module_files) or sum(path.stat().st_size for path in module_files)>100*1024**2:
                raise ValueError('Node package staging budget exceeded')
            archive=output/'node-packages.zip'
            with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as package:
                for source in module_files:
                    info=zipfile.ZipInfo(source.relative_to(modules).as_posix(),date_time=(2020,1,1,0,0,0))
                    info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
                    package.writestr(info,source.read_bytes())
            artifacts.append({'id':'node-packages','path':archive.name,'sha256':digest(archive)})
            components['node_packages']=['node-packages']
        model_ids=[]
        for index,relative in enumerate([model_manifest,*blobs]):
            artifact_id=f'model-{index}'
            _stage_asset(root,output,relative,artifact_id,artifacts)
            model_ids.append(artifact_id)
        components['generative_model']=model_ids
        embedding_ids=[]
        for index,source in enumerate(embedding_files):
            relative=source.relative_to(root).as_posix();artifact_id=f'embedding-{index}'
            _stage_asset(root,output,relative,artifact_id,artifacts)
            embedding_ids.append(artifact_id)
            if source.name=='tokenizer.json':components['tokenizer']=[artifact_id]
        components['embeddings']=embedding_ids
        model_layers=json.loads((root/model_manifest).read_text())['layers']
        license_layers=[index for index,layer in enumerate(model_layers,start=2)
                        if layer.get('mediaType')=='application/vnd.ollama.image.license']
        if not license_layers:
            raise ValueError('Pinned model license layer absent')
        inventory={'schema_version':1,'scope':'Pointers to license metadata/text in bundled artifacts; operator legal review remains separate',
                   'python_wheels':components.get('python_packages',[]),
                   'node_packages':components.get('node_packages',[]),
                   'ocr_packages':components.get('ocr_runtime',[]),
                   'ollama_archives':components.get('ollama_runtime',[]),
                   'generative_model_license_layer':f'model-{license_layers[0]}',
                   'embedding_model':'local/models/multilingual-minilm/asset-manifest.json'}
        license_path=output/'licenses-inventory.json'
        license_path.write_text(json.dumps(inventory,indent=2)+'\n',encoding='utf-8')
        artifacts.append({'id':'licenses-inventory','path':license_path.name,'sha256':digest(license_path)})
        components['licenses']=['licenses-inventory']
    manifest=BundleManifest(schema_version='1.0',artifacts=artifacts,components=components)
    (output/'manifest.json').write_text(manifest.model_dump_json(indent=2)+'\n',encoding='utf-8')
    missing=[c for c in BUNDLE_COMPONENTS if c not in components]
    result={'status':'partial_bundle' if missing else 'components_staged','source_file_count':len(sources),'artifacts':artifacts,
            'components_staged':sorted(components),'components_missing':missing,
            'offline_validated':False,'platform':('windows-amd64+ubuntu-24.04-amd64' if include_local_models and 'ocr_runtime' in components else 'windows-amd64') if include_local_models else 'application-only',
            'scope':'Checksummed component inventory; installation and full-stack acceptance require separate evidence'}
    (output/'inventory.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(ROOT/'local/offline-bundle'))
    parser.add_argument('--include-local-models',action='store_true')
    args=parser.parse_args();print(json.dumps(build(args.output,include_local_models=args.include_local_models)))
