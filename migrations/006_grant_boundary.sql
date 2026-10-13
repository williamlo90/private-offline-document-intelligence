-- A normal app transaction cannot mint document access grants for itself.
BEGIN;
ALTER TABLE actors ADD COLUMN document_ids text[];

CREATE FUNCTION public.grant_new_document() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
 INSERT INTO public.document_grants(tenant_id,document_id,actor_id)
 SELECT NEW.tenant_id,NEW.id,a.id FROM public.actors a
 WHERE a.tenant_id=NEW.tenant_id
 AND a.role IN ('technician','service_manager','administrator')
 AND (a.document_ids IS NULL OR NEW.id=ANY(a.document_ids));
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.grant_new_document() FROM PUBLIC;
CREATE TRIGGER grant_new_document AFTER INSERT ON documents
 FOR EACH ROW EXECUTE FUNCTION public.grant_new_document();

DROP POLICY tenant_boundary ON document_grants;
CREATE POLICY read_document_grants ON document_grants FOR SELECT USING (
 tenant_id=nullif(current_setting('app.tenant_id',true),'')
);
DROP POLICY scoped_revocations ON document_revocations;
CREATE POLICY read_revocations ON document_revocations FOR SELECT USING (
 tenant_id=nullif(current_setting('app.tenant_id',true),'')
);
CREATE POLICY administrator_revocations_insert ON document_revocations FOR INSERT WITH CHECK (
 tenant_id=nullif(current_setting('app.tenant_id',true),'')
 AND EXISTS (SELECT 1 FROM actors a WHERE a.tenant_id=document_revocations.tenant_id
  AND a.id=current_setting('app.actor_id',true) AND a.role='administrator')
);
CREATE POLICY administrator_revocations_delete ON document_revocations FOR DELETE USING (
 tenant_id=nullif(current_setting('app.tenant_id',true),'')
 AND EXISTS (SELECT 1 FROM actors a WHERE a.tenant_id=document_revocations.tenant_id
  AND a.id=current_setting('app.actor_id',true) AND a.role='administrator')
);
COMMIT;
