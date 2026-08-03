from datetime import UTC, datetime

import pytest
from passlib.hash import bcrypt_sha256

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip() -> None:
    encoded = hash_password("correct horse battery staple")

    valid, replacement = verify_password("correct horse battery staple", encoded)

    assert valid is True
    assert replacement is None
    assert "correct horse" not in encoded


def test_wrong_password_is_rejected() -> None:
    encoded = hash_password("right-password")

    valid, replacement = verify_password("wrong-password", encoded)

    assert valid is False
    assert replacement is None


def test_legacy_bcrypt_sha256_hash_is_verified_and_upgraded() -> None:
    legacy_hash = bcrypt_sha256.hash("legacy-password")

    valid, replacement = verify_password("legacy-password", legacy_hash)

    assert valid is True
    assert replacement is not None
    assert replacement.startswith("$argon2")
    assert verify_password("legacy-password", replacement)[0] is True


def test_access_token_round_trip() -> None:
    token = create_access_token(42)

    payload = decode_access_token(token.encoded)

    assert payload.user_id == 42
    assert payload.session_id == token.session_id
    assert token.expires_at > datetime.now(UTC)


def test_invalid_access_token_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid or expired"):
        decode_access_token("not-a-jwt")
