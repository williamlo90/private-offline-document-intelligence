-- Prepared only: native PostgreSQL execution/RLS/crash acceptance remains Phase 7.
BEGIN;
CREATE TABLE save_operations (
 tenant_id text NOT NULL,
 id uuid NOT NULL,
 proposal_id uuid NOT NULL,
 requested_by text NOT NULL,
 approved_by text,
 payload jsonb NOT NULL,
 payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
 status text NOT NULL CHECK (status IN ('review','approved','dispatched','unknown','verified')),
 expires_at timestamptz NOT NULL,
 attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 1),
 revision integer NOT NULL DEFAULT 0 CHECK (revision >= 0),
 external_id bigint CHECK (external_id > 0),
 error_code text,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (tenant_id,id),
 UNIQUE (tenant_id,proposal_id),
 FOREIGN KEY (tenant_id,proposal_id) REFERENCES checklist_proposals(tenant_id,id),
 FOREIGN KEY (tenant_id,requested_by) REFERENCES actors(tenant_id,id),
 FOREIGN KEY (tenant_id,approved_by) REFERENCES actors(tenant_id,id),
 CHECK (approved_by IS NULL OR approved_by <> requested_by),
 CHECK (status NOT IN ('approved','dispatched','unknown','verified') OR approved_by IS NOT NULL),
 CHECK (status NOT IN ('dispatched','unknown','verified') OR attempts = 1),
 CHECK (status <> 'verified' OR external_id IS NOT NULL),
 CHECK (payload ? 'tenant' AND payload->>'tenant' IS NOT NULL AND payload->>'tenant' = tenant_id),
 CHECK (payload ? 'proposal_id' AND payload->>'proposal_id' IS NOT NULL AND payload->>'proposal_id' = proposal_id::text)
);
ALTER TABLE save_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE save_operations FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_save_operations ON save_operations USING (
 tenant_id = nullif(current_setting('app.tenant_id',true),'')
 AND EXISTS (SELECT 1 FROM actors a WHERE a.tenant_id=save_operations.tenant_id
   AND a.id=current_setting('app.actor_id',true) AND a.role='service_manager')
 AND EXISTS (SELECT 1 FROM proposal_sources s WHERE s.tenant_id=save_operations.tenant_id AND s.proposal_id=save_operations.proposal_id)
 AND NOT EXISTS (SELECT 1 FROM proposal_sources s WHERE s.tenant_id=save_operations.tenant_id AND s.proposal_id=save_operations.proposal_id
   AND NOT EXISTS (SELECT 1 FROM document_grants g WHERE g.tenant_id=s.tenant_id AND g.document_id=s.document_id
     AND g.actor_id=current_setting('app.actor_id',true)))
);
COMMIT;
