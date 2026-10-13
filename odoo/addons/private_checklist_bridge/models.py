"""Project-owned extension; prepared for isolated Odoo 19 acceptance only."""
import os
from uuid import UUID
from odoo import api, fields, models
from odoo.exceptions import ValidationError
from .rules import validate, render_note, note_matches, VERSION, REVISION


class ChecklistReceipt(models.Model):
    _name = 'private.checklist.receipt'
    _description = 'Atomic private checklist receipt'
    operation_id = fields.Char(required=True,index=True)
    proposal_id = fields.Char(required=True,index=True)
    company_id = fields.Many2one('res.company',required=True)
    tenant = fields.Char(required=True)
    payload_hash = fields.Char(required=True)
    payload = fields.Json(required=True)
    activity_id = fields.Many2one('mail.activity',required=True,ondelete='restrict')
    _operation_unique = models.Constraint('UNIQUE(operation_id)','Operation already exists')
    _proposal_unique = models.Constraint('UNIQUE(tenant, proposal_id)','Checklist already saved')
    # No user ACL grants. Access only through scoped facade using upstream helpers.


class PrivateBridge(models.AbstractModel):
    _name = 'private.checklist.bridge'
    _inherit = 'ops.bridge'
    _description = 'Full sourced checklist extension'

    @api.model
    def info(self):
        b=self._binding()
        return {'contract_version':VERSION,'upstream_revision':REVISION,'tenant':b.tenant,
                'company_id':b.company_id.id,'atomic_receipt':True,'full_checklist_readback':True}

    def _note(self,payload):
        return render_note(payload)

    def _receipt(self,record,b):
        activity=record.activity_id.exists()
        p=record.payload;target=p['target']
        if (not activity or record.tenant!=b.tenant or record.company_id!=b.company_id or
            activity.res_model!='crm.lead' or activity.res_id!=target['opportunity_id'] or
            activity.user_id.id!=target['assignee_id'] or not note_matches(activity.note,p)):
            raise ValidationError('OPS:postcondition_failed')
        lead=self._record('crm.lead',activity.res_id,b)
        if lead.partner_id.id!=target['customer_id']:
            raise ValidationError('OPS:postcondition_failed')
        return {'operation_id':record.operation_id,'payload_hash':record.payload_hash,
                'external_id':activity.id,'payload':p}

    @api.model
    def status(self,operation_id):
        b=self._binding()
        try:UUID(operation_id)
        except (ValueError,TypeError,AttributeError):raise ValidationError('OPS:invalid_input') from None
        record=self._model('private.checklist.receipt',b).search([
            ('operation_id','=',operation_id),('tenant','=',b.tenant),('company_id','=',b.company_id.id)],limit=1)
        return self._receipt(record,b) if record else None

    @api.model
    def execute(self,envelope,signature):
        self._binding()
        with self.env.registry.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
            scoped=self.with_env(api.Environment(cursor,self.env.uid,{}))
            result=scoped._execute_checklist(envelope,signature)
            cursor.commit()
            return result

    def _execute_checklist(self,envelope,signature):
        self.env.cr.execute("SET LOCAL lock_timeout = '3s'")
        self.env.cr.execute('LOCK TABLE ops_connection, res_company, res_partner, crm_lead, res_users, res_company_users_rel, private_checklist_receipt IN SHARE ROW EXCLUSIVE MODE')
        b=self._binding()
        try:envelope=validate(envelope,signature,os.environ.get('PRIVATE_CHECKLIST_SIGNING_KEY','').encode(),b.tenant,b.company_id.id)
        except ValueError:raise ValidationError('OPS:invalid_signature_or_payload') from None
        p=envelope['payload'];target=p['target']
        receipts=self._model('private.checklist.receipt',b)
        existing=receipts.search([('operation_id','=',envelope['operation_id'])],limit=1)
        if existing:
            if existing.tenant!=b.tenant or existing.company_id!=b.company_id or existing.payload_hash!=envelope['payload_hash']:
                raise ValidationError('OPS:idempotency_conflict')
            return self._receipt(existing,b)
        if receipts.search_count([('tenant','=',b.tenant),('proposal_id','=',p['proposal_id'])]):
            raise ValidationError('OPS:idempotency_conflict')
        customer=self._record('res.partner',target['customer_id'],b)
        lead=self._record('crm.lead',target['opportunity_id'],b)
        user=self._model('res.users',b).browse(target['assignee_id']).exists()
        if (not customer.active or not lead.active or lead.type!='opportunity' or lead.partner_id!=customer or
            not user or not user.active or user.share or b.company_id not in user.company_ids):
            raise ValidationError('OPS:scope_mismatch')
        activity=self._model('mail.activity',b).create({'res_model_id':self.env['ir.model']._get_id('crm.lead'),
            'res_id':lead.id,'activity_type_id':self.env.ref('mail.mail_activity_data_todo').id,
            'user_id':user.id,'summary':'Reviewed MSP checklist','note':self._note(p),
            'date_deadline':fields.Date.today()})
        receipt=receipts.create({'operation_id':envelope['operation_id'],'proposal_id':p['proposal_id'],
            'company_id':b.company_id.id,'tenant':b.tenant,'payload_hash':envelope['payload_hash'],
            'payload':p,'activity_id':activity.id})
        return self._receipt(receipt,b)
