"""Operator-owned local watch manifest; harness process, no Odoo/model actions."""
import argparse
import json
import os
from pathlib import Path
import time
from backend.document_worker import DocumentWorker, WatchedSource
from backend.main import load_app
from backend.domain import Actor


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--watch',action='store_true')
    args=parser.parse_args()
    config=json.loads(Path(args.config).read_text(encoding='utf-8'))
    # Identity comes from the same server-owned lab profile as the API.
    identities=json.loads(Path(os.environ['PRIVATE_LAB_CONFIG']).read_text(encoding='utf-8'))
    entry=next(a for a in identities['actors'] if a['id']==config['actor_id'])
    actor=Actor(entry['id'],entry['tenant'],entry['role'],
                None if entry.get('document_ids') is None else frozenset(entry['document_ids']))
    app=load_app()
    worker=DocumentWorker(app.state.service,actor,config['root'],config['checkpoint'],
                          [WatchedSource(**source) for source in config['sources']])
    interval=config.get('poll_seconds',10)
    if type(interval) is not int or not 5<=interval<=60:raise ValueError('poll_seconds must be 5-60')
    try:
        while True:
            result=worker.run_once()
            counts={status:sum(e['status']==status for e in result['entries'].values())
                    for status in ('pending','processing','done','review')}
            print(json.dumps({'status':'completed_poll','counts':counts,'persistence':'memory-harness','vector_index':'pending'}),flush=True)
            if not args.watch:break
            time.sleep(interval)
    except KeyboardInterrupt:
        return


if __name__=='__main__':main()
