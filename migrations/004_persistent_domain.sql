-- Phase 7: retain exact page provenance and review metadata across restarts.
BEGIN;
ALTER TABLE documents ADD COLUMN deleted boolean NOT NULL DEFAULT false;
ALTER TABLE document_versions ADD COLUMN snapshot jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE checklist_proposals ADD COLUMN approver_id text;
ALTER TABLE checklist_proposals ADD CONSTRAINT proposal_approver_actor
 FOREIGN KEY (tenant_id,approver_id) REFERENCES actors(tenant_id,id);
CREATE INDEX document_chunks_cosine_hnsw ON document_chunks
 USING hnsw (embedding vector_cosine_ops);
COMMIT;
