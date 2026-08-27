import hashlib
import hmac
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet, InvalidToken
from jwt import InvalidTokenError
from passlib.hash import bcrypt_sha256
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings

password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))
DUMMY_PASSWORD_HASH = password_hash.hash("not-a-real-user-password")
COMMON_PASSWORDS = {
    "123456789012",
    "adminpassword",
    "letmeinplease",
    "password123!",
    "qwertyuiop123!",
    "welcome123!",
}


@dataclass(frozen=True)
class AccessToken:
    encoded: str
    expires_at: datetime


@dataclass(frozen=True)
class TokenPayload:
    user_id: int
    session_id: str
    generation: int


def password_policy_errors(password: str, *, email: str = "", name: str = "") -> list[str]:
    errors: list[str] = []
    if len(password) < 12:
        errors.append("Use at least 12 characters")
    if len(password) > 128:
        errors.append("Use no more than 128 characters")
    if not re.search(r"[a-z]", password):
        errors.append("Add a lowercase letter")
    if not re.search(r"[A-Z]", password):
        errors.append("Add an uppercase letter")
    if not re.search(r"\d", password):
        errors.append("Add a number")
    if not re.search(r"[^A-Za-z0-9\s]", password):
        errors.append("Add a symbol")
    if any(unicodedata.category(char) in {"Cc", "Cf"} for char in password):
        errors.append("Remove control characters")
    folded = unicodedata.normalize("NFKC", password).casefold()
    if folded in COMMON_PASSWORDS:
        errors.append("Choose a less common password")
    email_name = email.partition("@")[0].strip().casefold()
    if len(email_name) >= 4 and email_name in folded:
        errors.append("Do not include your email address")
    compact_name = re.sub(r"\W", "", name, flags=re.UNICODE).casefold()
    if len(compact_name) >= 4 and compact_name in re.sub(r"\W", "", folded):
        errors.append("Do not include your name")
    return errors


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


def create_access_token(user_id: int, session_id: str, generation: int) -> AccessToken:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "sid": session_id,
        "ver": generation,
        "jti": secrets.token_hex(16),
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": expires_at,
        "iss": settings.app_name,
        "aud": "verifai-web",
    }
    encoded = jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return AccessToken(encoded=encoded, expires_at=expires_at)


def decode_access_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience="verifai-web",
            issuer=settings.app_name,
            options={"require": ["sub", "sid", "ver", "jti", "exp", "iat", "nbf"]},
        )
        if payload.get("type") != "access":
            raise InvalidTokenError("Unexpected token type")
        return TokenPayload(
            user_id=int(payload["sub"]),
            session_id=str(payload["sid"]),
            generation=int(payload["ver"]),
        )
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid or expired access token") from exc


def new_refresh_token(session_id: str) -> tuple[str, str]:
    secret = secrets.token_urlsafe(48)
    return f"{session_id}.{secret}", hash_token(secret)


def split_refresh_token(token: str) -> tuple[str, str]:
    try:
        session_id, secret = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Invalid refresh token") from exc
    if not session_id or len(secret) < 40:
        raise ValueError("Invalid refresh token")
    return session_id, secret


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(token: str, expected_hash: str | None) -> bool:
    return expected_hash is not None and hmac.compare_digest(hash_token(token), expected_hash)


def fingerprint(value: str | None) -> str:
    normalized = (value or "unknown").strip()[:512]
    return hmac.new(
        settings.jwt_secret.get_secret_value().encode(), normalized.encode(), hashlib.sha256
    ).hexdigest()


def encrypt_sensitive(value: str | None) -> str | None:
    if not value or settings.data_encryption_key is None:
        return None
    cipher = Fernet(settings.data_encryption_key.get_secret_value().encode())
    return "enc:" + cipher.encrypt(value.encode()).decode()


def decrypt_sensitive(value: str | None) -> str | None:
    if not value or not value.startswith("enc:") or settings.data_encryption_key is None:
        return None
    try:
        cipher = Fernet(settings.data_encryption_key.get_secret_value().encode())
        return cipher.decrypt(value[4:].encode()).decode()
    except (InvalidToken, ValueError):
        return None
