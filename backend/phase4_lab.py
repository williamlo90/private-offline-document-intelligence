"""Explicit synthetic Phase 4 harness. Never configure this against real Odoo."""
from copy import deepcopy

from backend.main import load_app as load_base_app
from backend.odoo_contract import CONTRACT_VERSION, UPSTREAM_REVISION, Target
from backend.save_operations import MemorySaveLedger, SaveOperations


class SyntheticBridge:
    def __init__(self):
        self.receipts={}

    def info(self):
        return {'contract_version':CONTRACT_VERSION,'upstream_revision':UPSTREAM_REVISION,
                'atomic_receipt':True,'full_checklist_readback':True}

    def execute(self,envelope):
        operation_id=envelope['operation_id']
        if operation_id not in self.receipts:
            self.receipts[operation_id]={'operation_id':operation_id,
                'payload_hash':envelope['payload_hash'],'external_id':42,
                'payload':deepcopy(envelope['payload'])}
        raise TimeoutError('synthetic lost response after receipt')

    def status(self,tenant,company_id,operation_id):
        receipt=self.receipts.get(operation_id)
        if receipt is None or receipt['payload']['tenant']!=tenant or receipt['payload']['target']['company_id']!=company_id:
            return None
        return deepcopy(receipt)


def load_app():
    app=load_base_app()
    app.state.save_ops=SaveOperations(app.state.service,MemorySaveLedger(),
        {'atlas':Target(company_id=1,customer_id=2,opportunity_id=3,assignee_id=4),
         'birch':Target(company_id=5,customer_id=6,opportunity_id=7,assignee_id=8)},
        SyntheticBridge())
    return app
