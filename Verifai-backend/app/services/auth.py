from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    AccessToken,
    create_access_token,
    hash_password,
    run_dummy_password_check,
    verify_password,
)
from app.models import AuditLog, SessionRecord, User


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InactiveUserError(Exception):
    pass


def find_user_by_email(db: Session, email: str) -> User | None:
    normalized_email = email.strip().lower()
    return db.scalar(select(User).where(func.lower(User.email) == normalized_email))


def register_user(
    db: Session, *, name: str, email: str, password: str, ip_address: str | None
) -> tuple[User, AccessToken]:
    normalized_email = email.strip().lower()
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
        token = _create_session(db, user)
        db.add(
            AuditLog(
                user_id=user.user_id,
                action="register",
                ip_address=ip_address,
                msg="User account created",
                type="auth",
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise EmailAlreadyRegisteredError from exc

    db.refresh(user)
    return user, token


def authenticate_user(
    db: Session, *, email: str, password: str, ip_address: str | None
) -> tuple[User, AccessToken]:
    user = find_user_by_email(db, email)
    if user is None:
        run_dummy_password_check(password)
        raise InvalidCredentialsError

    valid, replacement_hash = verify_password(password, user.password_hash)
    if not valid:
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        db.add(
            AuditLog(
                user_id=user.user_id,
                action="login_failed",
                ip_address=ip_address,
                msg="Invalid credentials",
                type="auth",
            )
        )
        db.commit()
        raise InvalidCredentialsError

    if not user.is_active:
        raise InactiveUserError

    if replacement_hash:
        user.password_hash = replacement_hash
    user.failed_login_attempts = 0
    user.last_login = datetime.now().replace(tzinfo=None)
    user.updated_at = datetime.now().replace(tzinfo=None)
    token = _create_session(db, user)
    db.add(
        AuditLog(
            user_id=user.user_id,
            action="login",
            ip_address=ip_address,
            msg="Successful login",
            type="auth",
        )
    )
    db.commit()
    db.refresh(user)
    return user, token


def _create_session(db: Session, user: User) -> AccessToken:
    token = create_access_token(user.user_id)
    db.add(
        SessionRecord(
            token=token.session_id,
            subject_type="user",
            user_id=user.user_id,
            email=user.email,
            expires_at=token.expires_at,
        )
    )
    return token


def get_active_session_user(db: Session, user_id: int, session_id: str) -> User | None:
    now = datetime.now(UTC)
    statement = (
        select(User)
        .join(SessionRecord, SessionRecord.user_id == User.user_id)
        .where(
            User.user_id == user_id,
            User.is_active.is_(True),
            SessionRecord.token == session_id,
            SessionRecord.subject_type == "user",
            SessionRecord.expires_at > now,
        )
    )
    return db.scalar(statement)


def revoke_session(
    db: Session, *, session_id: str, user: User, ip_address: str | None
) -> None:
    record = db.get(SessionRecord, session_id)
    if record is not None:
        db.delete(record)
    db.add(
        AuditLog(
            user_id=user.user_id,
            action="logout",
            ip_address=ip_address,
            msg="Session revoked",
            type="auth",
        )
    )
    db.commit()

