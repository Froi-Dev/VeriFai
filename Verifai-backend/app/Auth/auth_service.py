import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.Auth.models import (
    AuditLog,
    AuthSession,
    IdempotencyRecord,
    PasswordResetToken,
    User,
    UserSecurityState,
)
from app.Global.config import settings
from app.Global.security import (
    AccessToken,
    create_access_token,
    encrypt_sensitive,
    fingerprint,
    hash_password,
    hash_token,
    new_refresh_token,
    password_policy_errors,
    refresh_token_for_generation,
    run_dummy_password_check,
    split_refresh_token,
    tokens_match,
    verify_password,
)


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InactiveUserError(Exception):
    pass


class InvalidSessionError(Exception):
    pass


class RefreshTokenReuseError(InvalidSessionError):
    pass


class InvalidPasswordResetError(Exception):
    pass


class PasswordPolicyError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors


class IdempotencyConflictError(Exception):
    pass


class SessionLimitError(Exception):
    pass


@dataclass(frozen=True)
class AuthResult:
    user: User
    access_token: AccessToken
    refresh_token: str
    session: AuthSession


def _now() -> datetime:
    return datetime.now(UTC)


def _audit(
    db: Session,
    *,
    action: str,
    user_id: int | None,
    ip_address: str | None,
    message: str,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            ip_address=encrypt_sensitive(ip_address),
            msg=message,
            type="auth",
        )
    )


def find_user_by_email(db: Session, email: str, *, for_update: bool = False) -> User | None:
    statement = select(User).where(func.lower(User.email) == email.strip().lower())
    if for_update:
        statement = statement.with_for_update()
    return db.scalar(statement)


def register_user(
    db: Session,
    *,
    name: str,
    email: str,
    password: str,
    ip_address: str | None,
    user_agent: str | None,
) -> AuthResult:
    normalized_email = email.strip().lower()
    errors = password_policy_errors(password, email=normalized_email, name=name)
    if errors:
        raise PasswordPolicyError(errors)

    if find_user_by_email(db, normalized_email):
        raise EmailAlreadyRegisteredError

    user = User(
        username=name,
        email=normalized_email,
        password_hash=hash_password(password),
        role="user",
        is_active=True,
    )
    db.add(user)

    try:
        db.flush()
        result = _create_session(db, user, ip_address=ip_address, user_agent=user_agent)
        _audit(
            db,
            action="register",
            user_id=user.user_id,
            ip_address=ip_address,
            message="User account created",
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise EmailAlreadyRegisteredError from exc

    db.refresh(user)
    return result


def authenticate_user(
    db: Session,
    *,
    email: str,
    password: str,
    ip_address: str | None,
    user_agent: str | None,
) -> AuthResult:
    now = _now()
    user = find_user_by_email(db, email, for_update=False)
    if user is None:
        run_dummy_password_check(password)
        raise InvalidCredentialsError

    state = db.get(UserSecurityState, user.user_id)

    valid, replacement_hash = verify_password(password, user.password_hash)
    if not valid:
        attempts = (user.failed_login_attempts or 0) + 1
        user.failed_login_attempts = attempts
        _audit(
            db,
            action="login_failed",
            user_id=user.user_id,
            ip_address=ip_address,
            message="Invalid credentials",
        )
        db.commit()
        raise InvalidCredentialsError

    if not user.is_active:
        raise InactiveUserError

    if replacement_hash:
        user.password_hash = replacement_hash
    user.failed_login_attempts = 0
    if state:
        state.locked_until = None
    user.last_login = now.replace(tzinfo=None)
    user.updated_at = now.replace(tzinfo=None)
    result = _create_session(db, user, ip_address=ip_address, user_agent=user_agent)
    _audit(
        db,
        action="login",
        user_id=user.user_id,
        ip_address=ip_address,
        message="Successful login",
    )
    db.commit()
    db.refresh(user)
    return result


def _create_session(
    db: Session, user: User, *, ip_address: str | None, user_agent: str | None
) -> AuthResult:
    now = _now()
    active_sessions = list(
        db.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user.user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.idle_expires_at > now,
                AuthSession.expires_at > now,
            )
        )
    )
    if len(active_sessions) >= settings.max_active_sessions:
        raise SessionLimitError

    session_id = secrets.token_urlsafe(32)
    refresh_token, refresh_hash = new_refresh_token(session_id)
    session = AuthSession(
        session_id=session_id,
        user_id=user.user_id,
        refresh_token_hash=refresh_hash,
        generation=1,
        user_agent_hash=fingerprint(user_agent),
        ip_hash=fingerprint(ip_address),
        created_at=now,
        last_seen_at=now,
        idle_expires_at=now + timedelta(hours=settings.session_idle_expire_hours),
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)

    access_token = create_access_token(user.user_id, session_id, session.generation)
    return AuthResult(user, access_token, refresh_token, session)


def refresh_session(
    db: Session,
    *,
    refresh_token: str,
    ip_address: str | None,
    user_agent: str | None,
) -> AuthResult:
    try:
        session_id, secret = split_refresh_token(refresh_token)
    except ValueError as exc:
        raise InvalidSessionError from exc

    now = _now()
    session = db.scalar(
        select(AuthSession).where(AuthSession.session_id == session_id).with_for_update()
    )
    if session is None or session.revoked_at is not None:
        raise InvalidSessionError

    if tokens_match(secret, session.previous_refresh_token_hash):
        grace_deadline = (
            session.last_rotated_at
            + timedelta(seconds=settings.refresh_token_reuse_grace_seconds)
            if session.last_rotated_at
            else None
        )
        if grace_deadline and now <= grace_deadline:
            user = db.get(User, session.user_id)
            if user is None or not user.is_active:
                session.revoked_at = now
                db.commit()
                raise InvalidSessionError
            current_token, current_hash = refresh_token_for_generation(
                session.session_id, session.generation
            )
            if not secrets.compare_digest(current_hash, session.refresh_token_hash):
                session.revoked_at = now
                db.commit()
                raise InvalidSessionError
            session.last_seen_at = now
            session.idle_expires_at = min(
                session.expires_at,
                now + timedelta(hours=settings.session_idle_expire_hours),
            )
            access_token = create_access_token(
                user.user_id, session.session_id, session.generation
            )
            _audit(
                db,
                action="concurrent_session_refresh",
                user_id=user.user_id,
                ip_address=ip_address,
                message="Concurrent refresh reused the current token rotation",
            )
            db.commit()
            return AuthResult(user, access_token, current_token, session)
        session.revoked_at = now
        _audit(
            db,
            action="refresh_token_reuse",
            user_id=session.user_id,
            ip_address=ip_address,
            message="Rotated refresh token was reused; session revoked",
        )
        db.commit()
        raise RefreshTokenReuseError

    if not tokens_match(secret, session.refresh_token_hash):
        raise InvalidSessionError
    if session.expires_at <= now or session.idle_expires_at <= now:
        session.revoked_at = now
        db.commit()
        raise InvalidSessionError
    current_user_agent_hash = fingerprint(user_agent)
    if not secrets.compare_digest(session.user_agent_hash, current_user_agent_hash):
        _audit(
            db,
            action="session_client_changed",
            user_id=session.user_id,
            ip_address=ip_address,
            message="Refresh continued after the client User-Agent changed",
        )
        session.user_agent_hash = current_user_agent_hash

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        session.revoked_at = now
        db.commit()
        raise InvalidSessionError

    next_generation = session.generation + 1
    new_token, new_hash = refresh_token_for_generation(session.session_id, next_generation)
    session.previous_refresh_token_hash = session.refresh_token_hash
    session.refresh_token_hash = new_hash
    session.generation = next_generation
    session.last_rotated_at = now
    session.last_seen_at = now
    session.idle_expires_at = min(
        session.expires_at, now + timedelta(hours=settings.session_idle_expire_hours)
    )
    session.ip_hash = fingerprint(ip_address)
    access_token = create_access_token(user.user_id, session.session_id, session.generation)
    _audit(
        db,
        action="session_refreshed",
        user_id=user.user_id,
        ip_address=ip_address,
        message="Session token rotated",
    )
    db.commit()
    return AuthResult(user, access_token, new_token, session)


def get_active_session_user(
    db: Session, user_id: int, session_id: str, generation: int
) -> User | None:
    now = _now()
    statement = (
        select(User)
        .join(AuthSession, AuthSession.user_id == User.user_id)
        .where(
            User.user_id == user_id,
            User.is_active.is_(True),
            AuthSession.session_id == session_id,
            AuthSession.generation == generation,
            AuthSession.revoked_at.is_(None),
            AuthSession.idle_expires_at > now,
            AuthSession.expires_at > now,
        )
    )
    return db.scalar(statement)


def list_sessions(db: Session, user_id: int) -> list[AuthSession]:
    now = _now()
    return list(
        db.scalars(
            select(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.idle_expires_at > now,
                AuthSession.expires_at > now,
            )
            .order_by(AuthSession.last_seen_at.desc())
        )
    )


def revoke_session(
    db: Session,
    *,
    session_id: str,
    user: User,
    ip_address: str | None,
) -> bool:
    session = db.get(AuthSession, session_id)
    if session is None or session.user_id != user.user_id:
        return False
    if session.revoked_at is None:
        session.revoked_at = _now()
    _audit(
        db,
        action="logout",
        user_id=user.user_id,
        ip_address=ip_address,
        message="Session revoked",
    )
    db.commit()
    return True


def revoke_all_sessions(db: Session, *, user: User, ip_address: str | None) -> None:
    now = _now()
    for session in db.scalars(
        select(AuthSession).where(
            AuthSession.user_id == user.user_id, AuthSession.revoked_at.is_(None)
        )
    ):
        session.revoked_at = now
    _audit(
        db,
        action="logout_all",
        user_id=user.user_id,
        ip_address=ip_address,
        message="All sessions revoked",
    )
    db.commit()


def request_password_reset(db: Session, *, email: str, ip_address: str | None) -> str | None:
    user = find_user_by_email(db, email)
    if user is None or not user.is_active:
        run_dummy_password_check(secrets.token_urlsafe(16))
        return None

    now = _now()
    db.execute(
        delete(PasswordResetToken).where(PasswordResetToken.user_id == user.user_id)
    )
    token = secrets.token_urlsafe(48)
    db.add(
        PasswordResetToken(
            token_hash=hash_token(token),
            user_id=user.user_id,
            expires_at=now + timedelta(minutes=settings.password_reset_expire_minutes),
        )
    )
    _audit(
        db,
        action="password_reset_requested",
        user_id=user.user_id,
        ip_address=ip_address,
        message="Password reset requested",
    )
    db.commit()
    return token


def reset_password(
    db: Session,
    *,
    token: str,
    new_password: str,
    ip_address: str | None,
) -> None:
    now = _now()
    reset = db.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hash_token(token))
        .with_for_update()
    )
    if reset is None or reset.used_at is not None or reset.expires_at <= now:
        raise InvalidPasswordResetError
    user = db.get(User, reset.user_id)
    if user is None or not user.is_active:
        raise InvalidPasswordResetError

    errors = password_policy_errors(new_password, email=user.email, name=user.username)
    if errors:
        raise PasswordPolicyError(errors)
    if verify_password(new_password, user.password_hash)[0]:
        raise PasswordPolicyError(["Choose a password you have not used for this account"])

    user.password_hash = hash_password(new_password)
    user.failed_login_attempts = 0
    user.updated_at = now.replace(tzinfo=None)
    state = db.get(UserSecurityState, user.user_id)
    if state is None:
        state = UserSecurityState(user_id=user.user_id)
        db.add(state)
    state.locked_until = None
    state.password_changed_at = now
    reset.used_at = now
    for session in db.scalars(
        select(AuthSession).where(
            AuthSession.user_id == user.user_id, AuthSession.revoked_at.is_(None)
        )
    ):
        session.revoked_at = now
    _audit(
        db,
        action="password_reset_completed",
        user_id=user.user_id,
        ip_address=ip_address,
        message="Password reset completed; all sessions revoked",
    )
    db.commit()


def claim_idempotency_key(
    db: Session, *, scope: str, key: str, request_fingerprint: str
) -> bool:
    """Return True for a new request, False for an identical prior request."""
    if not (8 <= len(key) <= 200):
        raise IdempotencyConflictError
    key_digest = hash_token(key)
    request_digest = hash_token(request_fingerprint)
    now = _now()
    existing = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key_hash == key_digest,
        ).with_for_update()
    )
    if existing:
        if existing.expires_at <= now:
            existing.request_hash = request_digest
            existing.created_at = now
            existing.expires_at = now + timedelta(hours=24)
            db.commit()
            return True
        if not secrets.compare_digest(existing.request_hash, request_digest):
            raise IdempotencyConflictError
        return False
    db.add(
        IdempotencyRecord(
            scope=scope,
            key_hash=key_digest,
            request_hash=request_digest,
            expires_at=now + timedelta(hours=24),
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        winner = db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.key_hash == key_digest,
            )
        )
        if (
            winner is not None
            and winner.expires_at > _now()
            and secrets.compare_digest(winner.request_hash, request_digest)
        ):
            return False
        raise IdempotencyConflictError from exc
    return True


def release_idempotency_key(
    db: Session, *, scope: str, key: str, request_fingerprint: str
) -> None:
    """Release a failed operation so an identical retry can claim its key again."""
    db.execute(
        delete(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key_hash == hash_token(key),
            IdempotencyRecord.request_hash == hash_token(request_fingerprint),
        )
    )
    db.commit()
