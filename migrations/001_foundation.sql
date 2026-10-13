-- Prepared schema only. Real migration/RLS/transactions acceptance belongs to Phase 7.
BEGIN;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE tenants (id text PRIMARY KEY);
CREATE TABLE actors (
 tenant_id text NOT NULL REFERENCES tenants(id), id text NOT NULL,
 role text NOT NULL CHECK (role IN ('technician','service_manager','administrator','auditor')),
 PRIMARY KEY (tenant_id,id)
);
CREATE TABLE documents (
 tenant_id text NOT NULL REFERENCES tenants(id), id text NOT NULL, title text NOT NULL,
 current_version integer NOT NULL CHECK (current_version > 0),
 PRIMARY KEY (tenant_id,id)
);
CREATE TABLE document_grants (
 tenant_id text NOT NULL, document_id text NOT NULL, actor_id text NOT NULL,
 PRIMARY KEY (tenant_id,document_id,actor_id),
 FOREIGN KEY (tenant_id,document_id) REFERENCES documents(tenant_id,id),
 FOREIGN KEY (tenant_id,actor_id) REFERENCES actors(tenant_id,id)
);
CREATE TABLE document_versions (
 tenant_id text NOT NULL, document_id text NOT NULL, version integer NOT NULL CHECK (version > 0),
 content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
 body text NOT NULL, effective_date date, expires_date date,
 PRIMARY KEY (tenant_id,document_id,version),
 FOREIGN KEY (tenant_id,document_id) REFERENCES documents(tenant_id,id),
 CHECK (expires_date IS NULL OR effective_date IS NULL OR expires_date >= effective_date)
);
ALTER TABLE documents ADD CONSTRAINT current_document_version
 FOREIGN KEY (tenant_id,id,current_version) REFERENCES document_versions(tenant_id,document_id,version)
 DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE checklist_proposals (
 tenant_id text NOT NULL, id uuid NOT NULL, actor_id text NOT NULL,
 payload jsonb NOT NULL, payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
 status text NOT NULL CHECK (status IN ('review','approved','stale','rejected')),
 expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (tenant_id,id), UNIQUE (tenant_id,id,payload_hash),
 FOREIGN KEY (tenant_id,actor_id) REFERENCES actors(tenant_id,id)
);
CREATE TABLE proposal_sources (
 tenant_id text NOT NULL, proposal_id uuid NOT NULL, document_id text NOT NULL, version integer NOT NULL,
 PRIMARY KEY (tenant_id,proposal_id,document_id),
 FOREIGN KEY (tenant_id,proposal_id) REFERENCES checklist_proposals(tenant_id,id),
 FOREIGN KEY (tenant_id,document_id,version) REFERENCES document_versions(tenant_id,document_id,version)
);
CREATE TABLE approvals (
 tenant_id text NOT NULL, proposal_id uuid NOT NULL, payload_hash text NOT NULL,
 approver_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (tenant_id,proposal_id),
 FOREIGN KEY (tenant_id,proposal_id,payload_hash) REFERENCES checklist_proposals(tenant_id,id,payload_hash),
 FOREIGN KEY (tenant_id,approver_id) REFERENCES actors(tenant_id,id)
);
CREATE TABLE audit_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tenant_id text NOT NULL REFERENCES tenants(id), actor_id text NOT NULL,
 action text NOT NULL, resource_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
-- Each adapter transaction must SET LOCAL app.tenant_id and app.actor_id from
-- authenticated server identity. Never grant application roles BYPASSRLS/ownership.
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['actors','documents','document_grants','document_versions','checklist_proposals','proposal_sources','approvals','audit_events'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY tenant_boundary ON %I USING (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'',true),''''))',t);
 END LOOP;
END $$;
-- Restrictive policy composes with the tenant boundary above. Writes remain
-- domain-authorized; adapter acceptance must test denied grants and source drift.
CREATE POLICY document_read_grant ON documents AS RESTRICTIVE FOR SELECT USING (
 EXISTS (SELECT 1 FROM document_grants g WHERE g.tenant_id=documents.tenant_id
 AND g.document_id=documents.id AND g.actor_id=current_setting('app.actor_id',true))
);
CREATE POLICY version_read_grant ON document_versions AS RESTRICTIVE FOR SELECT USING (
 EXISTS (SELECT 1 FROM document_grants g WHERE g.tenant_id=document_versions.tenant_id
 AND g.document_id=document_versions.document_id AND g.actor_id=current_setting('app.actor_id',true))
);
COMMIT;
