-- Client reports: a frozen copy of one assessment that stays locked until a licensed reviewer signs it.
-- Holds the APN and the project inputs only (never the address that was typed); the purge job deletes
-- reports older than the feedback retention period.
CREATE TABLE report (
    token           text PRIMARY KEY,
    created_at      timestamptz NOT NULL DEFAULT now(),
    apn             text NOT NULL,
    project         jsonb NOT NULL DEFAULT '{}',
    snapshot        jsonb NOT NULL,
    status          text NOT NULL DEFAULT 'awaiting_signoff'
                    CHECK (status IN ('awaiting_signoff', 'signed', 'withdrawn')),
    signer_name     text CHECK (length(signer_name) <= 120),
    signer_license  text CHECK (length(signer_license) <= 60),
    signer_note     text CHECK (length(signer_note) <= 2000),
    signed_by       text,
    signed_at       timestamptz
);
CREATE INDEX report_status_idx ON report (status, created_at);
