BEGIN;

-- Supports idempotent refresh rotation during a short concurrent-request grace period.
ALTER TABLE public.auth_sessions
    ADD COLUMN IF NOT EXISTS last_rotated_at timestamptz;

COMMIT;
