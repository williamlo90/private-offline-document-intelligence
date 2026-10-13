"""Parameterized pgvector read contract. Connected execution is Phase 7 acceptance."""
import math
from backend.domain import DomainError

def vector_literal(values):
    if len(values)!=384 or any(not math.isfinite(v) for v in values):raise ValueError('invalid_vector')
    return '['+','.join(format(float(v),'.9g') for v in values)+']'

class PgVectorSearch:
    def __init__(self,connection,model_revision):
        self.connection=connection
        self.model_revision=model_revision

    def replace_index(self,service,actor,identifier,expected_version,chunks):
        if len(chunks)>1000:raise ValueError('chunk_limit')
        with service.repo.lock:
            document=service.read_document(actor,identifier)
            if document.version!=expected_version:raise DomainError('source_changed_or_expired',409)
            rows=[];keys=set()
            for chunk in chunks:
                page=next((p for p in document.pages if p.number==chunk['page']),None)
                start,end=chunk['start'],chunk['end']
                if page is None or not 0<=start<end<=len(page.text) or page.text[start:end]!=chunk['quote']:
                    raise DomainError('invalid_evidence',422)
                key=(chunk['page'],start)
                if key in keys:raise ValueError('duplicate_chunk')
                keys.add(key)
                rows.append((actor.tenant,identifier,document.version,chunk['page'],start,end,chunk['quote'],document.digest,self.model_revision,vector_literal(chunk['embedding'])))
            with self.connection.transaction():
                self.connection.execute("SELECT set_config('app.tenant_id', %s, true), set_config('app.actor_id', %s, true)",(actor.tenant,actor.id))
                current=self.connection.execute('SELECT current_version FROM documents WHERE tenant_id=%s AND id=%s FOR UPDATE',(actor.tenant,identifier)).fetchone()
                if current is None or current[0]!=expected_version:raise DomainError('source_changed_or_expired',409)
                self.connection.execute('DELETE FROM document_chunks WHERE tenant_id=%s AND document_id=%s AND embedding_model=%s',(actor.tenant,identifier,self.model_revision))
                for row in rows:
                    self.connection.execute('''INSERT INTO document_chunks
                        (tenant_id,document_id,version,page,start_offset,end_offset,quote,source_hash,embedding_model,embedding)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)''',row)
            return {'indexed_chunks':len(rows),'version':document.version,'model_revision':self.model_revision}

    def delete_index(self,service,actor,identifier):
        if actor.role!='service_manager':raise DomainError('forbidden')
        with service.repo.lock:
            service.read_document(actor,identifier)
            with self.connection.transaction():
                self.connection.execute("SELECT set_config('app.tenant_id', %s, true), set_config('app.actor_id', %s, true)",(actor.tenant,actor.id))
                self.connection.execute('SELECT current_version FROM documents WHERE tenant_id=%s AND id=%s FOR UPDATE',(actor.tenant,identifier))
                self.connection.execute('DELETE FROM document_chunks WHERE tenant_id=%s AND document_id=%s',(actor.tenant,identifier))
            return {'status':'index_deleted','document_id':identifier}

    def search(self,service,actor,embedding,limit=5):
        vector=vector_literal(embedding)
        with service.repo.lock:
            docs={d.id:d for d in service.list_documents(actor)}
            if not docs:return []
            with self.connection.transaction():
                self.connection.execute("SELECT set_config('app.tenant_id', %s, true), set_config('app.actor_id', %s, true)",(actor.tenant,actor.id))
                rows=self.connection.execute('''SELECT c.document_id,c.version,c.source_hash,c.page,c.start_offset,c.end_offset,c.quote
                    FROM document_chunks c JOIN documents d ON d.tenant_id=c.tenant_id AND d.id=c.document_id AND d.current_version=c.version
                    WHERE c.tenant_id=%s AND c.document_id=ANY(%s) AND c.embedding_model=%s
                    ORDER BY c.embedding <=> %s::vector LIMIT %s''',(actor.tenant,list(docs),self.model_revision,vector,max(1,min(limit,20)))).fetchall()
            result=[]
            for identifier,version,digest,page,start,end,quote in rows:
                document=docs.get(identifier)
                if document is None or document.version!=version or document.digest!=digest:continue
                source=next((p for p in document.pages if p.number==page),None)
                if source is None or not 0<=start<end<=len(source.text) or source.text[start:end]!=quote:continue
                result.append({'document_id':identifier,'version':version,'sha256':digest,'page':page,'start':start,'end':end,'quote':quote,'method':'pgvector'})
            return result
