-- One row per document per scheduled source check (python -m app.ingest.regtext.refresh).
-- outcome: unchanged, changed (re-ingested; affected rules went back to review), failed (could not fetch),
-- manual_due (a hand-saved source older than the re-check interval), manual_ok.
CREATE TABLE source_check (
    id           bigserial PRIMARY KEY,
    checked_at   timestamptz NOT NULL DEFAULT now(),
    document_id  text NOT NULL,
    outcome      text NOT NULL CHECK (outcome IN ('unchanged', 'changed', 'failed', 'manual_due', 'manual_ok')),
    detail       jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX source_check_doc_idx ON source_check (document_id, checked_at DESC);
