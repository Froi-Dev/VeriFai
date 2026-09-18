BEGIN;
CREATE TABLE IF NOT EXISTS guest_identities (
    identity_hash varchar(64) PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS guest_sessions (
    token_hash varchar(64) PRIMARY KEY,
    identity_hash varchar(64) NOT NULL REFERENCES guest_identities(identity_hash),
    fingerprint_hash varchar(64) NOT NULL,
    consent_version varchar(20) NOT NULL,
    created_at double precision NOT NULL,
    expires_at double precision NOT NULL
);
CREATE TABLE IF NOT EXISTS guest_usage (
    id serial PRIMARY KEY,
    identity_hash varchar(64) NOT NULL REFERENCES guest_identities(identity_hash),
    kind varchar(10) NOT NULL CHECK (kind IN ('text', 'image', 'news')),
    used_at double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_guest_usage_identity_hash ON guest_usage(identity_hash);
CREATE INDEX IF NOT EXISTS ix_guest_usage_used_at ON guest_usage(used_at);
COMMIT;
