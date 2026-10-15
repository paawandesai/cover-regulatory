-- Advisory results from checking candidates against their source text, a second model and official sources.
-- Shown to reviewers next to each candidate. Nothing reads this table to change a fragment's status: only a
-- person approves or rejects.
CREATE TABLE fragment_verification (
    fragment_id     bigint PRIMARY KEY REFERENCES rule_fragment (id) ON DELETE CASCADE,
    checked_on      date NOT NULL,
    recommendation  text NOT NULL CHECK (recommendation IN ('approve', 'approve_with_note', 'reject')),
    note            text CHECK (length(note) <= 2000),
    checks          jsonb NOT NULL DEFAULT '{}'::jsonb
);
