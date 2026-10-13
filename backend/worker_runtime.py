"""Attach the document watcher to the native API's own repository process."""
import json
from pathlib import Path
from threading import Event,Thread

from backend.document_worker import DocumentWorker,WatchedSource


def attach_worker(app, identities, config_path):
    path=Path(config_path).resolve()
    if path.stat().st_size>100_000:raise ValueError('Worker configuration too large')
    config=json.loads(path.read_text(encoding='utf-8'))
    if set(config)-{'actor_id','root','checkpoint','sources','poll_seconds'}:
        raise ValueError('Unknown worker configuration field')
    actor=next((actor for actor in identities if actor.id==config['actor_id']),None)
    if actor is None or actor.role!='technician':raise ValueError('Worker requires a configured technician identity')
    interval=config.get('poll_seconds',10)
    if type(interval) is not int or not 5<=interval<=60:raise ValueError('poll_seconds must be 5-60')
    worker=DocumentWorker(app.state.service,actor,config['root'],config['checkpoint'],
                          [WatchedSource(**source) for source in config['sources']])
    stop=Event();started=Event();thread=None
    app.state.worker_identity=(actor.tenant,actor.id)
    app.state.worker_state=None
    app.state.worker_error=None

    def loop():
        while not stop.is_set():
            try:
                app.state.worker_state=worker.run_once()
                app.state.worker_error=None
            except Exception as error:
                # Keep the service up; expose only a code, never source content.
                app.state.worker_error=getattr(error,'code','worker_failed')
            finally:started.set()
            stop.wait(interval)

    def start():
        nonlocal thread
        if thread is None:
            thread=Thread(target=loop,name='project07-document-worker',daemon=True)
            thread.start()

    def shutdown():
        stop.set()
        if thread is not None:thread.join(timeout=5)

    app.router.add_event_handler('startup',start)
    app.router.add_event_handler('shutdown',shutdown)
    app.state.worker_first_poll=started
    return worker
