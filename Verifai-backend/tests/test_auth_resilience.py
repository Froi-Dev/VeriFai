from datetime import UTC, datetime, timedelta

import pytest

from app.Auth import auth_router as auth_api
from app.Auth import auth_service as auth
from app.Auth.models import AuthSession, IdempotencyRecord, User, UserSecurityState
from app.Global.security import hash_password, new_refresh_token, split_refresh_token


class FakeSession:
    def __init__(self, *, scalar_value=None, scalar_values=(), gets=None) -> None:
        self.scalar_value = scalar_value
        self.scalar_values = list(scalar_values)
        self.gets = gets or {}
        self.added = []
        self.commits = 0

    def scalar(self, statement):
        del statement
        return self.scalar_value

    def scalars(self, statement):
        del statement
        return iter(self.scalar_values)

    def get(self, model, key):
        return self.gets.get((model, key))

    def add(self, value) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, value) -> None:
        del value


def _user() -> User:
    return User(
        user_id=7,
        username="Test User",
        email="test@example.com",
        password_hash=hash_password("Violet-River-9082!"),
        role="user",
        is_active=True,
        failed_login_attempts=0,
    )


def _auth_session(now: datetime, token_hash: str) -> AuthSession:
    return AuthSession(
        session_id="session-id",
        user_id=7,
        refresh_token_hash=token_hash,
        previous_refresh_token_hash=None,
        generation=1,
        user_agent_hash=auth.fingerprint("Browser/1"),
        ip_hash=auth.fingerprint("127.0.0.1"),
        created_at=now,
        last_seen_at=now,
        idle_expires_at=now + timedelta(hours=1),
        expires_at=now + timedelta(days=1),
        revoked_at=None,
    )


def test_concurrent_refresh_returns_same_rotation_without_revoking(monkeypatch) -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    original_token, original_hash = new_refresh_token("session-id")
    user = _user()
    session = _auth_session(now, original_hash)
    db = FakeSession(
        scalar_value=session,
        gets={(User, user.user_id): user},
    )
    monkeypatch.setattr(auth, "_now", lambda: now)

    first = auth.refresh_session(
        db,
        refresh_token=original_token,
        ip_address="127.0.0.1",
        user_agent="Browser/1",
    )
    monkeypatch.setattr(auth, "_now", lambda: now + timedelta(seconds=1))
    concurrent = auth.refresh_session(
        db,
        refresh_token=original_token,
        ip_address="127.0.0.1",
        user_agent="Browser/1",
    )

    assert first.refresh_token == concurrent.refresh_token
    assert session.generation == 2
    assert session.revoked_at is None
    _, current_secret = split_refresh_token(concurrent.refresh_token)
    assert auth.tokens_match(current_secret, session.refresh_token_hash)


def test_delayed_previous_refresh_token_reuse_still_revokes(monkeypatch) -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    original_token, original_hash = new_refresh_token("session-id")
    user = _user()
    session = _auth_session(now, original_hash)
    db = FakeSession(scalar_value=session, gets={(User, user.user_id): user})
    monkeypatch.setattr(auth, "_now", lambda: now)
    auth.refresh_session(
        db,
        refresh_token=original_token,
        ip_address="127.0.0.1",
        user_agent="Browser/1",
    )
    monkeypatch.setattr(
        auth,
        "_now",
        lambda: now + timedelta(seconds=auth.settings.refresh_token_reuse_grace_seconds + 1),
    )

    with pytest.raises(auth.RefreshTokenReuseError):
        auth.refresh_session(
            db,
            refresh_token=original_token,
            ip_address="127.0.0.1",
            user_agent="Browser/1",
        )

    assert session.revoked_at is not None


def test_user_agent_change_is_audited_but_does_not_revoke(monkeypatch) -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    token, token_hash = new_refresh_token("session-id")
    user = _user()
    session = _auth_session(now, token_hash)
    db = FakeSession(scalar_value=session, gets={(User, user.user_id): user})
    monkeypatch.setattr(auth, "_now", lambda: now)

    auth.refresh_session(
        db,
        refresh_token=token,
        ip_address="127.0.0.1",
        user_agent="Browser/2",
    )

    assert session.revoked_at is None
    assert session.user_agent_hash == auth.fingerprint("Browser/2")
    assert any(item.action == "session_client_changed" for item in db.added)


def test_legacy_account_lock_does_not_block_a_valid_password(monkeypatch) -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    user = _user()
    state = UserSecurityState(
        user_id=user.user_id,
        locked_until=now + timedelta(hours=1),
    )
    db = FakeSession(
        scalar_value=user,
        scalar_values=[],
        gets={(UserSecurityState, user.user_id): state},
    )
    monkeypatch.setattr(auth, "_now", lambda: now)

    result = auth.authenticate_user(
        db,
        email=user.email,
        password="Violet-River-9082!",
        ip_address="127.0.0.1",
        user_agent="Browser/1",
    )

    assert result.user is user
    assert state.locked_until is None


def test_session_limit_rejects_new_login_without_revoking_old_sessions(monkeypatch) -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    user = _user()
    retained = [object(), object()]
    db = FakeSession(scalar_values=retained)
    monkeypatch.setattr(auth, "_now", lambda: now)
    monkeypatch.setattr(auth.settings, "max_active_sessions", len(retained))

    with pytest.raises(auth.SessionLimitError):
        auth._create_session(
            db,
            user,
            ip_address="127.0.0.1",
            user_agent="Browser/1",
        )

    assert not db.added


def test_expired_idempotency_record_is_reclaimed() -> None:
    now = datetime.now(UTC)
    record = IdempotencyRecord(
        record_id=1,
        scope="password-reset-request",
        key_hash=auth.hash_token("request-key"),
        request_hash=auth.hash_token("old@example.com"),
        created_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )
    db = FakeSession(scalar_value=record)

    assert auth.claim_idempotency_key(
        db,
        scope="password-reset-request",
        key="request-key",
        request_fingerprint="new@example.com",
    )
    assert record.request_hash == auth.hash_token("new@example.com")
    assert record.expires_at > now
    assert db.commits == 1


def test_failed_reset_email_releases_idempotency_key(monkeypatch) -> None:
    released = []
    db = object()

    class SessionContext:
        def __enter__(self):
            return db

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

    monkeypatch.setattr(auth_api, "send_password_reset_email", lambda email, token: False)
    monkeypatch.setattr(auth_api, "SessionLocal", SessionContext)
    monkeypatch.setattr(
        auth_api,
        "release_idempotency_key",
        lambda session, **kwargs: released.append((session, kwargs)),
    )

    auth_api._deliver_password_reset(
        "person@example.com",
        "reset-token",
        "request-key",
        "person@example.com",
    )

    assert released == [
        (
            db,
            {
                "scope": "password-reset-request",
                "key": "request-key",
                "request_fingerprint": "person@example.com",
            },
        )
    ]
