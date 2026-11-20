-- Migration 002: idempotent finance source imports.
BEGIN;
CREATE UNIQUE INDEX IF NOT EXISTS cost_records_source_unique
  ON commerce.cost_records(store_id,source_document_id,variant_gid,effective_at);
COMMIT;
