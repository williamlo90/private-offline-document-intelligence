"""Explicit online provisioning only. No documents are sent to the download host."""
import json
from pathlib import Path
import shutil
from urllib.request import urlopen
from backend.embeddings import checksum
from backend.resources import require_memory

root=Path(__file__).resolve().parents[1]
profile=json.loads((root/'config/embedding-profile.json').read_text(encoding='utf-8-sig'))
# Streaming provisioning does not import ONNX or load model tensors. Keep a
# separate reserve; inference retains its larger guard in embedding-profile.json.
require_memory(.5)
if shutil.disk_usage(root).free<2*1024**3:raise RuntimeError('insufficient_disk')
directory=root/'local/models/multilingual-minilm';directory.mkdir(parents=True,exist_ok=True)
hashes={}
for filename in profile['files']:
    target=directory/filename;target.parent.mkdir(parents=True,exist_ok=True)
    url=f"https://huggingface.co/{profile['model_id']}/resolve/{profile['revision']}/{filename}"
    temporary=target.with_suffix(target.suffix+'.download')
    size=0
    with urlopen(url,timeout=60) as response, temporary.open('wb') as out:
        while block:=response.read(1024*1024):
            size+=len(block)
            if size>200*1024**2:raise RuntimeError('asset_size_limit')
            require_memory(.5)
            out.write(block)
    temporary.replace(target);hashes[filename]=checksum(target)
manifest={'model_id':profile['model_id'],'revision':profile['revision'],'license':profile['license'],'sha256':hashes}
(directory/'asset-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'status':'provisioned','files':len(hashes),'inference':'not run'}))
