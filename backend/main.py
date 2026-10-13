"""Entrypoint: PRIVATE_LAB_CONFIG must point to a local, ignored identity file."""
import json
import os
from pathlib import Path

from backend.api import create_app
from backend.domain import Actor
from backend.pdf_parser import Page


def load_app():
    path = os.environ.get('PRIVATE_LAB_CONFIG')
    if not path:
        raise RuntimeError('PRIVATE_LAB_CONFIG is required; generate an isolated lab profile first')
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    database_config = os.environ.get('PRIVATE_DB_CONFIG')
    expected_profile = 'persistent-postgres-lab' if database_config else 'native-memory-harness'
    if config.get('profile') != expected_profile:
        raise RuntimeError('Identity profile does not match configured persistence mode')
    actors = {}
    for entry in config['actors']:
        actor = Actor(entry['id'], entry['tenant'], entry['role'],
                      None if entry.get('document_ids') is None else frozenset(entry['document_ids']))
        if entry['token'] in actors:
            raise ValueError('Duplicate identity token')
        actors[entry['token']] = actor
    repository = None
    if database_config:
        from backend.postgres_repository import PostgresRepository
        settings = json.loads(Path(database_config).read_text(encoding='utf-8'))
        if settings.get('profile') != 'persistent-postgres-lab':
            raise RuntimeError('Database profile must be the explicit Phase 7 lab profile')
        repository = PostgresRepository({key: settings[key] for key in
                                        ('host', 'port', 'dbname', 'user', 'password')}, list(actors.values()))
    application = create_app(actors, repository)
    bridge_config = os.environ.get('PRIVATE_ODOO_CONFIG')
    if bridge_config:
        if repository is None:
            raise RuntimeError('Live Odoo bridge requires persistent PostgreSQL repository')
        from backend.bridge_adapter import BridgeProfile, SignedChecklistBridge
        from backend.odoo_contract import Target
        from backend.persistent_save_operations import PersistentSaveOperations

        settings = json.loads(Path(bridge_config).read_text(encoding='utf-8'))
        if settings.get('profile') != 'project07-connected-odoo-lab' or set(settings['bridges']) != {'atlas', 'birch'}:
            raise RuntimeError('Expected isolated two-company Odoo bridge profile')
        bridges = {tenant: SignedChecklistBridge(BridgeProfile.model_validate(row['bridge']))
                   for tenant, row in settings['bridges'].items()}
        targets = {tenant: Target.model_validate(row['target'])
                   for tenant, row in settings['bridges'].items()}
        application.state.save_ops = PersistentSaveOperations(application.state.service, targets, bridges)
    model_profile = os.environ.get('PRIVATE_OLLAMA_PROFILE')
    if model_profile:
        from backend.ollama_adapter import OllamaGenerator, OllamaProfile
        profile = OllamaProfile.model_validate_json(Path(model_profile).read_bytes())
        queue_wait = float(os.environ.get('PRIVATE_INFERENCE_QUEUE_WAIT_SECONDS', '0'))
        application.state.skills.assistant.generator = OllamaGenerator(
            profile, queue_wait_seconds=queue_wait)
    # Seed synthetic sources only. No general filesystem upload or path is exposed to clients.
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'evaluation/development/manifest.json').read_text(encoding='utf-8'))
    for document in manifest['documents']:
        importer = next(a for a in actors.values() if a.tenant == document['tenant'] and a.role == 'technician')
        application.state.service.ingest(importer, document['id'], document['id'],
                                         '\n\n'.join(p['text'] for p in document['pages']),
                                         pages=tuple(Page(p['number'],p['text'],'synthetic-seed') for p in document['pages']),
                                         effective=document['effective'],expires=document['expires'],family=document['family'])
    worker_config=os.environ.get('PRIVATE_WORKER_CONFIG')
    if worker_config:
        from backend.worker_runtime import attach_worker
        attach_worker(application,actors.values(),worker_config)
    return application
