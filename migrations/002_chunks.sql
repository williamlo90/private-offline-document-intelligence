BEGIN;
CREATE TABLE document_chunks (
 tenant_id text NOT NULL,document_id text NOT NULL,version integer NOT NULL,
 page integer NOT NULL CHECK(page>0),start_offset integer NOT NULL CHECK(start_offset>=0),
 end_offset integer NOT NULL CHECK(end_offset>start_offset),quote text NOT NULL,
 source_hash text NOT NULL,embedding_model text NOT NULL,embedding vector(384) NOT NULL,
 PRIMARY KEY(tenant_id,document_id,version,page,start_offset,embedding_model),
 FOREIGN KEY(tenant_id,document_id,version) REFERENCES document_versions(tenant_id,document_id,version)
);
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY;
CREATE POLICY authorized_chunks ON document_chunks USING (
 tenant_id=nullif(current_setting('app.tenant_id',true),'') AND EXISTS(
 SELECT 1 FROM document_grants g WHERE g.tenant_id=document_chunks.tenant_id
 AND g.document_id=document_chunks.document_id AND g.actor_id=current_setting('app.actor_id',true))
);
-- Planner/index/concurrency behavior must be validated on the real Phase 7 backend.
COMMIT;
