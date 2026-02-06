"""Tests for shared.jwt_utils — Cognito JWT validation."""

from __future__ import annotations

from shared.jwt_utils import validate_cognito_token

from tests.conftest import CognitoJwtKeys


def test_valid_id_token(cognito_jwt_keys: CognitoJwtKeys) -> None:
    """Valid Cognito ID token returns decoded claims."""
    token = cognito_jwt_keys.sign_token({"sub": "user-abc-123", "email": "a@b.com"})
    claims = validate_cognito_token(token)

    assert claims is not None
    assert claims["sub"] == "user-abc-123"
    assert claims["email"] == "a@b.com"
    assert claims["token_use"] == "id"


def test_access_token_rejected(cognito_jwt_keys: CognitoJwtKeys) -> None:
    """Cognito access tokens (token_use != 'id') are rejected."""
    token = cognito_jwt_keys.sign_token({"token_use": "access"})
    claims = validate_cognito_token(token)

    assert claims is None


def test_expired_token_rejected(cognito_jwt_keys: CognitoJwtKeys) -> None:
    """Expired tokens are rejected."""
    token = cognito_jwt_keys.sign_token(expired=True)
    claims = validate_cognito_token(token)

    assert claims is None


def test_invalid_signature_rejected(cognito_jwt_keys: CognitoJwtKeys) -> None:
    """Tokens signed with a different key are rejected."""
    # Tamper with the token by changing the last character of the signature
    token = cognito_jwt_keys.sign_token()
    parts = token.rsplit(".", 1)
    tampered_sig = parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B")
    tampered_token = parts[0] + "." + tampered_sig

    claims = validate_cognito_token(tampered_token)

    assert claims is None
