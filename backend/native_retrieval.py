"""Local vector index for the native memory harness; current ACL is checked on every read."""
from datetime import date
import math
from threading import RLock

from backend.domain import DomainError
from backend.retrieval import document_chunks, document_status


class NativeVectorIndex:
    def __init__(self, encoder, model_revision):
        self.encoder = encoder
        self.model_revision = model_revision
        self.lock = RLock()
        self.entries = {}

    def search(self, service, actor, query, as_of=None, limit=5):
        if not query.strip() or len(query) > 1000:
            raise DomainError('invalid_query', 422)
        as_of = as_of or date.today()
        # Hold the domain lock through generation and ranking: a permission or
        # version change cannot race an already-authorized result into output.
        with service.repo.lock, self.lock:
            documents = service.list_documents(actor)
            current = {(d.tenant, d.id):(d.version,d.digest) for d in service.repo.documents(actor.tenant) if not d.deleted}
            for key, (version, digest, _) in list(self.entries.items()):
                if key[0] == actor.tenant and current.get(key) != (version, digest):
                    del self.entries[key]
            missing = []
            for document in documents:
                key=(document.tenant,document.id)
                if key not in self.entries:
                    chunks=list(document_chunks(document))
                    if len(chunks)>1000:
                        raise DomainError('index_capacity',413)
                    missing.append((document,chunks))
            if sum(len(chunks) for _,chunks in missing)>5000:
                raise DomainError('index_capacity',413)
            for document,chunks in missing:
                vectors=[]
                for offset in range(0,len(chunks),32):
                    vectors.extend(self.encoder.embed([c['quote'] for c in chunks[offset:offset+32]]))
                if len(vectors)!=len(chunks):
                    raise ValueError('embedding_count_mismatch')
                for chunk, vector in zip(chunks,vectors):
                    if len(vector)!=384 or not all(math.isfinite(v) for v in vector):
                        raise ValueError('invalid_embedding')
                    chunk['embedding']=vector
                self.entries[(document.tenant,document.id)]=(document.version,document.digest,chunks)
            if not documents:
                return []
            needle=self.encoder.embed([query])[0]
            if len(needle)!=384 or not all(math.isfinite(v) for v in needle):
                raise ValueError('invalid_embedding')
            rows=[]
            for document in documents:
                version,digest,chunks=self.entries[(document.tenant,document.id)]
                state=document_status(document,documents,as_of)
                for chunk in chunks:
                    page=next((p for p in document.pages if p.number==chunk['page']),None)
                    if (page is None or version!=document.version or digest!=document.digest or
                            page.text[chunk['start']:chunk['end']]!=chunk['quote']):
                        continue
                    score=sum(a*b for a,b in zip(needle,chunk['embedding']))
                    rows.append({'document_id':document.id,'version':version,'sha256':digest,
                                 'page':chunk['page'],'start':chunk['start'],'end':chunk['end'],'quote':chunk['quote'],
                                 'status':'review' if chunk['quality']=='review' else state,
                                 'score':score,'method':'native-vector-v1','model_revision':self.model_revision})
            return sorted(rows,key=lambda r:(-r['score'],r['document_id'],r['page'],r['start']))[:max(1,min(limit,20))]
