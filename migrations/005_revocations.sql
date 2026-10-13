-- Explicit revocations preserve default access for newly ingested documents.
BEGIN;
CREATE TABLE document_revocations (
 tenant_id text NOT NULL, document_id text NOT NULL, actor_id text NOT NULL,
 PRIMARY KEY (tenant_id,document_id,actor_id),
 FOREIGN KEY (tenant_id,document_id) REFERENCES documents(tenant_id,id),
 FOREIGN KEY (tenant_id,actor_id) REFERENCES actors(tenant_id,id)
);
ALTER TABLE document_revocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_revocations FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_revocations ON document_revocations
 USING (tenant_id=nullif(current_setting('app.tenant_id',true),''))
 WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),''));

DROP POLICY document_read_grant ON documents;
CREATE POLICY document_read_grant ON documents AS RESTRICTIVE FOR SELECT USING (
 EXISTS (SELECT 1 FROM document_grants g WHERE g.tenant_id=documents.tenant_id
 AND g.document_id=documents.id AND g.actor_id=current_setting('app.actor_id',true))
 AND NOT EXISTS (SELECT 1 FROM document_revocations r WHERE r.tenant_id=documents.tenant_id
 AND r.document_id=documents.id AND r.actor_id=current_setting('app.actor_id',true))
);
DROP POLICY version_read_grant ON document_versions;
CREATE POLICY version_read_grant ON document_versions AS RESTRICTIVE FOR SELECT USING (
 EXISTS (SELECT 1 FROM document_grants g WHERE g.tenant_id=document_versions.tenant_id
 AND g.document_id=document_versions.document_id AND g.actor_id=current_setting('app.actor_id',true))
 AND NOT EXISTS (SELECT 1 FROM document_revocations r WHERE r.tenant_id=document_versions.tenant_id
 AND r.document_id=document_versions.document_id AND r.actor_id=current_setting('app.actor_id',true))
);
DROP POLICY authorized_chunks ON document_chunks;
CREATE POLICY authorized_chunks ON document_chunks USING (
 tenant_id=nullif(current_setting('app.tenant_id',true),'') AND EXISTS(
 SELECT 1 FROM document_grants g WHERE g.tenant_id=document_chunks.tenant_id
 AND g.document_id=document_chunks.document_id AND g.actor_id=current_setting('app.actor_id',true))
 AND NOT EXISTS (SELECT 1 FROM document_revocations r WHERE r.tenant_id=document_chunks.tenant_id
 AND r.document_id=document_chunks.document_id AND r.actor_id=current_setting('app.actor_id',true))
);
COMMIT;
