import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.domain import Actor
from backend.worker_runtime import attach_worker


ROOT=Path(__file__).resolve().parents[1]


def test_api_worker_shares_repository_and_authorized_review_queue(tmp_path):
    source=tmp_path/'source';source.mkdir()
    (source/'backup.pdf').write_bytes((ROOT/'evaluation/development/atlas-backup-v1.pdf').read_bytes())
    checkpoint=tmp_path/'worker.json';config=tmp_path/'watch.json'
    config.write_text(json.dumps({'actor_id':'tech','root':str(source),'checkpoint':str(checkpoint),
                                  'sources':[{'id':'watched','path':'backup.pdf','title':'Watched backup'},
                                             {'id':'missing','path':'missing.pdf','title':'Missing SOP'}],
                                  'poll_seconds':5}))
    tech=Actor('tech','atlas','technician');other=Actor('other','birch','technician')
    tokens={'atlas-fixture-token-1234567890123':tech,'birch-fixture-token-1234567890123':other}
    app=create_app(tokens);attach_worker(app,tokens.values(),config)
    with TestClient(app) as client:
        assert app.state.worker_first_poll.wait(10)
        headers={'Authorization':'Bearer atlas-fixture-token-1234567890123'}
        documents=client.get('/documents',headers=headers).json()
        assert any(item['id']=='watched' for item in documents)
        assert client.get('/search?q=backup',headers=headers).json()
        reviews=client.get('/source-reviews',headers=headers).json()
        assert {'document_id':'missing','version':None,'reasons':['source_missing'],'available':False} in reviews
        other_reviews=client.get('/source-reviews',headers={'Authorization':'Bearer birch-fixture-token-1234567890123'}).json()
        assert other_reviews==[]
