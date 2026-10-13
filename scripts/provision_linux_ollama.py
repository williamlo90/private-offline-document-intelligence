"""Online provisioning only: fetch one pinned Ollama Linux archive with ranged requests."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]


def provision(parts=8):
    lock=json.loads((ROOT/'config/ollama-linux-runtime-lock.json').read_text())
    target=ROOT/'local/runtime/ollama-linux-amd64-v0.40.3.tar.zst'
    if target.exists():
        if target.stat().st_size==lock['bytes']:
            digest=hashlib.sha256()
            with target.open('rb') as source:
                while chunk:=source.read(1024*1024):digest.update(chunk)
            if digest.hexdigest()==lock['sha256']:return target
        raise ValueError('Existing Linux archive does not match pinned release')
    if not 1<=parts<=8 or shutil.disk_usage(target.parent).free<lock['bytes']*2+1024**3:
        raise ValueError('Linux archive download resource budget exceeded')
    def fetch(index):
        start=index*lock['bytes']//parts
        end=(index+1)*lock['bytes']//parts-1
        path=target.with_name(target.name+f'.part{index}')
        if path.exists() and path.stat().st_size==end-start+1:return path
        request=Request(lock['source'],headers={'Range':f'bytes={start}-{end}','User-Agent':'Project07-offline-provisioning'})
        with urlopen(request,timeout=45) as response:
            if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{lock["bytes"]}':
                raise ValueError('Release server did not honor pinned byte range')
            with path.open('wb') as output:shutil.copyfileobj(response,output,1024*1024)
        if path.stat().st_size!=end-start+1:raise ValueError('Incomplete archive segment')
        return path
    with ThreadPoolExecutor(max_workers=parts) as pool:
        segments=list(pool.map(fetch,range(parts)))
    temporary=target.with_suffix(target.suffix+'.assembling')
    digest=hashlib.sha256()
    with temporary.open('wb') as output:
        for path in segments:
            with path.open('rb') as source:
                while chunk:=source.read(1024*1024):output.write(chunk);digest.update(chunk)
    if temporary.stat().st_size!=lock['bytes'] or digest.hexdigest()!=lock['sha256']:
        temporary.unlink(missing_ok=True)
        raise ValueError('Pinned Ollama Linux archive checksum mismatch')
    temporary.replace(target)
    for path in segments:path.unlink()
    return target


if __name__=='__main__':print(provision())
