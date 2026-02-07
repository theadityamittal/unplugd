"""JWT token validation for Cognito WebSocket auth."""

from __future__ import annotations

import logging
from typing import Any

import jwt
from jwt import PyJWKClient
from shared.constants import COGNITO_APP_CLIENT_ID, COGNITO_USER_POOL_ID

logger = logging.getLogger(__name__)

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    """Lazily initialize and cache the JWKS client (survives warm starts)."""
    global _jwks_client
    if _jwks_client is None:
        region = COGNITO_USER_POOL_ID.split("_")[0]
        jwks_url = (
            f"https://cognito-idp.{region}.amazonaws.com/"
            f"{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
        )
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_client


def validate_cognito_token(token: str) -> dict[str, Any] | None:
    """Validate a Cognito ID token and return decoded claims.

    Returns None if the token is invalid.
    """
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        region = COGNITO_USER_POOL_ID.split("_")[0]
        issuer = f"https://cognito-idp.{region}.amazonaws.com/{COGNITO_USER_POOL_ID}"

        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=COGNITO_APP_CLIENT_ID or None,
            options={"verify_aud": bool(COGNITO_APP_CLIENT_ID)},
        )

        if claims.get("token_use") != "id":
            logger.warning("Token is not an ID token: token_use=%s", claims.get("token_use"))
            return None

        return claims
    except jwt.exceptions.PyJWTError:
        logger.warning("JWT validation failed", exc_info=True)
        return None
