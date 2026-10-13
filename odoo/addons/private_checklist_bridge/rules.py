"""Standalone receiver validation; no Odoo imports, filesystem or network."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
import html
from html.parser import HTMLParser
from uuid import UUID

REVISION = '6a55b9dc61acd87e61b3aacb4da97d61af84b0fa'
VERSION = 'private-checklist-1.0'


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',', ':'),ensure_ascii=False)


def render_note(payload):
    return '<pre>'+html.escape(canonical(payload))+'</pre>'


def note_matches(note,payload):
    class Reader(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts=[];self.tags=[];self.valid=True
        def handle_starttag(self,tag,attrs):
            self.tags.append(tag)
            if tag!='pre' or attrs:self.valid=False
        def handle_endtag(self,tag):
            self.tags.append('/'+tag)
        def handle_data(self,data):self.parts.append(data)
        def handle_comment(self,data):self.valid=False
    reader=Reader()
    try:reader.feed(str(note));reader.close()
    except Exception:return False
    return reader.valid and reader.tags==['pre','/pre'] and ''.join(reader.parts)==canonical(payload)


def validate(envelope, signature, key, tenant, company, now=None):
    try:
        raw=canonical(envelope).encode()
        if len(key)<32 or len(raw)>110000 or not isinstance(signature,str):raise ValueError()
        if not hmac.compare_digest(hmac.new(key,raw,hashlib.sha256).hexdigest(),signature):raise ValueError()
        if set(envelope)!={'operation_id','payload_hash','payload','requested_by','approved_by','expires_at'}:raise ValueError()
        UUID(envelope['operation_id'])
        p=envelope['payload']
        if set(p)!={'contract_version','upstream_revision','tenant','target','proposal_id','proposal_hash','prepared_by','reviewed_by','steps','source_versions','step_sources'}:raise ValueError()
        if p['contract_version']!=VERSION or p['upstream_revision']!=REVISION or p['tenant']!=tenant:raise ValueError()
        UUID(p['proposal_id'])
        if hashlib.sha256(canonical(p).encode()).hexdigest()!=envelope['payload_hash']:raise ValueError()
        if not re.fullmatch('[a-f0-9]{64}',p['proposal_hash']):raise ValueError()
        target=p['target']
        if set(target)!={'company_id','customer_id','opportunity_id','assignee_id'}:raise ValueError()
        if any(type(v) is not int or v<1 for v in target.values()) or target['company_id']!=company:raise ValueError()
        actors=[p['prepared_by'],p['reviewed_by'],envelope['requested_by'],envelope['approved_by']]
        if any(not isinstance(a,str) or not 1<=len(a)<=100 for a in actors):raise ValueError()
        if p['prepared_by']==p['reviewed_by'] or envelope['approved_by'] in {envelope['requested_by'],p['prepared_by']}:raise ValueError()
        expiry=datetime.fromisoformat(envelope['expires_at'])
        if expiry.tzinfo is None or expiry<=(now or datetime.now(timezone.utc)):raise ValueError()
        steps=p['steps'];sources=p['source_versions'];spans=p['step_sources']
        if not isinstance(steps,list) or not 1<=len(steps)<=30 or any(not isinstance(s,str) or not 1<=len(s)<=2000 or not s.strip() for s in steps):raise ValueError()
        if not isinstance(sources,list) or not 1<=len(sources)<=10:raise ValueError()
        versions={}
        for source in sources:
            if not isinstance(source,list) or len(source)!=3:raise ValueError()
            identifier,version,digest=source
            if not isinstance(identifier,str) or not 1<=len(identifier)<=100 or type(version) is not int or version<1 or not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError()
            if identifier in versions:raise ValueError()
            versions[identifier]=version
        if not isinstance(spans,list) or len(spans)!=len(steps):raise ValueError()
        for step,span in zip(steps,spans):
            if not isinstance(span,list) or len(span)!=5:raise ValueError()
            identifier,version,page,start,end=span
            if versions.get(identifier)!=version or any(type(v) is not int for v in (version,page,start,end)) or page<1 or start<0 or end-start!=len(step):raise ValueError()
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
        raise ValueError('invalid_checklist_envelope') from None
    return json.loads(raw)
