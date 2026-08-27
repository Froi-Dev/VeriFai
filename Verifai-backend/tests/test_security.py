from datetime import UTC, datetime

import pytest
from passlib.hash import bcrypt_sha256
from pydantic import ValidationError

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    new_refresh_token,
    password_policy_errors,
    split_refresh_token,
    tokens_match,
    verify_password,
)
from app.schemas import RegisterRequest


def test_password_hash_round_trip() -> None:
    encoded = hash_password("Correct Horse Battery Staple!7")
    valid, replacement = verify_password("Correct Horse Battery Staple!7", encoded)
    assert valid is True
    assert replacement is None
    assert "Correct Horse" not in encoded
    assert encoded.startswith("$argon2")


def test_wrong_password_is_rejected() -> None:
    encoded = hash_password("Right-Password-123!")
    valid, replacement = verify_password("Wrong-Password-123!", encoded)
    assert valid is False
    assert replacement is None


def test_legacy_bcrypt_sha256_hash_is_verified_and_upgraded() -> None:
    legacy_hash = bcrypt_sha256.hash("legacy-password")
    valid, replacement = verify_password("legacy-password", legacy_hash)
    assert valid is True
    assert replacement is not None
    assert replacement.startswith("$argon2")
    assert verify_password("legacy-password", replacement)[0] is True


def test_strong_password_policy() -> None:
    assert password_policy_errors("Violet-River-9082!") == []
    errors = password_policy_errors("password123!", email="person@example.com")
    assert "Add an uppercase letter" in errors
    assert "Choose a less common password" in errors


def test_registration_rejects_name_markup_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            name="<script>alert(1)</script>",
            email="person@example.com",
            password="Violet-River-9082!",
        )
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(
            {
                "name": "Safe Name",
                "email": "person@example.com",
                "password": "Violet-River-9082!",
                "role": "admin",
            }
        )


def test_password_is_not_silently_trimmed() -> None:
    request = RegisterRequest(
        name="Safe Name",
        email="person@example.com",
        password=" Violet-River-9082! ",
    )
    assert request.password.startswith(" ")
    assert request.password.endswith(" ")


def test_access_token_round_trip() -> None:
    token = create_access_token(42, "session-id", 3)
    payload = decode_access_token(token.encoded)
    assert payload.user_id == 42
    assert payload.session_id == "session-id"
    assert payload.generation == 3
    assert token.expires_at > datetime.now(UTC)


def test_invalid_access_token_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid or expired"):
        decode_access_token("not-a-jwt")


def test_refresh_token_is_opaque_and_hash_verifiable() -> None:
    token, secret_hash = new_refresh_token("session-id")
    session_id, secret = split_refresh_token(token)
    assert session_id == "session-id"
    assert secret not in secret_hash
    assert tokens_match(secret, secret_hash)
    assert not tokens_match("wrong-secret", secret_hash)
