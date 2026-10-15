-- Regulatory documents and the chunks citations must resolve to.
CREATE TABLE reg_document (
    id               text PRIMARY KEY,
    title            text NOT NULL,
    publisher        text NOT NULL,
    doc_type         text NOT NULL,            -- ordinance | memo | guidance | statute | code_section
    jurisdiction     text NOT NULL,            -- City of Los Angeles | State of California
    code_chapter     text CHECK (code_chapter IN ('I', '1A')),
    source_url       text NOT NULL,
    retrieved_at     timestamptz NOT NULL,
    effective_date   date,
    effective_note   text,
    manual_retrieval boolean NOT NULL DEFAULT false,  -- saved by a person, not fetched by code
    ocr_text         boolean NOT NULL DEFAULT false,  -- text layer is OCR; numbers need human check
    mock             boolean NOT NULL DEFAULT false,
    file_sha256      text NOT NULL,
    pages            integer
);

CREATE TABLE reg_chunk (
    id              text PRIMARY KEY,            -- stable: <doc>#<section slug>#<n>
    document_id     text NOT NULL REFERENCES reg_document(id) ON DELETE CASCADE,
    section_id      text NOT NULL,               -- as the document numbers it, e.g. "LAMC 12.08 C.2(a)"
    heading         text,
    text            text NOT NULL,
    page_start      integer,
    page_end        integer,
    source_url      text NOT NULL,
    retrieved_at    timestamptz NOT NULL,
    effective_date  date,
    code_chapter    text CHECK (code_chapter IN ('I', '1A')),
    content_hash    text NOT NULL,
    mock            boolean NOT NULL DEFAULT false,
    embedding       vector(768),
    tsv             tsvector GENERATED ALWAYS AS (
                        setweight(to_tsvector('english', coalesce(section_id, '') || ' ' || coalesce(heading, '')), 'A') ||
                        setweight(to_tsvector('english', text), 'B')) STORED
);
CREATE INDEX reg_chunk_tsv_idx ON reg_chunk USING gin (tsv);
CREATE INDEX reg_chunk_doc_idx ON reg_chunk (document_id);
CREATE INDEX reg_chunk_section_idx ON reg_chunk (lower(section_id));

-- One row per ingestion run per document: what changed since last time (by content hash).
CREATE TABLE ingest_run (
    id              bigserial PRIMARY KEY,
    document_id     text NOT NULL REFERENCES reg_document(id) ON DELETE CASCADE,
    ran_at          timestamptz NOT NULL DEFAULT now(),
    file_sha256     text NOT NULL,
    added           integer NOT NULL,
    changed         integer NOT NULL,
    removed         integer NOT NULL,
    unchanged       integer NOT NULL
);
