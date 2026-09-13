BEGIN;

-- Prevent case variants from bypassing account uniqueness checks.
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower ON public.users (lower(email));

CREATE TABLE IF NOT EXISTS public.auth_sessions (
    session_id varchar(64) PRIMARY KEY,
    user_id integer NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    refresh_token_hash varchar(64) NOT NULL,
    previous_refresh_token_hash varchar(64),
    last_rotated_at timestamptz,
    generation integer NOT NULL DEFAULT 1 CHECK (generation > 0),
    user_agent_hash varchar(64) NOT NULL,
    ip_hash varchar(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    idle_expires_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_user_id ON public.auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_expiry ON public.auth_sessions(expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS public.user_security_state (
    user_id integer PRIMARY KEY REFERENCES public.users(user_id) ON DELETE CASCADE,
    locked_until timestamptz,
    password_changed_at timestamptz
);

CREATE TABLE IF NOT EXISTS public.password_reset_tokens (
    token_hash varchar(64) PRIMARY KEY,
    user_id integer NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    used_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id
    ON public.password_reset_tokens(user_id);

CREATE TABLE IF NOT EXISTS public.idempotency_records (
    record_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scope varchar(100) NOT NULL,
    key_hash varchar(64) NOT NULL,
    request_hash varchar(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    CONSTRAINT uq_idempotency_scope_key UNIQUE (scope, key_hash)
);
CREATE INDEX IF NOT EXISTS ix_idempotency_expiry
    ON public.idempotency_records(expires_at);

COMMIT;
