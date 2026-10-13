from contextlib import nullcontext
import json
import pytest
from backend.embeddings import LocalEmbeddings,checksum,verify_assets,configure_tokenizer
from backend.domain import Actor,Service,MemoryRepository
from backend.vector_adapter import PgVectorSearch,vector_literal

def test_assets_reject_tamper_and_different_revision(tmp_path):
    (tmp_path/'model.onnx').write_bytes(b'contract-fixture-not-a-real-model')
    profile={'model_id':'test','revision':'revision-1','files':['model.onnx']}
    manifest={**profile,'sha256':{'model.onnx':checksum(tmp_path/'model.onnx')}}
    (tmp_path/'asset-manifest.json').write_text(json.dumps(manifest))
    verify_assets(tmp_path,profile)
    (tmp_path/'model.onnx').write_bytes(b'changed')
    with pytest.raises(ValueError,match='checksum'):verify_assets(tmp_path,profile)
    with pytest.raises(ValueError,match='revision'):verify_assets(tmp_path,{**profile,'revision':'revision-2'})

def test_model_not_loaded_when_memory_guard_fails(monkeypatch,tmp_path):
    def blocked(gib):raise RuntimeError('resource_budget_unavailable')
    monkeypatch.setattr('backend.embeddings.require_memory',blocked)
    with pytest.raises(RuntimeError,match='resource_budget'):LocalEmbeddings(tmp_path,{'minimum_available_ram_gib':6})

def test_tokenizer_uses_pinned_special_token_and_rejects_missing_token(tmp_path):
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    tokenizer=Tokenizer(WordLevel({'<unk>':0,'<pad>':1,'hello':2},unk_token='<unk>'))
    tokenizer.pre_tokenizer=Whitespace()
    config=tmp_path/'tokenizer_config.json'
    config.write_text(json.dumps({'pad_token':'<pad>'}))
    configure_tokenizer(tokenizer,tmp_path,3)
    encoded=tokenizer.encode_batch(['hello','hello hello hello hello'])
    assert encoded[0].ids==[2,1,1]
    assert encoded[0].attention_mask==[1,0,0]
    assert len(encoded[1].ids)==3
    config.write_text(json.dumps({'pad_token':'[PAD]'}))
    with pytest.raises(ValueError,match='padding_token_missing'):
        configure_tokenizer(tokenizer,tmp_path,3)

def test_vector_query_scope_and_stale_row_validation():
    service=Service(MemoryRepository());actor=Actor('a','atlas','technician')
    doc=service.ingest(actor,'d','Document','Some evidence.')
    class Connection:
        def __init__(self):self.calls=[]
        def transaction(self):return nullcontext()
        def execute(self,sql,params):self.calls.append((sql,params));return self
        def fetchall(self):return [('d',1,doc.digest,1,0,14,'Some evidence.'),('foreign',1,doc.digest,1,0,6,'secret'),('d',2,doc.digest,1,0,14,'Some evidence.'),('d',1,doc.digest,1,0,6,'secret')]
    connection=Connection();adapter=PgVectorSearch(connection,'pinned-model@revision')
    result=adapter.search(service,actor,[0.0]*384)
    assert len(result)==1 and result[0]['quote']=='Some evidence.'
    sql,params=connection.calls[-1]
    assert params[:3]==('atlas',['d'],'pinned-model@revision')
    assert 'ANY(%s)' in sql and 'c.tenant_id=%s' in sql
    assert adapter.search(service,Actor('b','birch','technician'),[0.0]*384)==[]
    for vector in ([0.0]*383,[float('nan')]*384):
        with pytest.raises(ValueError):vector_literal(vector)
