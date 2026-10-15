-- Feedback on an answer goes to a queue for admin review. Nothing reads this table to change rules, prompts
-- or retrieval; an unreviewed feedback loop would be a poisoning channel.
CREATE TABLE feedback (
    id              bigserial PRIMARY KEY,
    created_at      timestamptz NOT NULL DEFAULT now(),
    apn             text,
    item_id         text,
    kind            text NOT NULL CHECK (kind IN ('wrong_value', 'missing_rule', 'bad_citation', 'other')),
    comment         text CHECK (length(comment) <= 2000),
    status          text NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'reviewed', 'dismissed')),
    reviewed_by     text,
    reviewed_at     timestamptz
);
