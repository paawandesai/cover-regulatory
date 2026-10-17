-- Named reviewer accounts and an append-only audit log of every review action.
-- Accounts are managed on the server with `python -m app.api.reviewers`; the ADMIN_USERNAME account from the
-- environment still works as a bootstrap login. The audit log holds who did what to which object, never
-- feedback text, addresses or report links.
CREATE TABLE reviewer (
    username        text PRIMARY KEY CHECK (username ~ '^[a-z0-9._-]{3,40}$'),
    display_name    text NOT NULL CHECK (length(display_name) BETWEEN 2 AND 120),
    password_scrypt text NOT NULL,
    active          boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    last_login_at   timestamptz
);

CREATE TABLE audit_log (
    id          bigserial PRIMARY KEY,
    at          timestamptz NOT NULL DEFAULT now(),
    actor       text NOT NULL,
    action      text NOT NULL,
    object_type text NOT NULL,
    object_id   text NOT NULL,
    detail      jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX audit_log_at_idx ON audit_log (at DESC);
CREATE INDEX audit_log_object_idx ON audit_log (object_type, object_id);

-- The application can only add rows. The one exception is a DELETE in a session that has set
-- regengine.audit_maintenance = 'on' (used by the test suite to remove the rows its own tests wrote).
CREATE FUNCTION audit_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('regengine.audit_maintenance', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'audit_log is append-only';
END $$;
CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
