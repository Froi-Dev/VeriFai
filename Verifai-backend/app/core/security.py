from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from jwt import InvalidTokenError
from passlib.hash import bcrypt_sha256
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings

password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))
DUMMY_PASSWORD_HASH = password_hash.hash("not-a-real-user-password")


@dataclass(frozen=True)
class AccessToken:
    encoded: str
    session_id: str
    expires_at: datetime


@dataclass(frozen=True)
class TokenPayload:
    user_id: int
    session_id: str


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> tuple[bool, str | None]:
    if encoded_hash.startswith("$bcrypt-sha256$"):
        try:
            valid = bcrypt_sha256.verify(password, encoded_hash)
            return valid, hash_password(password) if valid else None
        except (ValueError, TypeError):
            return False, None
    try:
        return password_hash.verify_and_update(password, encoded_hash)
    except (ValueError, TypeError):
        return False, None


def run_dummy_password_check(password: str) -> None:
    password_hash.verify(password, DUMMY_PASSWORD_HASH)


def create_access_token(user_id: int) -> AccessToken:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    session_id = uuid4().hex
    payload = {
        "sub": str(user_id),
        "jti": session_id,
        "type": "access",
        "iat": now,
        "exp": expires_at,
    }
    encoded = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return AccessToken(encoded=encoded, session_id=session_id, expires_at=expires_at)


def decode_access_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "jti", "exp", "iat"]},
        )
        if payload.get("type") != "access":
            raise InvalidTokenError("Unexpected token type")
        return TokenPayload(user_id=int(payload["sub"]), session_id=str(payload["jti"]))
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid or expired access token") from exc
