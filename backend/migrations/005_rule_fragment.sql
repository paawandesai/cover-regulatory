-- Rule fragments: what the extraction model read out of one chunk, waiting for a human decision.
-- Nothing here is used by an assessment until status = 'approved'. The model's own confidence is never stored.
CREATE TABLE extraction_run (
    id              bigserial PRIMARY KEY,
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    model_id        text NOT NULL,              -- requested (from config)
    served_model    text,                       -- as reported by the API response
    prompt_version  text NOT NULL,
    chunk_ids       text[] NOT NULL,
    input_tokens    integer,
    output_tokens   integer,
    stop_reason     text,
    status          text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ok', 'refused', 'error')),
    error_class     text                        -- exception class name only; never the payload
);

CREATE TABLE rule_fragment (
    id              bigserial PRIMARY KEY,
    run_id          bigint NOT NULL REFERENCES extraction_run(id),
    chunk_id        text NOT NULL REFERENCES reg_chunk(id) ON DELETE CASCADE,
    chunk_hash      text NOT NULL,              -- reg_chunk.content_hash at extraction; a mismatch marks it stale
    rule_family     text NOT NULL,
    parameter       text NOT NULL,
    applies_to      text[] NOT NULL DEFAULT '{}',
    conditions      text,
    value_numeric   numeric,
    unit            text,
    value_text      text,
    source_quote    text NOT NULL,
    quote_start     integer,                    -- character offsets of source_quote in the chunk text
    quote_end       integer,
    validation      text NOT NULL,              -- 'ok' or the reason the deterministic check failed
    status          text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'invalid')),
    reviewed_by     text,
    reviewed_at     timestamptz,
    review_note     text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX rule_fragment_status_idx ON rule_fragment (status, rule_family, parameter);
CREATE INDEX rule_fragment_chunk_idx ON rule_fragment (chunk_id);
