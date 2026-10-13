"""Single-run local watcher/worker with atomic checkpoint, no automatic actions."""
from contextlib import contextmanager
from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path
import time
from backend.domain import DomainError
from backend.pdf_parser import MAX_BYTES, ParseError, parse_pdf


@dataclass(frozen=True)
class WatchedSource:
    id: str
    path: str
    title: str
    language: str = 'eng'
    effective: str | None = None
    expires: str | None = None
    family: str = ''


@contextmanager
def checkpoint_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            if path.stat().st_size == 0:
                handle.write(b'0');handle.flush();handle.seek(0)
            try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise DomainError('worker_busy',503) from None
        else:
            import fcntl
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:raise DomainError('worker_busy',503) from None
        try:yield
        finally:
            if os.name=='nt':handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle,fcntl.LOCK_UN)


class DocumentWorker:
    def __init__(self, service, actor, root, checkpoint, sources, *, parser=parse_pdf, clock=time.time):
        self.service,self.actor=service,actor
        self.root,self.checkpoint=Path(root).resolve(),Path(checkpoint)
        self.sources=list(sources);self.parser,self.clock=parser,clock
        if not 1<=len(self.sources)<=100 or len({s.id for s in self.sources})!=len(self.sources):
            raise ValueError('worker source limit or duplicate identifier')
        if any(s.language not in {'eng','ind'} or not s.id or not s.title for s in self.sources):
            raise ValueError('invalid source configuration')

    def _read(self, source):
        relative=Path(source.path);path=(self.root/relative).resolve()
        if relative.is_absolute() or '..' in relative.parts or ':' in source.path or not path.is_relative_to(self.root):
            raise ParseError('unsafe_source_path')
        if not path.is_file():raise ParseError('source_missing')
        with path.open('rb') as handle:data=handle.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:raise ParseError('file_too_large')
        return data,hashlib.sha256(data).hexdigest()

    def _save(self,state):
        temp=self.checkpoint.with_suffix(self.checkpoint.suffix+'.tmp')
        with temp.open('w',encoding='utf-8') as handle:
            json.dump(state,handle,indent=2);handle.flush();os.fsync(handle.fileno())
        os.replace(temp,self.checkpoint)

    def run_once(self):
        with checkpoint_lock(self.checkpoint.with_suffix('.lock')):
            identity={'tenant':self.actor.tenant,'actor':self.actor.id}
            state={'schema_version':1,**identity,'entries':{}}
            if self.checkpoint.exists():
                if self.checkpoint.stat().st_size>1_000_000:raise DomainError('invalid_worker_checkpoint',409)
                try:
                    state=json.loads(self.checkpoint.read_text(encoding='utf-8'))
                    if state['schema_version']!=1 or any(state[k]!=v for k,v in identity.items()) or not isinstance(state['entries'],dict):raise ValueError()
                except (ValueError,KeyError,TypeError):raise DomainError('invalid_worker_checkpoint',409) from None
            # Current permissions are checked before any source bytes are read.
            authorized={d.id:d for d in self.service.list_documents(self.actor)}
            state['entries']={key:value for key,value in state['entries'].items() if key in {s.id for s in self.sources}}
            entries=state['entries'];pending=[]
            for source in self.sources:
                if ((self.actor.document_ids is not None and source.id not in self.actor.document_ids) or
                    self.service.repo.is_revoked(self.actor.tenant,self.actor.id,source.id)):
                    entries[source.id]={'status':'review','error':'forbidden'};continue
                try:data,digest=self._read(source)
                except (OSError,ParseError) as error:
                    entries[source.id]={'status':'review','error':getattr(error,'code','source_unreadable')};continue
                previous=entries.get(source.id,{})
                config_hash=hashlib.sha256(json.dumps(asdict(source),sort_keys=True).encode()).hexdigest()
                same=previous.get('digest')==digest and previous.get('config_hash')==config_hash
                document=authorized.get(source.id)
                if same and previous.get('status')=='done' and document and document.digest==digest:
                    continue
                if same and previous.get('status')=='review':continue
                if same and previous.get('retry_at',0)>self.clock():continue
                if len(pending)>=10:continue  # Remaining sources reconsidered on the next poll.
                attempts=previous.get('attempts',0) if same and previous.get('status')!='done' else 0
                if attempts>=3:
                    entries[source.id]={**previous,'status':'review','error':'retry_limit'};continue
                entries[source.id]={'status':'pending','digest':digest,'config_hash':config_hash,'attempts':attempts}
                pending.append(source)
            self._save(state)
            for source in pending:
                entry=entries[source.id]
                # Persist attempt before processing so crashes consume the retry budget.
                entry['attempts']+=1;entry['status']='processing';self._save(state)
                try:
                    data,digest=self._read(source)
                    if digest!=entry['digest']:raise ParseError('source_changed')
                    parsed=self.parser(data,source.language)
                    if self._read(source)[1]!=digest:raise ParseError('source_changed')
                    document=self.service.ingest(self.actor,source.id,source.title,'\n\n'.join(p.text for p in parsed.pages),
                        pages=parsed.pages,source_hash=parsed.sha256,effective=source.effective,expires=source.expires,family=source.family)
                    review=any(p.quality!='usable' for p in parsed.pages)
                    entry.update(status='review' if review else 'done',version=document.version,index='keyword-current',
                                 error='source_requires_review' if review else None)
                except (ParseError,DomainError,OSError) as error:
                    code=getattr(error,'code','source_unreadable')
                    transient=code in {'parser_busy','parse_timeout','ocr_timeout','source_changed'}
                    entry.update(status='pending' if transient and entry['attempts']<3 else 'review',error=code,
                                 retry_at=self.clock()+min(60,2**entry['attempts']))
                self._save(state)
            # Return metadata only; checkpoint stores no document content or tokens.
            return state
